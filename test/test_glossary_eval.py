"""Glossary eval items (E1 pilot)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import glossary_items  # noqa: E402


def test_select_terms_keeps_terms_citing_an_indexed_doi():
    english = [
        {"title": "A", "references": ["X (2020). https://doi.org/10.1000/ABC.", "Y (2021). No DOI."]},
        {"title": "B", "references": ["Z (2019). https://doi.org/10.1000/other"]},
        {"title": "C"},
    ]
    terms = glossary_items.select_terms(english, {"10.1000/abc"})
    assert [(t["title"], dois) for t, dois in terms] == [("A", ["10.1000/abc"])]
