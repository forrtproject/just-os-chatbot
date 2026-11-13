"""eval/answers.py (#54): eval runs, arena rounds and chat turns in one answer record format."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import answers  # noqa: E402

FIELDS = ["id", "question", "outcome", "answered_from", "retrieval", "seconds", "cost_usd", "answer", "passages", "sources"]


def test_run_records_carry_sources_with_passages_and_the_model_from_the_file_name(tmp_path):
    run = tmp_path / "run_261113-0800_openai__gpt-oss-20b__route-forrt.csv"
    with open(run, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({"id": "pr01", "question": "What?", "outcome": "answered", "answered_from": "papers",
                    "retrieval": "hybrid+rerank", "seconds": "3.5", "cost_usd": "0.0001", "answer": "It is [0].",
                    "passages": json.dumps(["the passage"]), "sources": json.dumps([{"n": 0, "title": "T", "doi": "10.1/a"}])})
        w.writerow({"id": "rf01", "question": "Cook?", "outcome": "refused", "answer": "x" * 2000, "passages": "[]",
                    "sources": "[]"})
    first, second = answers.from_run(run)
    assert first["answer_id"] == "run_261113-0800_openai__gpt-oss-20b__route-forrt#pr01" and first["question_id"] == "pr01"
    assert first["config"]["answer_model"] == "openai/gpt-oss-20b" and first["config"]["route"] == "forrt"
    assert first["sources"] == [{"n": 0, "title": "T", "doi": "10.1/a", "passage": "the passage"}]
    assert first["seconds"] == 3.5 and first["complete"] and not second["complete"]  # 2,000 characters: cut


def test_arena_and_chat_records(tmp_path):
    rounds = tmp_path / "rounds.jsonl"
    rounds.write_text(json.dumps({"time": "t", "battle_id": "b1", "question": "Q", "answers": {
        "A": {"model": "m1", "seconds": 2.0, "answer": "<p>a</p>", "sources": "[1] Paper one. [2] Paper two."}}}) + "\n")
    (record,) = answers.from_rounds(str(rounds))
    assert record["answer_id"] == "arena:b1:m1" and record["question_id"] == ""
    assert [s["title"] for s in record["sources"]] == ["Paper one.", "Paper two."]
    chats = tmp_path / "chats.jsonl"
    chats.write_text("".join(json.dumps({"turn_id": t, "question": "Q", "model": "m", "outcome": o, "answer": "a",
                                          "references": [{"number": 1, "title": "T", "url": "u", "snippet": "s"}]}) + "\n"
                             for t, o in [("t1", "forrt_lookup"), ("t2", "off_topic"), ("t3", "error")]))
    got = [(r["answer_id"], r["outcome"], r["answered_from"]) for r in answers.from_chats(str(chats))]
    assert got == [("chat:t1", "answered", "forrt pages"), ("chat:t2", "refused", ""), ("chat:t3", "error", "")]
    assert answers.from_rounds(str(tmp_path / "none.jsonl")) == [] == answers.from_chats(str(tmp_path / "none.jsonl"))


def test_load_reads_every_store_file(tmp_path):
    answers.write([answers.record("x#1", "run", "Q", {}, "a")], tmp_path / "answers_x.jsonl")
    answers.write([answers.record("chat:t", "chat", "Q", {}, "b")], tmp_path / "answers_chat.jsonl")
    assert set(answers.load(tmp_path)) == {"x#1", "chat:t"}
