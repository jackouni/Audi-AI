# Audi A4 RAG — Architecture Decisions

2026-09-19 · Companion to the Data Source Plan

Decisions made for the 2-day MVP: file structure, the runtime chain, and the reasoning behind both.

## The core split: build-time vs runtime

The MVP diagram's top row (Knowledge Base → Chunking → Vector DB) runs **once, offline**. The bottom row (prompt → retrieval → LLM → response) runs **on every user question**. Different lifecycles, different failure modes, different debugging. That is the split the file structure follows.

Rejected: `frontend/` + `backend/` + `vectordb/`.

- `vectordb/` — the vector DB is Postgres. It lives outside the repo. The only code is a connection helper and a couple of queries: one file, not a directory.
- `frontend/` + `backend/` — that split exists to mark an HTTP boundary. With a CLI and later Gradio, both run in the same Python process. The real boundary is a function signature, not a folder.

## File structure

```
audi-b9-rag/
├── pyproject.toml
├── .env                     # OPENAI_API_KEY, DB creds
├── .gitignore
├── README.md
├── data/
│   └── raw/                 # ALL sources
│   └── processed/           # ALL processed sources
├── scripts/
│   ├── fetch_nhtsa.py       # JSON API → markdown files
│   ├── fetch_reddit.py      # .json trick → markdown files
│   └── extract_pdf.py       # takes a path, works for both manuals
└── src/
    ├── config.py            # models, thresholds, top_k, DB params
    ├── db.py                # connection + similarity query
    ├── setup_db.py          # ONE-TIME: create audi_doc
    ├── ingest.py            # ONE-TIME: raw/*.md → chunks → DB
    ├── memory.py            # Message / ChatHistory (from the lab)
    ├── retrieval.py         # condense query → embed → search
    ├── rag.py               # ask(question, history) -> str
    ├── main.py              # CLI loop
    └── app.py               # Gradio (day 2, if time)
```

### Why each decision

**Flat `src/`, ~9 files.** Small enough to hold in your head at 11pm on day 2. Mirrors the lab structure already familiar (`db_check.py`, `search.py`, `rag.py`, `main.py`) with ingestion added.

**`config.py` exists on purpose.** The embedding model must be identical in `ingest.py` and `retrieval.py`. If they drift there is no crash and no error, just bad results. One constant, imported twice.

**Three scripts for six sources.** Acquisition differs per source (API, PDF, copy-paste). Ingestion does not, because every source lands as the same markdown-with-frontmatter file. Copy-paste sources need zero code — that is the payoff of the convention. `ingest.py` cannot tell an API pull from a clipboard paste.

**`rag.py` knows no UI.** `ask(question, history) -> str`. No `print`, no `input`, no Gradio import. `main.py` wraps it in a while-loop, `app.py` wraps it in Gradio. Swapping interfaces becomes "write a new 20-line file," not a refactor.

**Run scripts as `python src/ingest.py` from the project root.** With `package-mode = false`, Python puts the script's directory on the path, so `from db import get_connection` works with no packaging setup.

## Chain of operations

### Build-time (runs once)

1. `scripts/*` pull raw sources, or paste manually → write markdown files with frontmatter into `data/raw/`
2. `setup_db.py` creates the `audi_doc` table
3. `ingest.py`: glob `data/raw/*.md` → parse frontmatter → chunk the body → embed each chunk → insert
4. Each chunk row = chunk text + embedding vector + a **copy of the parent document's metadata**

Metadata is per-document in the file, but per-chunk in the database, because retrieval returns chunks, not documents.

### Runtime (every question)

1. User asks a question
2. **Condense**: cheap `gpt-4o-mini` call takes chat history + new question → one standalone search query
3. **Embed** only that condensed query
4. **Search** the vector DB → top-k chunks
5. **Assemble** the final prompt: system instructions + retrieved chunks + full chat history + question
6. **Send** to the LLM → response
7. Append the turn to history

## The condenser — why it exists

Retrieval fires *before* history reaches the prompt. So a follow-up like "how hard is it to replace?" gets embedded on its own, with nothing to resolve "it" against. The search returns garbage exactly when a demo is going well.

Two things worth being clear on:

- **It is a retrieval fix, not a token saver.** Its output never reaches the final prompt. It exists purely to become a good embedding.
- **Do not embed the raw history instead.** Embeddings are closer to an average than a sum — several turns squashed into one fixed-size vector muddy the meaning. The goal is resolving the pronoun, not adding context.

Cost: one mini call, ~0.5s, fractions of a cent. If skipped for time, embed the raw question alone (never the full history) and add the condenser later — it is one function at the top of `retrieval.py` and nothing downstream notices.

## Memory

Memory = the list of past turns re-sent on every request. The model is stateless; it forgets the instant it responds. Reuse `Message` / `ChatHistory` from the conversation loop lab.

**Keep retrieved chunks out of permanent history.** History stays plain user/assistant turns. Inject fresh chunks each turn and let them fall away, or the context window is gone by turn four.

## Open items

- `audi_doc` schema: the field reference table from the Data Source Plan, plus `id`, `chunk_text`, `embedding`
- Enums (`source_type`, `model`, `engine`, `category`) stay a documented convention, not a Postgres check constraint — a typo should not crash a whole ingest run
