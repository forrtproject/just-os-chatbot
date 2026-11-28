"""Small pure helpers for references: DOIs, links, licences, publication years.

No heavy imports, so ingestion scripts can use them too.
"""

import csv
import re
import urllib.parse
from pathlib import Path
from typing import Dict, Optional, Union

# A DOI is "10.<registrant>/<suffix>"; the suffix may contain almost anything
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
TRAILING = ".,;:'\"!?"
PAIRS = {")": "(", "]": "["}

# CC BY (and SA), CC0 and public domain allow showing a passage (F4). Matched on licence_words(): lower case,
# separators as spaces, so "cc-by", "CC BY" and "Creative Commons Attribution" read alike
OPEN_LICENCE = re.compile(
    r"\bcc ?0\b|\bcc zero\b|\bpublic domain\b|\bcc by\b|\bccby\b|creative commons (attribution|zero|public domain)"
)
# Any of these in any licence field vetoes the quote: NC/ND variants, negations ("Not licensed under CC BY", "not open
# access", "I don't see any of these"), closed access and reserved rights
RESTRICTED = re.compile(
    r"\bnc\b|\bnd\b|non ?commercial|no ?deriv|\bnot\b|n['\u2019]t\b|\bclosed\b|\brights reserved\b|copyright|\u00a9"
)
# Free to read is not free to quote: the label of a FORRT cluster PDF never makes a passage quotable, and neither does
# the OpenAlex licence recorded next to it (scripts/convert_cluster_pdfs.py), which belongs to one open-access copy
# (best_oa_location), not necessarily to the PDF in FORRT's cluster folder
CLUSTER_PDF = re.compile(r"forrt cluster pdf")
GLOSSARY_TYPE = "FORRT Glossary"  # material_type of the glossary documents (scripts/build_glossary.py)

# Reference-list chunk: many "(2013)", "2013.", "et al.", "12(3)" or "123-130." per 100 words (eval/topic_map,
# SKIP_REFERENCE_CHUNKS); 14% of the index's chunks are reference lists or near-empty (docs/evaluation.md 3.27)
CITATION = re.compile(r"\(\d{4}[a-z]?\)|\b(19|20)\d{2}[a-z]?\.|et al\.|\b\d+\(\d+\)|\b\d{1,4}[–-]\d{1,4}\.")
CITATIONS_PER_100_WORDS = 4
MIN_WORDS = 25


def citation_density(text: str) -> float:
    """Citation patterns per 100 words."""
    return len(CITATION.findall(text)) / max(len(text.split()), 1) * 100


def is_reference_chunk(text: str) -> bool:
    """A reference list, author block or near-empty chunk."""
    return citation_density(text) > CITATIONS_PER_100_WORDS or len(text.split()) < MIN_WORDS


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


def normalize_url(url: Optional[str]) -> str:
    """A link for comparing: scheme and host in lower case, trailing slash stripped only from path; path, query and
    fragment keep their case. Malformed bracketed URLs fall back cleanly without raising. "" for no link."""
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url.rstrip("/")
    if not parts.scheme or not parts.netloc:
        return url.rstrip("/")
    path = parts.path.rstrip("/")
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))


def document_key(metadata: Dict) -> str:
    """One key per paper, so chunks of the same paper share one reference number: the DOI, else the title, else (a
    web page or recommendation with neither) "url:" and its normalized link, so two untitled links stay apart."""
    title = re.sub(r"[^a-z0-9]", "", str(metadata.get("title") or "").lower())
    if doi := _doi(metadata):
        return doi
    if title:
        return title
    link = normalize_url(metadata.get("link_to_resource"))
    return f"url:{link}" if link else ""


def paper_key(metadata: Dict) -> str:
    """One reference number per paper in an answer: the title, so a preprint without DOI
    and its journal version (same title) share a number; document_key without a title."""
    title = re.sub(r"[^a-z0-9]", "", str(metadata.get("title") or "").lower())
    return title or document_key(metadata)


def licence_words(text: Optional[str]) -> str:
    """A licence text for matching: lower case, with ASCII and Unicode hyphens/dashes, slashes, commas and brackets as spaces."""
    return " ".join(re.sub(r"[-_\u2010-\u2015\u2212\u00ad/,;:()\[\].]+", " ", str(text or "").lower()).split())


def licence_vetoes(text: Optional[str]) -> bool:
    """The text restricts or denies reuse (NC, ND, a negation, closed, reserved rights) or is a cluster PDF label."""
    words = licence_words(text)
    return bool(RESTRICTED.search(words) or CLUSTER_PDF.search(words))


def passage_allowed(conditions_of_use: Union[str, Dict, None]) -> bool:
    """True for CC BY (and SA), CC0 and public domain; False for NC/ND, negated, closed or unknown licences and the
    FORRT cluster PDF label. A metadata dict is checked with metadata_passage_allowed."""
    if isinstance(conditions_of_use, dict):
        return metadata_passage_allowed(conditions_of_use)
    return bool(OPEN_LICENCE.search(licence_words(conditions_of_use))) and not licence_vetoes(conditions_of_use)


def metadata_passage_allowed(meta: Dict) -> bool:
    """A chunk's passage may be shown only when its conditions_of_use is itself an open licence (passage_allowed).
    licence and oa_status can only veto: closed access, NC/ND or a negation in either field denies the quote, but an
    open `licence` never allows one, since convert_cluster_pdfs records there the licence of an OpenAlex open-access
    copy, not of the cluster PDF in the index. So a cluster PDF shows no passage until its conditions_of_use is set
    to a licence checked for that copy."""
    meta = plain_metadata(meta or {})
    if str(meta.get("oa_status") or "").strip().lower() == "closed":
        return False
    if any(licence_vetoes(meta.get(key)) for key in ("licence", "conditions_of_use")):
        return False
    return passage_allowed(str(meta.get("conditions_of_use") or ""))


SNIPPET_MAX = 300  # characters of the quote under a source
WORD = re.compile(r"[a-z0-9]{3,}")


MIN_LETTER_SHARE = 0.75  # below this a "sentence" is mostly numbers, links or table cells


def clean_markdown(text: str) -> str:
    """Plain text from converted-PDF Markdown: [text](link) -> text, no "( page-7-27)"
    anchors, no backslash escapes, no #*_|>` marks, single spaces."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # Markdown links keep their words
    text = re.sub(r"\(\s*#?page-[\d-]+\s*\)", "", text)  # page anchors from the PDF converter
    text = re.sub(r"\\([\\()\[\]*_#.-])", r"\1", text)
    return re.sub(r"[#*_|>`]+|\s+", " ", text).strip()


def readable(sentence: str) -> bool:
    """A full sentence of words: starts with a capital letter or a digit (not mid-sentence)
    and at least MIN_LETTER_SHARE of its non-space characters are letters."""
    chars = [c for c in sentence if not c.isspace()]
    first = sentence[:1]
    return (
        len(sentence) >= 40
        and (first.isdigit() or (first.isalpha() and not first.islower()))
        and sum(c.isalpha() for c in chars) >= MIN_LETTER_SHARE * len(chars)
    )


def best_snippet(claim: str, passage: str) -> str:
    """The readable sentence of the passage that shares the most words with the claim
    citing it, cut at SNIPPET_MAX. Empty when no sentence is readable: a broken quote
    (reference lists, tables, link debris) is withheld rather than shown."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", clean_markdown(passage)) if readable(s)]
    if not sentences:
        return ""
    words = set(WORD.findall(claim.lower()))
    best = max(sentences, key=lambda s: len(words & set(WORD.findall(s.lower()))))
    return best if len(best) <= SNIPPET_MAX else best[:SNIPPET_MAX].rsplit(" ", 1)[0] + " …"


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
