"""eval/questions.jsonl keeps one structure (Meltem's and Mohit's question bank, 12 Nov)."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = [json.loads(line) for line in open(ROOT / "eval/questions.jsonl", encoding="utf-8")]
CLASSES = [r["Question type"] for r in csv.DictReader(open(ROOT / "data/raw/questions_bank_classes_261112.csv", encoding="utf-8"))]
# The Classes sheet lists the 10 question types, then a "FORRT cluster" header row, then the 11 clusters
TYPES = set(CLASSES[: CLASSES.index("FORRT cluster")])
CLUSTERS = set(CLASSES[CLASSES.index("FORRT cluster") + 1:]) | {"FORRT Lookup", ""}
KEYS = ["id", "cluster", "type", "lang", "format", "question", "expect", "route", "expected_dois", "expected_urls", "source"]
# A question with a rubric (the FORRT glossary items, eval/rubric_judge.py) carries all three
RUBRIC_KEYS = {"term", "reference_answer", "rubric"}


def test_every_question_has_the_agreed_fields_and_labels():
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    for q in QUESTIONS:
        assert list(q)[: len(KEYS)] == KEYS, q["id"]
        assert set(q) <= set(KEYS) | {"history", "note"} | RUBRIC_KEYS, q["id"]
        assert q["type"] in TYPES and q["cluster"] in CLUSTERS, q["id"]
        assert q["expect"] in ("answer", "refuse") and q["route"] in ("open_science", "forrt", "both", "neither"), q["id"]
        assert (q["route"] == "neither") == (q["expect"] == "refuse"), q["id"]
        assert ("history" in q) == (q["format"] == "Multi-turn"), q["id"]
        assert q["question"].strip() and all(isinstance(t, str) and t for t in q.get("history", [])), q["id"]


def test_old_questions_are_kept():
    ids = {q["id"] for q in QUESTIONS}
    assert {f"pr0{i}" for i in range(1, 8)} | {f"off{i:02d}" for i in range(1, 18)} | {f"ml{i:02d}" for i in range(1, 14)} <= ids


def test_generated_refusals_follow_the_same_structure():
    refusals = [json.loads(line) for line in (ROOT / "eval/refusal_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = {q["id"] for q in refusals}
    assert len(ids) == len(refusals) and not ids & {q["id"] for q in QUESTIONS}
    for q in refusals:
        assert list(q)[: len(KEYS)] == KEYS and set(q) == set(KEYS) | {"kind"}, q["id"]
        assert q["type"] in TYPES and q["cluster"] == "", q["id"]
        assert (q["expect"], q["route"]) == ("refuse", "neither"), q["id"]
        assert q["kind"] in ("general", "academic", "decline_task", "near_miss"), q["id"]
        assert q["lang"] == "en" or q["source"].startswith("translation of rf"), q["id"]

def test_rubric_questions_carry_a_reference_answer_and_numbered_rubric_items():
    rubric = [q for q in QUESTIONS if RUBRIC_KEYS & set(q)]
    assert len(rubric) == 25
    for q in rubric:
        assert RUBRIC_KEYS <= set(q) and q["expect"] == "answer" and q["reference_answer"].strip(), q["id"]
        assert [r["id"] for r in q["rubric"]] == [f"r{i}" for i in range(1, len(q["rubric"]) + 1)], q["id"]
        assert 3 <= len(q["rubric"]) <= 5 and all(r["type"] in ("core", "detail") and r["criterion"] for r in q["rubric"]), q["id"]


def test_refusal_generator_stops_before_writing_a_short_set(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "eval"))
    import make_refusal_questions as gen
    monkeypatch.setattr(gen, "OUTPUT", tmp_path / "refusal_questions.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(gen, "chat", lambda *a, **k: "")
    monkeypatch.setattr(gen, "json_list", lambda text: ["Only one question this time?"])  # every try: one new question
    monkeypatch.setattr(sys, "argv", ["make_refusal_questions.py"])
    import pytest
    with pytest.raises(SystemExit, match="unchanged"):
        gen.main()
    assert not (tmp_path / "refusal_questions.jsonl").exists()
