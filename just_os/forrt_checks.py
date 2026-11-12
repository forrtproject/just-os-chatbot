"""Rules every FORRT-page answer must follow, enforced in code (the answer model is not trusted to).

- links:     a link or email must appear in the pages the model read; others are removed (the words stay)
- citations: 【1】 -> [1]; numbers that point to no page are removed
- dates:     "upcoming" next to a date before today is flagged (ForrtPages then asks for one rewrite)
- language:  English answer to a non-English question (or the reverse) is flagged (same)
Measured on 226 simulated questions (docs/evaluation.md): without these rules Llama 3.1 8B answered
non-English questions in English, invented forrt.org links and called past events upcoming.
"""

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from just_os import messages as msg

URL_IN_TEXT = re.compile(r"https?://[^\s)\]>\"'`]+")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>")
BARE_URL = re.compile(r"(?<![(<\w/])https?://[^\s)\]>\"'`]+")
UPCOMING = re.compile(r"upcoming|coming up|will (take place|be held|happen)|register now|save the date|"
                      r"is open for registration|bevorstehend|kommende|próxim|aankomend|em breve|即将", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}


def language_name(code: Optional[str]) -> str:
    """'nl' -> 'Dutch'; unknown -> 'the language of the question'."""
    if not code:
        return "English"
    try:
        from lingua import IsoCode639_1, Language
        return Language.from_iso_code_639_1(getattr(IsoCode639_1, code.upper())).name.title()
    except Exception:
        return "the language of the question"


def wrong_language(answer: str, question_code: Optional[str]) -> Optional[str]:
    """Name of the answer's language when it is English for a non-English question, or the reverse.
    Other mismatches (Dutch vs German...) are too noisy to detect on short answers."""
    text = URL_IN_TEXT.sub(" ", re.sub(r"\[[^\]]*\]\([^)]*\)", " ", answer))
    if len(text.split()) < 12:
        return None
    got = msg.detect_language(text)
    asked = question_code or "en"
    if got and got != asked and "en" in (got, asked):
        return language_name(got)
    return None


# ---------- links ----------

def clean_url(url: str) -> str:
    url = re.sub(r"\\([_*~#\[\]()])", r"\1", url.strip())
    return url.rstrip(".,;:!?*'\"")


def url_key(url: str) -> str:
    url = clean_url(url)
    if url.lower().startswith("mailto:"):
        return url.lower()
    p = urlparse(url if "://" in url else "https://" + url)
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    return f"{host}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def allowed_keys(pages: Iterable[Dict[str, Any]]) -> Set[str]:
    keys = {url_key("https://forrt.org/")}
    for p in pages:
        keys.add(url_key(p["url"]))
        text = p.get("excerpt", "")
        keys |= {url_key(u) for u in URL_IN_TEXT.findall(text)}
        keys |= {f"mailto:{e.lower()}" for e in EMAIL.findall(text)}
    return keys | {k.split("?")[0] for k in keys}


def strip_unsupported_links(text: str, pages: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    keys = allowed_keys(pages)
    removed: List[str] = []
    kept: List[str] = []

    def ok(url: str) -> bool:
        k = url_key(url)
        return k in keys or k.split("?")[0] in keys

    def md(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if not url.lower().startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        if not ok(url):
            removed.append(clean_url(url))
            return "" if label.lower().startswith(("http", "www.")) else label
        kept.append(f"[{label}]({clean_url(url)})")
        return f"\x00{len(kept) - 1}\x00"

    def auto(m: re.Match) -> str:
        if not ok(m.group(1)):
            removed.append(clean_url(m.group(1)))
            return ""
        kept.append(f"<{clean_url(m.group(1))}>")
        return f"\x00{len(kept) - 1}\x00"

    def bare(m: re.Match) -> str:
        if not ok(m.group(0)):
            removed.append(clean_url(m.group(0)))
            return ""
        return clean_url(m.group(0))

    text = MD_LINK.sub(md, text)
    text = AUTOLINK.sub(auto, text)
    text = BARE_URL.sub(bare, text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    return re.sub(r"\(\s*\)|\[\s*\]", "", text), removed


# ---------- citations ----------

def clean_citations(text: str, n_pages: int) -> str:
    text = re.sub(r"【(\d+)(?:†[^】]*)?】", r"[\1]", text)
    text = re.sub(r"\s*\[(?:no|without|not)\b[^\]\n]{0,40}\b(?:page|citation|source|number)s?\b[^\]\n]{0,20}\]", "", text, flags=re.I)  # "[no specific page number]"
    return re.sub(r"\[(\d+)\](?!\()", lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_pages else "", text)


# ---------- dates ----------

def dates_in(text: str) -> List[date]:
    found: List[date] = []
    month = "(" + "|".join(MONTHS) + r")"
    patterns = [
        (rf"(\d{{1,2}})(?:\s*[–-]\s*\d{{1,2}})?\s+{month},?\s+(\d{{4}})",
         lambda m: (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))),
        (rf"{month}\s+(\d{{1,2}})(?:\s*[–-]\s*\d{{1,2}})?,?\s+(\d{{4}})",
         lambda m: (int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))),
        (r"(\d{4})-(\d{2})-(\d{2})", lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    ]
    for pattern, parts in patterns:
        for m in re.finditer(pattern, text, re.I):
            try:
                found.append(date(*parts(m)))
            except ValueError:
                pass
    return found


def past_events_called_upcoming(text: str, today: date) -> List[str]:
    """Sentences that say 'upcoming' (or similar) next to a date before today."""
    return [s.strip()[:160] for s in re.split(r"(?<=[.!?])\s+|\n+", text)
            if UPCOMING.search(s) and any(d < today for d in dates_in(s))]
