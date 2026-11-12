"""Markdown + metadata for every FORRT cluster PDF, ready for scripts/add_to_index.py (#17).

    docker run -d --rm --name grobid -p 8070:8070 grobid/grobid:0.8.2-crf
    python -m scripts.convert_cluster_pdfs

Each unique PDF (same bytes in several cluster folders = one paper) goes through GROBID,
which gives the body text without the reference list and page headers, plus title, authors
and DOI. The DOI is taken from GROBID, the first two pages or the sheet match
(scripts/match_cluster_pdfs.py), and is kept only when the title OpenAlex has for it is in
the first pages of the PDF. A PDF without a checked DOI keeps the GROBID title and authors,
or else its own title field, the largest text on its first page, or its file name.
Books (more than 80 pages) get only their title page read by GROBID; their text, and the text
of PDFs where GROBID finds almost no body, comes from pymupdf4llm. Scans are rejected.

Output: data/processed/cluster_markdown/<doi_hash>.md, metadata.csv and rejected.csv.
The GROBID XML and the OpenAlex answers are cached in data/interim/, so a second run is fast.
"""

import csv
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from just_os.references import normalize_doi
from scripts.get_pub_years import fetch_works
from scripts.match_cluster_pdfs import OUT as MATCHES
from scripts.match_cluster_pdfs import PDF_DIR

OUT = Path("data/processed/cluster_markdown")
TEI_CACHE = Path("data/interim/grobid_tei")
WORKS_CACHE = Path("data/interim/openalex_works.json")
GROBID = os.environ.get("GROBID_URL", "http://localhost:8070")
TEI = "{http://www.tei-c.org/ns/1.0}"
MIN_BODY = 2000  # characters; less than this is a scan or a failed parse
MAX_GROBID_PAGES = 80  # books: GROBID is made for articles and runs out of memory on them
# FORRT confirmed (12 Nov 2026) that the cluster PDFs are open access, so passages may be shown
CLUSTER_LICENCE = "FORRT cluster PDF (open access)"
OPENALEX_FIELDS = "doi,title,publication_year,authorships,open_access,best_oa_location"


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def title_in_text(title: str, text: str) -> bool:
    """The first 60 letters/digits of the title appear in the text (line breaks, hyphens and
    case ignored; the cut-off allows a different subtitle)."""
    key = squash(title)[:60]
    return len(key) >= 15 and key in squash(text)


def doi_hash(row: dict) -> str:
    return hashlib.md5((row["doi"] or squash(row["title"])).encode("utf-8")).hexdigest()


def find_dois(text: str) -> list:
    """Every DOI printed in the text, in order, without repeats."""
    found = (normalize_doi(m.group(0)) for m in re.finditer(r"10\.\d{4,9}/\S+", text))
    return list(dict.fromkeys(d for d in found if d))


def _text(element) -> str:
    return " ".join("".join(element.itertext()).split())


def tei_to_markdown(tei_xml: str):
    """GROBID TEI → ({title, creators, doi}, Markdown). Headings become '## ', figures and
    tables keep their caption only, and the reference list is left out."""
    root = ET.fromstring(tei_xml)
    title_element = root.find(f"{TEI}teiHeader//{TEI}titleStmt/{TEI}title")
    title = _text(title_element) if title_element is not None else ""
    # name parts are separate elements without a space between them
    authors = [" ".join(t.strip() for t in a.itertext() if t.strip()) for a in root.iterfind(f".//{TEI}sourceDesc//{TEI}analytic/{TEI}author/{TEI}persName")]
    doi = next((normalize_doi(e.text) for e in root.iterfind(f".//{TEI}sourceDesc//{TEI}idno")
                if e.get("type") == "DOI" and normalize_doi(e.text)), "")

    lines = [f"# {title}"] if title else []
    abstract = [_text(p) for p in root.iterfind(f".//{TEI}profileDesc/{TEI}abstract//{TEI}p")]
    if any(abstract):
        lines += ["## Abstract", *abstract]
    sections = list(root.iterfind(f".//{TEI}text/{TEI}body/{TEI}div"))
    sections += [d for d in root.iterfind(f".//{TEI}text/{TEI}back/{TEI}div") if d.get("type") == "annex"]
    for section in sections:
        for element in section.iter():
            if element.tag == f"{TEI}head" and _text(element):
                number = f"{element.get('n')} " if element.get("n") else ""
                lines.append(f"## {number}{_text(element)}")
            elif element.tag == f"{TEI}p":
                lines.append(_text(element))
    for figure in root.iterfind(f".//{TEI}text/{TEI}body//{TEI}figure"):
        caption = " ".join(_text(e) for e in figure if e.tag in (f"{TEI}head", f"{TEI}figDesc"))
        lines.append(caption.strip())
    return {"title": title, "creators": ", ".join(authors), "doi": doi}, "\n\n".join(line for line in lines if line)


def body_length(markdown: str) -> int:
    return sum(len(line) for line in markdown.splitlines() if not line.startswith("#"))


def choose_work(candidates: list, works: dict, first_pages: str):
    """The first candidate DOI whose OpenAlex title is in the first pages (None if there is none).
    The check keeps out DOIs of other papers that a first page cites."""
    for doi in candidates:
        work = works.get(doi)
        if work and title_in_text(work.get("title") or "", first_pages):
            return work
    return None


def work_metadata(work: dict) -> dict:
    authors = [a["author"]["display_name"] for a in work.get("authorships") or [] if a.get("author")]
    licence = ((work.get("best_oa_location") or {}).get("license")) or ""
    return {"title": work["title"], "creators": ", ".join(authors), "doi": normalize_doi(work["doi"]),
            "oa_status": (work.get("open_access") or {}).get("oa_status") or "", "licence": licence}


def largest_text(page) -> str:
    """The text in the largest font on a page: the title, when nothing else names it."""
    spans = [s for block in page.get_text("dict")["blocks"] for line in block.get("lines", []) for s in line["spans"]
             if s["text"].strip()]
    size = max((s["size"] for s in spans), default=0)
    return " ".join(" ".join(s["text"] for s in spans if s["size"] >= size - 0.5).split())[:200]


def grobid_tei(pdf: Path, content_hash: str, header_only: bool = False) -> str:
    """The GROBID XML of a PDF ('' when GROBID fails); cached by file content.
    header_only: title, authors and DOI without the body."""
    import requests

    cache = TEI_CACHE / f"{content_hash}.xml"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    try:
        with open(pdf, "rb") as f:
            response = requests.post(f"{GROBID}/api/process{'Header' if header_only else 'Fulltext'}Document",
                                     files={"input": f}, data={"consolidateHeader": "1"},
                                     headers={"Accept": "application/xml"}, timeout=600)
        tei = response.text if response.status_code == 200 and response.text.lstrip().startswith("<") else ""
    except requests.Timeout:  # one slow PDF falls back; a server that is down stops the run
        tei = ""
    if tei:
        cache.write_text(tei, encoding="utf-8")
    return tei


def read_pdf(job):
    """(file, content hash) → what the second pass needs. Runs in a thread: GROBID is the slow part."""
    import pymupdf

    file, content_hash = job
    pdf = PDF_DIR / file
    try:
        with pymupdf.open(pdf) as doc:
            pages = [page.get_text() for page in doc.pages(0, min(3, doc.page_count))]
            pdf_title = (doc.metadata or {}).get("title") or ""
            if not title_in_text(pdf_title, "".join(pages)):
                pdf_title = largest_text(doc[0])
            is_book = doc.page_count > MAX_GROBID_PAGES
    except Exception as e:  # a broken PDF should not stop the batch
        return {"file": file, "error": f"unreadable: {e}"}
    tei = grobid_tei(pdf, content_hash, header_only=is_book)
    try:
        meta, markdown = tei_to_markdown(tei)
    except ET.ParseError:  # no or broken XML: the pymupdf4llm fallback takes over
        meta, markdown = {"title": "", "creators": "", "doi": ""}, ""
    return {"file": file, "first_pages": "".join(pages), "grobid": meta, "markdown": markdown,
            "pdf_title": pdf_title, "dois": find_dois("".join(pages[:2]))}


if __name__ == "__main__":
    # Not project dependencies: pip install pymupdf4llm requests
    import pymupdf4llm

    OUT.mkdir(parents=True, exist_ok=True)
    TEI_CACHE.mkdir(parents=True, exist_ok=True)
    with open(MATCHES, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    unique = {}  # content hash → the first row with these bytes
    for row in rows:
        unique.setdefault(hashlib.md5((PDF_DIR / row["file"]).read_bytes()).hexdigest(), row)
    sheet = {row["file"]: row for row in unique.values()}

    with ThreadPoolExecutor(3) as pool:
        papers = list(pool.map(read_pdf, [(row["file"], h) for h, row in unique.items()]))
    for paper in papers:
        if "error" not in paper:
            sheet_doi = normalize_doi(sheet[paper["file"]]["doi"])
            paper["candidates"] = list(dict.fromkeys(d for d in [paper["grobid"]["doi"], *paper["dois"], sheet_doi] if d))

    works = json.loads(WORKS_CACHE.read_text(encoding="utf-8")) if WORKS_CACHE.exists() else {}
    wanted = sorted({d for p in papers for d in p.get("candidates", []) if d not in works})
    for work in fetch_works(wanted, OPENALEX_FIELDS):
        works[normalize_doi(work["doi"])] = work
    works.update({d: None for d in wanted if d not in works})  # not in OpenAlex: do not ask again
    WORKS_CACHE.write_text(json.dumps(works), encoding="utf-8")

    kept, rejected, fallbacks = {}, [], 0
    for paper in papers:
        if "error" in paper:
            rejected.append((paper["file"], paper["error"]))
            continue
        match, first_pages = sheet[paper["file"]], paper["first_pages"]
        work = choose_work(paper["candidates"], works, first_pages)
        if work:
            meta = work_metadata(work)
        elif title_in_text(paper["grobid"]["title"], first_pages):
            meta = {**paper["grobid"], "doi": "", "oa_status": "", "licence": ""}
        elif match["matched"] == "1" and title_in_text(match["title"], first_pages):
            meta = {"title": match["title"], "creators": "", "doi": "", "oa_status": "", "licence": ""}
        elif len(squash(paper["pdf_title"])) >= 15:  # the PDF's own title field, or its largest text
            meta = {"title": paper["pdf_title"], "creators": "", "doi": "", "oa_status": "", "licence": ""}
        else:  # last resort: the file name (C01_SC01_<topic>_<author>_<year>)
            meta = {"title": Path(paper["file"]).stem.replace("_", " "), "creators": "", "doi": "", "oa_status": "", "licence": ""}
        key = doi_hash(meta)
        if key in kept:  # same paper, different file (other version or scan)
            continue
        markdown = paper["markdown"]
        if body_length(markdown) < MIN_BODY:
            fallbacks += 1
            if (OUT / f"{key}.md").exists():  # a book converted by an earlier run
                markdown = (OUT / f"{key}.md").read_text(encoding="utf-8")
            else:
                markdown = pymupdf4llm.to_markdown(str(PDF_DIR / paper["file"]))
            if body_length(markdown) < MIN_BODY:
                rejected.append((paper["file"], "almost no text (scan)"))
                continue
        (OUT / f"{key}.md").write_text(markdown, encoding="utf-8")
        kept[key] = {"doi_hash": key, **meta, "material_type": "Reading", "conditions_of_use": CLUSTER_LICENCE,
                     "link_to_resource": f"https://doi.org/{meta['doi']}" if meta["doi"] else match["url"],
                     "source_file": paper["file"]}
    with open(OUT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(next(iter(kept.values()))))
        writer.writeheader()
        writer.writerows(kept.values())
    with open(OUT / "rejected.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("file", "reason"), *rejected])
    with_doi = sum(bool(m["doi"]) for m in kept.values())
    print(f"{len(rows)} files, {len(unique)} unique PDFs, {len(kept)} papers converted ({with_doi} with a DOI, "
          f"{fallbacks} by pymupdf4llm), {len(rejected)} rejected → {OUT}")
