"""Turn the raw reddit .json thread dumps in data/raw/reddit_threads.py into markdown with frontmatter in data/processed/."""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data" / "raw"))
from reddit_threads import json_reddit_threads  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
REMOVED_BODIES = {"[deleted]", "[removed]", ""}

CATEGORY_KEYWORDS = [
    ("engine-cooling", ("coolant", "thermostat", "water pump", "overheat", "radiator")),
    ("engine", ("engine mount", "pcv", "oil consumption", "burning oil", "juddering", "shaking", "engine")),
    ("brakes", ("brake", "rotor", "pad")),
    ("electrical", ("carplay", "wiring", "battery", "electrical")),
    ("mods", ("upgrade", "build", "mod ", "transformation", "tips", "tricks")),
    ("reliability", ("reliab", "common issues", "things to look out", "do's and don'ts", "review")),
]


def clean(text: str) -> str:
    """Unescape HTML entities and drop lone surrogates left over from the raw json dump."""
    return html.unescape(text).encode("utf-8", "ignore").decode("utf-8")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "thread"


def categorize(title: str, selftext: str) -> str:
    haystack = f"{title} {selftext}".lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "general"


def flatten_comments(children: list[dict], depth: int = 0) -> list[str]:
    lines = []
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child["data"]
        body = clean((data.get("body") or "").strip())
        author = clean(data.get("author", "unknown"))
        if body not in REMOVED_BODIES:
            indent = "  " * depth
            lines.append(f"{indent}- **{author}**: {body}")
        replies = data.get("replies")
        if isinstance(replies, dict):
            lines.extend(flatten_comments(replies["data"]["children"], depth + 1))
    return lines


def write_markdown(post: dict, comment_children: list[dict]) -> Path | None:
    title = clean(post.get("title", "").strip())
    selftext = clean((post.get("selftext") or "").strip())
    permalink = post.get("permalink", "")
    post_id = post.get("id") or slugify(title)

    comment_lines = flatten_comments(comment_children)
    if selftext in REMOVED_BODIES and not comment_lines:
        return None

    category = categorize(title, selftext)
    slug = slugify(title)
    filepath = OUTPUT_DIR / f"reddit-{slug}-{post_id}.md"

    frontmatter = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f'url: "https://www.reddit.com{permalink}"',
            "source_type: reddit_thread",
            "model: A4",
            'year_range: ""',
            'engine: ""',
            f"category: {category}",
            "---",
            "",
        ]
    )

    body_parts = []
    if selftext not in REMOVED_BODIES:
        body_parts.append(selftext)
    if comment_lines:
        body_parts.append("## Comments")
        body_parts.append("\n".join(comment_lines))

    filepath.write_text(frontmatter + "\n\n".join(body_parts) + "\n")
    return filepath


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    seen_permalinks = set()
    written = 0
    for thread in json_reddit_threads:
        post_listing, comments_listing = thread
        post = post_listing["data"]["children"][0]["data"]

        permalink = post.get("permalink")
        if permalink in seen_permalinks:
            continue
        seen_permalinks.add(permalink)

        path = write_markdown(post, comments_listing["data"]["children"])
        if path is None:
            print(f"skipped (no content): {post.get('title')}")
            continue

        written += 1
        print(f"wrote {path.name}")

    print(f"\nDone. Wrote {written} thread files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
