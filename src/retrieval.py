"""Condense (history + question -> standalone query) -> embed -> search the vector DB -> top-k chunks.

The contract upward is one function:

    search(question, history) -> list[dict]

Each dict is a chunk row from audi_doc plus a `similarity` score. rag.py never
learns that a condenser or an embedding model was involved.

Smoke-test retrieval on its own, without the chat loop in the way:

    python src/retrieval.py "coolant smell after parking"

That is the first thing to reach for when answers come back wrong-but-fluent —
it shows exactly which chunks the model was handed.
"""

import sys

from openai import OpenAI

from config import (
    CONDENSER_MODEL,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from db import similarity_search
from memory import ChatHistory

client = OpenAI(api_key=OPENAI_API_KEY)

# Deliberately narrow. The condenser is not a mini-assistant — it rewrites and
# nothing else. "Do not answer it" is in there because gpt-4o-mini will happily
# start diagnosing the car if you let it, and that answer would then get embedded
# instead of the question.
CONDENSER_PROMPT = """\
You rewrite the latest message in a car-repair conversation into a single \
standalone search query for a vector database of Audi A4 B9 repair sources.

Rules:
- Resolve pronouns and references from the conversation ("it", "that part", \
"how hard is it to replace") into explicit terms.
- Keep the car details the user already gave — year, model, engine — even when \
they were mentioned several turns ago.
- Keep the user's own vocabulary. Do not invent symptoms, parts, or causes.
- If the latest message already stands alone, return it unchanged.
- Output only the query. No quotes, no preamble, no answer to the question.
"""

# The condenser only needs enough history to resolve a reference, and a short
# window keeps this call cheap and fast. Six messages is three turns back.
CONDENSER_WINDOW = 6


def condense(question: str, history: ChatHistory | None) -> str:
    """Turn a conversational follow-up into a query that means something alone.

    Retrieval fires before history reaches the prompt, so "how hard is it to
    replace?" gets embedded with nothing to resolve "it" against — garbage
    results at exactly the moment a demo is going well.

    Two shortcuts worth noting:
    - No history (None, or empty) means there is nothing to resolve, so the
      call is skipped entirely. First question of a session costs zero extra
      latency.
    - A failed condenser falls back to the raw question rather than raising.
      Slightly worse retrieval beats no answer, and the caller can't do anything
      useful with the exception anyway.
    """
    if not history:
        return question

    recent = history.to_list()[-CONDENSER_WINDOW:]
    messages = [
        {"role": "developer", "content": CONDENSER_PROMPT},
        *recent,
        {"role": "user", "content": f"Latest message: {question}\n\nStandalone search query:"},
    ]

    try:
        response = client.responses.create(model=CONDENSER_MODEL, input=messages)
        condensed = response.output_text.strip()
    except Exception:
        return question

    return condensed or question


def embed_query(text: str) -> list[float]:
    """Embed a single string with the same model ingest.py used.

    Both sides import EMBEDDING_MODEL from config.py. If they ever diverge there
    is no crash — the vectors just stop meaning the same thing and every result
    goes quietly bad.
    """
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def search(
    question: str,
    history: ChatHistory | None = None,
    k: int = TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Condense -> embed -> similarity search. Returns top-k chunk dicts, best first.

    May legitimately return an empty list: the threshold in db.py drops chunks
    that are merely the least irrelevant. rag.py treats that as "no sources" and
    says so, which is the behavior we want for an off-topic question.
    """
    query = condense(question, history)
    return similarity_search(embed_query(query), k=k, threshold=threshold)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python src/retrieval.py "your question here"')

    question = " ".join(sys.argv[1:])
    chunks = search(question)

    print(f"\nQuery: {question}")
    print(f"{len(chunks)} chunks above similarity {SIMILARITY_THRESHOLD}\n")

    for chunk in chunks:
        print("-" * 60)
        print(f"{chunk['similarity']:.3f}  {chunk['source_file']} #{chunk['chunk_index']}")
        print(chunk["chunk_text"][:400])
        print()
