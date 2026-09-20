"""Convert a CARB Executive Order CSV export into markdown files with frontmatter in data/raw/.

CARB's EO search (https://ww2.arb.ca.gov/our-work/programs/aftermarket-performance-parts)
doesn't have a JSON API — you search it by hand and export matching rows to CSV.
This script turns that export into the same one-file-per-document format the other
fetch_*.py scripts produce, so ingest.py has one code path.

COLUMN_MAP below assumes CARB's export uses the column names on the left. If your
actual download uses different headers, edit COLUMN_MAP's values (not the keys) to
match — the script will tell you exactly which mapped column is missing if it can't
find one.
"""

import csv
import re
import sys
from pathlib import Path

# left = our field name, right = the column header in CARB's CSV export.
# Check your actual export's header row and fix these if they don't match.
COLUMN_MAP = {
    "eo_number": "EO Number",
    "title": "Vehicle/Engine/Device Description",
    "category": "Category",
    "make": "Vehicle Make",
    "year_range": "Model Year",
    "engine": "Engine Family",
    "issue_date": "Issue Date",
    "status": "Status",
}

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "sources" / "carb_eo_export.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EO_LOOKUP_URL = "https://ww2.arb.ca.gov/our-work/programs/aftermarket-performance-parts"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "eo"


def read_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [col for col in COLUMN_MAP.values() if col not in header]
        if missing:
            sys.exit(
                f"CSV is missing expected column(s): {missing}\n"
                f"Found columns: {header}\n"
                "Fix COLUMN_MAP at the top of this script to match your export."
            )
        return list(reader)


def write_markdown(row: dict) -> Path:
    eo_number = row[COLUMN_MAP["eo_number"]].strip()
    desc = row[COLUMN_MAP["title"]].strip()
    category = row[COLUMN_MAP["category"]].strip()
    make = row[COLUMN_MAP["make"]].strip()
    year_range = row[COLUMN_MAP["year_range"]].strip()
    engine = row[COLUMN_MAP["engine"]].strip()
    status = row[COLUMN_MAP["status"]].strip()
    issue_date = row[COLUMN_MAP["issue_date"]].strip()

    title = f"CARB EO {eo_number} - {desc}"
    slug = slugify(f"{eo_number}-{desc}")
    filepath = OUTPUT_DIR / f"carb-{slug}.md"

    frontmatter = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f'url: "{EO_LOOKUP_URL}"',
            "source_type: carb_eo",
            f"model: {make or 'unknown'}",
            f'year_range: "{year_range}"',
            f'engine: "{engine}"',
            f"category: {slugify(category) if category else 'emissions'}",
            "---",
            "",
        ]
    )

    body = "\n".join(
        [
            desc,
            "",
            f"- EO number: {eo_number}",
            f"- Status: {status or 'unknown'}",
            f"- Issue date: {issue_date or 'unknown'}",
        ]
    )

    filepath.write_text(frontmatter + body + "\n")
    return filepath


def main() -> None:
    if not CSV_PATH.exists():
        sys.exit(
            f"No CSV found at {CSV_PATH}.\n"
            "Search CARB's EO tool by hand, export matching rows to CSV, "
            f"and save it there first: {EO_LOOKUP_URL}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows(CSV_PATH)

    written = 0
    for row in rows:
        path = write_markdown(row)
        written += 1
        print(f"wrote {path.name}")

    print(f"\nDone. Wrote {written} EO files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
