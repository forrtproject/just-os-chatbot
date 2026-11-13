"""eval/context_eval.py (#14): the question file, the judge parsing and the tables; offline."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import context_eval  # noqa: E402


def test_every_chat_has_turns_a_gold_question_and_labels():
    chats = [json.loads(line) for line in open("eval/context_questions.jsonl", encoding="utf-8")]
    assert len({c["id"] for c in chats}) == len(chats) >= 100
    for c in chats:
        assert c["history"] and c["question"] and c["gold"] and c["expect"] in ("answer", "refuse"), c["id"]
        assert c["split"] in ("tune", "report") and (c["expect"] == "refuse") == (c["route"] == ["off_topic"]), c["id"]
        assert set(c["route"]) <= {"open_science", "forrt", "both", "off_topic"}, c["id"]


def test_judge_prompt_and_score():
    chat = {"history": ["What is preregistration?"], "question": "What are its criticisms?",
            "gold": "What are the criticisms of preregistration?", "expect": "answer", "must_keep": ["preregistration"]}
    prompt = context_eval.judge_prompt(chat, "It is rigid [0].")
    assert "What are the criticisms of preregistration?" in prompt and "Must keep: preregistration" in prompt
    assert "declines" in context_eval.judge_prompt({**chat, "expect": "refuse"}, "Sorry, open science only.")
    assert context_eval.parse_score('Sure: {"score": 2, "reason": "answers it"}') == (2, "answers it")
    assert context_eval.parse_score("no json")[0] is None


def test_source_recall_and_tables():
    assert context_eval.source_recall(["a", "b"], ["b", "c"]) == 0.5
    assert context_eval.source_recall(["a"], []) is None
    rows = [{"run": run, "method": m, "id": "a01", "group": "needs_context", "score": s, "route_ok": 1,
             "recall": 0.5 if m != "oracle" else "", "seconds": 2.0, "cost_usd": 0.0001}
            for run, m, s in [(1, "none", 0), (1, "oracle", 2), (2, "none", 1), (2, "oracle", 2)]]
    table = context_eval.summary(rows, ["none", "oracle"])
    assert "| none | 0.50 | 0% | 100% | 50% | 2.0 | 0.10 |" in table
    assert "| needs_context | 1 | 0.50 | 2.00 |" in table and "| none | 0.00 | 1.00 |" in table
