"""Glossary eval items and the rubric judge (E1 pilot)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import glossary_items  # noqa: E402
import rubric_judge  # noqa: E402

RUBRIC = [{"id": "r1", "type": "core", "criterion": "a"}, {"id": "r2", "type": "detail", "criterion": "b"}]


def test_select_terms_keeps_terms_citing_an_indexed_doi():
    english = [
        {"title": "A", "references": ["X (2020). https://doi.org/10.1000/ABC.", "Y (2021). No DOI."]},
        {"title": "B", "references": ["Z (2019). https://doi.org/10.1000/other"]},
        {"title": "C"},
    ]
    terms = glossary_items.select_terms(english, {"10.1000/abc"})
    assert [(t["title"], dois) for t, dois in terms] == [("A", ["10.1000/abc"])]


def test_coverage_over_all_items_and_core_items():
    scores = {"r1": 5, "r2": 3}  # 1-5 (#54): coverage is (score - 1) / 4, as ResearchQA's 4 and 2 on 0-4
    assert rubric_judge.coverage(scores, RUBRIC) == 0.75
    assert rubric_judge.coverage(scores, RUBRIC, "core") == 1.0


def test_doi_recall_counts_only_cited_sources():
    item = {"expected_dois": ["10.1/a", "10.1/b"]}
    row = {"retrieved_dois": "10.1/x 10.1/a 10.1/b", "answer": "One [1]. Out of range [9]."}
    assert rubric_judge.doi_recall(row, item) == 0.5
    assert rubric_judge.doi_recall({"retrieved_dois": "", "answer": "x"}, item) == ""


class FakeResponse:
    def __init__(self, content):
        self.usage = type("U", (), {"cost": 0.001})()
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class FakeManager:
    def __init__(self, content):
        create = lambda **kw: FakeResponse(content)  # noqa: E731
        self.client = type("Cl", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})})})


def test_judge_clamps_scores_and_survives_bad_output():
    cost = [0.0]
    good = rubric_judge.judge(FakeManager(json.dumps({"scores": {"r1": 7, "r2": -1}})), "m", "q", "a", RUBRIC, cost)
    assert good == {"r1": 5, "r2": 1} and cost[0] == 0.001
    assert rubric_judge.judge(FakeManager("not json"), "m", "q", "a", RUBRIC, cost) is None


def test_select_terms_follows_the_listed_titles():
    english = [
        {"en_title": "A", "references": ["https://doi.org/10.1000/a"]},
        {"en_title": "B", "references": ["https://doi.org/10.1000/b", "https://doi.org/10.1000/x"]},
    ]
    terms = glossary_items.select_terms(english, {"10.1000/b"}, ["B", "A"])
    assert [(t["en_title"], dois) for t, dois in terms] == [("B", ["10.1000/b"]), ("A", [])]


def test_select_terms_stops_on_an_unknown_title():
    import pytest

    with pytest.raises(SystemExit):
        glossary_items.select_terms([{"en_title": "A"}], set(), ["Z"])


def test_parse_json_accepts_a_code_fence():
    assert glossary_items.parse_json('```json\n{"question": "q"}\n```') == {"question": "q"}
    assert glossary_items.parse_json('{"question": "q"}') == {"question": "q"}


def test_skip_classifier_routes_every_question_to_the_library():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    import run

    qualle = type("Q", (), {})()
    run.skip_classifier(qualle)
    assert qualle.route("anything") == qualle.route("anything", "jev") == "open_science"


def test_grading_page_is_blind_and_rotates_generators(tmp_path):
    import build_grading_page

    rubric = [{"id": "r1", "type": "core", "criterion": "c"}]
    items = {g: [{"id": f"gl0{n}en", "term": f"T{n}", "question": f"{g} q{n}", "rubric": rubric} for n in (1, 2, 3)]
             for g in ("a/x", "b/y", "c/z")}
    for g in items:
        for mode in build_grading_page.MODES:
            with open(tmp_path / f"glossary_{g.replace('/', '__')}_{mode}.csv", "w", encoding="utf-8") as f:
                f.write("id,outcome,answer\n" + "".join(f"gl0{n}en,answered,{g} {mode} {n}\n" for n in (1, 2, 3)))
    glossary = [{"en_title": f"T{n}", "definition": f"d{n}"} for n in (1, 2, 3)]
    data, keys = build_grading_page.build(glossary, items, tmp_path)

    assert len(data["part1"]) == 9 and len(data["part2"]) == 6
    fields = {f for part in data.values() for entry in part for f in entry}
    assert fields == {"key", "term", "definition", "question", "rubric", "answer"}
    part2 = [k for k in keys if k["part"] == 2]
    assert sorted((k["item"], k["generator"]) for k in part2 if k["condition"] == "library") == [
        ("gl01en", "a/x"), ("gl02en", "b/y"), ("gl03en", "c/z")]
    by_key = {e["key"]: e for e in data["part2"]}
    assert all(by_key[k["key"]]["question"].startswith(k["generator"]) for k in part2)


def test_answer_is_shown_as_the_app_shows_it_without_citations():
    import build_grading_page as b

    raw = "Plan.\n[Response_Start] HARKing is X [0], see [1, 2]. [Response_End]\n[0] Title: echoed passage"
    assert b.shown_answer(raw) == "HARKing is X [0], see [1, 2]."
    assert b.without_citations(b.shown_answer(raw)) == "HARKing is X, see."
    assert b.shown_answer("No markers [3].") == "No markers [3]."
