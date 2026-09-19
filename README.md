# audi-b9-rag

RAG chatbot for Audi B9 (A4/S4) repair and modification. Built for Launch School Capstone.

See `planning/plans/Architecture_Decisions.md` for the design and `CLAUDE.md` for the full project brief.

## Setup

```
poetry install
eval $(poetry env activate)
```

Fill in `.env` with your OpenAI key and Postgres credentials, then:

```
python src/setup_db.py
python src/ingest.py
python src/main.py
```
