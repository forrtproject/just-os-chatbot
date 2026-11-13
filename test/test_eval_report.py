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
    assert (r["mean_s"], r["p95_s"], r["tokens"], r["usd_per_1k"], r["judge"], r["rubric"]) == (10.8, 10.0, 150, 0.1, None, None)



def test_rubric_coverage_averages_the_questions_with_a_rubric(tmp_path):
    rows = [{**run_row("gl01", "answer", "answered", 5), "rubric_coverage": "0.5"},
            {**run_row("gl02", "answer", "answered", 5), "rubric_coverage": "1.0"},
            {**run_row("pr02", "answer", "answered", 5), "rubric_coverage": ""}]  # no rubric
    write(tmp_path / "run_261112-1600_meta-llama__llama-3.1-8b-instruct.csv", rows)
    assert eval_report.answer_runs(str(tmp_path))[0]["rubric"] == 0.75

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


def test_run_labels_tell_full_runs_forced_runs_and_configurations_apart():
    assert eval_report.run_label("openai__gpt-oss-20b") == {"model": "openai/gpt-oss-20b", "kind": "full pipeline", "config": ""}
    assert eval_report.run_label("openai__gpt-oss-20b__route-forrt")["kind"] == "FORRT pages"
    assert eval_report.run_label("cfg-search-bm25__route-open_science") == {"model": "search-bm25", "kind": "papers",
                                                                           "config": "search-bm25"}


def test_eval_page_shows_pairs_answer_models_and_search(tmp_path):
    import fakeredis
    from just_os.app import FlaskApp
    pair = {"n": 2, "answered": 1, "should_answer": 1, "refused": 1, "should_refuse": 1, "hit": "", "citations_valid": 1,
            "judge_support": 0.9, "mean_s": 3, "usd_per_1k": 0.1}
    write(tmp_path / "pairs_261113-0600.csv", [{"topic_check": "jev", "answer_model": "m/a", "correct": 1.0, **pair},
                                              {"topic_check": "clef", "answer_model": "m/a", "correct": 0.5, **pair}])
    write(tmp_path / "run_261113-0100_m__a__route-open_science.csv", [{**run_row("a", "answer", "answered", 4), "judge_support": 0.7}])
    write(tmp_path / "run_261113-0200_m__a__route-forrt.csv", [run_row("a", "answer", "answered", 2, hit=1)])
    write(tmp_path / "run_261113-0300_cfg-search-bm25__route-open_science.csv", [run_row("a", "answer", "answered", 1, hit=1)])
    assert eval_report.pair_results(str(tmp_path))["checks"] == ["jev", "clef"]  # best mean first
    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app.config.update(EVAL_RESULTS_DIR=str(tmp_path))
    html = flask_app.app.test_client().get("/eval").get_data(as_text=True)
    assert "Best pair<b>jev + m/a</b>" in html and "hsl(120 65% 85%)" in html  # summary card and green cell
    assert "Best search<b>search-bm25</b>" in html and "<td>m/a</td><td><b>0.7</b></td>" in html


def test_best_defaults_take_only_complete_runs_and_the_newest_topic_check_run(tmp_path):
    def run(name, judge, n=2, errors=0):
        rows = [{**run_row(str(i), "answer", "error" if i < errors else "answered", 3), "judge_support": judge} for i in range(n)]
        write(tmp_path / f"run_261113-0{name[0]}00_{name}__route-open_science.csv", rows)

    run("1a__good", 0.7)
    run("2b__partial", 0.95, n=1)  # higher judge, but not all questions
    run("3c__broken", 0.9, errors=1)  # errors
    def classify(stamp, rows):
        write(tmp_path / f"classify_{stamp}.csv", [{"model": m, "id": str(i), "gold": "forrt", "predicted": p, "seconds": s, "usd": 0}
                                                   for m, p, s in rows for i in range(2)])
    classify("261112-0900", [("router: jev", "forrt", 0.3), ("router: cosine", "neither", 0.1)])
    classify("261112-1700", [("router: jev", "forrt", 0.3), ("router: banded", "forrt", 0.2), ("m/llm", "forrt", 0.1)])
    chosen = eval_report.best_defaults(str(tmp_path), ["", "jev", "banded", "cosine"])
    assert chosen == {"CITATION_MODEL": "1a/good", "ROUTER": "banded"}  # tie on accuracy: the faster router
    assert eval_report.best_defaults(str(tmp_path / "none"), ["jev"]) == {}


def test_auto_defaults_set_chat_and_arena_defaults(tmp_path, monkeypatch):
    import fakeredis
    from config import settings
    from just_os.app import FlaskApp
    write(tmp_path / "run_261113-0100_m__best__route-open_science.csv", [{**run_row("a", "answer", "answered", 3), "judge_support": 0.9}])
    monkeypatch.setitem(settings.DEFAULT_CONFIG, "AUTO_DEFAULTS", True)
    monkeypatch.setitem(settings.DEFAULT_CONFIG, "EVAL_RESULTS_DIR", str(tmp_path))
    monkeypatch.setitem(settings.DEFAULT_CONFIG, "ARENA_MODELS", "x/other,m/best")
    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app.config.update(ARENA_ENABLED=True)
    assert flask_app.config["CITATION_MODEL"] == "m/best"
    html = flask_app.app.test_client().get("/arena").get_data(as_text=True)
    assert html.index("m/best (default)") < html.index("x/other")
