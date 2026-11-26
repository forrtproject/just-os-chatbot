"""Curator ingestion (C4, #25): add new FORRT resources to the index with one command.

    docker run -d --rm --name grobid -p 8070:8070 grobid/grobid:0.8.2-crf     # once, for PDFs
    ./run curate [--csv new_rows.csv | --recommendations] [--limit N] [--in-place] [--no-index]

(`./run curate` runs this module in the web container with data/curation, data/processed and data/interim
writable, since compose.yaml mounts data/ read-only.)

Input: --csv with the columns title and link_to_resource (optional: doi, creators,
conditions_of_use, material_type), --recommendations (what people sent on the /recommend page,
RECOMMENDATIONS_FILE), or by default both FORRT sheets. Per resource:
  1. its DOI or title is already in the index (its docstore.json)  -> already_indexed
  2. a DOI (column or link) -> an open copy (ingest/pdf_sources.py: row link, arXiv/OSF, Unpaywall, OpenAlex,
     Semantic Scholar, Europe PMC, publisher page) -> GROBID -> Markdown, kept only when its title matches
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from just_os.references import document_key, normalize_doi, plain_metadata

MAX_TRIES = 6  # PDF copies tried per resource (each one may go through GROBID)
MIN_PROSE_WORDS = 200  # words in lines of 8+ words: a page below is a menu or landing page (26 Nov: 102 of 420)
WORKERS = 6  # resources at a time
OUTCOMES = {
    "already_indexed": "The index already has this DOI or title",
    "no_open_access_pdf": "No open copy found (Unpaywall, OpenAlex, Semantic Scholar, Europe PMC, arXiv, OSF, "
                          "publisher page): add the PDF by hand or skip",
    "pdf_download_failed": "The open-access links did not give a PDF (blocked, paywall or gone)",
    "pdf_not_converted": "GROBID gave no text (scan, or GROBID not running)",
    "wrong_document": "A PDF was found, but its title is not this resource's: check the link by hand",
    "web_page_failed": "The page could not be downloaded or is not HTML",
    "web_page_too_short": "The page has too little running text (a menu or landing page)",
    "converted": "Markdown written; added to the index unless add_to_index found it there",
}


def read_rows(csv_path, limit=None, recommendations=None):
    if recommendations:  # the /recommend page's JSON lines; a title is looked up from the DOI
        df = pd.read_json(recommendations, lines=True, dtype=str).fillna("")
    elif csv_path:
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
    """document_key of every document in the index (DOI, else title) except abstract cards, as
    scripts/add_to_index.py checks: a resource with only its card is looked for again."""
    from scripts.build_abstract_cards import CARD_TYPE

    nodes = json.loads((Path(index_dir) / "docstore.json").read_text(encoding="utf-8"))["docstore/data"]
    metas = (plain_metadata(n["__data__"].get("metadata", {})) for n in nodes.values())
    return {document_key(m) for m in metas if not str(m.get("material_type", "")).startswith(CARD_TYPE)}


def pdf_markdown(row, work, http=None):
    """(outcome, Markdown) for a row with a DOI: each open copy ingest/pdf_sources.py finds (row link,
    arXiv/OSF, Unpaywall, OpenAlex, Semantic Scholar, Europe PMC, landing page) → PDF → GROBID, until one
    converts and its title matches the row's. MAX_TRIES copies at most."""
    from ingest import pdf_sources
    from scripts.convert_cluster_pdfs import grobid_tei, tei_to_markdown

    http = http or pdf_sources.client()
    if not row["title"]:
        row["title"] = pdf_sources.lookup_title(http, row["doi"])
    outcome = "no_open_access_pdf"
    for n, (url, source, licence) in enumerate(pdf_sources.candidates(http, row["doi"], row["link_to_resource"])):
        if n >= MAX_TRIES:
            break
        content = pdf_sources.download(http, url)
        if content is None:
            outcome = "pdf_download_failed"
            continue
        pdf = work / "pdfs" / f"{hashlib.md5(row['doi'].encode()).hexdigest()}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(content)
        try:
            tei = grobid_tei(pdf, hashlib.md5(content).hexdigest())
        except Exception:  # GROBID not running: the next copy would fail the same way
            return "pdf_not_converted", ""
        meta, markdown = tei_to_markdown(tei) if tei else ({}, "")
        if len(markdown) < 2000:
            outcome = "pdf_not_converted"
            continue
        if not pdf_sources.title_matches(row["title"], meta.get("title", "") + " " + markdown[:3000]):
            outcome = "wrong_document"
            continue
        row["conditions_of_use"] = row["conditions_of_use"] or licence
        row["creators"] = row["creators"] or meta.get("creators", "")
        return "converted", markdown
    return outcome, ""


def prose_words(text):
    """Words in lines of at least 8 words: running text, not menu items."""
    return sum(len(line.split()) for line in text.splitlines() if len(line.split()) >= 8)


def web_markdown(row):
    """(outcome, Markdown) for a row without a DOI: the page's main text."""
    from scripts.fetch_web_resources import MIN_CHARS, fetch, main_text

    try:
        text = main_text(fetch(row["link_to_resource"].strip()))
    except Exception:
        return "web_page_failed", ""
    if len(text) < MIN_CHARS or prose_words(text) < MIN_PROSE_WORDS:
        return "web_page_too_short", ""
    return "converted", f"# {row['title']}\n\nSource: {row['link_to_resource']}\n\n{text}\n"


def curate(rows, known, work, workers=WORKERS):
    """Convert the new rows into work/markdown; returns (report rows, metadata rows). `workers` resources at a time
    (most of the time is waiting for publishers' servers); a resource whose Markdown this run's folder already has is
    taken from there (a stopped run resumes)."""
    markdown_dir = work / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    def one(row):
        key = hashlib.md5((row["doi"] or row["link_to_resource"]).encode("utf-8")).hexdigest()
        done = markdown_dir / f"{key}.md"
        if document_key(row) in known:
            return row, key, "already_indexed", ""
        if done.exists():
            return row, key, "converted", done.read_text(encoding="utf-8")
        outcome, markdown = pdf_markdown(row, work) if row["doi"] else web_markdown(row)
        return row, key, outcome, markdown

    report, metadata = [], []
    with ThreadPoolExecutor(workers) as pool:
        for row, key, outcome, markdown in pool.map(one, rows):  # in the order of the rows
            if markdown:
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
    parser.add_argument("--recommendations", action="store_true",
                        help="the studies recommended on the /recommend page (RECOMMENDATIONS_FILE)")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--in-place", action="store_true", help="add to VECTOR_STORE itself, not to a copy")
    parser.add_argument("--no-index", action="store_true", help="only download and convert")
    parser.add_argument("--work", help="folder for this run (default data/curation/<YYMMDD>; a second run on one day "
                                       "would otherwise overwrite that day's report.csv and metadata.csv)")
    args = parser.parse_args()

    from config import settings

    day = f"{date.today():%y%m%d}"
    work = Path(args.work) if args.work else Path("data/curation") / day
    rows = read_rows(args.csv, args.limit, settings.RECOMMENDATIONS_FILE if args.recommendations else None)
    report, metadata = curate(rows, indexed_keys(settings.VECTOR_STORE), work)
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
