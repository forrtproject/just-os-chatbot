"""The FORRT article list (CLUSTERS_FILE, made by scripts/forrt_article_list.py) for the dev app's /articles page:
every resource FORRT wants in the bot, whether and how it is in the index, and why a missing one is missing."""

import csv
from collections import Counter
from typing import Dict, List

# The columns the page shows and filters on (the CSV has more: abstract, summary, found_in, …)
COLUMNS = ["title", "authors", "year", "doi", "url", "category", "type", "clusters", "sub_clusters", "open_access",
           "in_index", "in_index_as", "last_try", "what_it_means", "lists", "excluded_in_source"]


def load(path: str) -> List[Dict[str, str]]:
    """The list's rows (only COLUMNS); [] when the file is missing."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return [{c: (r.get(c) or "") for c in COLUMNS} for r in csv.DictReader(f)]
    except OSError:
        return []


def status(row: Dict[str, str]) -> str:
    """One word for the page: how the resource is in the index, or "missing"."""
    return row["in_index_as"] or ("full text" if row["in_index"] == "yes" else "missing")


def summary(rows: List[Dict[str, str]]) -> Dict:
    """Counts per category and status, the missing ones by their last download outcome, and the missing web pages.
    Rows FORRT excludes in its own sheet (excluded_in_source) are not counted as wanted."""
    wanted = [r for r in rows if r["excluded_in_source"] != "yes"]
    by_category: Dict[str, Counter] = {}
    for r in wanted:
        by_category.setdefault(r["category"] or "Other", Counter())[status(r)] += 1
    missing = [r for r in wanted if status(r) == "missing"]
    return {"total": len(rows), "wanted": len(wanted), "excluded": len(rows) - len(wanted),
            "in_index": len(wanted) - len(missing), "missing": len(missing),
            "by_status": dict(Counter(status(r) for r in wanted)),
            "by_category": {c: dict(n) for c, n in sorted(by_category.items(), key=lambda x: -sum(x[1].values()))},
            "missing_by_try": dict(Counter(r["last_try"] or "not tried yet" for r in missing).most_common()),
            "missing_web": sum(1 for r in missing if r["category"].startswith("Website"))}
