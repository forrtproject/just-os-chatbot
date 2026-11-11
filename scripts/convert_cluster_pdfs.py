"""Markdown + metadata for the matched FORRT cluster PDFs, ready for scripts/add_to_index.py (#17).

    python -m scripts.convert_cluster_pdfs

Reads data/interim/cluster_pdf_metadata.csv (scripts/match_cluster_pdfs.py). The match is
first author + year only, so a PDF is kept only when the matched title is in its first pages.
Identical files (same bytes in several cluster folders) are converted once.
Output: data/processed/cluster_markdown/<doi_hash>.md and metadata.csv. conditions_of_use is
left empty: the licence is unknown, so the bot uses the text but never shows passages.
"""

import csv
import hashlib
import re
from pathlib import Path

from scripts.match_cluster_pdfs import OUT as MATCHES
from scripts.match_cluster_pdfs import PDF_DIR

OUT = Path("data/processed/cluster_markdown")


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def title_in_text(title: str, text: str) -> bool:
    """The first 60 letters/digits of the title appear in the text (line breaks, hyphens and
    case ignored; the cut-off allows a different subtitle)."""
    key = squash(title)[:60]
    return len(key) >= 15 and key in squash(text)


def doi_hash(row: dict) -> str:
    return hashlib.md5((row["doi"] or squash(row["title"])).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # Not a project dependency: pip install pymupdf4llm
    import pymupdf
    import pymupdf4llm

    OUT.mkdir(parents=True, exist_ok=True)
    with open(MATCHES, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["matched"] == "1"]
    seen_files, kept, rejected = set(), {}, []
    for row in rows:
        pdf = PDF_DIR / row["file"]
        content = hashlib.md5(pdf.read_bytes()).hexdigest()
        if content in seen_files:
            continue
        seen_files.add(content)
        try:
            with pymupdf.open(pdf) as doc:
                first_pages = "".join(page.get_text() for page in doc.pages(0, min(3, doc.page_count)))
        except Exception as e:  # a broken PDF should not stop the batch
            rejected.append((row["file"], f"unreadable: {e}"))
            continue
        if not title_in_text(row["title"], first_pages):
            rejected.append((row["file"], f"title not in PDF: {row['title'][:70]}"))
            continue
        key = doi_hash(row)
        if key in kept:  # same paper, different file (other version or scan)
            continue
        (OUT / f"{key}.md").write_text(pymupdf4llm.to_markdown(str(pdf)), encoding="utf-8")
        kept[key] = {"doi_hash": key, "title": row["title"], "link_to_resource": row["url"] or
                     (f"https://doi.org/{row['doi']}" if row["doi"] else ""), "doi": row["doi"],
                     "material_type": "Reading", "conditions_of_use": ""}
        print(f"{len(kept)} {row['file']}")
    with open(OUT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(next(iter(kept.values()))))
        writer.writeheader()
        writer.writerows(kept.values())
    with open(OUT / "rejected.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("file", "reason"), *rejected])
    print(f"{len(rows)} matched files, {len(seen_files)} unique, {len(kept)} papers converted, "
          f"{len(rejected)} rejected → {OUT}")
