"""config/criteria.json (#54): one set of criteria and one scale for the review page, the arena and later the judges."""

from just_os import criteria
from just_os.app import ARENA_CRITERIA, REVIEW_CRITERIA, REVIEW_DECISIONS, review_rows, valid_ratings

ITEMS = {"q1": {"category": "", "expected": "answer", "bot_did": "answered", "question": "?"}}


def test_pages_show_the_same_texts_as_before():
    assert REVIEW_CRITERIA == {
        "correctness": "Correctness: what the answer says is true and accurate",
        "citation_support": "Citation support: each cited passage or page really says what the sentence citing it says",
        "source_relevance": "Source relevance: the sources are the right ones for this question",
        "completeness": "Completeness: it covers what a good answer to this question needs",
        "clarity": "Clarity: clear, well organised, easy to act on",
    }
    assert ARENA_CRITERIA == {
        "correct": "Correct: the answer is right and complete",
        "references": "References: the cited sources support the answer",
        "clarity": "Clarity: clear and useful for the question",
    }
    assert list(REVIEW_DECISIONS) == ["right", "should_refuse", "should_answer", "unsure"]


def test_forms_use_only_shared_criteria():
    shared = set(criteria.CRITERIA)
    assert set(REVIEW_CRITERIA) <= shared
    assert all(set(maps) <= shared for maps in criteria.ARENA_MAPS_TO.values())
    assert set().union(*criteria.ARENA_MAPS_TO.values()) == shared  # the arena covers every shared criterion


def test_review_and_arena_accept_the_same_scale():
    assert list(criteria.SCALE) == [1, 2, 3, 4, 5] == list(criteria.SCALE_LABELS)
    for value, ok in [(1, True), (5, True), (0, False), (6, False)]:
        problem, _ = review_rows({"reviewer": "r", "scores": {"q1": {"correctness": str(value)}}}, ITEMS)
        assert (problem is None) == ok, value
        assert valid_ratings({"A": {c: value for c in ARENA_CRITERIA}}) == ok, value


def test_review_keeps_empty_fields_empty():
    problem, rows = review_rows({"reviewer": "r", "scores": {"q1": {"decision": "", "correctness": "4", "note": ""}}}, ITEMS)
    assert problem is None
    assert rows[0]["decision"] == "" and rows[0]["note"] == "" and rows[0]["clarity"] == ""  # was "'" before #54
    _, rows = review_rows({"reviewer": "r", "scores": {"q1": {"note": "=1+1"}}}, ITEMS)
    assert rows[0]["note"] == "'=1+1"  # a formula is still quoted


def test_judges_take_criteria_levels_and_models_from_the_file():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    import criteria_judge
    import rubric_judge
    judges = criteria.DEFINITIONS["judges"]
    assert criteria_judge.JUDGED == judges["criteria"]["criteria"] and set(criteria_judge.JUDGED) <= set(criteria.CRITERIA)
    text = criteria_judge.prompt({"question": "Q?", "answer": "A [1].", "sources": [{"n": 1, "title": "T", "passage": "p"}]})
    assert all(criteria.CRITERIA[k] in text for k in criteria_judge.JUDGED)
    assert "1 wrong or very poor" in text and '"clarity": <1-5>' in text and "[1] T" in text
    assert rubric_judge.LEVELS == "1 not at all, 2 barely, 3 partly, 4 mostly, 5 fully"
    assert rubric_judge.coverage({"r1": 5, "r2": 1}, [{"id": "r1", "type": "core"}, {"id": "r2", "type": "detail"}]) == 0.5
