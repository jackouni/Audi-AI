"""Models, thresholds, top_k, DB params — the one place ingest.py and retrieval.py both import the embedding model from."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Explicit path so `python src/setup_db.py` works from anywhere, not just root.
load_dotenv(PROJECT_ROOT / ".env")

# --- Corpus ---------------------------------------------------------------

# Every source lands here as one markdown file with frontmatter.
DATA_DIR = PROJECT_ROOT / "data" / "raw"

# --- Chunking -------------------------------------------------------------

# Target size for the FALLBACK splitter only. Most chunks never see it:
# ingest.py splits on real structure first (one NHTSA complaint = one chunk,
# one Reddit comment subtree = one chunk) and only hands the recursive splitter
# the pieces that are still too big afterwards.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Floor for a structural piece before it gets merged into its neighbour. Reddit
# threads are full of one-line comments ("Clean build", "Zero issues") that are
# noise alone but a useful chorus together — and at TOP_K=5 a junk chunk that
# matches weakly still costs a real one its slot.
MIN_CHUNK_CHARS = 250

# --- Models ---------------------------------------------------------------

# THE contract between ingest.py and retrieval.py. If these two ever embed with
# different models nothing crashes — the vectors just stop meaning the same
# thing and results go quietly bad. One constant, imported twice.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # must match the vector(N) column in setup_db.py

CONDENSER_MODEL = "gpt-4o-mini"  # history + question -> standalone search query
CHAT_MODEL = "gpt-5.6-luna"  # the answer itself

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY is not set. Add it to .env in the project root.")

# --- Retrieval ------------------------------------------------------------

TOP_K = 5

# Both numbers are measured, not guessed — `scripts/probe_thresholds.py`
# Scores for this corpus:
#
#   answerable question      top chunk 0.70-0.73
#   car-adjacent but absent  top chunk 0.52-0.60   (B8 torque spec, BMW mounts)
#   unrelated entirely       top chunk 0.18-0.27   (sourdough, driving directions)
#
# The trap is the middle band. Any car-shaped question matches *something* 
# at ~0.5 — which is why a 0.3 never fired and the model got handed five 
# irrelevant chunks to answer over.
SIMILARITY_THRESHOLD = 0.5  # hard floor: below this a chunk is dropped entirely

# If even the BEST chunk is under this, the corpus probably doesn't cover the
# question. The chunks still go to the model, but framed as weak background
# rather than as sources — see WEAK_CONTEXT_TEMPLATE in rag.py.
STRONG_MATCH_THRESHOLD = 0.65

# Tuned on a small sample. If a legitimate question starts coming back with
# "the sources don't cover this", this is the first number to lower.

# --- Database -------------------------------------------------------------

TABLE_NAME = "audi_doc"

DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}
