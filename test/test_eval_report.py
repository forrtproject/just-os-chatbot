"""The /eval page tables (just_os/eval_report.py) and the route."""

import csv

from just_os import eval_report


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_row(id, expect, outcome, seconds, cost="0.0001", correct=1, hit=""):
    return {"id": id, "expect": expect, "outcome": outcome, "correct": correct, "hit": hit,
            "citations_valid": "1" if outcome == "answered" else "", "seconds": seconds,
            "prompt_tokens": 100, "completion_tokens": 50, "cost_usd": cost}


def test_answer_run_summary(tmp_path):
    write(tmp_path / "run_261112-1034_meta-llama__llama-3.1-8b-instruct.csv", [
        run_row("a", "answer", "answered", 10, hit=1), run_row("b", "answer", "no_sources", 2, correct=0, hit=0),
        run_row("c", "refuse", "refused", 1), run_row("d", "refuse", "error", 30, correct=0),
    ])
    write(tmp_path / "run_261111-0900_openai__gpt-oss-20b.csv", [run_row("a", "answer", "answered", 5)])
    runs = eval_report.answer_runs(str(tmp_path))
    assert [r["model"] for r in runs] == ["meta-llama/llama-3.1-8b-instruct", "openai/gpt-oss-20b"]  # newest first
    r = runs[0]
    assert (r["n"], r["correct"], r["answered"], r["refused"], r["errors"], r["hit"]) == (4, 0.5, "1/2", "1/2", 1, 0.5)
    assert (r["mean_s"], r["p95_s"], r["tokens"], r["usd_per_1k"], r["judge"]) == (10.8, 10.0, 150, 0.1, None)


def test_classifier_summary_counts_both_refusal_labels(tmp_path):
    rows = [
        {"model": "jev", "id": "1", "gold": "open_science", "predicted": "open_science", "seconds": 1, "usd": 0.00002},
        {"model": "jev", "id": "2", "gold": "forrt", "predicted": "neither", "seconds": 1, "usd": 0.00002},  # false refusal
        {"model": "jev", "id": "3", "gold": "neither", "predicted": "both", "seconds": 1, "usd": 0.00002},  # false answer
        {"model": "jev", "id": "4", "gold": "off_topic", "predicted": "", "seconds": 8, "usd": 0},  # error
        {"model": "clef", "id": "1", "gold": "open_science", "predicted": "open_science", "seconds": 2, "usd": 0.00006},
    ]
    write(tmp_path / "classify_261112-1200.csv", rows)
    clef, jev = eval_report.classifier_runs(str(tmp_path))  # best accuracy first
    assert clef["accuracy"] == 1.0 and clef["usd_per_1k"] == 0.06
    assert (jev["n"], jev["accuracy"], jev["false_refusals"], jev["false_answers"], jev["errors"], jev["mean_s"]) == (4, 0.25, 1, 1, 1, 2.8)


def test_missing_folder_gives_empty_tables(tmp_path):
    folder = str(tmp_path / "nothing")
    assert eval_report.answer_runs(folder) == eval_report.classifier_runs(folder) == eval_report.embedding_runs(folder) == []


def test_eval_page_renders_the_tables(tmp_path):
    import fakeredis
    from just_os.app import FlaskApp
    write(tmp_path / "run_261112-1034_meta-llama__llama-3.1-8b-instruct.csv", [run_row("a", "answer", "answered", 10)])
    write(tmp_path / "embeddings_261028.csv", [{"model": "E3", "name": "BAAI/bge-m3", "lang": "all", "n": 474, "hit@1": 0.2,
                                                "hit@5": 0.5, "hit@20": 0.7, "mrr@20": 0.4, "ms_per_query": 268.4, "dim": 1024}])
    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app.config.update(EVAL_RESULTS_DIR=str(tmp_path), ARENA_ENABLED=True)
    html = flask_app.app.test_client().get("/eval").get_data(as_text=True)
    assert "meta-llama/llama-3.1-8b-instruct" in html and "BAAI/bge-m3" in html
    assert "eval/classify.py --routers" in html and "No arena ratings yet" in html  # empty states
    assert html.index("Answer models") < html.index("Run history") < html.index("How the numbers are calculated")


def test_by_model_keeps_the_newest_run_and_counts_runs():
    runs = [{"model": "llama", "correct": 0.93, "run": "261112-1034"}, {"model": "gpt", "correct": 0.86, "run": "261105-2123"},
            {"model": "llama", "correct": 0.86, "run": "261105-2059"}]  # newest first, as answer_runs gives them
    rows = eval_report.by_model(runs, "correct")
    assert [(r["model"], r["run"], r["runs"]) for r in rows] == [("llama", "261112-1034", 2), ("gpt", "261105-2123", 1)]
