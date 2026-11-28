"""One list of every resource FORRT wants in the bot, from all lists in data/FORRT Clusters (and List/).

    python -m scripts.forrt_article_list            # host; reads the index docstore, asks Unpaywall for OA status

Sources (identical copies and format-only copies count once; see SOURCES):
  Publications   FORRT Clusters - Website Source: the Publications CSV and the xlsx "Publications" sheet (6 files,
                 the same 1,295 rows; the xlsx copies differ from the CSV only in formatting)
  FORRT DB 2.0   FORRT Database 2.0 - Curated List of Resources [linked to G-form].csv
  clusters_panos clusters_panos - Sheet1.csv (2 identical copies)
  ORxD           ORxD - Website Source.xlsx, sheet "Resources"
  JUSTOS-URL-Org JUSTOS-URL-Org-2026 - Sheet1.csv
The Clusters / Sub-Clusters sheets are lookup tables (sub-cluster -> cluster), not resources.

One row per resource: the same DOI, else the same title as a row with a DOI, else the same link, else the same
title. found_in lists every list and row (spreadsheet row numbers) where it appears. Open access from Unpaywall
(DOIs only; cached in data/curation/unpaywall_oa.json; OpenAlex's keyless daily budget is shared per IP and ran out); in_index and pdf_on_disk by DOI, else title, else link, against the bot's index
(VECTOR_STORE), the cluster PDFs (data/interim/cluster_pdf_metadata.csv, and file names in data/FORRT Clusters
pdfs) and the JUST-OS PDFs (docs/indexed_documents.csv). in_index_as: full text, abstract card or web page (a page
of a `./run curate` web run). last_try: the newest `./run curate` outcome for the resource (data/curation/*/report.csv).

Output: data/curation/forrt_article_list.csv (all resources) and data/curation/forrt_article_list.xlsx, 7 sheets:
All resources, With DOI, Without DOI, Books, Websites, In index not in lists, Need a PDF; and
data/curation/forrt_need_pdf.csv: the "Need a PDF" rows in the columns `./run curate --csv` reads, with the last try,
to share with someone who has better access to the PDFs. The dev app's /articles page shows the CSV.
"""

import csv
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

from just_os.references import normalize_doi

BASE = Path("data/FORRT Clusters")
PDF_DIR = Path("data/FORRT Clusters pdfs")
OUT = Path("data/curation/forrt_article_list")
CURATION = Path("data/curation")
INDEX_KINDS = ("full text", "web page", "abstract card")  # one resource in the index several ways: the first wins
SOURCES = {  # list name -> the files that hold it (the first is read)
    "Publications": ["FORRT Clusters - Website Source - Publications.csv",
                     "List/FORRT Clusters - Website Source - Publications.csv",
                     "FORRT Clusters - Website Source.xlsx › Publications",
                     "List/FORRT Clusters - Website Source.xlsx › Publications",
                     "List/FORRT Clusters - Website Source (1).xlsx › Publications",
                     "List/FORRT Clusters - Website Source (2).xlsx › Publications"],
    "FORRT DB 2.0": ["List/FORRT Database 2.0 - Curated List of Resources [linked to G-form].csv"],
    "clusters_panos": ["List/clusters_panos - Sheet1.csv", "List/clusters_panos - Sheet1 (1).csv"],
    "ORxD": ["List/ORxD - Website Source.xlsx › Resources"],
    "JUSTOS-URL-Org": ["List/JUSTOS-URL-Org-2026 - Sheet1.csv"],
}
BOOK = re.compile(r"book|textbook|chapter", re.I)
WEB = re.compile(r"website|blog|video|podcast|course|module|syllabus|lecture|lesson|interactive|repository|software|"
                 r"data ?set|tool|list|activity|student guide|teaching", re.I)
ARTICLE = re.compile(r"paper|article|preprint|editorial|letter|review|report|policy|reading|primary source|case study", re.I)
DOCUMENT = re.compile(r"paper|article|preprint|editorial|letter|review|report|policy", re.I)  # a document even without a DOI
OSF_VERSION = re.compile(r"(osf\.io/[a-z0-9]+)_v\d+$")
FIELDS = ["title", "authors", "year", "doi", "url", "category", "type", "clusters", "sub_clusters", "language",
          "licence", "open_access", "oa_status", "oa_url", "in_index", "pdf_on_disk", "pdf_file", "found_in",
          "times_listed", "lists", "excluded_in_source", "in_index_as", "last_try", "last_try_run", "what_it_means",
          "abstract", "summary", "apa_reference"]


def title_key(title) -> str:
    return re.sub(r"[^a-z0-9]", "", html.unescape(str(title or "")).lower())


def url_key(url) -> str:
    url = str(url or "").strip().lower()
    return re.sub(r"^https?://(www\.)?|/+$", "", url) if url.startswith("http") else ""


def read_csv(name):
    with open(BASE / name, encoding="utf-8") as f:
        return [(i, r) for i, r in enumerate(csv.DictReader(f), start=2)]


def read_sheet(name, sheet):
    import openpyxl  # only here: the web image has no openpyxl, and the tests use merge() alone

    rows = list(openpyxl.load_workbook(BASE / name, read_only=True)[sheet].iter_rows(values_only=True))
    head = [str(h or "").strip() for h in rows[0]]
    return [(i, {h: ("" if v is None else str(v).strip()) for h, v in zip(head, r)})
            for i, r in enumerate(rows[1:], start=2) if any(v not in (None, "") for v in r)]


def records():
    """(list name, row number, unified fields) for every row of every list."""
    sub_to_cluster = {r["Name"].strip(): r["Cluster"].strip()
                      for _, r in read_csv("FORRT Clusters - Website Source - Sub-Clusters.csv")}
    for i, r in read_csv(SOURCES["Publications"][0]):
        sub = r["Sub-Cluster"].strip()
        yield "Publications", i, dict(title=r["Title"], authors=r["Authors"], doi=r["DOI"], url=r["OA Link"],
                                      type=r["Resource Type"], clusters=sub_to_cluster.get(sub, ""), sub_clusters=sub,
                                      language=r["Language"], licence=r["License"], abstract=r["Abstract"],
                                      summary=r["Summary"], apa_reference=r["APA Reference"],
                                      excluded=r.get("Display exclusion") == "TRUE")
    rows = read_csv(SOURCES["FORRT DB 2.0"][0])
    url_col = next(k for k in rows[0][1] if k.startswith("URL/DOI"))
    type_col = next(k for k in rows[0][1] if k.startswith("Material Type"))
    old_cluster = next(k for k in rows[0][1] if k.startswith("FORRT Clusters"))
    for i, r in rows:
        yield "FORRT DB 2.0", i, dict(title=r["Title"], authors=r["Provider/Creators"], doi=r["DOI"] or r[url_col],
                                      url=r[url_col], type=r[type_col], clusters=r["FORRT_Clusters_New"] or r[old_cluster],
                                      sub_clusters=r["FORRT_Sub_Clusters"], language=r["Language"],
                                      licence=r["Conditions of Use"], abstract=r["Abstract"],
                                      apa_reference=r["APA reference"], pdf_file=r["PDF name"],
                                      excluded=r["Exclude"] == "TRUE")
    for i, r in read_csv(SOURCES["clusters_panos"][0]):
        yield "clusters_panos", i, dict(title=r["title"], authors=r["authors"], doi=r["DOI"], url=r["url"],
                                        type=r["material_type"], clusters=r["clusters"], apa_reference=r["reference"])
    for i, r in read_sheet("List/ORxD - Website Source.xlsx", "Resources"):
        yield "ORxD", i, dict(title=r["Title"], url=r["Link"], doi=r["Link"], type="",
                              clusters=f"ORxD: {r['Discipline']} ({r['Category']})")
    for i, r in read_csv(SOURCES["JUSTOS-URL-Org"][0]):
        yield "JUSTOS-URL-Org", i, dict(title=r["Specific resource / page"], url=r["Official URL"],
                                        doi=r["Official URL"], type="Website", clusters=r["Topic cluster"])


def merge(rows):
    """Rows -> one dict per resource. Keys: DOI; else the title of a resource with a DOI; else link; else title."""
    by_key, title_of_doi = {}, {}
    # OSF preprint versions (osf.io/ab12c_v3) are the same preprint
    rows = [(src, i, {**r, "doi": OSF_VERSION.sub(r"\1", normalize_doi(r.get("doi")) or "")}) for src, i, r in rows]
    for src, i, r in sorted(rows, key=lambda x: not x[2]["doi"]):  # DOI rows first, so titles can join them
        tk = title_key(r.get("title"))
        if r["doi"]:
            key = "doi:" + r["doi"]
            if len(tk) >= 20:
                title_of_doi.setdefault(tk, key)
        elif len(tk) >= 20 and tk in title_of_doi:
            key = title_of_doi[tk]
        elif url_key(r.get("url")):
            key = "url:" + url_key(r.get("url"))
        elif tk:
            key = "title:" + tk
        else:
            continue
        item = by_key.setdefault(key, {"found": defaultdict(list), "clusters": [], "sub_clusters": []})
        item["found"][src].append(i)
        for field in ("clusters", "sub_clusters"):
            for part in re.split(r"\s*;\s*|,\s+(?=[A-Z])", str(r.get(field) or "")):
                if part.strip() and part.strip() not in item[field]:
                    item[field].append(part.strip())
        for field, value in r.items():
            if field not in ("clusters", "sub_clusters") and value and not item.get(field):
                item[field] = value.strip() if isinstance(value, str) else value
    return by_key


def category(item) -> str:
    """Book, Article or Website / web resource. Without a DOI, only a document type or a PDF link makes an article:
    FORRT DB 2.0 calls blog posts and seminar pages "Reading" too."""
    kind, url = item.get("type", ""), str(item.get("url", "")).lower()
    if BOOK.search(kind):
        return "Book"
    if WEB.search(kind) and not ARTICLE.search(kind):
        return "Website / web resource"
    if item.get("doi") or DOCUMENT.search(kind) or url.split("?")[0].endswith(".pdf"):
        return "Article"
    return "Website / web resource" if url_key(url) or ARTICLE.search(kind) else "Other"


def open_access(dois, cache=Path("data/curation/unpaywall_oa.json")):
    """{doi: (is_oa, oa_status, oa_url, license, year)} from Unpaywall (UNPAYWALL_EMAIL in .env, as ingest/helpers.py),
    8 requests at a time; answers are kept in `cache`, so a rerun asks only for new DOIs. A DOI Unpaywall does not
    know (404) is stored as unknown; a failed request is not stored and is asked again next time."""
    from concurrent.futures import ThreadPoolExecutor

    from dotenv import load_dotenv

    load_dotenv()
    email = os.environ.get("UNPAYWALL_EMAIL", "")
    known = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}

    def ask(doi):
        url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                w = json.load(r)
        except urllib.error.HTTPError as e:
            return doi, [None, "", "", "", ""] if e.code == 404 else None
        except Exception:
            return doi, None
        loc = w.get("best_oa_location") or {}
        return doi, [w.get("is_oa"), w.get("oa_status") or "", loc.get("url_for_pdf") or loc.get("url") or "",
                     loc.get("license") or "", w.get("year") or ""]

    todo = sorted(d for d in dois if d not in known)
    if email and todo:
        with ThreadPoolExecutor(8) as pool:
            for doi, answer in pool.map(ask, todo):
                if answer is not None:
                    known[doi] = answer
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known), encoding="utf-8")
    return {d: tuple(v) for d, v in known.items()}


def index_kind(m, web_links) -> str:
    """How a document is in the index: its FORRT abstract card, a web page (curate web run), else full text."""
    if str(m.get("material_type", "")).startswith("FORRT abstract card"):
        return "abstract card"
    return "web page" if url_key(m.get("link_to_resource")) in web_links else "full text"


def last_tries():
    """key (DOI, link or title) -> (outcome, run folder, what it means) of the newest `./run curate` report."""
    out = {}
    for report in sorted(CURATION.glob("*/report.csv")):  # folder names start with YYMMDD: oldest first
        for r in csv.DictReader(open(report, encoding="utf-8")):
            for key in (normalize_doi(r.get("doi")), url_key(r.get("link_to_resource")), title_key(r.get("title"))):
                if key:
                    out[key] = (r["outcome"], report.parent.name, r.get("what_it_means", ""))
    return out


def have():
    """Index documents (by DOI, title and link, with how they are indexed) and PDFs on disk (by DOI, title, file)."""
    from config import settings

    web_links = {url_key(r["link_to_resource"]) for m in CURATION.glob("*/metadata.csv")
                 for r in csv.DictReader(open(m, encoding="utf-8")) if not r.get("doi")}
    nodes = json.loads((Path(settings.VECTOR_STORE) / "docstore.json").read_text(encoding="utf-8"))["docstore/data"]
    index, kinds = {}, {}
    for v in nodes.values():
        m = {k: (next(iter(x.values()), "") if isinstance(x, dict) else x) for k, x in v["__data__"]["metadata"].items()}
        if m.get("material_type") == "FORRT Glossary":
            continue
        key = normalize_doi(m.get("doi")) or normalize_doi(m.get("link_to_resource")) or title_key(m.get("title"))
        index.setdefault(key, m)
        kind = index_kind(m, web_links)
        for k in (key, url_key(m.get("link_to_resource"))):
            if k and (k not in kinds or INDEX_KINDS.index(kind) < INDEX_KINDS.index(kinds[k])):
                kinds[k] = kind
    index_titles = {title_key(m.get("title")): k for k, m in index.items() if len(title_key(m.get("title"))) >= 20}
    pdfs = {}
    for r in csv.DictReader(open("data/interim/cluster_pdf_metadata.csv", encoding="utf-8")):
        for k in (normalize_doi(r["doi"]), title_key(r["title"])):
            if k:
                pdfs.setdefault(k, (PDF_DIR / r["file"].strip()).as_posix())
    for r in csv.DictReader(open("docs/indexed_documents.csv", encoding="utf-8")):
        if r["pdf_path"]:
            for k in (normalize_doi(r["doi"]), title_key(r["title"])):
                if k:
                    pdfs.setdefault(k, r["pdf_path"])
    files = {f.lower(): os.path.join(d, f) for d, _, fs in os.walk(PDF_DIR) for f in fs}
    return index, index_titles, kinds, pdfs, files


def build():
    items = merge(records())
    index, index_titles, kinds, pdfs, files = have()
    tries = last_tries()
    oa = open_access({i["doi"] for i in items.values() if i.get("doi")})
    listed, rows = set(), []
    for it in items.values():
        doi, tk = it.get("doi", ""), title_key(it.get("title"))
        uk = url_key(it.get("url"))
        in_index = doi in index or tk in index_titles or uk in kinds
        kind = kinds.get(doi) or kinds.get(index_titles.get(tk)) or kinds.get(uk) or ("full text" if in_index else "")
        tried = tries.get(doi) or tries.get(uk) or tries.get(tk) or ("", "", "")
        listed.update({doi or tk, index_titles.get(tk)})
        pdf = pdfs.get(doi) or pdfs.get(tk) or files.get(str(it.get("pdf_file", "")).lower(), "")
        is_oa, status, oa_url, oa_licence, year = oa.get(doi, (None, "", "", "", ""))
        licence = it.get("licence") or oa_licence
        if is_oa is None and re.search(r"\bcc[- ]?(by|0)|public.?domain", licence, re.I):
            is_oa = True
        rows.append({
            "title": html.unescape(it.get("title", "")), "authors": it.get("authors", ""), "year": year, "doi": doi,
            "url": it.get("url", "") or (f"https://doi.org/{doi}" if doi else ""), "category": category(it),
            "type": it.get("type", ""), "clusters": "; ".join(it["clusters"]), "sub_clusters": "; ".join(it["sub_clusters"]),
            "language": it.get("language", ""), "licence": licence,
            "open_access": {True: "yes", False: "no"}.get(is_oa, "unknown" if doi or category(it) != "Website / web resource"
                                                         else "web page"), "oa_status": status, "oa_url": oa_url,
            "in_index": "yes" if in_index else "no", "pdf_on_disk": "yes" if pdf else "no",
            "pdf_file": pdf or it.get("pdf_file", ""),
            "found_in": "; ".join(f"{src} (row{'s' if len(n) > 1 else ''} {', '.join(map(str, n))})"
                                  for src, n in it["found"].items()),
            "times_listed": sum(len(n) for n in it["found"].values()), "lists": len(it["found"]),
            "excluded_in_source": "yes" if it.get("excluded") else "", "in_index_as": kind,
            "last_try": tried[0], "last_try_run": tried[1], "what_it_means": tried[2], "abstract": it.get("abstract", ""),
            "summary": it.get("summary", ""), "apa_reference": it.get("apa_reference", "")})
    df = pd.DataFrame(rows, columns=FIELDS).sort_values(["category", "title"], key=lambda s: s.str.lower())
    extra = pd.DataFrame([{"title": m.get("title", ""), "authors": m.get("creators", ""),
                           "doi": normalize_doi(m.get("doi")) or "", "url": m.get("link_to_resource", ""),
                           "type": m.get("material_type", ""), "licence": m.get("licence") or m.get("conditions_of_use", ""),
                           "oa_status": m.get("oa_status", ""), "clusters": m.get("FORRT_clusters", "")}
                          for k, m in index.items() if k not in listed]).sort_values("title", key=lambda s: s.str.lower())
    # an article or book with no full text yet: missing, or only its abstract card in the index
    need = df[df.in_index_as.isin(["", "abstract card"]) & (df.pdf_on_disk == "no") & df.category.isin(["Article", "Book"])
              & (df.excluded_in_source != "yes")]
    return {"All resources": df, "With DOI": df[df.doi != ""], "Without DOI": df[df.doi == ""],
            "Books": df[df.category == "Book"], "Websites": df[df.category == "Website / web resource"],
            "In index not in lists": extra, "Need a PDF": need}


def save(sheets):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheets["All resources"].to_csv(OUT.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    need = sheets["Need a PDF"].rename(columns={"url": "link_to_resource", "authors": "creators",
                                                "licence": "conditions_of_use", "type": "material_type"})
    need[["title", "doi", "link_to_resource", "creators", "conditions_of_use", "material_type", "year", "oa_url",
          "last_try", "what_it_means", "clusters"]].to_csv(CURATION / "forrt_need_pdf.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(OUT.with_suffix(".xlsx"), engine="openpyxl") as xl:
        for name, frame in sheets.items():
            frame.to_excel(xl, sheet_name=name, index=False)
            ws = xl.sheets[name]
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in list(col)[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    for name, frame in sheets.items():
        print(f"{name:24} {len(frame):5}")
    print(f"-> {OUT.with_suffix('.xlsx')} and {OUT.with_suffix('.csv')}")


if __name__ == "__main__":
    save(build())
