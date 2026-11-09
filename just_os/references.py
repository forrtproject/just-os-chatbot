"""Small pure helpers for references: DOIs, links, licences, publication years.

No heavy imports, so ingestion scripts can use them too.
"""

import csv
import re
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

# A DOI is "10.<registrant>/<suffix>"; the suffix may contain almost anything
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
TRAILING = ".,;:'\"!?"
PAIRS = {")": "(", "]": "["}

# CC BY, CC0 and public domain allow showing a passage; NC/ND variants do not (F4)
OPEN_LICENCE = re.compile(
    r"\bcc[\s-]?0\b|\bcc[\s-]?zero\b|public domain|\bcc[\s-]?by\b|creative commons attribution",
    re.I,
)
RESTRICTED = re.compile(r"\bnc\b|\bnd\b|non-?commercial|no-?deriv", re.I)


def plain_metadata(metadata: Dict) -> Dict:
    """Unwrap {"<doi_hash>": value} values: 10 documents of the current index were stored
    that way (issue #24, fixed in scripts/embed.py for new builds)."""
    return {
        key: next(iter(value.values()), None) if isinstance(value, dict) else value
        for key, value in metadata.items()
    }


def short_authors(creators: Optional[str]) -> str:
    """'A, B, C' → 'A et al.'; one or two authors stay as they are."""
    creators = " ".join(str(creators or "").split())
    if creators.count(",") + creators.count("&") + creators.count(" and ") <= 1:
        return creators
    return re.split(r",|&| and ", creators)[0].strip() + " et al."


def normalize_doi(text: Optional[str]) -> Optional[str]:
    """Return the bare, lower-case DOI in a string (URL, "doi:" prefix, ...) or None."""
    if not text:
        return None
    match = DOI_PATTERN.search(urllib.parse.unquote(str(text)))
    if not match:
        return None
    doi = match.group(0)
    # Strip trailing punctuation and unbalanced closing brackets, e.g. "(see 10.1/x)."
    while doi:
        last = doi[-1]
        if last in TRAILING:
            doi = doi[:-1]
        elif last in PAIRS and doi.count(last) > doi.count(PAIRS[last]):
            doi = doi[:-1]
        else:
            break
    return doi.lower()


def safe_url(url: Optional[str]) -> Optional[str]:
    """Only http(s) links may reach the page (no javascript: etc.)."""
    url = (url or "").strip()
    return url if re.match(r"https?://", url, re.I) else None


def _doi(metadata: Dict) -> Optional[str]:
    return normalize_doi(metadata.get("doi")) or normalize_doi(metadata.get("link_to_resource"))


def reference_url(metadata: Dict) -> Optional[str]:
    """https://doi.org/<doi> when there is a DOI, else the resource link if it is http(s)."""
    doi = _doi(metadata)
    if doi:
        return f"https://doi.org/{urllib.parse.quote(doi, safe='/:;()._-')}"
    return safe_url(metadata.get("link_to_resource"))


def document_key(metadata: Dict) -> str:
    """One key per paper, so chunks of the same paper share one reference number."""
    return _doi(metadata) or re.sub(r"[^a-z0-9]", "", str(metadata.get("title", "")).lower())


def passage_allowed(conditions_of_use: Optional[str]) -> bool:
    """True for CC BY (and SA), CC0 and public domain; False for NC/ND and unknown licences."""
    text = str(conditions_of_use or "")
    return bool(OPEN_LICENCE.search(text)) and not RESTRICTED.search(text)


def load_publication_years(path: Optional[str]) -> Dict[str, str]:
    """Read a doi,year CSV (made by scripts/get_pub_years.py). Missing file → empty dict."""
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {
            doi: row["year"]
            for row in csv.DictReader(f)
            if (doi := normalize_doi(row.get("doi"))) and row.get("year")
        }


def publication_year(metadata: Dict, years: Dict[str, str]) -> str:
    """Publication year from the metadata or the lookup table; never the form time stamp."""
    if metadata.get("pub_year"):
        return str(metadata["pub_year"])
    doi = _doi(metadata)
    return years.get(doi, "n.d.") if doi else "n.d."
