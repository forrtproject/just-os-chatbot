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
