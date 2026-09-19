# Audi A4 RAG — Architecture Map

Companion to the Data Source Plan, Architecture Decisions, and Setup Decisions docs. This one maps how every file connects and what each one is responsible for.

## The core split

The project splits cleanly into two halves that share a database and nothing else:

- **Runs once** (build time) — six data sources become one table of embedded chunks
- **Runs on every question** (runtime) — a question goes down the stack, chunks come back up, an answer goes out

Different lifecycles, different failure modes, different debugging. This is the single most useful thing to hold in your head while building.

---

## Part 1: Runs once (build time)

```
scripts/*.py  ──fetch/extract──>  data/raw/  ──ingest.py──>  audi_doc
(fetch+extract)                  (markdown)   (chunk+embed)  (pgvector table)

config.py ──(settings)──> ingest.py
setup_db.py ──(creates table)──> audi_doc
```

### What happens

Six sources (service manuals, forum threads, CARB EOs, NHTSA complaints, owner's manual, Reddit) get pulled down three different ways — a JSON API, a PDF extractor, or a human copy-pasting. They all land as one markdown file per document with YAML frontmatter. Then `ingest.py` globs the folder, parses frontmatter into metadata, chunks the body, embeds each chunk, and inserts rows. You run this once; after that the database just sits there.

### The entities and their jobs

| File | Job |
|---|---|
| `scripts/*.py` | Three acquisition scripts — `fetch_nhtsa.py`, `fetch_reddit.py`, `extract_pdf.py`. Each knows how to talk to exactly one kind of source and write markdown out the other end. |
| `data/raw/` | Folder of markdown-plus-frontmatter files. Not code — it's the handoff point where six acquisition methods become one uniform thing. |
| `setup_db.py` | Creates the `audi_doc` table and enables pgvector. Runs before `ingest.py`, then never again. |
| `ingest.py` | The whole preprocessing pipeline: parse → chunk → embed → insert. Copies the parent document's metadata onto every chunk row, because retrieval returns chunks, not documents. |
| `config.py` | Model names, thresholds, `top_k`, DB params. Imported by both halves of the project. |
| `audi_doc` | The Postgres table. One row per chunk: chunk text, embedding vector, and a copy of the document metadata. |

### How they connect

`data/raw/` is the seam. Everything upstream of it is six messy, incompatible acquisition methods. Everything downstream is a single code path — `ingest.py` literally cannot tell an API pull from a clipboard paste. That's the entire payoff of the markdown-with-frontmatter convention: copy-paste sources cost zero lines of code.

`config.py` exists for one specific reason: the embedding model must be identical in `ingest.py` and `retrieval.py`. If those drift apart, nothing crashes and no error appears — you just get quietly garbage results, which is worse than a stack trace. One constant, imported twice.

`ingest.py` also imports `db.py` (the runtime file below) for its inserts — the only place the two halves share code.

---

## Part 2: Runs on every question (runtime)

```
User ──asks──> main.py/app.py ──ask(question, history)──> rag.py
 ^                                                            |  \
 |                                                            v   \--> memory.py (chat history)
 |__________________answer___________________________________|         (returns updated history)
                                                               |
                                                               v
                                                         retrieval.py ──(condense, embed)──> OpenAI
                                                               |
                                                               v
                                                            db.py ──(similarity query)──> audi_doc
                                                               |
                                                               v
                                                        top-k chunks (returned back up the chain)
```

### The full round trip

1. User types "coolant smell after I park, B9 S4"
2. `main.py` appends it to history and calls `ask(question, history)`
3. `rag.py` hands both to `retrieval.py`
4. `retrieval.py` condenses the question into a standalone query, embeds it, and asks `db.py` for the top-k matches
5. Chunks come back up to `rag.py`, which assembles the final prompt: system instructions + retrieved chunks + full chat history + question
6. One OpenAI call; the answer string returns
7. `main.py` prints it, appends the turn to history, loops

### The entities and their jobs

| File | Job |
|---|---|
| User | A mechanic or enthusiast with a specific car and a specific problem. Only ever touches the interface layer. |
| `main.py` / `app.py` | The interface. `main.py` is a while-loop over `input()`; `app.py` is the Gradio wrapper for day 2. Both are thin — they own I/O and nothing else. |
| `rag.py` | The orchestrator and center of gravity. Calls retrieval, assembles the prompt, calls the model, returns a string. Knows no UI: no `print`, no `input`, no Gradio import. |
| `memory.py` | `Message` and `ChatHistory`, lifted from the conversation loop lab. The model is stateless, so memory is just the list of past turns re-sent on every request. |
| `retrieval.py` | Condense → embed → search. Turns a conversational follow-up into a standalone query, embeds only that, and hands the vector down to `db.py`. |
| `db.py` | Connection helper plus the pgvector similarity query. The only file in the project that knows a database exists. |
| OpenAI | External. Hit multiple times per question: a cheap `gpt-4o-mini` call for the condenser, an embedding call for search, and the main completion for the answer. |

### The contracts between files

Four function signatures hold the whole thing together. Each layer can be swapped without touching the others.

- `main.py` → `rag.ask(question, history)` → a string
- `rag.py` → `retrieval.search(question, history)` → a list of chunk dicts
- `retrieval.py` → `db.similarity_search(embedding, k)` → rows
- `db.py` → Postgres

This is why swapping the CLI for Gradio on day 2 changes exactly one file. The user-facing behavior is identical because the contract underneath never moved.

---

## The condenser, and why it exists

Retrieval fires *before* history reaches the prompt. So a follow-up like "how hard is it to replace?" gets embedded on its own, with nothing to resolve "it" against — and the search returns garbage at exactly the moment a demo is going well. The condenser is one cheap `gpt-4o-mini` call at the top of `retrieval.py`: history plus new question in, one standalone search query out.

Two things worth being clear on:
- It's a **retrieval fix, not a token saver** — its output never reaches the final prompt; it exists purely to become a good embedding.
- **Don't embed the raw history instead**: embeddings behave more like an average than a sum, so several turns squashed into one fixed-size vector just muddy the meaning. The goal is resolving the pronoun, not adding context.

## Keep retrieved chunks out of permanent history

History stays plain user/assistant turns. Inject fresh chunks each turn and let them fall away. Store them permanently and your context window is gone by turn four.

---

## Debugging heuristic

- **Wrong but fluent** → the bug is in retrieval. Open `retrieval.py` or `db.py`, check what chunks actually came back.
- **Right but weird-sounding** → the bug is in prompt assembly. Open `rag.py`.
- **Confidently blending B8 and B9 facts** → metadata filtering isn't doing its job at query time.

---