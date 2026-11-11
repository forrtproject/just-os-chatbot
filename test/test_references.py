import json
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from just_os import qualle
from just_os.references import (
    document_key,
    load_publication_years,
    normalize_doi,
    passage_allowed,
    publication_year,
    reference_url,
)


# --- R2: normalize_doi


@pytest.mark.parametrize(
    "raw, doi",
    [
        ("https://dx.doi.org/10.2139/ssrn.3796813", "10.2139/ssrn.3796813"),
        ("https://doi.org/10.1037/a0021524.", "10.1037/a0021524"),
        ("doi:10.1016/S0140-6736(15)60696-1", "10.1016/s0140-6736(15)60696-1"),
        ("(see 10.1000/xyz123).", "10.1000/xyz123"),
        ("https://doi.org/10.1002%2Fpsp4.12345;", "10.1002/psp4.12345"),
        ("10.1177/2515245918770963 ", "10.1177/2515245918770963"),
        ("https://osf.io/abcd/", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_doi(raw, doi):
    assert normalize_doi(raw) == doi


def test_reference_url_prefers_doi_and_blocks_javascript():
    assert reference_url({"link_to_resource": "https://dx.doi.org/10.1234/abc."}) == "https://doi.org/10.1234/abc"
    assert reference_url({"doi": "10.1234/x", "link_to_resource": "https://example.org"}) == "https://doi.org/10.1234/x"
    assert reference_url({"link_to_resource": "https://osf.io/abcd/"}) == "https://osf.io/abcd/"
    assert reference_url({"link_to_resource": "javascript:alert(1)"}) is None


# --- R5: passage only for open licences


@pytest.mark.parametrize(
    "licence, allowed",
    [
        ("CC BY", True),
        ("cc-by", True),
        ("Creative Commons Attribution 4.0 International", True),
        ("CC0", True),
        ("Public Domain", True),
        ("CC BY-NC-ND", False),
        ("CC BY-NC", False),
        ("I don't see any of these", False),
        ("", False),
        (None, False),
    ],
)
def test_passage_allowed(licence, allowed):
    assert passage_allowed(licence) is allowed


# --- R1: publication year, never the form time stamp


def test_publication_year(tmp_path):
    table = tmp_path / "years.csv"
    table.write_text("doi,year\n10.1234/ABC,2019\n", encoding="utf-8")
    years = load_publication_years(str(table))
    assert publication_year({"doi": "10.1234/abc", "timestamp": "12/18/2023 17:12:02"}, years) == "2019"
    assert publication_year({"link_to_resource": "https://doi.org/10.1234/abc"}, years) == "2019"
    assert publication_year({"doi": "10.9999/unknown"}, years) == "n.d."
    assert publication_year({"timestamp": "12/18/2023 17:12:02"}, years) == "n.d."
    assert publication_year({"pub_year": 2021}, years) == "2021"
    assert load_publication_years(str(tmp_path / "missing.csv")) == {}


# --- R3: one reference per paper


def chunk(title, doi, text="passage", licence="CC BY"):
    return SimpleNamespace(
        text=text,
        metadata={
            "title": title,
            "creators": "Author",
            "timestamp": "12/18/2023 17:12:02",
            "doi": doi,
            "link_to_resource": f"https://dx.doi.org/{doi}",
            "conditions_of_use": licence,
        },
    )


def links(html):
    return [
        (a.text, json.loads(a["data-reference"]))
        for a in BeautifulSoup(html, "html.parser").find_all("a", class_="reference-link")
    ]


def test_chunks_of_one_paper_share_one_number():
    nodes = [chunk("Manual", "10.1234/m", "first"), chunk("Other", "10.1234/o"), chunk("Manual", "10.1234/m", "second")]
    processor = qualle.ReferenceProcessor({"10.1234/m": "2020"})

    html, used = processor.process_markdown_with_references("A [0]. B [2]. C [1].", nodes)

    found = links(html)
    assert [text for text, _ in found] == ["[1]", "[1]", "[2]"]
    # each citation keeps the passage of its own chunk
    assert [data["text"] for _, data in found][:2] == ["first", "second"]
    sources = processor.references_from_nodes(nodes, used)
    assert sources.count("Manual") == 1
    assert sources.splitlines() == [
        "[1] Author (2020). Manual. https://doi.org/10.1234/m",
        "[2] Author (n.d.). Other. https://doi.org/10.1234/o",
    ]


def test_source_list_without_citations_lists_each_paper_once():
    nodes = [chunk("Manual", "10.1234/m"), chunk("Manual", "10.1234/m")]
    assert qualle.ReferenceProcessor().references_from_nodes(nodes).count("Manual") == 1


def test_tooltip_hides_passage_for_closed_licence_and_never_shows_timestamp():
    nodes = [chunk("Closed", "10.1234/c", "secret passage", licence="I don't see any of these")]
    html, _ = qualle.ReferenceProcessor().process_markdown_with_references("X [0].", nodes)
    data = links(html)[0][1]
    assert data["text"] == ""
    assert data["year"] == "n.d."
    assert data["url"] == "https://doi.org/10.1234/c"


def test_document_key_falls_back_to_title():
    assert document_key({"title": "A Paper!"}) == document_key({"title": "a paper"})


def test_dict_valued_metadata_is_unwrapped():
    broken = SimpleNamespace(
        text="t",
        metadata={"title": {"abc": "Adapting open science"}, "creators": {"abc": "Petersen"},
                  "doi": {"abc": "10.1002/icd.2315"}, "conditions_of_use": {"abc": "CC BY"}},
    )
    line = qualle.ReferenceProcessor({"10.1002/icd.2315": "2022"}).references_from_nodes([broken])
    assert line == "[1] Petersen (2022). Adapting open science. https://doi.org/10.1002/icd.2315"


def test_short_authors():
    from just_os.references import short_authors
    assert short_authors("Benjamin Le") == "Benjamin Le"
    assert short_authors("Robert T. Thibault, Olavo B. Amaral, Felipe Argolo") == "Robert T. Thibault et al."
    assert short_authors("Bartscherer, S. F., & Reinhart, M.") == "Bartscherer et al."


def test_reference_list_is_structured_and_deduplicated():
    nodes = [chunk("Manual", "10.1234/m", "first"), chunk("Manual", "10.1234/m", "second"), chunk("Other", "10.1234/o")]
    entries = qualle.ReferenceProcessor({"10.1234/m": "2020"}).reference_list(nodes, None, {2})
    assert [(e["number"], e["title"], e["year"], e["unverified"]) for e in entries] == [(1, "Manual", "2020", False), (2, "Other", "n.d.", True)]
    assert entries[0]["url"] == "https://doi.org/10.1234/m"


# --- snippet under each source


def test_best_snippet_picks_the_sentence_that_matches_the_claim():
    from just_os.references import best_snippet
    passage = ("## Methods\nWe surveyed researchers in three countries about their habits. "
               "Preregistration reduced questionable research practices by a third in our sample. "
               "Funding came from the **NWO**.")
    assert best_snippet("Preregistration reduces questionable research practices", passage) == (
        "Preregistration reduced questionable research practices by a third in our sample.")
    assert best_snippet("anything", "x " * 400).endswith(" …")  # long text is cut
    assert len(best_snippet("anything", "x " * 400)) <= 302


def test_reference_list_snippet_follows_the_cited_chunk_and_the_licence():
    nodes = [
        chunk("Open", "10.1234/o", "Open data makes results easier to check for other researchers. Unrelated closing words here."),
        chunk("Closed", "10.1234/c", "Data sharing is common in genetics research nowadays.", licence="CC BY-NC-ND"),
    ]
    answer = "Open data helps others check results [0]. Sharing is common [1]."
    entries = qualle.ReferenceProcessor().reference_list(nodes, [0, 1], answer=answer)
    assert entries[0]["snippet"] == "Open data makes results easier to check for other researchers."
    assert entries[1]["snippet"] == ""  # licence does not allow showing a passage
    assert qualle.ReferenceProcessor().reference_list(nodes, [0])[0]["snippet"] == ""  # no answer, no snippet
