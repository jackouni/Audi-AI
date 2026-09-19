# Audi A4 RAG — Setup Decisions

2026-09-19 · Companion to the Data Source Plan and Architecture Decisions

Dependency management and the dependency list for the 2-day MVP, with reasoning.

## Project vitals

- **Project:** `audi-b9-rag`
- **Scope:** RAG chatbot for Audi B9 repair and modification
- **Build window:** 2 days
- **Manager:** Poetry, `package-mode = false`
- **Runtime:** Python 3.12, Postgres + pgvector

## What we settled on

**Poetry stays.** uv is faster, but a 2-day build is the wrong time to learn a new package manager. The labs' workflow carries over untouched: `poetry install`, then `eval $(poetry env activate)`.

**pdfplumber over pypdf.** Slower extraction, better table handling. Service manuals are full of torque-spec tables, and that's the content most worth retrieving cleanly. Preprocessing runs once, so the speed hit costs nothing.

**LangChain handles chunking.** It covers structural and semantic in one dependency. Markdown headers split first, a character splitter caps size after, and the semantic chunker stays in reserve for messier forum text.

**Flat `src/`, scripts alongside.** Build-time and runtime code live in the same directory, separated by filename rather than folders. Small enough to hold in your head at 11pm on day two.

## pyproject.toml

```toml
[tool.poetry]
name = "audi-b9-rag"
version = "0.1.0"
description = "RAG chatbot for Audi B9 repair and modification"
authors = ["Your Name"]
readme = "README.md"
package-mode = false  # not a distributable package — lets you run
                      #   `python src/ingest.py` from the root, no install step

[tool.poetry.dependencies]
python = ">=3.12,<4.0"

# Runtime — every question
openai = "^1.100.2"
psycopg2-binary = "^2.9.10"           # Postgres driver; `-binary` ships precompiled
python-dotenv = "^1.1.1"

# Build-time — ingest pipeline
pdfplumber = "^0.11.0"                # PDF text + table extraction
python-frontmatter = "^1.1.0"         # splits `---` metadata from body
requests = "^2.32.0"                  # NHTSA API + Reddit `.json` trick
langchain-text-splitters = "^0.3.0"   # markdown-header + recursive splitters
langchain-experimental = "^0.3.4"     # SemanticChunker only
langchain-openai = "^0.3.30"          # embeddings wrapper SemanticChunker needs

# Day 2, if time
gradio = "^5.43.1"                    # browser UI wrapping ask()

[build-system]
requires = ["poetry-core>=2.0.0,<3.0.0"]
build-backend = "poetry.core.masonry.api"
```

If `poetry install` hits a resolution error on any of the four new packages, delete that line and run `poetry add <name>` — Poetry writes the correct current constraint itself.

## Every dependency, and why

### Runtime — runs on every question

**`openai`**
- *Does:* Generates embeddings and calls the chat model.
- *Why:* Both halves of RAG go through it — the embedding for search, the completion for the answer. Same library as every lab.

**`psycopg2-binary`**
- *Does:* Connects Python to Postgres and runs queries.
- *Why:* The vector DB is Postgres with pgvector, so this is the whole data layer. The `-binary` variant ships precompiled — no C compiler, no install surprises.

**`python-dotenv`**
- *Does:* Loads `.env` into environment variables.
- *Why:* Keeps the OpenAI key and DB credentials out of the repo.

### Build-time — runs once, during ingest

**`pdfplumber`**
- *Does:* Extracts text and tables from PDFs.
- *Why:* The service and owner's manuals are PDFs, and their torque specs live in tables. pypdf would flatten those into unreadable mush; pdfplumber keeps the structure. Slower, but it only runs once.

**`python-frontmatter`**
- *Does:* Parses a markdown file into a metadata dict plus a body string.
- *Why:* Every source lands as markdown with a `---` frontmatter block. This turns that convention into DB columns in one line instead of a hand-rolled YAML splitter.

**`requests`**
- *Does:* Makes HTTP calls.
- *Why:* Two of the six sources are plain JSON endpoints — the NHTSA complaints API and the Reddit `.json` trick. Both are a few lines with this.

**`langchain-text-splitters`**
- *Does:* Provides `MarkdownHeaderTextSplitter` (splits on headers, keeps them as metadata) and `RecursiveCharacterTextSplitter` (caps chunk size with overlap).
- *Why:* Manual sections are already chunked by their authors — headers mark real topic boundaries, so splitting there is free accuracy. Declared explicitly rather than inherited, since ingest imports from it directly.

**`langchain-experimental`**
- *Does:* Provides `SemanticChunker`, which splits on meaning shifts between sentences.
- *Why:* Held in reserve for forum threads, which have no headers to split on. Drop this line if structural chunking turns out good enough.

**`langchain-openai`**
- *Does:* Wraps the OpenAI embeddings API in LangChain's interface.
- *Why:* Only exists because `SemanticChunker` needs an embeddings object to compare sentences. Goes out with `langchain-experimental` if that gets cut.

### Day 2, if time allows

**`gradio`**
- *Does:* Builds a browser chat UI from a Python function.
- *Why:* Because `rag.py` exposes `ask(question, history) -> str` and knows nothing about UI, this is a ~20-line wrapper rather than a refactor. Cut it and the CLI still demos fine.

## What we cut from the labs file

All three are one `poetry add` away if the need shows up.

- **`numpy`** — was there for hand-rolled cosine similarity. pgvector does that math inside Postgres now with the `<=>` operator.
- **`tiktoken`** — only matters if you enforce a hard token cap on chat memory. Not MVP.
- **`jupyter` / `ipykernel`** — this is a standalone project, not a notebook. Add them back if you'd rather prototype ingest interactively first.

## Next up

The `audi_doc` schema. It's the chokepoint — `ingest.py` can't insert into a table that doesn't exist, and `retrieval.py` can't query columns it doesn't know the names of. Renaming a column after 200 chunks are embedded means re-running the whole ingest.
