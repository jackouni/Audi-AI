"""Format manually copy-pasted Reddit threads as markdown with frontmatter into data/processed/.

Reddit walls off unauthenticated .json requests behind a login page now (confirmed
against both www.reddit.com and old.reddit.com — even valid endpoints return a login
page instead of JSON), so there's no working anonymous fetch left. This follows the
same manual process the roadmap already uses for forums: open the thread yourself,
paste the post text and a few good comments in below, and this script just handles
consistent frontmatter + filenames so ingest.py has one code path.
"""

import re
import sys
from pathlib import Path

# Curate threads here — one entry per thread. Fill in what you know; leave "" if you don't.
# model/year_range/engine are per-thread because a thread about a B8 A4 shouldn't get
# tagged as B9, and wrong tags are worse than missing ones (retrieval would filter it in
# for the wrong car).
THREADS = [
    # {
    #     "url": "https://www.reddit.com/r/audi/comments/abc123/coolant_smell_after_i_park/",
    #     "title": "Coolant smell after I park",
    #     "selftext": "Started noticing a sweet smell in the garage after driving...",
    #     "comments": [
    #         "Check your water pump weep hole, this is super common on the 2.0T.",
    #         "Same thing happened to me at 60k miles, ended up being the thermostat housing.",
    #     ],
    #     "model": "A4",
    #     "year_range": "2017-2020",
    #     "engine": "2.0T",
    #     "category": "engine-cooling",
    # },
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "thread"


def write_markdown(entry: dict) -> Path:
    title = entry.get("title", "untitled").strip()
    url = entry.get("url", "")
    selftext = entry.get("selftext", "").strip()
    comments = entry.get("comments", [])

    slug = slugify(title)
    filepath = OUTPUT_DIR / f"reddit-{slug}.md"

    frontmatter = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f'url: "{url}"',
            "source_type: reddit",
            f"model: {entry.get('model', 'A4')}",
            f"year_range: \"{entry.get('year_range', '')}\"",
            f"engine: \"{entry.get('engine', '')}\"",
            f"category: {entry.get('category', '')}",
            "---",
            "",
        ]
    )

    sections = [selftext] if selftext else []
    sections += [f"> {c.strip()}" for c in comments]  # blockquote comments to set them off from OP text
    body = "\n\n".join(sections)

    filepath.write_text(frontmatter + body + "\n")
    return filepath


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not THREADS:
        print("THREADS is empty — paste thread title/selftext/comments in at the top of this file first.", file=sys.stderr)
        return

    written = 0
    for entry in THREADS:
        path = write_markdown(entry)
        written += 1
        print(f"wrote {path.name}")

    print(f"\nDone. Wrote {written} thread files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
