"""FORRT page router (issues #15, #34): answer questions about FORRT from forrt.org's own pages.

    question -> embed (the app's bge-m3) -> top FORRT_TOP_K pages of the page index
             -> decision model (FORRT_SELECT_MODEL, e.g. cloudflare/clef) scores each page yes/no -> 1-4 pages
             -> fetch those pages live from forrt.org (in-memory cache FORRT_CACHE_TTL s; no stored copies)
             -> answer model with the page excerpts -> checks in code (forrt_checks) -> Markdown + sources

The page index (FORRT_PAGES_DIR = vector_data/forrt_pages/, built by scripts/build_forrt_pages.py) holds
LINKS AND SHORT DESCRIPTIONS ONLY, NOT PAGE CONTENT: index.json has one record per page (its url, title,
date and an LLM-written summary / "use when" / example questions / key links, used to pick the page) and
vectors.npy one vector per record (of the description). The content of the chosen pages is always fetched
live from forrt.org; it is never stored. Scope: forrt.org menu pages, announcements, newsletters and FORRT
project sites; not the curated resources, clusters or glossary terms (open-science content).
"""

import json
import logging
import re
from collections import Counter
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import numpy as np
from bs4 import BeautifulSoup, NavigableString, Tag

from just_os import forrt_checks as checks
from just_os import messages as msg
from just_os.decisions import DecisionClient
from just_os import trace

logger = logging.getLogger(__name__)

STOP = set("""the and for with that this what which who how are was were can could should would does did have has had
you your our from about into there their they them where when why will not but any all some more most other such
only own same than too very just also its it's i'm forrt""".split())
TIME_WORDS = re.compile(
    r"\b(events?|upcoming|latest|recent(ly)?|news|new|newest|current(ly)?|now|today|this (week|month|year)|next|soon|"
    r"conferences?|workshops?|webinars?|hackathons?|deadlines?|calls?|announce\w*|newsletters?|opportunit\w*|"
    r"positions?|vacanc\w*|jobs?|happening|schedule|veranstaltung\w*|aktuell\w*|neu\w*|nieuws|eventos?|noticias)\b", re.I)
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "form", "iframe", "button"]
NOISE_SELECTORS = [".navbar", ".page-footer", ".modal", ".docs-sidebar", ".search-results", "#search", ".d-none", ".sr-only"]

ANSWER_SYSTEM = """You are the FORRT assistant on forrt.org. Today's date is {today}.
Answer the visitor's question using ONLY the numbered page excerpts. Rules:
1. Language: write the whole answer in {language}.
2. Citations: after each fact, put the number of the page it comes from in square brackets, e.g. [1] or [2][3].
   Every paragraph and every bullet needs at least one citation.
3. Links: give the links the visitor needs (sign-up forms, Slack, project pages) as Markdown links, copied exactly
   from the excerpts. Never make up a URL or an email address.
4. Dates: today is {today}. Anything dated before today is in the past: say it took place, never call it
   upcoming. If the excerpts mention nothing upcoming, say so.
5. If any excerpt is relevant, answer with what it says, even if it is only part of the answer. Say you could not
   find the information only when no excerpt is relevant.
6. Be concise and practical. When a page lists several relevant items (teams, projects, references), include them.
Never invent names, dates, numbers, emails or links."""
ANSWER_USER = """Page excerpts:

{context}

Question: {question}

Reminder: answer in {language}, cite page numbers like [1], today is {today}, use only links from the excerpts."""
REWRITE_USER = """{original}

Your draft answer:
{draft}

The draft has these problems: {problems}
Return only the corrected answer, following all rules."""


def as_list(value: Any) -> List[str]:
    return [v.strip() for v in (value.split(",") if isinstance(value, str) else value or []) if v.strip()]


def tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOP}


# ---------- HTML -> Markdown (BeautifulSoup only) ----------

def _md(node, url: str) -> str:
    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    if not isinstance(node, Tag):
        return ""
    inner = "".join(_md(child, url) for child in node.children)
    name = node.name
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return f"\n\n{'#' * int(name[1])} {inner.strip()}\n\n"
    if name in ("p", "div", "section", "article", "main", "blockquote", "table", "ul", "ol", "dl"):
        return f"\n\n{inner.strip()}\n\n"
    if name == "li":
        return f"\n- {inner.strip()}"
    if name in ("tr",):
        return f"\n{inner.strip()}"
    if name in ("td", "th"):
        return f" {inner.strip()} |"
    if name == "br":
        return "\n"
    if name in ("strong", "b"):
        return f"**{inner.strip()}**" if inner.strip() else ""
    if name == "a" and node.get("href"):
        href = urljoin(url, node["href"].strip())
        text = inner.strip() or node.get("title", "")
        return f"[{text}]({href})" if text and href.startswith(("http", "mailto:")) else text
    if name == "img":
        return ""
    return inner


def refresh_target(html: str, url: str) -> Optional[str]:
    """Where a meta-refresh stub sends the browser (forrt.org/glossary/ → /glossary/english/), else None."""
    m = re.search(r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]*content=[\"'][^\"']*url=([^\"'>\s]+)", html[:3000], re.I)
    return urljoin(url, m.group(1)) if m else None


def extract(html: str, url: str) -> Dict[str, Any]:
    """Title and Markdown of a forrt.org page (menus, footers and scripts removed)."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    title = re.sub(r"\s*[|\-–·•]\s*FORRT.*$", "", title).strip() or url
    meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    meta = " ".join((meta_tag.get("content") or "").split()) if meta_tag else ""
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()
    body = soup.select_one("main") or soup.body or soup
    markdown = re.sub(r"[ \t]+\n", "\n", _md(body, url))
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    if len(markdown) < 300 and meta and meta not in markdown:  # JavaScript apps: keep their meta description
        markdown = f"# {title}\n\n{meta}\n\n{markdown}".strip()
    return {"title": title, "markdown": markdown}


def trim(markdown: str, question: str, max_chars: int) -> str:
    """Keep the parts of a long page that best match the question, in page order.

    The page is cut into paragraphs; a paragraph longer than 1,500 characters (a long list, such as
    /contributors/ with 200,000 characters in one block) is cut further into ~500-character pieces of
    whole lines. Pieces are scored by the question words they contain, rare words counting more
    ("Rohan" appears once, "contributed" in every entry). The best pieces and the piece after each
    (a list entry often continues there) are kept, then the rest in page order while space is left.
    """
    if len(markdown) <= max_chars:
        return markdown
    pieces: List[str] = []
    for block in re.split(r"\n\s*\n|\n(?=#)", markdown):
        if not block.strip():
            continue
        if len(block) <= 1500:
            pieces.append(block)
            continue
        window: List[str] = []
        for line in block.split("\n"):
            window.append(line)
            if sum(len(x) + 1 for x in window) >= 500:
                pieces.append("\n".join(window))
                window = []
        if window:
            pieces.append("\n".join(window))
    q = tokens(question)
    piece_tokens = [tokens(p) & q for p in pieces]
    df = Counter(t for ts in piece_tokens for t in ts)
    score = [sum(1.0 / df[t] for t in ts) for ts in piece_tokens]
    keep, used = {0}, len(pieces[0])
    for i in sorted(range(1, len(pieces)), key=lambda i: -score[i]):
        for j in ((i, i + 1) if score[i] > 0 else (i,)):
            if j < len(pieces) and j not in keep and used + len(pieces[j]) <= max_chars:
                keep.add(j)
                used += len(pieces[j])
    out, last = [], -1
    for i in sorted(keep):
        if last >= 0 and i != last + 1:
            out.append("[…]")
        out.append(pieces[i])
        last = i
    return "\n\n".join(out)


class ForrtPages:
    def __init__(self, config: Dict[str, Any], embed_model, client_manager, decisions: Optional[DecisionClient] = None):
        self.config = config
        self.dir = Path(config["FORRT_PAGES_DIR"])
        self.records: List[Dict[str, Any]] = json.loads((self.dir / "index.json").read_text(encoding="utf-8"))
        vectors = np.load(self.dir / "vectors.npy").astype(np.float32)
        self.vectors = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
        self.lex = [tokens(" ".join([r["title"], r.get("use_when", ""), " ".join(r.get("example_questions", []))]))
                    for r in self.records]
        self.news_dates = [date.fromisoformat(r["date"]) if r.get("date") and (
            r.get("section") in ("post", "newsletters") or r.get("page_kind") == "event_or_news") else None
            for r in self.records]
        self.embed_model = embed_model
        self.client_manager = client_manager
        self.decisions = decisions or DecisionClient(config)
        self.listing_urls = as_list(config.get("FORRT_LISTING_URLS", "https://forrt.org/post/"))
        self.allowed_domains = as_list(config.get("FORRT_FETCH_DOMAINS", "forrt.org"))
        self.http = httpx.Client(timeout=config.get("FORRT_FETCH_TIMEOUT", 6), follow_redirects=True,
                                 headers={"User-Agent": "JUST-OS chatbot (forrt.org page reader)"})
        self.cache: Dict[str, Any] = {}
        self.lock = threading.Lock()
        logger.info(f"FORRT pages: {len(self.records)} pages from {self.dir}")

    # 1. candidates
    @trace.step("page search", lambda result, *a, **k: {"pages": [
        {"title": c["rec"]["title"], "url": c["rec"]["url"], "score": round(c["score"], 4)} for c in result]})
    def retrieve(self, question: str) -> List[Dict[str, Any]]:
        qv = np.asarray(self.embed_model.get_query_embedding(question), dtype=np.float32)
        qv = qv / max(float(np.linalg.norm(qv)), 1e-12)
        scores = self.vectors @ qv
        q = tokens(question)
        if q:
            scores = scores + self.config.get("FORRT_LEXICAL_WEIGHT", 0.1) * np.array([len(q & t) / len(q) for t in self.lex])
        time_question = bool(TIME_WORDS.search(question))
        if time_question:  # recent news first: the boost halves every FORRT_RECENCY_HALF_LIFE days
            today, half = date.today(), max(self.config.get("FORRT_RECENCY_HALF_LIFE", 90), 1)
            scores = scores + np.array([self.config.get("FORRT_RECENCY_WEIGHT", 0.1) * 0.5 ** (max((today - d).days, 0) / half)
                                        if d else 0.0 for d in self.news_dates])
        top = list(np.argsort(-scores)[: self.config.get("FORRT_TOP_K", 12)])
        if time_question:  # the live news listing always shows the newest posts: the selector must see it
            index_of = {r["url"]: i for i, r in enumerate(self.records)}
            for slot, url in enumerate(u for u in self.listing_urls if index_of.get(u) is not None and index_of[u] not in top):
                top[-1 - slot] = index_of[url]
        return [{"rec": self.records[i], "score": float(scores[i])} for i in top]

    # 2. selection (decision model; falls back to the top search results)
    def select(self, question: str, candidates: List[Dict[str, Any]], strict: bool = False) -> List[Dict[str, Any]]:
        """strict (pages next to the papers): only a clear yes counts; no fallback when unsure or failed."""
        max_pages = self.config.get("FORRT_MAX_PAGES", 4)
        questions = {}
        for n, c in enumerate(candidates, 1):
            r = c["rec"]
            dated = f", published {r['date']}" if r.get("date") and r.get("section") == "post" else ""
            page = f"{r['title']} ({r['url']}{dated}). {r.get('summary', '')} Use when: {r.get('use_when', '')}"[:700]
            questions[f"page_{n}"] = {"type": "noul",
                                      "instructions": f"Would reading this forrt.org page help answer the user's question? Page: {page}"}
        answers, info = self.decisions.decide(self.config.get("FORRT_SELECT_MODEL", "cloudflare/clef"),
                                              f"Today's date: {date.today().isoformat()}\nUser question: {question}", questions)
        if answers is None:
            chosen = [] if strict else list(range(min(max_pages, len(candidates))))
        else:
            probs = []
            for n in range(1, len(candidates) + 1):
                a = answers.get(f"page_{n}")
                p = a.get("noul") if isinstance(a, dict) else a
                probs.append(float(p) if isinstance(p, (int, float)) else 0.0)
            order = sorted(range(len(probs)), key=lambda i: -probs[i])
            threshold, floor = self.config.get("FORRT_DECISION_THRESHOLD", 0.7), self.config.get("FORRT_DECISION_FLOOR", 0.2)
            chosen = [i for i in order if probs[i] >= threshold][:max_pages]
            if not chosen and order and probs[order[0]] >= floor and not strict:
                # unsure (e.g. "what is zotero"): keep the plausible pages and the top search result
                chosen = [i for i in order if probs[i] >= floor][: min(3, max_pages)]
                if 0 not in chosen:
                    chosen = chosen[: min(3, max_pages) - 1] + [0]
        if TIME_WORDS.search(question) and not strict:
            for i, c in enumerate(candidates):
                if c["rec"]["url"] in self.listing_urls and i not in chosen:
                    chosen = [i] + chosen[: max_pages - 1]
        return [candidates[i]["rec"] for i in chosen]

    # 2b. pages next to the papers (FORRT_IN_PAPERS): a papers answer can also read forrt.org pages
    def extra_sources(self, question: str, min_score: Optional[float]) -> List[Dict[str, Any]]:
        """[{title, url, date, text}] for the papers route: pages with a search score >= min_score (None: no
        floor, for the `both` route), then a clear yes from the decision model (strict select), at most
        FORRT_IN_PAPERS_MAX_PAGES, each cut to the FORRT_IN_PAPERS_MAX_CHARS that best match the question.
        No page close enough: no decision call."""
        candidates = [c for c in self.retrieve(question) if min_score is None or c["score"] >= min_score]
        if not candidates:
            return []
        chosen = self.select(question, candidates, strict=True)[: self.config.get("FORRT_IN_PAPERS_MAX_PAGES", 2)]
        found = []
        for rec in chosen:
            markdown = self.fetch(rec["url"])["markdown"]
            if markdown:
                found.append({"title": rec["title"], "url": rec["url"], "date": rec.get("date"),
                              "text": trim(markdown, question, self.config.get("FORRT_IN_PAPERS_MAX_CHARS", 3000))})
        return found

    # 3. fetch: always live from forrt.org; an in-memory cache of FORRT_CACHE_TTL seconds, no files
    def fetch(self, url: str) -> Dict[str, Any]:
        host = urlparse(url).netloc
        if not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
            return {"markdown": "", "status": "failed"}
        with self.lock:
            hit = self.cache.get(url)
        if hit and time.time() - hit[0] < self.config.get("FORRT_CACHE_TTL", 3600):
            return {"markdown": hit[1], "status": "cache"}
        try:
            resp = self.http.get(url)
            resp.raise_for_status()
            target = refresh_target(resp.text, url)
            if target and urlparse(target).netloc == host:  # a "this page has moved" stub: read the real page
                resp = self.http.get(target)
                resp.raise_for_status()
            markdown = extract(resp.text, target or url)["markdown"]
            with self.lock:
                self.cache[url] = (time.time(), markdown)
            return {"markdown": markdown, "status": "live"}
        except Exception as exc:
            if hit:  # forrt.org unreachable: an expired cached copy is better than nothing
                logger.warning(f"FORRT page fetch failed for {url}: {exc.__class__.__name__}; using the expired cache")
                return {"markdown": hit[1], "status": "cache (expired)"}
            logger.warning(f"FORRT page fetch failed for {url}: {exc.__class__.__name__}; page skipped")
            return {"markdown": "", "status": "failed"}

    # 4. answer
    def _chat(self, model: str, system: str, user: str) -> str:
        completion = self.client_manager.create_chat_completion(
            model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0, max_tokens=self.config.get("FORRT_MAX_ANSWER_TOKENS", 1500))
        return (completion.choices[0].message.content or "").strip() if completion else ""

    @trace.step("FORRT pages", lambda result, *a, **k: {k2: v for k2, v in (result.get("trace") or {}).items()
                                                         if k2 in ("fetched", "language", "rewrite", "removed_links")})
    def answer(self, question: str, model: Optional[str] = None, language_text: Optional[str] = None) -> Dict[str, Any]:
        """{"text": Markdown answer citing [n], "sources": [{n, title, url}], "trace": {...}}; text is None on error.
        language_text: what the user typed (a rephrased follow-up may be in another language)."""
        start = time.perf_counter()
        language_code = checks.question_language(language_text or question)
        language = checks.language_name(language_code)
        candidates = self.retrieve(question)
        chosen = self.select(question, candidates)
        with ThreadPoolExecutor(max(1, len(chosen))) as pool:
            fetched = list(pool.map(lambda r: {**self.fetch(r["url"]), "rec": r}, chosen))
        pages = []
        for f in fetched:
            excerpt = trim(f["markdown"], question, self.config.get("FORRT_MAX_CHARS_PER_PAGE", 12000))
            # a moved page (forrt.org/glossary/) and its new address give the same text: read it once
            if excerpt.strip() and all(excerpt != p["excerpt"] for p in pages):
                pages.append({"n": len(pages) + 1, "url": f["rec"]["url"], "title": f["rec"]["title"],
                              "date": f["rec"].get("date"), "excerpt": excerpt, "status": f["status"]})
        trace = {"candidates": [c["rec"]["url"] for c in candidates], "selected": [r["url"] for r in chosen],
                 "fetched": [f"{p['url']} ({p['status']})" for p in pages], "language": language}
        if not pages:
            return {"text": msg.message("no_sources", language_text or question), "sources": [], "found": False, "trace": trace}

        today = date.today()

        def published(p: Dict[str, Any]) -> str:
            if p["url"] in self.listing_urls:
                return "Live news listing, fetched today: newest posts first.\n"
            if not p.get("date"):
                return ""
            age = (today - date.fromisoformat(p["date"])).days
            past = " Events and deadlines it announces before today are in the past." if age > 0 else ""
            return f"Published: {p['date']} ({age} days before today).{past}\n"

        context = "\n\n".join(f"[{p['n']}] {p['title']}\nURL: {p['url']}\n{published(p)}{p['excerpt']}" for p in pages)
        model = model or self.config.get("FORRT_ANSWER_MODEL") or self.config["CITATION_MODEL"]
        system = ANSWER_SYSTEM.format(today=today.isoformat(), language=language)
        user = ANSWER_USER.format(context=context, question=question, language=language, today=today.isoformat())
        text = self._chat(model, system, user)
        if not text:
            return {"text": None, "sources": [], "found": False, "trace": trace}

        problems = []
        got = checks.wrong_language(text, language_code)
        if got:
            problems.append(f"it is written in {got}, but must be written in {language}")
        stale = checks.past_events_called_upcoming(text, today)
        if stale:
            problems.append(f"it calls events before today ({today.isoformat()}) upcoming: " + " | ".join(stale[:3]))
        if problems:  # one rewrite, only when a check failed
            text = self._chat(model, system, REWRITE_USER.format(original=user, draft=text, problems="; ".join(problems))) or text
        text, removed = checks.strip_unsupported_links(text, pages)
        text = checks.clean_citations(text, len(pages))
        # the pages go to the Sources box under the answer (Qualle), not into the text
        # excerpt: the text the model read (eval/run.py saves it for the judges; the app shows title and url)
        sources = [{"n": p["n"], "title": p["title"], "url": p["url"], "excerpt": p["excerpt"]} for p in pages]
        trace.update(rewrite=problems, removed_links=removed, seconds=round(time.perf_counter() - start, 1))
        logger.info(f"Timing: FORRT pages {trace['seconds']}s, {len(pages)} pages, removed links {removed}")
        return {"text": text, "sources": sources, "found": True, "trace": trace}

    def links(self, question: str, limit: int = 3) -> List[Dict[str, str]]:
        """The best FORRT pages for a question, without fetching or an answer (the "both" route)."""
        chosen = self.select(question, self.retrieve(question))[:limit]
        return [{"title": r["title"], "url": r["url"]} for r in chosen]
