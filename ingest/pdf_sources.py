"""Find an open copy of a paper's PDF in several places (scripts/curate.py).

A lean version of FLoRA's multi-tier acquisition (github.com/forrtproject/flora-extractor,
shared/pdf_sources.py), with the sources that matter for FORRT's library, in this order:

  1. the row's own link, when it is a PDF          5. Semantic Scholar openAccessPdf
  2. arXiv and OSF preprints (from the DOI alone)  6. Europe PMC (PMC copy, rendered PDF)
  3. Unpaywall: every open-access location         7. the landing page's citation_pdf_url
     (needs UNPAYWALL_EMAIL; skipped without)         (the row's link, then doi.org)
  4. OpenAlex: every location it knows

candidates() lists (url, source, licence) without downloading; download() fetches one and keeps it
only when it is a real PDF of a plausible size (a landing page, a paywall or a captcha answers HTML).
Whether it is the RIGHT paper is checked after GROBID, on its title (title_matches, scripts/curate.py):
a server can answer the right URL with the wrong document, and a wrong document is worse than none.
The licence comes from Unpaywall/OpenAlex; a copy found without one keeps an empty licence, so the
bot cites it but shows no passage (references.passage_allowed).
"""

import os
import re
from typing import Iterator, Optional, Tuple
from urllib.parse import quote, urljoin

import httpx

EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")  # as ingest/helpers.py
MIN_PDF_BYTES = 5_000  # FLoRA's floor: smaller "PDFs" are error pages or covers
MAX_PDF_BYTES = 60_000_000
TITLE_MATCH = 0.6  # share of the title's words that must appear (FLoRA's _TITLE_MATCH_CLEAR)
OSF_PREPRINT = re.compile(r"^10\.\d{4,5}/osf\.io/([a-z0-9]+)(?:_v\d+)?$", re.I)
ARXIV = re.compile(r"^10\.48550/arxiv\.(\d{4}\.\d{4,5})$", re.I)
PDF_META = re.compile(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)', re.I)
WORD = re.compile(r"[^\W\d_]{3,}", re.U)


def client(transport: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    """transport: e.g. scripts.fetch_web_resources.PublicOnlyTransport, which curate uses (SSRF guard)."""
    agent = "JUST-OS curate (+https://github.com/forrtproject/just-os-chatbot" + (f"; mailto:{EMAIL}" if EMAIL else "") + ")"
    return httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": agent}, transport=transport)


def _json(http: httpx.Client, url: str, **params) -> dict:
    try:
        response = http.get(url, params=params or None)
        return response.json() if response.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {}


def candidates(http: httpx.Client, doi: str = "", link: str = "") -> Iterator[Tuple[str, str, str]]:
    """(url, source, licence) for every place a PDF may be, best first; duplicates removed. Lazy: the
    APIs are asked only while the caller wants more."""
    seen = set()

    def new(url):
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            return True
        return False

    if link and link.lower().split("?")[0].endswith(".pdf") and new(link):
        yield link, "row_link", ""
    if doi:
        if (m := ARXIV.match(doi)) and new(url := f"https://arxiv.org/pdf/{m.group(1)}"):
            yield url, "arxiv", "arxiv"
        # 10.17605 is OSF registrations: containers, not files
        if (m := OSF_PREPRINT.match(doi)) and not doi.startswith("10.17605") and new(url := f"https://osf.io/download/{m.group(1).lower()}/"):
            yield url, "osf", ""
        if EMAIL:
            for loc in _json(http, f"https://api.unpaywall.org/v2/{quote(doi)}", email=EMAIL).get("oa_locations") or []:
                if new(loc.get("url_for_pdf")):
                    yield loc["url_for_pdf"], "unpaywall", loc.get("license") or ""
        for loc in _json(http, f"https://api.openalex.org/works/doi:{quote(doi)}", select="locations").get("locations") or []:
            if new(loc.get("pdf_url")):
                yield loc["pdf_url"], "openalex", loc.get("license") or ""
        s2 = _json(http, f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi)}", fields="openAccessPdf")
        if new(url := (s2.get("openAccessPdf") or {}).get("url")):
            yield url, "semanticscholar", ""
        epmc = _json(http, "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                     query=f'DOI:"{doi}"', format="json", resultType="lite", pageSize=1)
        for item in (epmc.get("resultList") or {}).get("result") or []:
            if item.get("pmcid") and new(url := f"https://europepmc.org/articles/{item['pmcid']}?pdf=render"):
                yield url, "europepmc", ""
    for page in (link, f"https://doi.org/{doi}" if doi else ""):
        for url in landing_pdf_urls(http, page):
            if new(url):
                yield url, "landing_page", ""


def landing_pdf_urls(http: httpx.Client, page: str) -> list:
    """The PDF a publisher page declares (citation_pdf_url, which Google Scholar also reads)."""
    if not page or not page.startswith("http"):
        return []
    try:
        response = http.get(page)
    except httpx.HTTPError:
        return []
    if "html" not in response.headers.get("content-type", ""):
        return []
    return [urljoin(str(response.url), m) for m in PDF_META.findall(response.text[:300_000])]


def download(http: httpx.Client, url: str) -> Optional[bytes]:
    """The PDF at url, or None when the answer is not a PDF of a plausible size."""
    try:
        with http.stream("GET", url) as response:
            if response.status_code != 200:
                return None
            content = b""
            for part in response.iter_bytes():
                content += part
                if len(content) > MAX_PDF_BYTES:
                    return None
    except httpx.HTTPError:
        return None
    return content if content.startswith(b"%PDF") and len(content) >= MIN_PDF_BYTES else None


def title_matches(expected: str, found_text: str) -> bool:
    """At least TITLE_MATCH of the expected title's words occur in found_text (GROBID's title and the
    start of the text); True when there is no title to check against."""
    words = {w.lower() for w in WORD.findall(expected or "")}
    if not words:
        return True
    found = {w.lower() for w in WORD.findall(found_text or "")}
    return len(words & found) / len(words) >= TITLE_MATCH


def lookup_title(http: httpx.Client, doi: str) -> str:
    """A DOI's title from OpenAlex, for rows (recommendations) that give only a DOI."""
    return (_json(http, f"https://api.openalex.org/works/doi:{quote(doi)}", select="title").get("title") or "").strip()
