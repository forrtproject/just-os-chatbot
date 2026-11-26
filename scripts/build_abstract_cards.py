"""Abstract cards: FORRT resources the index has no text for, as one short document each, for scripts/add_to_index.py.

    python -m scripts.build_abstract_cards                 # host, after python -m scripts.forrt_article_list
    docker compose run --rm -T --no-deps -v ./data/processed:/app/data/processed web python -m scripts.add_to_index \\
        data/processed/abstract_cards data/processed/abstract_cards/metadata.csv --index data/processed/vs_latest_bge-m3_glossary

Reads data/curation/forrt_article_list.csv and takes every resource not in the index (and not excluded in its list)
whose FORRT summary and abstract together have at least MIN_CHARS characters (paywalled papers, books, web resources;
decided 25 Nov 2026). A card is the title, authors and year, type, cluster and sub-cluster, the FORRT summary, the
abstract and the link; the bot finds and cites it like a paper. Its licence is the resource's, so for anything not
openly licensed the bot links it but shows no quote (references.passage_allowed). add_to_index skips a resource whose
DOI or title is already in the index, so run the full-text downloads (./run curate) first; shortcut: a card stays
until the index is rebuilt even when its full text is added later (the FAISS store cannot delete), so rebuild the
index from scratch once most cards have full text.
"""

import csv
import hashlib
from pathlib import Path

import pandas as pd

LIST = Path("data/curation/forrt_article_list.csv")
OUT = Path("data/processed/abstract_cards")
MIN_CHARS = 100
CARD_TYPE = "FORRT abstract card"


def card(r) -> str:
    head = " ".join(x for x in (r.authors, f"({r.year})" if r.year else "") if x)
    lines = [f"# {r.title}", ""]
    if head:
        lines.append(head)
    lines.append(" · ".join(x for x in (r.type, r.clusters, r.sub_clusters) if x))
    if r.summary:
        lines += ["", f"Summary (FORRT): {r.summary}"]
    if r.abstract:
        lines += ["", f"Abstract: {r.abstract}"]
    return "\n".join(lines).strip() + "\n"


def cards(table: pd.DataFrame) -> pd.DataFrame:
    """The rows that get a card."""
    text = (table.summary + " " + table.abstract).str.strip().str.len()
    return table[(table.in_index == "no") & (table.excluded_in_source != "yes") & (text >= MIN_CHARS) & (table.title != "")]


def main():
    rows = cards(pd.read_csv(LIST, dtype=str).fillna(""))
    OUT.mkdir(parents=True, exist_ok=True)
    meta = []
    for r in rows.itertuples():
        stem = "card-" + hashlib.sha1((r.doi or r.url or r.title).encode()).hexdigest()[:16]
        (OUT / f"{stem}.md").write_text(card(r), encoding="utf-8")
        meta.append({"doi_hash": stem, "title": r.title, "creators": r.authors, "doi": r.doi,
                     "link_to_resource": r.url or (f"https://doi.org/{r.doi}" if r.doi else ""),
                     "material_type": f"{CARD_TYPE}: {r.type or r.category}", "conditions_of_use": r.licence,
                     "FORRT_clusters": r.clusters})
    with open(OUT / "metadata.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(meta[0]))
        writer.writeheader()
        writer.writerows(meta)
    print(f"{len(meta)} abstract cards -> {OUT} ({rows.category.value_counts().to_dict()})")


if __name__ == "__main__":
    main()
