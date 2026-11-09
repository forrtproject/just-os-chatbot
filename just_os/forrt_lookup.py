"""FORRT lookup mode (issue M6, #15): "Where on FORRT is X?" / "How can I contribute?".

The answer is a short list of FORRT resources with links, not a summary. It searches the
title, abstract, clusters and tags of every row of the FORRT sheet (also the videos,
courses and web pages that are not in the vector index) with BM25. On with FORRT_LOOKUP=true.
"""

import csv
import html
import logging
from pathlib import Path
from typing import Dict, List

from just_os.hybrid import BM25
from just_os.references import reference_url

logger = logging.getLogger(__name__)

INTRO = "Here are FORRT resources that match your question:"
NOTHING = "I could not find a FORRT resource for that. You can browse FORRT at https://forrt.org/."
# shortcut: one generic pointer; add the real "get involved" pages once FORRT confirms them
CONTRIBUTE = "To get involved with FORRT, see https://forrt.org/ for current projects and how to join."


def column(row: Dict[str, str], prefix: str) -> str:
    """Value of the first column whose name starts with prefix (the sheet has long headers)."""
    return next((value or "" for key, value in row.items() if key and key.startswith(prefix)), "")


def plain(text: str) -> str:
    """Text that is safe inside Markdown that becomes HTML: no tags, no link brackets."""
    return html.escape(" ".join(str(text).split())).replace("[", "(").replace("]", ")")


class ForrtLookup:
    def __init__(self, sheet_file: str, top_k: int = 5):
        self.top_k = top_k
        with open(Path(sheet_file), encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if column(r, "Title").strip() and not column(r, "Exclude").strip()]
        self.rows: List[Dict[str, str]] = [
            {
                "title": column(r, "Title"),
                "url": reference_url({"link_to_resource": column(r, "URL/DOI"), "doi": column(r, "DOI")}) or "",
                "type": column(r, "Material Type"),
                "clusters": column(r, "FORRT Clusters"),
                "text": " ".join(column(r, c) for c in ("Title", "Abstract", "FORRT Clusters", "User Tags")),
            }
            for r in rows
        ]
        self.bm25 = BM25([r["text"] for r in self.rows])
        logger.info(f"FORRT lookup: {len(self.rows)} resources from {sheet_file}")

    def search(self, query: str) -> List[Dict[str, str]]:
        return [self.rows[i] for i in self.bm25.top(query, self.top_k)]

    def answer(self, query: str) -> str:
        """Markdown list of the best matching resources (titles escaped, http(s) links only)."""
        hits = self.search(query)
        lines = [INTRO, ""] if hits else [NOTHING]
        for hit in hits:
            title = plain(hit["title"])
            details = "; ".join(plain(x) for x in (hit["type"], hit["clusters"]) if x.strip())
            entry = f"[{title}]({hit['url']})" if hit["url"] else title
            lines.append(f"- {entry}" + (f" ({details})" if details else ""))
        if any(word in query.lower() for word in ("contribute", "involved", "join", "volunteer")):
            lines += ["", CONTRIBUTE]
        return "\n".join(lines)
