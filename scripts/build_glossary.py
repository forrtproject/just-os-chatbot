"""FORRT glossary as sources: one Markdown document per term and language, for scripts/add_to_index.py.

    docker compose run --rm -v ./data:/app/data web python -m scripts.build_glossary [--glossary FILE]
    cp -r data/processed/vs_latest_bge-m3 data/processed/vs_glossary_staging_<YYMMDD>   # a fresh copy of the paper index
    docker compose run --rm -v ./data:/app/data web python -m scripts.add_to_index \\
        data/processed/glossary_markdown data/processed/glossary_markdown/metadata.csv \\
        --index data/processed/vs_glossary_staging_<YYMMDD> --output data/processed/vs_glossary_staging_<YYMMDD>

Check the staging folder, then point VECTOR_STORE at it (or move it to vs_latest_bge-m3_glossary after a backup):
never write into the live vs_latest_bge-m3_glossary, which already holds the glossary and the later additions.

Reads content/glossary/_glossaries.json of github.com/forrtproject/forrt (all five languages: english,
german, arabic, chinese, turkish; --glossary for a local copy) and forrt.org's sitemap, which gives each
entry's page address (forrt.org/glossary/<language>/<slug>/; the slug follows the title, but Hugo changes
some non-Latin ones, so the sitemap is the reference; an entry missing from it links to the language's
glossary page). Each document is the title, the definition and the related terms; the reference list is
left out of the text (it would become a chunk of its own) and its DOIs go to the metadata (reference_dois).
Title "<term> (FORRT Glossary, <Language>)": the Sources box shows that, and the language keeps the
document keys of the same term in different languages apart. Licence CC BY-NC-SA 4.0, so the bot links the
entry but shows no quote (references.passage_allowed). The retriever keeps at most one glossary entry
per answer (qualle.limit_per_document).
"""

import argparse
import ast
import csv
import hashlib
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

import httpx

from just_os.references import DOI_PATTERN, GLOSSARY_TYPE, normalize_doi
from scripts.build_forrt_pages import read_sitemap

GLOSSARY_URL = "https://raw.githubusercontent.com/forrtproject/forrt/master/content/glossary/_glossaries.json"
LICENCE = "CC BY-NC-SA 4.0"
OUT = Path("data/processed/glossary_markdown")


def as_list(value) -> list:
    """The JSON keeps some lists as their Python text ("['a', 'b']")."""
    if isinstance(value, list):
        return [v for v in value if v]
    try:
        parsed = ast.literal_eval(value or "[]")
    except (ValueError, SyntaxError):
        return [value] if value else []
    return [v for v in parsed if v] if isinstance(parsed, list) else []


def slug(title: str) -> str:
    """forrt's clean_filename (content/glossary/_create_glossaries.py): the title before " [", lower case."""
    name = re.sub(r"[^\w\s]", "_", title.split(" [")[0].strip().replace(" ", "_"))
    return name.lower().strip().replace("__", "_")


def loose(text: str) -> str:
    """For matching a slug to a sitemap address: no accents, no separators (Hugo drops some marks)."""
    text = unicodedata.normalize("NFKD", text.lower().replace("ı", "i"))
    return "".join(c for c in text if not unicodedata.combining(c) and c.isalnum())


def page_urls(sitemap: dict) -> dict:
    """{(language, loose slug): url} for the glossary entries in the sitemap."""
    out = {}
    for url in sitemap:
        parts = urllib.parse.unquote(urllib.parse.urlparse(url).path).strip("/").split("/")
        if len(parts) == 3 and parts[0] == "glossary":
            out[(parts[1], loose(parts[2]))] = url
    return out


def documents(glossary: list, urls: dict) -> list:
    """One (file stem, Markdown text, metadata, has its own page) per entry with a definition."""
    out = []
    for block in glossary:
        for language, terms in block.items():
            for term in terms:
                definition = (term.get("definition") or "").strip()
                if not definition:
                    continue
                url = urls.get((language, loose(slug(term["title"]))))
                related = as_list(term.get("related_terms"))
                text = f"# {term['title']}\n\n{definition}\n"
                if related:
                    text += f"\nRelated terms: {'; '.join(related)}\n"
                dois = dict.fromkeys(normalize_doi(d) for r in as_list(term.get("references"))
                                     for d in DOI_PATTERN.findall(r))
                out.append((f"glossary-{hashlib.sha1((language + term['title']).encode()).hexdigest()[:16]}", text, {
                    "title": f"{term['title']} (FORRT Glossary, {language.title()})",
                    "link_to_resource": url or f"https://forrt.org/glossary/{language}/",
                    "material_type": GLOSSARY_TYPE,
                    "conditions_of_use": LICENCE,
                    "creators": "; ".join(as_list(term.get("drafted_by"))),
                    "language": language,
                    "en_title": term.get("en_title", ""),
                    "reference_dois": "; ".join(d for d in dois if d),
                }, url is not None))
    return out


METADATA_FIELDS = ["doi_hash", "title", "link_to_resource", "material_type", "conditions_of_use", "creators", "language",
                   "en_title", "reference_dois"]


def write_documents(out: Path, docs: list) -> None:
    """The Markdown files and metadata.csv (a fixed header, so no entries still gives a readable file)."""
    out.mkdir(parents=True, exist_ok=True)
    for stem, body, _, _ in docs:
        (out / f"{stem}.md").write_text(body, encoding="utf-8")
    with open(out / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
        writer.writeheader()
        writer.writerows({"doi_hash": stem, **meta} for stem, _, meta, _ in docs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--glossary", help=f"local _glossaries.json (default: download {GLOSSARY_URL})")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    with httpx.Client(follow_redirects=True, headers={"User-Agent": "JUST-OS glossary builder"}) as client:
        text = (Path(args.glossary).read_text(encoding="utf-8") if args.glossary
                else client.get(GLOSSARY_URL, timeout=60).raise_for_status().text)
        urls = page_urls(read_sitemap(client))
    docs = documents(json.loads(text), urls)
    write_documents(args.out, docs)
    print(f"{len(docs)} glossary documents ({sum(d[3] for d in docs)} with their own page) -> {args.out}")


if __name__ == "__main__":
    main()
