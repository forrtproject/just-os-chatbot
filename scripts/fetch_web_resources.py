"""HTML route (issue C3, #18): turn FORRT web resources without a DOI into Markdown.

    docker compose run --rm -v ./data:/app/data web python -m scripts.fetch_web_resources [--sample 50]

Reads the newest eval/results/coverage_*.csv (eval/coverage.py), takes a random sample of
the rows with reason web_page or code_or_osf, downloads each page and keeps its main text.
Output in data/processed/web_markdown/: <hash>.md per page and metadata.csv (doi_hash,
title, link_to_resource, material_type, conditions_of_use), ready for scripts/add_to_index.py.
The licence is unknown, so the bot will not show passages from these pages (issue R5).
"""

import argparse
import csv
import hashlib
import random
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path("data/processed/web_markdown")
MIN_CHARS = 500  # shorter pages are menus or landing pages
MAX_BYTES = 5_000_000
DROP = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


def main_text(html: str) -> str:
    """The readable text of a page: <main> or <article> if present, else <body>, without menus."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = (" ".join(line.split()) for line in root.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "JUST-OS resource indexer"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if "html" not in response.headers.get("Content-Type", ""):
            raise ValueError("not an HTML page")
        return response.read(MAX_BYTES).decode(response.headers.get_content_charset() or "utf-8", "replace")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    coverage = sorted(Path("eval/results").glob("coverage_*.csv"))[-1]
    rows = [r for r in csv.DictReader(open(coverage, encoding="utf-8")) if r["reason"] in ("web_page", "code_or_osf")]
    random.Random(args.seed).shuffle(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    kept = []
    for row in rows[: args.sample]:
        url = row["url"].strip()
        try:
            text = main_text(fetch(url))
        except Exception as e:
            print(f"skip {url}: {e}")
            continue
        if len(text) < MIN_CHARS:
            print(f"skip {url}: only {len(text)} characters")
            continue
        key = hashlib.md5(url.encode("utf-8")).hexdigest()
        (OUT / f"{key}.md").write_text(f"# {row['title']}\n\nSource: {url}\n\n{text}\n", encoding="utf-8")
        kept.append({"doi_hash": key, "title": row["title"], "link_to_resource": url,
                     "material_type": row["material_type"], "conditions_of_use": ""})
    with open(OUT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doi_hash", "title", "link_to_resource", "material_type", "conditions_of_use"])
        writer.writeheader()
        writer.writerows(kept)
    print(f"{len(kept)} of {min(args.sample, len(rows))} pages kept → {OUT}")
