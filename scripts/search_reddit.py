"""Search Reddit for top B9 (8W) Audi A4 threads, then reuse fetch_reddit.py's fetch/write logic
to pull each one straight into data/raw/ — no manual URL curation needed.
"""

import sys
import time

import requests

# Reuse fetch_reddit's logic instead of copy-pasting it — one code path for the actual
# fetch+parse+write, so this file only has to handle *finding* threads.
from fetch_reddit import HEADERS, OUTPUT_DIR, collect_comments, fetch_thread, write_markdown

SEARCH_URL = "https://www.reddit.com/search.json"

# Each query hits Reddit's full-site search, not just one subreddit — B9 owners post
# in r/audi, r/AudiA4, r/CarAV, wherever. Multiple queries cover different phrasing.
QUERIES = [
    "Audi A4 B9",
    "Audi A4 8W",
    "B9 A4 repair",
    "B9 A4 mod",
    "A4 B9 problem",
]

# "A4" alone catches every generation back to the B5 (1994+). Requiring one of these in
# the title is what actually keeps this a B9-only corpus — see CLAUDE.md's warning that
# general LLMs blend B8/B9 facts confidently and wrongly. Don't drop this filter.
B9_KEYWORDS = ("b9", "8w", "b9.5", "8w0", "8w2")

MIN_SCORE = 10  # "top rated" per the ask — filters out zero-engagement posts
MIN_COMMENTS = 3  # need actual discussion in the thread, not just a lonely post
RESULTS_PER_QUERY = 50
TARGET_THREAD_COUNT = 15  # matches the roadmap's 10-15 thread target


def search(query: str) -> list[dict]:
    resp = requests.get(
        SEARCH_URL,
        headers=HEADERS,
        params={"q": query, "sort": "top", "t": "all", "limit": RESULTS_PER_QUERY},
        timeout=15,
    )
    resp.raise_for_status()
    return [child["data"] for child in resp.json().get("data", {}).get("children", [])]


def is_relevant_b9_post(post: dict) -> bool:
    if post.get("over_18"):
        return False
    if post.get("score", 0) < MIN_SCORE or post.get("num_comments", 0) < MIN_COMMENTS:
        return False
    # title + selftext, since the B9 giveaway (e.g. "8W") is often only in the body
    haystack = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    return any(keyword in haystack for keyword in B9_KEYWORDS)


def find_candidate_posts() -> list[dict]:
    seen_ids = set()
    candidates = []

    for query in QUERIES:
        try:
            results = search(query)
        except requests.RequestException as exc:
            print(f"search '{query}' failed ({exc}), skipping", file=sys.stderr)
            continue

        for post in results:
            post_id = post.get("id")
            if post_id in seen_ids or not is_relevant_b9_post(post):
                continue
            seen_ids.add(post_id)
            candidates.append(post)

        time.sleep(1)  # same politeness rule as fetch_reddit.py

    candidates.sort(key=lambda p: p.get("score", 0), reverse=True)
    return candidates[:TARGET_THREAD_COUNT]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = find_candidate_posts()
    if not candidates:
        print("No matching threads found — try loosening B9_KEYWORDS or MIN_SCORE.", file=sys.stderr)
        return

    written = 0
    for post in candidates:
        permalink = f"https://www.reddit.com{post.get('permalink', '')}"
        try:
            payload = fetch_thread(permalink)
        except requests.RequestException as exc:
            print(f"{permalink}: request failed ({exc}), skipping", file=sys.stderr)
            continue

        comments = collect_comments(payload[1])  # listing[1] is always the comment tree
        # model/year_range/engine/category left blank on purpose — search can't tell you
        # the engine code, only a human skimming the thread can. Tag these by hand after.
        meta = {"model": "A4", "year_range": "", "engine": "", "category": ""}
        path = write_markdown(payload[0]["data"]["children"][0]["data"], comments, meta)
        written += 1
        print(f"wrote {path.name}  (score={post.get('score')}, comments={post.get('num_comments')})")

        time.sleep(1)

    print(f"\nDone. Wrote {written} thread files to {OUTPUT_DIR}.")
    print("Go tag year_range/engine/category in each file before running ingest.py.")


if __name__ == "__main__":
    main()
