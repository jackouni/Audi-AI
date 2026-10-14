"""Postgres connection helper + the similarity search query."""

from contextlib import closing

import psycopg2

from config import DB_PARAMS, SIMILARITY_THRESHOLD, TABLE_NAME, TOP_K

# Cosine distance (`<=>`) is what pgvector gives back: 0 means identical, 2 means
# opposite. `1 - distance` flips it into the similarity everyone actually reasons
# about, which is also the unit SIMILARITY_THRESHOLD is written in.
#
# The threshold matters more than it looks. Without it, a question the corpus has
# nothing to say about still returns five chunks — the five least-irrelevant ones
# — and the model dutifully answers from them. With it, a bad question returns
# zero rows and rag.py can tell the model it has no sources.
SIMILARITY_QUERY = f"""
    SELECT
        id,
        source_file,
        chunk_index,
        chunk_text,
        title,
        url,
        source_type,
        model,
        year_range,
        engine,
        category,
        1 - (embedding <=> %s::vector) AS similarity
    FROM {TABLE_NAME}
    WHERE 1 - (embedding <=> %s::vector) >= %s
    ORDER BY similarity DESC
    LIMIT %s;
"""


def get_connection():
    """Open a connection to the Postgres database holding audi_doc.

    The only place in the project that knows a database exists is this file.
    Callers use it as a context manager:

        with get_connection() as conn, conn.cursor() as cur:
            ...
    """
    return psycopg2.connect(**DB_PARAMS)


def to_vector_literal(embedding: list[float]) -> str:
    """Format a Python list as the '[0.1,0.2,...]' literal pgvector parses.

    psycopg2 ships no adapter for the vector type, so the value travels as text
    and the `::vector` cast in the query turns it back into a vector. ingest.py
    imports this for its inserts, where the column type does the cast instead.
    """

    return "[" + ",".join(str(value) for value in embedding) + "]"


def similarity_search(
    embedding: list[float],
    k: int,
    threshold: float,
) -> list[dict]:

    """Return the k chunks closest to `embedding`, best match first.

    One dict per chunk: every column of the row plus a `similarity` float. Dicts
    rather than tuples because retrieval.py hands these straight to rag.py, and
    `chunk["chunk_text"]` survives a schema change that `row[3]` would not.

    `closing()` rather than a bare `with`: psycopg2's context manager commits or
    rolls back the transaction but leaves the socket open, and this runs once per
    question in a long-lived CLI session.
    """

    literal = to_vector_literal(embedding)

    with closing(get_connection()) as conn, conn.cursor() as cur:
        cur.execute(SIMILARITY_QUERY, (literal, literal, threshold, k))
        columns = [description[0] for description in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
