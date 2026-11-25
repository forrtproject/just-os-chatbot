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


def test_classifier_summary_scores_tasks_to_decline_apart(tmp_path):
    rows = [{"model": "jev", "id": "1", "gold": "neither", "predicted": "neither", "seconds": 1, "usd": 0},
            {"model": "jev", "id": "2", "gold": "decline_task", "predicted": "open_science", "seconds": 1, "usd": 0},
            {"model": "jev", "id": "3", "gold": "decline_task", "predicted": "neither", "seconds": 1, "usd": 0}]
    write(tmp_path / "classify_261113-1200.csv", rows)
    (jev,) = eval_report.classifier_runs(str(tmp_path))
    assert (jev["n"], jev["accuracy"], jev["false_answers"], jev["tasks_let_through"]) == (1, 1.0, 0, "1/2")
    rows.append({"model": "jev", "id": "4", "gold": "decline_task", "predicted": "", "seconds": 1, "usd": 0})  # failed call
    rows.append({"model": "llm", "id": "2", "gold": "decline_task", "predicted": "neither", "seconds": 1, "usd": 0})
    write(tmp_path / "classify_261113-1200.csv", rows)
    by = {r["model"]: r for r in eval_report.classifier_runs(str(tmp_path))}
    assert (by["jev"]["errors"], by["jev"]["tasks_let_through"]) == (1, "1/2")  # an error, not a decline
    assert (by["llm"]["n"], by["llm"]["accuracy"], by["llm"]["tasks_let_through"]) == (0, None, "0/1")


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
    assert html.index("The questions") < html.index("Answer models") < html.index("Run history")
    assert "<td>yes</td>" in html and "local (0)" in html  # bge-m3: multilingual, no API cost


def test_uni_price_ignores_the_provider_and_says_na_for_missing_models():
    assert eval_report.uni_price("openai/gpt-oss-120b@groq") == "0.15 / 0.6"
    assert eval_report.uni_price("qwen/qwen3.7-flash") == "NA"


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
    assert "hsl(120 65% 85%)" in html  # green cell
    assert "<b>jev + m/a</b>" not in html  # no best-pair card: m/a has no rubric score and is not on uniGPT's API
    assert "<b>search-bm25</b>" in html and "Score = (2 × Judge + Rubric coverage) / 3" in html


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


def test_a_run_of_tasks_to_decline_only_never_sets_the_topic_check(tmp_path):
    rows = [{"model": m, "id": str(i), "gold": g, "predicted": p, "seconds": s, "usd": 0}
            for m, g, p, s in [("router: jev", "forrt", "neither", 0.3), ("router: banded", "forrt", "neither", 0.5),
                               ("router: cosine", "decline_task", "neither", 0.1)] for i in range(2)]
    write(tmp_path / "classify_261113-1000.csv", rows)
    assert eval_report.best_defaults(str(tmp_path), ["jev", "banded", "cosine"]) == {"ROUTER": "jev"}


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


def test_score_weighs_the_citation_judge_twice_and_picks_the_default():
    assert eval_report.score({"judge": 0.75, "rubric": 0.69}) == 0.73  # (2 x 0.75 + 0.69) / 3
    assert eval_report.score({"judge": 0.75, "rubric": None}) is None


def test_default_answer_model_uses_the_2_to_1_score(tmp_path):
    def run(name, judge, rubric):
        write(tmp_path / f"run_261113-0100_{name}__route-open_science.csv",
              [{**run_row(str(i), "answer", "answered", 3), "judge_support": judge, "rubric_coverage": rubric} for i in range(2)])
    run("m__cites", 0.75, 0.69)   # score 0.73
    run("m__covers", 0.60, 0.95)  # score 0.717: better coverage, weaker citations
    assert eval_report.best_defaults(str(tmp_path), [""])["CITATION_MODEL"] == "m/cites"


def test_question_spread_counts_the_question_files(tmp_path):
    import json
    (tmp_path / "questions.jsonl").write_text("\n".join(json.dumps(q) for q in [
        {"id": "a", "route": "open_science", "expect": "answer", "lang": "en", "type": "How-to", "expected_dois": ["10.1/a"]},
        {"id": "b", "route": "neither", "expect": "refuse", "lang": "de", "type": "Out of scope", "rubric": []}]))
    (tmp_path / "forrt_questions.jsonl").write_text(json.dumps({"id": "o1", "kind": "org"}))
    spread = eval_report.question_spread(str(tmp_path))
    assert spread["main"]["n"] == 2 and dict(spread["main"]["expect"]) == {"answer": 1, "refuse": 1}
    assert (spread["main"]["with_dois"], spread["main"]["with_rubric"], spread["forrt"]["n"]) == (1, 1, 1)


def test_topics_page_shows_the_newest_topic_map(tmp_path):
    import fakeredis
    from just_os.app import FlaskApp
    (tmp_path / "topic_map_261112.html").write_text("<html>old map</html>", encoding="utf-8")
    (tmp_path / "topic_map_261113.html").write_text("<html>new map</html>", encoding="utf-8")
    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app.config.update(EVAL_RESULTS_DIR=str(tmp_path))
    client = flask_app.app.test_client()
    page = client.get("/topics").get_data(as_text=True)
    assert 'href="/topics"' in page and 'src="/topics/map"' in page and "261113" in page
    assert client.get("/topics/map").get_data(as_text=True) == "<html>new map</html>"
    flask_app.config.update(EVAL_RESULTS_DIR=str(tmp_path / "none"))
    assert client.get("/topics").status_code == 404 and 'href="/topics"' not in client.get("/eval").get_data(as_text=True)


def test_an_empty_pair_table_counts_as_none(tmp_path):
    (tmp_path / "pairs_261113-1235.csv").write_text("topic_check,answer_model,n,correct\n", encoding="utf-8")
    assert eval_report.pair_results(str(tmp_path)) == {}


def test_every_answer_run_names_its_setting_and_today_comes_first():
    configs = {"voyage+gemma": {"EMBEDDING_MODEL": "mongodb/voyage-4-large", "CITATION_MODEL": "google/gemma-4-31b-it"},
               "gemma4+cap2": {"CITATION_MODEL": "google/gemma-4-31b-it", "MAX_CHUNKS_PER_DOC": 2}}
    old = {"run": "261113-1200", "model": "openai/gpt-oss-20b", "config": ""}
    assert eval_report.setting(old, configs) == {"answer_model": "openai/gpt-oss-20b", "setting": "bge-m3 · hybrid + re-ranker"}
    voyage = {"run": "261120-0343", "model": "voyage+gemma", "config": "voyage+gemma"}
    assert eval_report.setting(voyage, configs) == {"answer_model": "google/gemma-4-31b-it", "setting": "Voyage-4-large · vector"}
    cap = {"run": "261125-1347", "model": "gemma4+cap2", "config": "gemma4+cap2"}
    assert eval_report.setting(cap, configs)["setting"] == "bge-m3 · vector · ≤ 2 chunks per paper"
    glossary = {"run": "261125-1800", "model": "g", "config": "g"}
    assert eval_report.setting(glossary, {"g": {"VECTOR_STORE": "data/processed/vs_latest_bge-m3_glossary"}})["setting"] ==         "bge-m3 + FORRT glossary · vector"
    runs = [{"run": "261119-1900", "model": "google/gemma-4-31b-it", "config": "", "kind": "papers", "score": 0.73},
            {"run": "261113-1200", "model": "google/gemma-4-31b-it", "config": "", "kind": "papers", "score": 0.70},
            {"run": "261113-1200", "model": "x", "config": "search-bm25", "kind": "papers", "score": 0.9},  # search table
            {"run": "261119-1900", "model": "m", "config": "", "kind": "FORRT pages", "score": None}]
    today, other = eval_report.answer_model_rows(runs)
    assert [(r["answer_model"], r["score"]) for r in today] == [("google/gemma-4-31b-it", 0.73)]
    assert [r["setting"] for r in other] == ["bge-m3 · hybrid + re-ranker"] and today[0]["why"].startswith("Production")


def test_unigpt_cost_uses_the_api_flat_rate_and_only_models_the_api_offers():
    gemma = {"answer_model": "google/gemma-4-31b-it", "tok_in": 4000, "tok_out": 500}
    assert eval_report.unigpt_credits_per_1k(gemma) == 2.5  # (4000 x 0.5 + 500 x 1) / 1M x 1000
    assert eval_report.unigpt_credits_per_1k({"answer_model": "openai/gpt-oss-120b@groq", "tok_in": 0, "tok_out": 1000}) == 1.0
    assert eval_report.unigpt_credits_per_1k({"answer_model": "openai/gpt-6-luna", "tok_in": 1, "tok_out": 1}) is None


def test_best_pair_weighs_quality_speed_cost_and_language_not_one_number():
    def pair(check, model, correct, usd):
        return {"topic_check": check, "answer_model": model, "correct": correct, "usd_per_1k": usd}

    def model(name, score, p95, credits, non_en, errors=0):
        return {"answer_model": name, "score": score, "p95_s": p95, "uni_credits": credits, "judge_non_en": non_en,
                "errors": errors, "n": 172}

    today = [model("meta/muse-glimmer-30b", 0.755, 35.0, 3.6, 0.90),      # best score, too slow
             model("google/gemma-4-31b-it", 0.729, 14.1, 2.7, 0.92),       # near the best, fast, cheap
             model("openai/gpt-oss-120b@groq", 0.671, 5.2, 3.6, 0.82),     # fastest, weaker
             model("qwen/qwen3.7-flash", 0.75, 6.0, 1.0, 0.95),            # not on uniGPT's API
             model("deepseek/deepseek-v4-flash", 0.74, 12.0, 3.1, 0.80, errors=1)]
    rows = [pair("jev", "google/gemma-4-31b-it", 0.959, 0.64), pair("banded", "google/gemma-4-31b-it", 0.953, 0.63),
            pair("jev", "meta/muse-glimmer-30b", 0.959, 2.5), pair("jev", "openai/gpt-oss-120b@groq", 0.959, 1.2),
            pair("jev", "qwen/qwen3.7-flash", 0.97, 0.2), pair("jev", "deepseek/deepseek-v4-flash", 0.97, 0.4),
            pair("cosine", "google/gemma-4-31b-it", 0.87, 0.6), pair("none", "google/gemma-4-31b-it", 0.04, 0.6)]
    choice = eval_report.best_pair({"rows": rows}, today)
    assert (choice["best"]["topic_check"], choice["best"]["answer_model"]) == ("banded", "google/gemma-4-31b-it")
    # the same model and score: the cheaper topic check first; gpt-oss is more than 0.06 below Muse's 0.755
    assert [p["topic_check"] + "+" + p["answer_model"] for p in choice["shortlist"]] == [
        "banded+google/gemma-4-31b-it", "jev+google/gemma-4-31b-it"]
    assert choice["excluded"] == {"answer model not on uniGPT's API": 1, "errors or an unfinished run": 1, "no topic check": 1,
                                  "quality not near the best": 2, "95% of answers slower than 15 s": 1}
    assert choice["shortlist"][0]["balance"] == round(2 * 0.729 / 0.755 + 1 + 1, 3)


def test_auto_defaults_reach_every_config_that_asks(tmp_path, monkeypatch):
    off = {"AUTO_DEFAULTS": False, "CITATION_MODEL": "old"}
    assert eval_report.apply_auto_defaults(off, ["jev"]) == {} and off["CITATION_MODEL"] == "old"
    monkeypatch.setattr(eval_report, "best_defaults", lambda folder, routers: {"CITATION_MODEL": "new", "ROUTER": "banded"})
    on = {"AUTO_DEFAULTS": True, "CITATION_MODEL": "old", "EVAL_RESULTS_DIR": str(tmp_path)}
    assert eval_report.apply_auto_defaults(on, ["banded"]) == {"CITATION_MODEL": "new", "ROUTER": "banded"}
    assert on["CITATION_MODEL"] == "new"  # in place: the preloaded RAG service (config/gunicorn.py) gets it too
