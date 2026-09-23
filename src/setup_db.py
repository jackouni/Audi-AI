"""ONE-TIME: create the audi_doc table (pgvector extension, chunk_text, embedding, per-chunk metadata).

Run from the project root:

    python src/setup_db.py            # create if missing
    python src/setup_db.py --reset    # drop and recreate (wipes all chunks)

The database itself must already exist:  createdb audi_b9
"""

import sys

from config import EMBEDDING_DIMENSIONS, TABLE_NAME
from db import get_connection

# One row per CHUNK, not per document. Retrieval returns chunks, so every row
# carries its own copy of the parent document's frontmatter — otherwise a hit
# comes back with no idea which model/year it describes, and the answer starts
# confidently blending B8 and B9 facts.
#
# The seven metadata columns are exactly the seven frontmatter keys in
# data/raw/*.md. Everything is TEXT and nullable: the enums
# (source_type, model, engine, category) stay a documented convention, not a
# CHECK constraint. A typo in one file should not kill a whole ingest run.
CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id          SERIAL PRIMARY KEY,

    -- provenance: which file this chunk came from, and where in it
    source_file TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- the retrievable unit
    chunk_text  TEXT NOT NULL,
    embedding   vector({EMBEDDING_DIMENSIONS}) NOT NULL,

    -- a copy of the parent document's frontmatter
    title       TEXT,
    url         TEXT,
    source_type TEXT,
    model       TEXT,
    year_range  TEXT,
    engine      TEXT,
    category    TEXT,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- lets ingest.py be re-run safely: it wipes the table and re-inserts
    UNIQUE (source_file, chunk_index)
);
"""

# Metadata filtering at query time ("B9 only") is the fix for B8/B9 blending,
# so these two get an index. No index on `embedding`: at 150-250 chunks a
# sequential scan is instant, and an approximate index (HNSW/IVFFlat) would
# only trade away exact recall for speed we don't need. Add one if the corpus
# grows past a few thousand rows.
CREATE_INDEXES = f"""
CREATE INDEX IF NOT EXISTS {TABLE_NAME}_model_idx       ON {TABLE_NAME} (model);
CREATE INDEX IF NOT EXISTS {TABLE_NAME}_source_type_idx ON {TABLE_NAME} (source_type);
"""


def setup(reset: bool = False) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        print("pgvector extension ready.")

        if reset:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME};")
            print(f"Dropped existing {TABLE_NAME}.")

        cur.execute(CREATE_TABLE)
        cur.execute(CREATE_INDEXES)
        conn.commit()

        cur.execute(f"SELECT count(*) FROM {TABLE_NAME};")
        (count,) = cur.fetchone()

    print(f"Database setup complete! {TABLE_NAME} holds {count} chunks.")


if __name__ == "__main__":
    setup(reset="--reset" in sys.argv)
