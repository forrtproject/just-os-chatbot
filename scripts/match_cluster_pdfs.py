"""Metadata for the FORRT cluster PDFs (issue C2, #17).

    python -m scripts.match_cluster_pdfs

The PDFs in data/FORRT Clusters pdfs/ are named C<cluster>_SC<sub>_<topic>_<author>_<year>.pdf.
Each name is matched to a reference in the two FORRT sheets (first author + year), which
gives title, DOI and link. Output: data/interim/cluster_pdf_metadata.csv (one row per PDF,
"matched" 0/1) and the match rate. Unmatched rows need the working lists or a person.
"""

import csv
import re
import unicodedata
from pathlib import Path

from just_os.references import normalize_doi

PDF_DIR = Path("data/FORRT Clusters pdfs")
RAW = Path("data/raw")
# Newest copy of each sheet (forrt_sheet{1,2}_<YYMMDD>.csv) → the column with the APA reference
SHEETS = {sorted(RAW.glob("forrt_sheet1_*.csv"))[-1]: "APA reference", sorted(RAW.glob("forrt_sheet2_*.csv"))[-1]: "reference"}
OUT = Path("data/interim/cluster_pdf_metadata.csv")
NAME = re.compile(r"^C(\d+)_SC(\d+)_(.+?)_([^_]+?)_(\d{4})[a-z]?(?:_b)?$", re.I)


def ascii_lower(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()


def parse_name(stem: str):
    """C01_SC01_HistRC_Crüwell_2019 → (1, 1, 'histrc', 'cruwell', '2019'), or None."""
    match = NAME.match(stem.strip())
    if not match:
        return None
    cluster, sub, topic, author, year = match.groups()
    return int(cluster), int(sub), topic.lower(), ascii_lower(author).replace(" ", ""), year


def first_author(reference: str) -> str:
    """'Bartscherer, S. F., & Reinhart, M. (2025)...' → 'bartscherer'."""
    return re.sub(r"[^a-z-]", "", ascii_lower(reference.split(",")[0]))


def load_references():
    refs = []
    for path, column in SHEETS.items():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                text = row.get(column) or ""
                year = re.search(r"\((\d{4})", text)
                if text and year:
                    title = row.get("title") or row.get("Title") or ""
                    url = row.get("url") or next((v for k, v in row.items() if k.startswith("URL/DOI")), "")
                    refs.append({
                        "author": first_author(text), "year": year.group(1), "title": title,
                        "doi": normalize_doi(row.get("DOI")) or normalize_doi(text) or "", "url": url or "",
                    })
    return refs


def match(parsed, refs):
    """The first reference with the same first author and year (None if there is none)."""
    _, _, _, author, year = parsed
    return next((r for r in refs if r["year"] == year and r["author"] and author.startswith(r["author"][:6])), None)


if __name__ == "__main__":
    refs = load_references()
    rows = []
    for pdf in sorted(PDF_DIR.rglob("*.pdf")):
        parsed = parse_name(pdf.stem)
        ref = match(parsed, refs) if parsed else None
        rows.append({
            "file": pdf.relative_to(PDF_DIR).as_posix(),
            "cluster": parsed[0] if parsed else "", "sub_cluster": parsed[1] if parsed else "",
            "author": parsed[3] if parsed else "", "year": parsed[4] if parsed else "",
            "matched": int(ref is not None),
            "title": ref["title"] if ref else "", "doi": ref["doi"] if ref else "", "url": ref["url"] if ref else "",
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    matched = sum(r["matched"] for r in rows)
    named = sum(r["year"] != "" for r in rows)
    print(f"{len(rows)} PDFs, {named} with a parsable name, {matched} matched ({matched / len(rows):.0%}) → {OUT}")
