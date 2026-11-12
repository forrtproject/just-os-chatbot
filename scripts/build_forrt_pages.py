"""Build (or update) the FORRT page index for the FORRT page router (just_os/forrt_pages.py).

    python -m scripts.build_forrt_pages                      # in the web container (needs LLM_API_KEY)
    python -m scripts.build_forrt_pages --limit 5            # quick test
    python -m scripts.build_forrt_pages --from-prototype DIR # reuse the descriptions in DIR/index.json,
                                                              # only re-embed (no fetching, no LLM)

Scope: every forrt.org page in the site's menu bar, every page under CHILD_SECTIONS (announcements,
newsletters, FORRT's own sections), and FORRT_EXTRA_URLS_FILE (project sites at forrt.org/<repo>/
that are missing from the sitemap); minus EXCLUDE_PREFIXES (curated resources, clusters) and the
glossary terms. Incremental: a page is fetched, described and embedded again only when its sitemap
<lastmod> changed (extra pages: every run) or with --force.

Per page an LLM (FORRT_DESCRIBE_MODEL) writes: summary, use_when, 5 example questions, page kind,
freshness and key links. Only that description is embedded, with EMBEDDING_MODEL (the app's model).
Output in FORRT_PAGES_DIR: index.json and vectors.npy. Page text is not stored: the app reads pages live.
"""

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import numpy as np
from bs4 import BeautifulSoup
from openai import OpenAI

from config.settings import get_config
from just_os.forrt_pages import extract, refresh_target

SITEMAP = "https://forrt.org/sitemap.xml"
MENU_PAGE = "https://forrt.org/"
SITE_INDEX = "https://raw.githubusercontent.com/forrtproject/forrtproject.github.io/gh-pages/index.json"
EXCLUDE_PREFIXES = ("/resources/", "/curated_resources/", "/clusters/", "/forrt_clusters/")
CHILD_SECTIONS = ("post", "newsletters", "educators-corner", "pedagogies", "neurodiversity-lessonbank", "replication-hub")
HEADERS = {"User-Agent": "JUST-OS chatbot (forrt.org page index)"}

DESCRIBE_SYSTEM = """You write index entries for pages of forrt.org (FORRT: Framework for Open and Reproducible Research Training).
A chatbot uses your entry to decide whether to open this page to answer a user's question.
Use only facts stated in the page content, title and links. Never guess what a name or acronym stands
for, and never say a page is empty: if the content is short, describe just what it states.
Reply with JSON only."""
DESCRIBE_USER = """Page URL: {url}
Title: {title}

Links on the page (url | text):
{links}

Page content (Markdown, may be cut):
{content}

Return this JSON object:
{{"summary": "2-3 sentences: what this page contains (concrete: names, programmes, what can be done here)",
  "use_when": "1-2 sentences: which user questions this page answers",
  "example_questions": ["5 varied questions a visitor might ask that this page answers, short and natural"],
  "page_kind": "one of: org_info, get_involved, team_or_project, event_or_news, teaching_material, listing, tool, other",
  "freshness": "static or changes_often",
  "key_links": [{{"url": "one of the URLs listed above", "label": "short label"}}]}}"""


def norm_url(url: str) -> str:
    url = urljoin("https://forrt.org/", url.strip()).split("#")[0].split("?")[0]
    url = re.sub(r"index\.html?$", "", url)
    return url if url.endswith("/") else url + "/"


def in_scope(url: str, menu: set, extras: set) -> bool:
    url = norm_url(url)
    path = urlparse(url).path
    if not urlparse(url).netloc.endswith("forrt.org") or path.startswith(EXCLUDE_PREFIXES):
        return False
    if url in menu or url in extras:
        return True
    parts = [p for p in path.strip("/").split("/") if p]
    if parts and parts[0] == "glossary":
        return len(parts) == 1
    return bool(parts) and parts[0] in CHILD_SECTIONS


def read_sitemap(client: httpx.Client) -> Dict[str, str]:
    root = ET.fromstring(client.get(SITEMAP, timeout=30).content)
    out = {}
    for node in root:
        fields = {child.tag.split("}")[-1]: (child.text or "").strip() for child in node}
        if fields.get("loc"):
            out[norm_url(fields["loc"])] = fields.get("lastmod", "")
    return out


def menu_urls(client: httpx.Client) -> set:
    nav = BeautifulSoup(client.get(MENU_PAGE, timeout=30).text, "html.parser").select_one("nav")
    return {norm_url(a["href"]) for a in nav.find_all("a", href=True)} if nav else set()


def page_links(html: str, url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    links: Dict[str, str] = {}
    for a in (soup.select_one("main") or soup.body or soup).find_all("a", href=True):
        href = urljoin(url, a["href"].strip()).split("#")[0]
        if href.startswith(("http", "mailto:")) and href.rstrip("/") != url.rstrip("/"):
            links.setdefault(href, a.get_text(" ", strip=True)[:120])
    return [{"url": u, "text": t} for u, t in list(links.items())[:50]]


def describe(llm: OpenAI, model: str, rec: Dict[str, Any], markdown: str, links: List[Dict[str, str]]) -> Dict[str, Any]:
    prompt = DESCRIBE_USER.format(url=rec["url"], title=rec["title"], content=markdown[:7000] or "(empty)",
                                  links="\n".join(f"{x['url']} | {x['text']}" for x in links) or "(none)")
    try:
        resp = llm.chat.completions.create(model=model, temperature=0, max_tokens=2500,
                                          messages=[{"role": "system", "content": DESCRIBE_SYSTEM},
                                                    {"role": "user", "content": prompt}])
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resp.choices[0].message.content or "").strip())
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as exc:
        print(f"  description failed for {rec['url']}: {exc.__class__.__name__}; using the page start")
        return {"summary": " ".join(markdown.split())[:400], "use_when": "", "example_questions": [],
                "page_kind": "other", "freshness": "static", "key_links": [], "described_by": "page start"}
    known = {x["url"] for x in links}
    return {"summary": str(data.get("summary", ""))[:800], "use_when": str(data.get("use_when", ""))[:400],
            "example_questions": [str(q)[:200] for q in data.get("example_questions") or []][:6],
            "page_kind": str(data.get("page_kind", "other")),
            "freshness": "changes_often" if data.get("freshness") == "changes_often" else "static",
            "key_links": [k for k in data.get("key_links") or [] if isinstance(k, dict) and k.get("url") in known][:6],
            "described_by": model}


def embed_text(rec: Dict[str, Any]) -> str:
    parts = [rec["title"], rec.get("summary", ""), f"Use when: {rec.get('use_when', '')}",
             "Questions: " + " | ".join(rec.get("example_questions", []))]
    return "\n".join(p for p in parts if p.strip())


def publish_dates(client: httpx.Client) -> Dict[str, str]:
    try:
        pages = client.get(SITE_INDEX, timeout=60).json()
    except Exception as exc:
        print(f"dates: could not read {SITE_INDEX} ({exc.__class__.__name__})")
        return {}
    return {norm_url(p["permalink"]): p["publishdate"][:10] for p in pages
            if str(p.get("publishdate", ""))[:4] >= "1990" and p.get("permalink")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--from-prototype", help="directory with an index.json to reuse descriptions from")
    args = ap.parse_args()
    cfg = get_config()
    out = Path(cfg["FORRT_PAGES_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=cfg["FORRT_FETCH_TIMEOUT"] * 3)

    sitemap = read_sitemap(client)
    menu = menu_urls(client)
    extras_file = Path(cfg["FORRT_EXTRA_URLS_FILE"])
    extras = {norm_url(line.split("#")[0]) for line in extras_file.read_text(encoding="utf-8").splitlines()
              if line.strip().startswith("http")} if extras_file.is_file() else set()
    wanted = {u: sitemap.get(u, "") for u in set(sitemap) | menu | extras if in_scope(u, menu, extras)}
    old_file = out / "index.json"
    existing = {r["url"]: r for r in json.loads(old_file.read_text(encoding="utf-8"))} if old_file.is_file() else {}

    if args.from_prototype:  # reuse descriptions; nothing is fetched or described
        src = Path(args.from_prototype)
        proto = {norm_url(r["url"]): r for r in json.loads((src / "index.json").read_text(encoding="utf-8"))}
        for url in wanted:
            if url in proto:
                existing[url] = {**proto[url], "url": url}
        todo = []
    else:
        todo = [u for u in wanted if args.force or u not in existing or u in extras or existing[u].get("lastmod") != wanted[u]]
    todo = todo[: args.limit] if args.limit else todo
    print(f"in scope: {len(wanted)} pages ({len(menu)} menu links, {len(extras)} extra URLs); "
          f"{len(existing)} already described; {len(todo)} to fetch and describe")

    llm = OpenAI(base_url=cfg["BASE_URL"], api_key=cfg["LLM_API_KEY"], timeout=cfg.get("LLM_TIMEOUT", 60), max_retries=1)

    def build(url: str) -> Optional[Dict[str, Any]]:
        time.sleep(0.2)
        try:
            resp = client.get(url)
            resp.raise_for_status()
            target = refresh_target(resp.text, url)
            if target:  # a "this page has moved" stub: describe the page it points to
                resp = client.get(target)
                resp.raise_for_status()
        except Exception as exc:
            print(f"  fetch failed {url}: {exc.__class__.__name__}")
            return None
        page = extract(resp.text, str(resp.url))  # read to describe the page; the text itself is not kept
        parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
        rec = {"url": url, "lastmod": wanted[url], "title": page["title"], "section": parts[0] if parts else "home",
               "chars": len(page["markdown"])}
        return {**rec, **describe(llm, cfg["FORRT_DESCRIBE_MODEL"], rec, page["markdown"], page_links(resp.text, str(resp.url)))}

    with ThreadPoolExecutor(6) as pool:
        for rec in pool.map(build, todo):
            if rec:
                existing[rec["url"]] = rec

    records = [r for u, r in existing.items() if u in wanted]  # drop pages that left the site or the scope
    dates = publish_dates(client)
    for r in records:
        m = re.search(r"/(20\d{2})-(\d{1,2})(?:-|/)", r["url"])
        r["date"] = dates.get(r["url"]) or (f"{m.group(1)}-{int(m.group(2)):02d}-01" if m else None)

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    print(f"embedding {len(records)} descriptions with {cfg['EMBEDDING_MODEL']} ...")
    embedder = HuggingFaceEmbedding(model_name=cfg["EMBEDDING_MODEL"])
    vectors = np.asarray(embedder.get_text_embedding_batch([embed_text(r) for r in records]), dtype=np.float32)
    old_file.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    np.save(out / "vectors.npy", vectors)
    print(f"wrote {len(records)} pages to {out} ({sum(1 for r in records if r.get('date'))} with a date)")


if __name__ == "__main__":
    main()
