"""Pull Reddit threads via the .json trick, write each as markdown with frontmatter into data/raw/."""

import re
import sys
import time
from pathlib import Path

import requests

# Curate threads here — one entry per URL. Fill in what you know; leave "" if you don't.
# model/year_range/engine are per-thread because a thread about a B8 A4 shouldn't get
# tagged as B9, and wrong tags are worse than missing ones (retrieval would filter it in
# for the wrong car).
THREADS = [
    # {
    #     "url": "https://www.reddit.com/r/audi/comments/abc123/coolant_smell_after_i_park/",
    #     "model": "A4",
    #     "year_range": "2017-2020",
    #     "engine": "2.0T",
    #     "category": "engine-cooling",
    # },
]

# Reddit 403s a bare requests User-Agent — anything identifiable works.
HEADERS = {"User-Agent": "audi-a4-rag-corpus-builder/0.1 (by /u/jacksebben)"}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
TOP_N_COMMENTS = 8  # optimized for signal, not the whole thread


def fetch_thread(url: str) -> dict:
    # .json on the end of any reddit URL returns the post + comment tree, no auth needed.
    json_url = url.rstrip("/") + ".json"
    resp = requests.get(json_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "thread"


def collect_comments(comment_listing: dict) -> list[str]:
    # Reddit's JSON is a listing wrapper: {"data": {"children": [{"data": {...}}, ...]}}
    # "more" children are just a stub saying "N more replies exist" — nothing to extract.
    bodies = []
    for child in comment_listing.get("data", {}).get("children", []):
        if child.get("kind") != "t1":  # t1 = comment; skip "more" stubs
            continue
        data = child["data"]
        body = (data.get("body") or "").strip()
        if not body or body in ("[deleted]", "[removed]"):
            continue
        bodies.append((data.get("score", 0), body))

    # Highest-score comments first — that's the signal, low-effort replies aren't.
    bodies.sort(key=lambda pair: pair[0], reverse=True)
    return [body for _, body in bodies[:TOP_N_COMMENTS]]


def write_markdown(post: dict, comments: list[str], meta: dict) -> Path:
    title = post.get("title", "untitled").strip()
    selftext = (post.get("selftext") or "").strip()
    permalink = f"https://www.reddit.com{post.get('permalink', '')}"
    subreddit = post.get("subreddit", "unknown")

    slug = slugify(f"{subreddit}-{title}")
    filepath = OUTPUT_DIR / f"reddit-{slug}.md"

    frontmatter = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f'url: "{permalink}"',
            "source_type: reddit",
            f"model: {meta.get('model', 'A4')}",
            f"year_range: \"{meta.get('year_range', '')}\"",
            f"engine: \"{meta.get('engine', '')}\"",
            f"category: {meta.get('category', '')}",
            "---",
            "",
        ]
    )

    sections = [selftext] if selftext else []
    sections += [f"> {c}" for c in comments]  # blockquote comments to set them off from OP text
    body = "\n\n".join(sections)

    filepath.write_text(frontmatter + body + "\n")
    return filepath


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not THREADS:
        print("THREADS is empty — paste thread URLs in at the top of this file first.", file=sys.stderr)
        return

    written = 0
    for entry in THREADS:
        url = entry["url"]
        try:
            payload = fetch_thread(url)
        except requests.RequestException as exc:
            print(f"{url}: request failed ({exc}), skipping", file=sys.stderr)
            continue

        post = payload[0]["data"]["children"][0]["data"]  # listing[0] is always the post itself
        comments = collect_comments(payload[1])  # listing[1] is always the comment tree

        path = write_markdown(post, comments, entry)
        written += 1
        print(f"wrote {path.name}")

        time.sleep(1)  # unauthenticated reddit is rate-limit-happy, don't get blocked mid-run

    print(f"\nDone. Wrote {written} thread files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
