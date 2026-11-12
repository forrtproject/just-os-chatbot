"""Curator ingestion (C4, #25): add new FORRT resources to the index with one command.

    docker run -d --rm --name grobid -p 8070:8070 grobid/grobid:0.8.2-crf     # once, for PDFs
    ./run curate [--csv new_rows.csv] [--limit N] [--in-place] [--no-index]

(`./run curate` runs this module in the web container with data/curation, data/processed and data/interim
writable, since compose.yaml mounts data/ read-only.)

Input: --csv with the columns title and link_to_resource (optional: doi, creators,
conditions_of_use, material_type), or by default both FORRT sheets. Per resource:
  1. its DOI or title is already in the index (its docstore.json)  -> already_indexed
  2. a DOI (column or link) -> Unpaywall open-access PDF -> GROBID -> Markdown
  3. no DOI -> the web page's main text (scripts/fetch_web_resources.py)
Then scripts/add_to_index.py adds the new Markdown to a copy of the index,
data/processed/vs_curated_<YYMMDD> (--in-place: VECTOR_STORE itself), and skips what the index has.
Report: data/curation/<YYMMDD>/report.csv, one row per resource with its outcome; see docs/curators.md.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from just_os.references import document_key, normalize_doi, plain_metadata

OUTCOMES = {
    "already_indexed": "The index already has this DOI or title",
    "no_open_access_pdf": "DOI without an open-access PDF (Unpaywall): add the PDF by hand or skip",
    "pdf_download_failed": "The open-access link did not give a PDF",
    "pdf_not_converted": "GROBID gave no text (scan, or GROBID not running)",
    "web_page_failed": "The page could not be downloaded or is not HTML",
    "web_page_too_short": "The page has too little text (a menu or landing page)",
    "converted": "Markdown written; added to the index unless add_to_index found it there",
}


def read_rows(csv_path, limit=None):
    if csv_path:
        df = pd.read_csv(csv_path, dtype=str).fillna("")
    else:
        from ingest.helpers import URL_FORRT, wrangle_data_forrt
        df = pd.concat([wrangle_data_forrt(pd.read_csv(url, dtype=str)) for url in URL_FORRT], ignore_index=True)
    for column in ("title", "link_to_resource", "doi", "creators", "conditions_of_use", "material_type"):
        if column not in df:
            df[column] = ""
    df["doi"] = [normalize_doi(d) or normalize_doi(link) or "" for d, link in zip(df["doi"], df["link_to_resource"])]
    rows = df.drop_duplicates(subset=["doi", "title"]).to_dict("records")
    return rows[:limit] if limit else rows


def indexed_keys(index_dir):
    """document_key of every document in the index (DOI, else title), as scripts/add_to_index.py checks."""
    nodes = json.loads((Path(index_dir) / "docstore.json").read_text(encoding="utf-8"))["docstore/data"]
    return {document_key(plain_metadata(n["__data__"].get("metadata", {}))) for n in nodes.values()}


def pdf_markdown(row, work):
    """(outcome, Markdown) for a row with a DOI: Unpaywall → PDF → GROBID."""
    from ingest.helpers import download_and_save_pdf, get_unpaywall_info_by_doi
    from scripts.convert_cluster_pdfs import grobid_tei, tei_to_markdown

    try:
        info = json.loads(get_unpaywall_info_by_doi(row["doi"]))
    except Exception:
        info = {}
    location = info.get("best_oa_location") or {}
    if not (info.get("is_oa") and location.get("url_for_pdf")):
        return "no_open_access_pdf", ""
    row["conditions_of_use"] = row["conditions_of_use"] or location.get("license") or ""
    name = download_and_save_pdf(location["url_for_pdf"], row["doi"], work)
    if not name:
        return "pdf_download_failed", ""
    pdf = work / name
    try:
        tei = grobid_tei(pdf, hashlib.md5(pdf.read_bytes()).hexdigest())
    except Exception:  # GROBID not running
        tei = ""
    meta, markdown = tei_to_markdown(tei) if tei else ({}, "")
    if len(markdown) < 2000:
        return "pdf_not_converted", ""
    row["creators"] = row["creators"] or meta.get("creators", "")
    return "converted", markdown


def web_markdown(row):
    """(outcome, Markdown) for a row without a DOI: the page's main text."""
    from scripts.fetch_web_resources import MIN_CHARS, fetch, main_text

    try:
        text = main_text(fetch(row["link_to_resource"].strip()))
    except Exception:
        return "web_page_failed", ""
    if len(text) < MIN_CHARS:
        return "web_page_too_short", ""
    return "converted", f"# {row['title']}\n\nSource: {row['link_to_resource']}\n\n{text}\n"


def curate(rows, known, work):
    """Convert the new rows into work/markdown; returns (report rows, metadata rows)."""
    markdown_dir = work / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    report, metadata = [], []
    for row in rows:
        if document_key(row) in known:
            outcome, markdown = "already_indexed", ""
        elif row["doi"]:
            outcome, markdown = pdf_markdown(row, work)
        else:
            outcome, markdown = web_markdown(row)
        if markdown:
            key = hashlib.md5((row["doi"] or row["link_to_resource"]).encode("utf-8")).hexdigest()
            (markdown_dir / f"{key}.md").write_text(markdown, encoding="utf-8")
            metadata.append({"doi_hash": key, **{k: row[k] for k in
                             ("title", "creators", "doi", "link_to_resource", "material_type", "conditions_of_use")}})
        report.append({"title": row["title"], "doi": row["doi"], "link_to_resource": row["link_to_resource"],
                       "outcome": outcome, "what_it_means": OUTCOMES[outcome]})
        print(f"{outcome:20} {str(row['title'])[:70]}", flush=True)
    return report, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="new rows (default: both FORRT sheets)")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--in-place", action="store_true", help="add to VECTOR_STORE itself, not to a copy")
    parser.add_argument("--no-index", action="store_true", help="only download and convert")
    args = parser.parse_args()

    from config import settings

    day = f"{date.today():%y%m%d}"
    work = Path("data/curation") / day
    report, metadata = curate(read_rows(args.csv, args.limit), indexed_keys(settings.VECTOR_STORE), work)
    pd.DataFrame(report).to_csv(work / "report.csv", index=False)
    pd.DataFrame(metadata, columns=["doi_hash", "title", "creators", "doi", "link_to_resource",
                                    "material_type", "conditions_of_use"]).to_csv(work / "metadata.csv", index=False)
    print(f"report: {work / 'report.csv'}  {pd.Series([r['outcome'] for r in report]).value_counts().to_dict()}")
    if not metadata or args.no_index:
        return

    output = settings.VECTOR_STORE if args.in_place else f"data/processed/vs_curated_{day}"
    if not args.in_place and not Path(output).exists():
        shutil.copytree(settings.VECTOR_STORE, output)  # the live index stays as it is
    subprocess.run([sys.executable, "-m", "scripts.add_to_index", str(work / "markdown"), str(work / "metadata.csv"),
                    "--index", output, "--output", output], check=True)
    if not args.in_place:
        print(f"To use it: set VECTOR_STORE={output} in .env and restart the web container")


if __name__ == "__main__":
    main()
