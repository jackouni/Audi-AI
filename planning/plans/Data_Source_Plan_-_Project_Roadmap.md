# B9 RAG — Data Source Plan

2026-09-18 · @Someone

Corpus plan for the Audi B9 repair/mod chatbot. 2-day MVP.

## Collection rules

One rule decides the method for every source: if it hands back structured data, automate it; if you would have to parse someone else's HTML, copy-paste it.

- **45-minute timebox per source.** If it is not returning usable data by then, switch that source to manual and move on.
- **Hard stop on collecting after 5 hours.** Whatever is in `data/raw/` at that point is the corpus.
- **Trim as you paste.** Kill signatures, quote chains, "bump" replies. About 30 seconds per document.
- **No HTML parsing.** Forum scrapers are the single biggest timeline risk in this build.
- Keep volume small and the corpus local. Forum terms of service generally prohibit scraping, which is the other reason manual wins on those.

## All sources, ranked

Ranked highest to lowest impact, where impact means how much the source improves answers the chatbot could not already give well. All six are in the MVP corpus. Total gathering time: **5 hours**.

| # | Source | How to obtain | Time | Impact | What it adds |
| --- | --- | --- | --- | --- | --- |
| 1 | Factory / service manuals | PDF extract (`pypdf`) | 60 min | **High** | Authoritative procedures, torque specs, part numbers — mostly absent from pretraining |
| 2 | Audi forums (Audizine, AudiWorld) | Manual copy-paste | 90 min | **High** | Symptom vocabulary; bridges how owners describe problems to what procedures are called |
| 3 | CARB Executive Orders | EO database search, manual export | 45 min | **High** (mods) | Emissions legality and EO numbers per part; general LLMs are poor at this |
| 4 | NHTSA complaints + ODI investigations | Public JSON API, no key | 45 min | **Medium-high** | Structured failure patterns by model year; ODI writeups analyze patterns, not single incidents |
| 5 | Owner's manual | PDF extract | 30 min | **Medium** | Fluid capacities, service intervals, warning-light meanings |
| 6 | Reddit threads | Append `.json` to thread URL | 30 min | **Medium** | More symptom vocabulary; overlaps the forums |

## Rank 1 and 2: the core corpus

These two cover the split that makes retrieval work — manuals give authority, forums give findability.

### Factory / service manuals

Highest value because they are paywalled and therefore mostly absent from pretraining. Real torque specs, real procedures, real part numbers. Sources: Audi ERWIN subscriptions, workshop manual PDFs, Bentley-style repair manuals.

Method: `pypdf` or `pdfplumber` for text extraction, then semantic chunking from the chunking lab. Target 8–12 extracted sections.

### Audi forums

Their value is not facts — it is **vocabulary**. Users type "coolant smell after I park" or "rough idle when cold." No manual contains that phrasing; forum posts do. Embedding them gives user queries something to land on, then metadata and the LLM bridge to the correct procedure.

They also carry a signal available nowhere else: which failures are actually common on this platform.

Method: manual copy-paste, one thread per file, trimmed. Target 15–20 threads. Do not scrape — vBulletin HTML behind Cloudflare is where this project's timeline goes to die.

## Ranks 4–6: cheap automated wins

All three are structured data. No HTML parsing, low failure risk, and each takes under an hour.

### NHTSA complaints

Public JSON API, no auth. Query by make, model and year and you get structured owner-reported failures. Strong differentiator for the demo because a general LLM cannot reproduce complaint records by model year, even though it was trained on the site.

Write this as `fetch_nhtsa.py` that dumps straight into `data/raw/`. Target 20–30 complaint summaries, grouped by component.

### Owner's manual

One PDF, clean extraction. Gives you fluid capacities, service intervals and warning-light meanings without arguing with anyone's HTML.

### Reddit threads

Append `.json` to any thread URL and you get structured data back with no scraper. Heavily represented in pretraining, which does not matter: the point is retrievable, citeable text in the context window, not novelty. Same vocabulary value as the forums.

## Government and regulatory sources

CARB and NHTSA are the only regulatory sources in this plan. Other jurisdictions were considered and dropped for the reason below.

Recall data is globally duplicated. A defect recalled in the US is usually recalled in Canada and the EU too, with near-identical wording. Ingesting four recall databases yields one fact four times, not four facts. Those duplicate chunks then crowd out the forum thread that actually explains the repair, because top-k retrieval fills with copies of the same recall notice.

So the filter is not "which bodies exist" but "which publish a different kind of data."

### CARB Executive Orders — add this

Emissions legality and EO numbers per aftermarket part. Directly serves the mods half of the application, enthusiasts ask about it constantly, and it appears nowhere in structured form in a forum thread. Highest-value addition beyond the core corpus.

### NHTSA ODI investigations and TSB index — expand what you already have

Same API you are already calling, different endpoints. Defect investigations are analytical writeups of failure patterns across many vehicles, which is far meatier than an individual complaint. The TSB index tells you which manufacturer bulletins exist for a given component. No new integration work.

## Day 1 schedule

| Block | Task | Output |
| --- | --- | --- |
| 0:00–0:45 | Run `fetch_nhtsa.py` (complaints + ODI) | 20–30 records |
| 0:45–1:15 | Owner's manual PDF extract | Reference sections |
| 1:15–2:15 | Service manual PDF extract | 8–12 sections |
| 2:15–3:00 | CARB EO lookup | EO records for common mods |
| 3:00–3:30 | Reddit `.json` pulls | 10–15 threads |
| 3:30–5:00 | Forum copy-paste session | 15–20 threads |
| 5:00 | **Hard stop on collecting** | — |
| 5:00–5:45 | Schema + `setup_db.py` | `audi_doc` table exists |
| 5:45–7:45 | `ingest.py`: parse, chunk, embed, load | Rows in the DB |
| 7:45–8:15 | Verify with a cosine similarity query | Sane results |

Total: 8 hours 15 minutes — 5 hours gathering, 3 hours 15 minutes preprocessing. End-of-day target: `SELECT count(*) FROM audi_doc` returns a real number and a similarity query returns relevant chunks.

## File format and corpus size

Every source lands as one markdown file per document in `data/raw/`, metadata in frontmatter. One format means `ingest.py` has one code path.

```markdown
---
title: "B9 S4 thermostat failure - symptoms and DIY"
url: "https://www.audizine.com/forum/..."
source_type: forum
model: S4
year_range: "2018-2023"
engine: "3.0T"
category: engine-cooling
---

Started throwing a P2181 last week. Coolant temp gauge
was slow to climb and cabin heat was weak...
```

Those metadata fields become DB columns and let you filter retrieval by model and year — which matters, because general LLMs blend B8 and B9 information confidently and wrongly.

**Targets:** 40–60 documents, 150–250 chunks. That is enough to demonstrate retrieval quality and keeps embedding cost near zero. Do not chase completeness; you are demonstrating that RAG works, not shipping a service manual.
