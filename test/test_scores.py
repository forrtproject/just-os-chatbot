"""eval/scores.py (#54): score rows from runs, reviews and arena ratings, and their agreement."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import scores  # noqa: E402

RUN_FIELDS = ["id", "expect", "outcome", "hit", "citations_valid", "judge_support", "rubric_scores", "rubric_coverage"]
REVIEW_FIELDS = ["reviewer", "item_id", "decision", "correctness", "citation_support", "source_relevance",
                 "completeness", "clarity", "note", "saved_at"]


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_run_rows_give_gold_decision_metrics_and_judges(tmp_path):
    run = tmp_path / "run_x.csv"
    write_csv(run, RUN_FIELDS, [
        {"id": "a", "expect": "answer", "outcome": "answered", "hit": "1", "citations_valid": "1", "judge_support": "0.5",
         "rubric_scores": json.dumps({"r1": 5, "r2": 1}), "rubric_coverage": "0.5"},
        {"id": "b", "expect": "refuse", "outcome": "answered"},
        {"id": "c", "expect": "answer", "outcome": "no_sources"},
    ])
    rows = scores.run_rows(run)
    got = {(r["answer_id"], r["criterion"], r["scorer"]): r["score"] for r in rows}
    assert got[("run_x#a", "decision", "outcome vs expect")] == "right"
    assert got[("run_x#b", "decision", "outcome vs expect")] == "should_refuse"
    assert got[("run_x#c", "decision", "outcome vs expect")] == "should_answer"
    assert got[("run_x#a", "source_relevance", "hit@7")] == 1
    assert got[("run_x#a", "citation_support", "support judge")] == 0.5
    assert got[("run_x#a", "rubric:r1", "rubric judge")] == 5 and got[("run_x#a", "completeness", "rubric judge")] == 0.5
    assert ("run_x#b", "source_relevance", "hit@7") not in got  # an empty cell gives no row


def test_review_rows_keep_each_reviewers_last_save_and_skip_na(tmp_path):
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    base = {"reviewer": "Ann", "item_id": "a", "decision": "right", "correctness": "2", "citation_support": "n/a",
            "source_relevance": "", "completeness": "3", "clarity": "4", "note": "", "saved_at": ""}
    write_csv(reviews / "review_ann_261113-090000.csv", REVIEW_FIELDS, [base])
    write_csv(reviews / "review_ann_261113-100000.csv", REVIEW_FIELDS, [{**base, "correctness": "5"}])
    rows = scores.review_rows(tmp_path / "run_x.csv", reviews)
    got = {r["criterion"]: r["score"] for r in rows}
    assert got == {"decision": "right", "correctness": 5, "completeness": 3, "clarity": 4}
    assert {r["scorer"] for r in rows} == {"Ann"} and {r["answer_id"] for r in rows} == {"run_x#a"}


def test_arena_rows_keep_the_arena_criteria_apart(tmp_path):
    path = tmp_path / "ratings.jsonl"
    path.write_text(json.dumps({"battle_id": "b1", "model": "m", "correct": 4, "references": 3, "clarity": 5}) + "\n")
    rows = scores.arena_rows(str(path))
    assert {r["criterion"]: r["score"] for r in rows} == {"arena_correct": 4, "arena_references": 3, "arena_clarity": 5}
    assert scores.arena_rows(str(tmp_path / "missing.jsonl")) == []


def test_agreement_statistics():
    assert scores.weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], 1, 5) == 1
    assert abs(scores.weighted_kappa([1, 1, 2, 2], [1, 2, 1, 2], 1, 5)) < 1e-9  # what chance gives
    assert abs(scores.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-9
    assert scores.spearman([1, 2, 3], [1, 1, 1]) is None  # no spread, no correlation
    assert scores.ranks([3, 1, 3]) == [1.5, 0, 1.5]


def test_report_compares_people_with_judges_and_with_each_other():
    row = scores.row
    rows = [row("a1", "a", "citation_support", s, scores.SCALE, "person", p) for s, p in [(5, "Ann"), (4, "Bo")]]
    rows += [row("a2", "a", "citation_support", s, scores.SCALE, "person", p) for s, p in [(1, "Ann"), (2, "Bo")]]
    rows += [row("a3", "a", "citation_support", s, scores.SCALE, "person", p) for s, p in [(3, "Ann"), (3, "Bo")]]
    rows += [row(a, "a", "citation_support", s, scores.UNIT, "llm", "support judge") for a, s in [("a1", 1), ("a2", 0), ("a3", 0.5)]]
    rows += [row("a1", "a", "decision", "right", None, "person", "Ann"), row("a1", "a", "decision", "right", None, "metric", "gold")]
    text = scores.report(rows)
    assert "| citation_support | support judge | 3 | 1.00 Spearman |" in text
    assert "| decision | gold | 1 | 1.00 same decision |" in text
    assert "| citation_support | Ann / Bo | 3 |" in text


def test_shared_report_by_configuration_and_on_the_eval_page(tmp_path):
    from just_os import eval_report
    from just_os.scores import by_config
    row = scores.row
    rows = [row("r#a", "a", "correctness", 4, scores.SCALE, "person", "Ann"),
            row("r#a", "a", "correctness", 0.5, scores.UNIT, "llm", "judge"),
            row("r#b", "b", "correctness", 2, scores.SCALE, "person", "Ann")]
    answers = {"r#a": {"config": {"answer_model": "m1", "retrieval": "hybrid+rerank"}}}
    got = {g["config"]: g for g in by_config(rows, answers)}
    assert got["m1, hybrid+rerank"]["scores"]["correctness"] == {"people": (0.75, 1), "judge": (0.5, 1)}
    assert got["unknown model"]["answers"] == 1
    (tmp_path / "scores").mkdir()
    (tmp_path / "scores" / "scores_x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "answers").mkdir()
    (tmp_path / "answers" / "answers_x.jsonl").write_text(json.dumps({"answer_id": "r#a", **answers["r#a"]}) + "\n")
    page = eval_report.people_and_judges(str(tmp_path / "scores"), str(tmp_path / "answers"))
    assert page["rows"] == 3 and page["criteria"] == ["correctness"] and page["labels"]["correctness"] == "Correctness"
    assert eval_report.people_and_judges(str(tmp_path / "none"), str(tmp_path / "none")) == {}
