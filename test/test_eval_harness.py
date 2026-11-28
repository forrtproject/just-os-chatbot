"""Eval harness accuracy: what eval/run.py records, file names and resumes, pair scoring, judges, presets."""

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import classify  # noqa: E402
import cluster_boost  # noqa: E402
import judge  # noqa: E402
import pairs  # noqa: E402
import rubric_judge  # noqa: E402
import run  # noqa: E402
import run_batches  # noqa: E402
import scorecard  # noqa: E402

from config.settings import DEFAULT_CONFIG  # noqa: E402
from just_os import answer_cache, eval_report  # noqa: E402
from just_os.answer_cache import NAMESPACE_KEYS, AnswerCache  # noqa: E402
from test_eval_report import run_row as report_row, write  # noqa: E402
from test_forrt_pages import forrt_in_papers_qualle  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def new_seen():
    return {"ranked": [], "raw": None, "forrt": None, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}


# --- eval/run.py records the turn itself


def test_run_records_the_forrt_pages_read_next_to_the_papers(tmp_path):
    q = forrt_in_papers_qualle(tmp_path, "open_science")
    evidence = {}
    final = list(q.get_response("Which teams can I join?", "chat", evidence=evidence))[-1]
    seen = {**new_seen(), **run.turn_record(evidence)}
    question = {"id": "f1", "question": "Which teams can I join?", "expect": "answer",
                "expected_urls": ["https://forrt.org/about/teams/"]}
    row = run.run_row(question, final, seen, 1.0, {}, "m")

    # the answer model saw [0] the paper and [1] the forrt.org page: both are in the row
    passages = json.loads(row["passages"])
    assert len(passages) == 2 and "Team Credit" in passages[1]
    assert [s["url"] for s in json.loads(row["sources"])] == ["https://x", "https://forrt.org/about/teams/"]
    assert row["outcome"] == "answered" and row["answered_from"] == "papers"
    assert (row["n_citations"], row["citations_valid"]) == (2, 1)  # [1] is the page, not out of range
    assert row["hit"] == 1  # the expected URL was among the pages read


def test_both_route_with_pages_next_to_the_papers_reports_both(tmp_path):
    q = forrt_in_papers_qualle(tmp_path, "both")
    evidence = {}
    final = list(q.get_response("Which teams can I join?", "chat", evidence=evidence))[-1]
    assert final["outcome"] == "both" and evidence["route"] == "both"
    assert run.outcome_of(final) == "answered"


def test_evidence_of_a_named_paper_and_of_the_forrt_route(tmp_path):
    from test_qualle import make_qualle, node
    from test_reference_lookup import PAPERS

    q = make_qualle(False, [], [], "They showed it [0].")
    q.document_retriever.n_context_items = 7
    q.references = SimpleNamespace(match=lambda *questions: ([PAPERS[0]], "title"),
                                   chunks=lambda query, found, n: [node("False-Positive Psychology")])
    evidence = {}
    list(q.get_response("What did False-Positive Psychology show?", "chat", evidence=evidence))
    assert evidence["reference_lookup"] and evidence["page_sources"] == []
    assert [n.metadata["title"] for n in evidence["nodes"]] == ["False-Positive Psychology"]

    from test_forrt_pages import make_pages
    pages, _ = make_pages(tmp_path, ["See the teams page [1]."], [0.95, 0.1])
    q = make_qualle(True, [], [], "unused")
    q.config = {"DECISION_ROUTER": True}
    q.decisions = SimpleNamespace(route=lambda model, query: ("forrt", 0.9, {}))
    q.forrt_pages = pages
    evidence = {}
    final = list(q.get_response("Which teams can I join?", "chat", evidence=evidence))[-1]
    seen = {**new_seen(), **run.turn_record(evidence)}
    row = run.run_row({"id": "f2", "question": "q", "expect": "answer"}, final, seen, 1.0, {}, "m")
    assert row["answered_from"] == "forrt pages" and row["citations_valid"] == 1


def test_forced_route_runs_answer_with_the_banded_router_and_an_embedding_model(tmp_path):
    """--route / --skip-classifier replace Qualle.route; the turn passes query_vector to it (ROUTER=banded)."""
    from test_query_embeddings import CountingEmbed, full_turn_qualle

    q = full_turn_qualle(tmp_path, CountingEmbed())
    q.config = {**q.config, "ROUTER": "banded"}
    run.skip_classifier(q, "open_science")
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    assert final["status"] == "complete" and run.outcome_of(final) == "answered"


def test_outcome_comes_from_the_final_message():
    assert run.outcome_of({"outcome": "off_topic", "message": "anything"}) == "refused"
    assert run.outcome_of({"outcome": "both", "message": ""}) == "answered"
    assert run.outcome_of({"outcome": "forrt", "message": ""}) == "answered"
    assert run.outcome_of({"outcome": "no_sources", "message": "an answer that quotes no refusal text"}) == "no_sources"
    assert run.outcome_of({"status": "error", "outcome": "answered"}) == "error"
    assert run.outcome_of({"message": "a direct answer"}) == "answered"  # no outcome (--no-retrieval): the text decides


def test_text_outside_the_response_markers_is_not_cited_or_judged():
    ranked = [SimpleNamespace(text=f"passage {i}", metadata={"title": f"t{i}"}) for i in range(2)]
    seen = {**new_seen(), "ranked": ranked,
            "raw": "Thinking [7]. [Response_Start]Open data helps [0].[Response_End] Passage [5] echoed"}
    row = run.run_row({"id": "a", "question": "q", "expect": "answer"}, {"outcome": "answered"}, seen, 1.0, {}, "m")
    assert row["answer"] == "Open data helps [0]." and row["n_citations"] == 1 and row["citations_valid"] == 1


def test_answers_and_passages_are_whole_by_default():
    assert run.build_parser().parse_args([]).truncate is False
    long = "x" * 3000
    seen = {**new_seen(), "raw": long, "ranked": [SimpleNamespace(text="y" * 1000, metadata={"title": "t"})]}
    q = {"id": "a", "question": "q", "expect": "answer"}
    row = run.run_row(q, {"outcome": "answered"}, seen, 1.0, {}, "m")
    assert len(row["answer"]) == 3000 and len(json.loads(row["passages"])[0]) == 1000
    row = run.run_row(q, {"outcome": "answered"}, seen, 1.0, {}, "m", truncate=True)
    assert len(row["answer"]) == 2000 and len(json.loads(row["passages"])[0]) == 800


def test_retrieval_cache_key_sees_the_index_corrections_clusters_and_settings(tmp_path):
    corrections, clusters_file = tmp_path / "corrections.json", tmp_path / "clusters.csv"
    corrections.write_text('{"exclude": {}}')
    clusters_file.write_text("doi,cluster\n")
    config = {"INDEX_CORRECTIONS_FILE": str(corrections), "CLUSTERS_FILE": str(clusters_file),
              "RERANK_MODEL": "a", "FORRT_IN_PAPERS": True, "CLUSTER_BOOST": 0.02, "SKIP_REFERENCE_CHUNKS": True}
    key = run.retrieval_settings(config)
    for change in ({"RERANK_MODEL": "b"}, {"FORRT_IN_PAPERS": False}, {"CLUSTER_BOOST": 0}, {"SKIP_REFERENCE_CHUNKS": False}):
        assert run.retrieval_settings({**config, **change}) != key, change
    corrections.write_text('{"exclude": {"10.1/x": "another work"}}')
    assert run.retrieval_settings(config) != key
    key = run.retrieval_settings(config)
    clusters_file.write_text("doi,cluster\n10.1/y,C1\n")
    assert run.retrieval_settings(config) != key


# --- eval/run_batches.py and eval/scorecard.py


def test_run_batches_default_general_model_is_the_bots():
    assert run_batches.build_parser().parse_args(["--since", "261128-1200", "m"]).general_model == DEFAULT_CONFIG["GENERAL_MODEL"]


def test_run_files_sort_minute_and_second_stamps_and_respect_since(tmp_path, monkeypatch):
    monkeypatch.setattr(run_batches, "RESULTS", tmp_path)
    for name in ("run_261128-1159_m.csv", "run_261128-1205_m.csv", "run_261128-120530_m.csv", "run_261128-120501_m.csv"):
        (tmp_path / name).write_text("id\n1\n")
    names = [f.name for f in run_batches.run_files("m", "261128-1200")]
    assert names == ["run_261128-1205_m.csv", "run_261128-120501_m.csv", "run_261128-120530_m.csv"]
    assert [f.name for f in run_batches.run_files("m", "261128-120502")] == ["run_261128-120530_m.csv"]


def test_a_resume_with_other_questions_or_settings_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(run_batches, "RESULTS", tmp_path)
    lines = ['{"id": "a"}\n', '{"id": "b"}\n']
    run_batches.check_manifest("m/x", "261128-1200", lines, ["--model", "m/x"], {"RERANK": True}, resuming=False)
    # the same setup resumes
    run_batches.check_manifest("m/x", "261128-1200", lines, ["--model", "m/x"], {"RERANK": True}, resuming=True)
    with pytest.raises(SystemExit, match="questions"):
        run_batches.check_manifest("m/x", "261128-1200", lines[:1], ["--model", "m/x"], {"RERANK": True}, resuming=True)
    with pytest.raises(SystemExit, match="settings"):
        run_batches.check_manifest("m/x", "261128-1200", lines, ["--model", "m/x"], {"RERANK": False}, resuming=True)
    # another --since that still picks up the recorded series' files is checked too
    with pytest.raises(SystemExit, match="questions"):
        run_batches.check_manifest("m/x", "261128-1159", lines[:1], ["--model", "m/x"], {"RERANK": True}, resuming=True)
    # a new series (no run files since its --since yet) records its own setup
    run_batches.check_manifest("m/x", "261128-1300", lines[:1], ["--model", "m/x"], {}, resuming=False)
    assert json.loads((tmp_path / "batch_m__x.json").read_text())["since"] == "261128-1300"


def test_scorecard_finds_runs_with_a_forced_route(tmp_path, monkeypatch):
    monkeypatch.setattr(run_batches, "RESULTS", tmp_path)
    for name in ("run_261127-1000_cfg-a.csv", "run_261128-1000_cfg-a__route-open_science.csv",
                 "run_261128-110000_cfg-a__route-open_science.csv", "run_261128-1000_cfg-a__route-forrt.csv"):
        (tmp_path / name).write_text("id\n")
    assert [p.name for p in scorecard.latest_runs(["a"], "open_science")] == ["run_261128-110000_cfg-a__route-open_science.csv"]
    assert [p.name for p in scorecard.latest_runs(["a"])] == [
        "run_261127-1000_cfg-a.csv", "run_261128-110000_cfg-a__route-open_science.csv", "run_261128-1000_cfg-a__route-forrt.csv"]


def test_run_files_with_seconds_are_read_by_the_eval_page(tmp_path):
    write(tmp_path / "run_261128-120530_m__a.csv", [report_row("a", "answer", "answered", 3)])
    assert [r["run"] for r in eval_report.answer_runs(str(tmp_path))] == ["261128-120530"]
    assert pairs.routed_runs(tmp_path) == {}
    for route in ("open_science", "forrt"):
        write(tmp_path / f"run_261128-120530_m__a__route-{route}.csv", [report_row("a", "answer", "answered", 3)])
    assert set(pairs.routed_runs(tmp_path)) == {"m/a"}


def test_best_defaults_drop_the_provider_pin(tmp_path):
    write(tmp_path / "run_261113-0100_m__fast@groq__route-open_science.csv",
          [{**report_row(str(i), "answer", "answered", 3), "judge_support": 0.9, "rubric_coverage": 0.9} for i in range(2)])
    assert eval_report.best_defaults(str(tmp_path), [""])["CITATION_MODEL"] == "m/fast"
    write(tmp_path / "run_261113-0200_m__judged@groq__route-open_science.csv",
          [{**report_row(str(i), "answer", "answered", 3), "judge_support": 0.95} for i in range(2)])
    (tmp_path / "run_261113-0100_m__fast@groq__route-open_science.csv").unlink()
    assert eval_report.best_defaults(str(tmp_path), [""])["CITATION_MODEL"] == "m/judged"  # judge only, no rubric yet


# --- eval/pairs.py


def test_pairs_do_not_count_no_sources_as_a_refusal_and_flag_both():
    papers = {"r1": {"expect": "refuse", "outcome": "no_sources", "seconds": "1", "cost_usd": "0"},
              "r2": {"expect": "refuse", "outcome": "refused", "seconds": "1", "cost_usd": "0"},
              "a1": {"expect": "answer", "outcome": "answered", "seconds": "1", "cost_usd": "0", "hit": "1"}}
    decisions = {"r1": ("open_science", 0, 0), "r2": ("neither", 0, 0), "a1": ("both", 0, 0)}
    result = pairs.score(decisions, papers, {})
    assert (result["refused"], result["should_refuse"], result["no_sources_refuse"]) == (1, 2, 1)
    assert result["correct"] == round(2 / 3, 3)  # the no-sources question is not credited
    assert result["both_as_papers"] == 1 and result["answered"] == 1
    assert set(pairs.FIELDS) >= {"no_sources_refuse", "both_as_papers"}


# --- eval/classify.py and eval/cluster_boost.py


def test_classify_gold_without_expect():
    assert classify.gold({"question": "How do I join FORRT?"}, False) == "open_science"
    assert classify.gold({"question": "pizza?", "route": "neither"}, False) == "off_topic"
    assert classify.gold({"question": "q", "expect": "refuse"}, False) == "off_topic"


def test_cluster_boost_limiter_applies_the_apps_exclusions_and_reference_filter(tmp_path):
    corrections = tmp_path / "corrections.json"
    corrections.write_text(json.dumps({"exclude": {"10.1234/bad": "another work"}}))
    config = {"MAX_CHUNKS": 7, "MAX_CHUNKS_PER_DOC": 2, "INDEX_CORRECTIONS_FILE": str(corrections),
              "SKIP_REFERENCE_CHUNKS": True}
    limiter = cluster_boost.make_limiter(config)
    text = "Open science makes research easier to check, because data, code and materials can be read by others. " * 3
    refs = "Smith, J. (2010). Title. Journal, 1(2), 3-4. Doe, A. (2011). T. J, 2, 5. Roe, B. (2012). T. J, 3, 6. " * 3
    nodes = [SimpleNamespace(text=text, metadata={"title": "Excluded", "doi": "10.1234/bad"}),
             SimpleNamespace(text=refs, metadata={"title": "Reference list", "doi": "10.1234/refs"}),
             SimpleNamespace(text=text, metadata={"title": "Kept", "doi": "10.1234/good"})]
    assert [n.metadata["title"] for n in limiter.limit_per_document(nodes, "What is open science?")] == ["Kept"]


# --- eval/judge.py and eval/rubric_judge.py


def test_failed_judge_calls_are_counted_not_hidden():
    row = {"outcome": "answered", "passages": json.dumps(["p0"]), "answer": "A [0]."}
    failing = SimpleNamespace(_structured_output=lambda *a: None)  # no answer from the judge model
    assert judge.judge_row(failing, row) is None
    raising = SimpleNamespace(_structured_output=lambda *a: (_ for _ in ()).throw(RuntimeError("API down")))
    assert judge.judge_row(raising, row) is None
    assert judge.judge_row(failing, {**row, "outcome": "refused"}) == ""  # nothing to judge is not a failure
    assert judge.summary([0.5, 1.0, "", None]) == "judged 2, mean 0.750; failed judge calls 1 (empty, not in the mean)"
    assert "failed judge calls 2 (empty, not in the mean): a, b" in rubric_judge.failure_summary([0.5], ["a", "b"])


def test_judges_read_only_the_shown_answer():
    prompts = []
    processor = SimpleNamespace(_structured_output=lambda prompt, *a: prompts.append(prompt) or 1)
    row = {"outcome": "answered", "passages": json.dumps(["p0"]),
           "answer": "[Response_Start]Shown [0].[Response_End] echoed passage [3]"}
    assert judge.judge_row(processor, row) == 1.0
    assert "Shown [0]." in prompts[0] and "echoed passage" not in prompts[0]
    recall_row = {"retrieved_dois": "10.1/a 10.1/b", "answer": "[Response_Start]Shown [0].[Response_End] Passage [1]"}
    assert rubric_judge.doi_recall(recall_row, {"expected_dois": ["10.1/a", "10.1/b"]}) == 0.5


# --- eval/configs.json


def test_dated_presets_pin_the_settings_they_compared():
    configs = json.loads((ROOT / "eval/configs.json").read_text(encoding="utf-8"))
    dated = {k: v for k, v in configs.items() if k.startswith("gemma4+") and k[-6:].isdigit()}
    assert set(dated) == {"gemma4+defaults-261126", "gemma4+cluster-boost-261126", "gemma4+skip-refs-261126",
                          "gemma4+glossary-swap-261127"}
    for name, settings in dated.items():
        assert {"CLUSTER_BOOST", "SKIP_REFERENCE_CHUNKS", "VECTOR_STORE", "RERANK", "SEARCH_MODE"} <= set(settings), name
        assert all(k in DEFAULT_CONFIG for k in settings), name
    differ = lambda a, b: {k for k in set(dated[a]) | set(dated[b]) if dated[a].get(k) != dated[b].get(k)}  # noqa: E731
    assert differ("gemma4+defaults-261126", "gemma4+cluster-boost-261126") == {"CLUSTER_BOOST", "CLUSTER_BOOST_MARGIN"}
    assert differ("gemma4+cluster-boost-261126", "gemma4+skip-refs-261126") == {"SKIP_REFERENCE_CHUNKS"}


# --- just_os/answer_cache.py


def answer_cache_for(**config):
    settings = {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9, "ANSWER_CACHE_MAX_ITEMS": 5, **config}
    return AnswerCache(fakeredis.FakeRedis(), SimpleNamespace(get_query_embedding=lambda q: [1.0, 0.0]), settings)


def test_answer_cache_is_off_by_default_and_keyed_by_every_answer_setting(tmp_path):
    assert DEFAULT_CONFIG["ANSWER_CACHE_TTL"] == 0
    new_keys = ("ROUTER", "CLUSTER_BOOST", "SKIP_REFERENCE_CHUNKS", "FORRT_IN_PAPERS", "ADAPTIVE_TOP_K", "REFERENCE_LOOKUP",
                "VERIFY_CITATIONS", "TEMPERATURE", "MAX_ANSWER_TOKENS", "BASE_URL")
    assert set(new_keys) <= set(NAMESPACE_KEYS)
    base = answer_cache_for().key
    for key in new_keys:
        assert answer_cache_for(**{key: "changed"}).key != base, key


def test_answer_cache_key_changes_with_the_index_and_its_corrections(tmp_path):
    store, corrections = tmp_path / "vs", tmp_path / "corrections.json"
    store.mkdir()
    (store / "docstore.json").write_text("{}")
    corrections.write_text('{"exclude": {}}')
    config = {"VECTOR_STORE": str(store), "INDEX_CORRECTIONS_FILE": str(corrections)}
    key = answer_cache_for(**config).key
    corrections.write_text('{"exclude": {"10.1/x": "another work"}}')
    assert answer_cache_for(**config).key != key
    key = answer_cache_for(**config).key
    (store / "docstore.json").write_text('{"docs": 1}')  # changed in place (fix_index_titles, add_to_index)
    assert answer_cache_for(**config).key != key
    assert answer_cache.index_fingerprint({}) == [None, None, None]


def test_merged_run_csv_keeps_the_new_columns_readable(tmp_path):
    """A run row as eval/run.py writes it has every FIELDS column."""
    seen = new_seen()
    row = run.run_row({"id": "a", "question": "q", "expect": "refuse"}, {"outcome": "off_topic"}, seen, 0.5, {}, "m")
    path = tmp_path / "run_261128-120000_m.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=run.FIELDS)
        writer.writeheader()
        writer.writerow(row)
    assert row["outcome"] == "refused" and row["correct"] == 1 and set(row) == set(run.FIELDS)
