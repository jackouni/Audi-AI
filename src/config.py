"""Models, thresholds, top_k, DB params — the one place ingest.py and retrieval.py both import the embedding model from."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Explicit path so `python src/setup_db.py` works from anywhere, not just root.
load_dotenv(PROJECT_ROOT / ".env")

# --- Corpus ---------------------------------------------------------------

# Every source lands here as one markdown file with frontmatter.
DATA_DIR = PROJECT_ROOT / "data" / "processed"

# --- Models ---------------------------------------------------------------

# THE contract between ingest.py and retrieval.py. If these two ever embed with
# different models nothing crashes — the vectors just stop meaning the same
# thing and results go quietly bad. One constant, imported twice.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # must match the vector(N) column in setup_db.py

CONDENSER_MODEL = "gpt-4o-mini"  # history + question -> standalone search query
CHAT_MODEL = "gpt-4o-mini"  # the answer itself

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Retrieval ------------------------------------------------------------

TOP_K = 5
SIMILARITY_THRESHOLD = 0.3  # cosine similarity, not distance: higher is closer

# --- Database -------------------------------------------------------------

TABLE_NAME = "audi_doc"

DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}
