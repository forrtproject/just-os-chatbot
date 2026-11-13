"""config/criteria.json (#54): one set of criteria and one scale for the review page, the arena and later the judges."""

from just_os import criteria
from just_os.app import ARENA_CRITERIA, REVIEW_CRITERIA, REVIEW_DECISIONS, review_rows, valid_ratings

ITEMS = {"q1": {"answer_id": "run#q1", "id": "q1", "category": "", "expected": "answer", "bot_did": "answered", "question": "?",
               "rubric": [{"id": "r1", "criterion": "Says what it is", "type": "core"}]}}


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


def test_review_saves_score_rows_for_the_answer():
    problem, rows = review_rows({"reviewer": " Ann ", "scores": {"q1": {"decision": "right", "correctness": "4",
                                                                       "clarity": "n/a", "note": "fine"}}}, ITEMS)
    assert problem is None
    assert [(r["answer_id"], r["criterion"], r["score"], r["scorer"]) for r in rows] == [
        ("run#q1", "decision", "right", "Ann"), ("run#q1", "correctness", 4, "Ann")]
    assert rows[0]["note"] == "fine" and rows[1]["scale"] == [1, 5] and rows[0]["scale"] is None
    assert review_rows({"reviewer": "Ann", "scores": {"q1": {"note": ""}}}, ITEMS)[0] == "Nothing scored yet."


def test_review_rubric_setting_adds_rubric_rows():
    data = {"reviewer": "Ann", "rubric": True, "scores": {"q1": {"rubric": {"r1": "5"}, "correctness": "3"}}}
    problem, rows = review_rows(data, ITEMS)
    assert problem is None and ("rubric:r1", 5, "rubric") in [(r["criterion"], r["score"], r["setting"]) for r in rows]
    for bad in ({"r9": "5"}, {"r1": "0"}, {"r1": "n/a"}, ["r1"]):
        assert review_rows({"reviewer": "Ann", "scores": {"q1": {"rubric": bad}}}, ITEMS)[0] == "Invalid score for q1."


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
    # each judge's --model default reads the model config/criteria.json names for it
    import judge
    assert criteria.JUDGES == judges and criteria_judge.CONFIG["model"] == judges["criteria"]["model"]
    for module, default in ((judge, 'criteria.JUDGES["support"]["model"]'), (rubric_judge, 'criteria.JUDGES["rubric"]["model"]'),
                            (criteria_judge, 'CONFIG["model"]')):
        assert f'"--model", default={default}' in Path(module.__file__).read_text(encoding="utf-8"), module.__name__
    assert rubric_judge.coverage({"r1": 5, "r2": 1}, [{"id": "r1", "type": "core"}, {"id": "r2", "type": "detail"}]) == 0.5
