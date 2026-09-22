"""Print top-k similarity scores for known-good and known-absent questions.

The two retrieval constants in config.py are measured, not guessed. This is
what measures them:

    python scripts/probe_thresholds.py

Read the output as three bands. Questions the corpus answers should score well
clear of the ones it can't, and the gap between those two groups is where
STRONG_MATCH_THRESHOLD belongs. SIMILARITY_THRESHOLD goes below the weakest
chunk of any ANSWERABLE row — cutting into those is cutting real evidence.

The band that matters is ABSENT: car-shaped questions this B9 corpus has no
answer for. Every document here is Audi A4 prose, so those still match
something at ~0.5. That is the band that produced a confidently invented wheel
torque spec, and the reason a single hard floor isn't enough on its own.

Re-run after the corpus changes. Scores drift as documents are added.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import SIMILARITY_THRESHOLD, STRONG_MATCH_THRESHOLD, TOP_K
from retrieval import search

# ANSWERABLE  the corpus demonstrably contains this answer
# ABSENT      car-shaped, plausible, and not in the corpus — the hard band
# UNRELATED   not about cars at all; the easy case, kept as a sanity floor
PROBES = [
    ("ANSWERABLE", "What caused the rear squeak on the B9 A4 and at what mileage?"),
    ("ANSWERABLE", "aftermarket water pump brand recommendation B9.5 A4"),
    ("ANSWERABLE", "normal oil consumption rate B9 A4"),
    ("ANSWERABLE", "engine mount failure mileage B9 A4 repair cost"),
    ("ANSWERABLE", "CarPlay retrofit 2016 A4 MIB2 versus MMI 3G"),
    ("ABSENT", "What's the torque spec for B8 A4 wheel bolts?"),
    ("ABSENT", "Summarize the BMW 3 Series forum consensus on engine mounts."),
    ("ABSENT", "What did people say about the Q5 infotainment lag?"),
    ("UNRELATED", "What's the best route from Berlin to Munich?"),
    ("UNRELATED", "How do I bake sourdough bread?"),
]


def main() -> None:
    print(f"\nfloor={SIMILARITY_THRESHOLD}  strong={STRONG_MATCH_THRESHOLD}  k={TOP_K}\n")

    for band, question in PROBES:
        # threshold=0.0 so the raw scores are visible, including the ones the
        # configured floor would have dropped.
        chunks = search(question, threshold=0.0, k=TOP_K)
        scores = [chunk["similarity"] for chunk in chunks]
        top = scores[0] if scores else 0.0
        kept = sum(1 for score in scores if score >= SIMILARITY_THRESHOLD)
        verdict = "sources" if top >= STRONG_MATCH_THRESHOLD else "weak" if kept else "none"

        print(f"{band:<11} top={top:.3f}  kept={kept}/{len(scores)}  -> {verdict:<8} {question[:52]}")
        print(f"{'':<11} {[f'{score:.3f}' for score in scores]}\n")


if __name__ == "__main__":
    main()
