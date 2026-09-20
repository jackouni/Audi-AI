"""Pull NHTSA complaints via their JSON API, write each as markdown with frontmatter into data/raw/."""

import re
import sys
import time
from pathlib import Path

import requests

MAKE = "audi"
MODEL = "a4"
MODEL_YEARS = range(2017, 2020)  # B9 A4, first three model years

API_URL = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PER_YEAR_CAP = 15  # roadmap target: 20-30 complaints; 3 years x 15 = 45 total


def fetch_complaints(model_year: int) -> list[dict]:
    resp = requests.get(
        API_URL,
        params={"make": MAKE, "model": MODEL, "modelYear": model_year},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "complaint"


def write_markdown(complaint: dict) -> Path:
    odi_number = complaint.get("odiNumber", "unknown")
    components = (complaint.get("components") or "unknown").strip()
    products = complaint.get("products") or [{}]
    year = products[0].get("productYear", "unknown")
    summary = (complaint.get("summary") or "").strip()
    vin = complaint.get("vin", "")

    category = slugify(components)
    title = f"NHTSA complaint {odi_number} - {components} - Audi A4 {year}"
    slug = slugify(f"{year}-{components}-{odi_number}")
    filepath = OUTPUT_DIR / f"nhtsa-{slug}.md"

    frontmatter = "\n".join(
        [
            "---",
            f'title: "{title}"',
            f'url: "https://www.nhtsa.gov/vin-decoder?vin={vin}"',
            "source_type: nhtsa_complaint",
            "model: A4",
            f'year_range: "{year}"',
            'engine: ""',
            f"category: {category}",
            "---",
            "",
        ]
    )

    body = "\n".join(
        [
            summary,
            "",
            f"- ODI number: {odi_number}",
            f"- Date of incident: {complaint.get('dateOfIncident', 'unknown')}",
            f"- Date filed: {complaint.get('dateComplaintFiled', 'unknown')}",
            f"- Crash: {complaint.get('crash', 'unknown')}",
            f"- Fire: {complaint.get('fire', 'unknown')}",
            f"- Injuries: {complaint.get('numberOfInjuries', 0)}",
            f"- Deaths: {complaint.get('numberOfDeaths', 0)}",
        ]
    )

    filepath.write_text(frontmatter + body + "\n")
    return filepath


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_written = 0
    for year in MODEL_YEARS:
        try:
            complaints = fetch_complaints(year)
        except requests.RequestException as exc:
            print(f"{year}: request failed ({exc}), skipping", file=sys.stderr)
            continue

        print(f"{year}: {len(complaints)} complaints")
        written_this_year = 0
        for complaint in complaints:
            if written_this_year >= PER_YEAR_CAP:
                break
            if not (complaint.get("summary") or "").strip():
                continue
            path = write_markdown(complaint)
            written_this_year += 1
            print(f"  wrote {path.name}")

        total_written += written_this_year
        time.sleep(0.2)  # be polite to the public API

    print(f"\nDone. Wrote {total_written} complaint files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
