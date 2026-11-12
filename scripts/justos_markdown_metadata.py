"""Metadata for every JUST-OS Markdown file, so the papers the open-access filter left out
can be added with scripts/add_to_index.py (which skips what is already in the index).

    python -m scripts.justos_markdown_metadata

Reads data/raw/forrt_db_250627.csv (one row per JUST-OS ID) and the open-access list
data/NWO JUST-OS/BOT/just-os_db_latest.csv. Output: data/interim/justos_markdown_metadata.csv
with the columns of the open-access list; doi_hash holds the Markdown file name (the JUST-OS ID).
A paper with a DOI that is not in the open-access list gets conditions_of_use
"Not open access (Unpaywall)": the bot answers from it but shows only title + link.
Markdown files over 1 MB are left out: they hold a whole book under the title of one chapter.
Standard library only.
"""

import csv
from pathlib import Path

from just_os.references import normalize_doi

SHEET = Path("data/raw/forrt_db_250627.csv")
OA_LIST = Path("data/NWO JUST-OS/BOT/just-os_db_latest.csv")
MARKDOWN = Path("data/NWO JUST-OS/BOT/markdown/markdown")
OUT = Path("data/interim/justos_markdown_metadata.csv")
NOT_OA = "Not open access (Unpaywall)"
MAX_BYTES = 1_000_000  # larger files are a whole book saved under the title of one chapter
# output column → the start of the sheet's column name (lower case)
COLUMNS = {
    "title": "title", "timestamp": "timestamp", "creators": "provider", "link_to_resource": "url",
    "material_type": "material type", "education_level": "education level",
    "conditions_of_use": "conditions of use", "primary_user": "primary user",
    "subject_areas": "subject areas", "FORRT_clusters": "forrt clusters", "tags": "user tags",
}


def metadata_row(row: dict, open_access: dict) -> dict:
    """One sheet row (keys lower case) → the metadata of its Markdown file.
    open_access: title → DOI of the open-access list (Unpaywall found some DOIs by title)."""
    out = {name: next((v for k, v in row.items() if k.startswith(start)), "") for name, start in COLUMNS.items()}
    # The open-access list first: it has the DOI the index uses (some links carry "?error=..." or a version)
    out["doi"] = open_access.get(out["title"]) or normalize_doi(out["link_to_resource"]) or ""
    if out["doi"] and out["doi"] not in open_access.values():
        out["conditions_of_use"] = NOT_OA
    out["doi_hash"] = next(v for k, v in row.items() if k.startswith("just-os internal identifier")).zfill(4)
    return out


if __name__ == "__main__":
    with open(OA_LIST, encoding="utf-8") as f:
        open_access = {r["title"]: normalize_doi(r["doi"]) for r in csv.DictReader(f)}
    with open(SHEET, encoding="utf-8") as f:
        sheet = [{(k or "").lower(): v or "" for k, v in r.items()} for r in csv.DictReader(f)]
    rows = [metadata_row(r, open_access) for r in sheet]
    rows = [r for r in rows if (MARKDOWN / f"{r['doi_hash']}.md").exists()]
    books = [r["doi_hash"] for r in rows if (MARKDOWN / f"{r['doi_hash']}.md").stat().st_size > MAX_BYTES]
    rows = [r for r in rows if r["doi_hash"] not in books]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    closed = sum(r["conditions_of_use"] == NOT_OA for r in rows)
    print(f"{len(rows)} Markdown files with a sheet row ({closed} not open access) → {OUT}; "
          f"left out as whole books under a chapter title: {', '.join(books)}")
