"""Re-runnable: glob data/raw/*.md -> parse frontmatter -> chunk the body -> embed each chunk -> insert into audi_doc.

Run from the project root:

    python src/ingest.py              # ingest every file in data/raw/
    python src/ingest.py --dry-run    # chunk and report, no OpenAI calls, no DB writes

Chunking is structure-first, size-second. The corpus has two shapes and they get
different treatment:

  nhtsa_complaint  One file = one chunk. A complaint is a single atomic story:
                   one owner, one problem, ~285 tokens. Splitting it only serves
                   to orphan the `- ODI number: / Crash: False` footer into its
                   own meaningless chunk.

  reddit_thread    Split on comment boundaries, because that is where the real
                   semantic seams are. A top-level comment keeps its whole reply
                   subtree ("Original one. Made of metal." means nothing without
                   the question above it). Only the pieces still over CHUNK_SIZE
                   get handed to the recursive splitter.

Every chunk is then prefixed with its parent document's metadata before being
embedded — see `decorate()` for why that matters more than it looks.

Safe to re-run as the corpus grows: each file's rows are deleted and rewritten,
and rows belonging to files that no longer exist are pruned at the end.
"""

import re
import sys

import frontmatter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATA_DIR,
    EMBEDDING_MODEL,
    MIN_CHUNK_CHARS,
    OPENAI_API_KEY,
    TABLE_NAME,
)
from db import get_connection

# The seven frontmatter keys, copied onto every chunk row. Retrieval returns
# chunks, not documents, so a chunk that doesn't carry its own provenance comes
# back with no idea which model/year it describes.
METADATA_FIELDS = ("title", "url", "source_type", "model", "year_range", "engine", "category")

# One request per 100 chunks instead of one per chunk. The whole corpus is ~45k
# tokens, so this is two round trips, not two hundred.
EMBED_BATCH_SIZE = 100

# A top-level Reddit comment. extract_reddit_threads.py writes `"  " * depth`
# before the bullet, so column 0 means depth 0 — everything indented under it is
# a reply and belongs to the same chunk.
TOP_LEVEL_COMMENT = re.compile(r"^- \*\*", re.M)

COMMENTS_HEADER = re.compile(r"^## Comments\s*$", re.M)

# Only ever sees pieces that structural splitting couldn't get small enough.
# The separator list is ordered so that even this last resort prefers a comment
# boundary, then a paragraph, then a line, before it starts cutting sentences.
fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n- **", "\n\n", "\n", ". ", " ", ""],
)

# NHTSA complaints are exempt from CHUNK_SIZE by design (see module docstring),
# but not from all limits: this ceiling stops one freak 10k-char complaint from
# becoming a single unusable chunk as the corpus grows.
NHTSA_MAX_CHARS = 4000


def split_reddit(body: str) -> list[str]:
    """Split a thread into the original post plus one piece per top-level comment subtree."""
    parts = COMMENTS_HEADER.split(body, maxsplit=1)
    post = parts[0]
    comments = parts[1] if len(parts) > 1 else ""

    pieces = []
    if post.strip():
        pieces.append(post.strip())

    # Each top-level bullet runs until the next one; replies nested underneath
    # are swept along with their parent.
    starts = [m.start() for m in TOP_LEVEL_COMMENT.finditer(comments)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(comments)
        piece = comments[start:end].strip()
        if piece:
            pieces.append(piece)

    return pieces


def coalesce(pieces: list[str]) -> list[str]:
    """Merge consecutive undersized pieces so one-line comments stop polluting the index.

    Splitting a thread one-comment-per-chunk takes the structural rule too
    literally: it produces chunks like "Clean build" and "Beautiful", which can
    never be the right answer but can still win a top-k slot on a vague query.
    Merged, the same lines become a useful chunk — several owners answering the
    same question in a row.

    Greedy and forward-only: keep absorbing the next piece while the buffer is
    still under the floor and the result would stay under CHUNK_SIZE.
    """
    merged: list[str] = []
    buffer = ""

    for piece in pieces:
        if not buffer:
            buffer = piece
        elif len(buffer) < MIN_CHUNK_CHARS and len(buffer) + len(piece) + 1 <= CHUNK_SIZE:
            buffer = f"{buffer}\n{piece}"
        else:
            merged.append(buffer)
            buffer = piece

    if buffer:
        merged.append(buffer)

    return merged


def chunk_document(body: str, source_type: str) -> list[str]:
    """Structure-aware split, with the recursive splitter as a size-gated fallback."""
    if source_type == "nhtsa_complaint":
        text = body.strip()
        # Whole, unless it is a runaway document.
        return [text] if len(text) <= NHTSA_MAX_CHARS else fallback_splitter.split_text(text)

    pieces = split_reddit(body) if source_type == "reddit_thread" else [body.strip()]
    pieces = coalesce(pieces)

    chunks = []
    for piece in pieces:
        if len(piece) <= CHUNK_SIZE:
            chunks.append(piece)  # already a clean semantic unit
        else:
            chunks.extend(fallback_splitter.split_text(piece))

    return [c for c in chunks if c.strip()]


def decorate(text: str, meta: dict) -> str:
    """Prefix a chunk with its parent document's context before it gets embedded.

    A comment reading "just keep an eye on the coolant level, if it drops to MIN
    take it in" is good advice attached to nothing — embedded on its own, that
    vector has no idea it concerns an A4 cooling system and will never match
    "B9 coolant smell". Fifteen tokens of provenance fixes that, and doubles as
    the guard against confidently blending B8 and B9 facts at answer time.

    Empty frontmatter fields are dropped rather than rendered as blanks, which
    is what keeps this readable while `engine` and Reddit's `year_range` are
    still unpopulated.
    """
    tag = " · ".join(str(meta.get(f, "")).strip() for f in ("model", "year_range", "category", "source_type") if str(meta.get(f, "")).strip())
    title = str(meta.get("title", "")).strip()
    header = f"[{tag}] {title}".strip() if tag else title
    return f"{header}\n{text}" if header else text


def load_documents() -> list[tuple[str, dict, str]]:
    """Read every markdown file in DATA_DIR as (filename, metadata, body)."""
    paths = sorted(DATA_DIR.glob("*.md"))
    if not paths:
        sys.exit(f"No markdown files found in {DATA_DIR}. Run the scripts in scripts/ first.")

    documents = []
    for path in paths:
        post = frontmatter.load(path)
        documents.append((path.name, post.metadata, post.content))
    return documents


def embed(texts: list[str]) -> list[list[float]]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        vectors.extend(item.embedding for item in response.data)
        print(f"  embedded {start + len(batch)}/{len(texts)} chunks")
    return vectors


def write_chunks(rows: list[tuple], source_files: set[str]) -> None:
    """Replace each file's rows, then drop rows for files that no longer exist."""
    insert = f"""
        INSERT INTO {TABLE_NAME}
            (source_file, chunk_index, chunk_text, embedding,
             title, url, source_type, model, year_range, engine, category)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with get_connection() as conn, conn.cursor() as cur:
        # Delete-then-insert rather than upsert: a file whose chunk count shrank
        # would otherwise leave its orphaned tail rows behind.
        for source_file in sorted(source_files):
            cur.execute(f"DELETE FROM {TABLE_NAME} WHERE source_file = %s;", (source_file,))

        cur.executemany(insert, rows)

        cur.execute(
            f"DELETE FROM {TABLE_NAME} WHERE NOT (source_file = ANY(%s));",
            (sorted(source_files),),
        )
        pruned = cur.rowcount

        conn.commit()

        cur.execute(f"SELECT count(*) FROM {TABLE_NAME};")
        (total,) = cur.fetchone()

    if pruned:
        print(f"Pruned {pruned} rows from files no longer in {DATA_DIR.name}/.")
    print(f"{TABLE_NAME} now holds {total} chunks.")


def report(documents, chunks_by_file) -> None:
    by_type: dict[str, list[int]] = {}
    for filename, metadata, _ in documents:
        source_type = metadata.get("source_type", "unknown")
        by_type.setdefault(source_type, []).extend(
            len(c) for c in chunks_by_file[filename]
        )

    print(f"\n{len(documents)} documents -> {sum(len(v) for v in by_type.values())} chunks")
    for source_type, lengths in sorted(by_type.items()):
        longest = max(lengths)
        average = sum(lengths) // len(lengths)
        print(f"  {source_type:<18} {len(lengths):>4} chunks   avg {average:>5} chars   max {longest:>5}")


def main(dry_run: bool = False) -> None:
    documents = load_documents()

    chunks_by_file = {
        filename: chunk_document(body, metadata.get("source_type", ""))
        for filename, metadata, body in documents
    }

    report(documents, chunks_by_file)

    if dry_run:
        print("\nDry run — nothing embedded, nothing written.")
        return

    # Flatten to a single list so every chunk in the corpus is embedded in one
    # batched pass, then zipped back onto its row.
    rows_without_vectors = []
    for filename, metadata, _ in documents:
        for index, chunk in enumerate(chunks_by_file[filename]):
            rows_without_vectors.append((filename, index, decorate(chunk, metadata), metadata))

    print(f"\nEmbedding {len(rows_without_vectors)} chunks with {EMBEDDING_MODEL}...")
    vectors = embed([text for _, _, text, _ in rows_without_vectors])

    rows = [
        (
            filename,
            index,
            text,
            # psycopg2 has no vector adapter; the string literal is cast to
            # vector by the column type on insert.
            "[" + ",".join(str(value) for value in vector) + "]",
            *(str(metadata.get(field, "") or "") for field in METADATA_FIELDS),
        )
        for (filename, index, text, metadata), vector in zip(rows_without_vectors, vectors)
    ]

    write_chunks(rows, {filename for filename, _, _ in documents})


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
