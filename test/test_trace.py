"""Debug trace of a chat turn (just_os/trace.py): the data behind the chat page's debug panel."""

import contextvars
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from just_os import qualle, trace
from test_qualle import make_qualle, node
from test_rerank import make_retriever


def test_without_debug_the_answer_has_no_trace_and_nothing_is_collected():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    final = list(q.get_response("question", "chat"))[-1]
    assert "debug" not in final
    assert trace.active() is None


def test_debug_answer_has_steps_settings_and_totals():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    final = list(q.get_response("question", "chat", model="chosen/model", debug=True))[-1]
    d = final["debug"]
    names = [s["name"] for s in d["steps"]]
    assert names == ["topic check", "answer"]
    assert d["steps"][0]["route"] == "open_science"
    assert d["info"]["settings"]["answer_model"] == "chosen/model"
    assert d["totals"]["ms"] >= 0 and d["timings"]["total_s"] >= 0
    assert trace.active() is None  # ended with the turn


def test_rephrase_step_keeps_both_questions():
    t = trace.begin()
    try:
        @trace.step("rephrase", lambda result, query: {"from": query, "to": result})
        def rephrase(query):
            return "What are the disadvantages of open data?"

        rephrase("Any disadvantages?")
        step = trace.active().steps[0]
        assert (step["from"], step["to"]) == ("Any disadvantages?", "What are the disadvantages of open data?")
    finally:
        trace.end(t)


def test_a_function_that_calls_itself_is_one_step_and_inner_steps_know_their_parent():
    t = trace.begin()
    try:
        @trace.step("inner")
        def inner():
            return 1

        @trace.step("outer")
        def outer(depth):
            inner()
            return outer(depth - 1) if depth else 0

        outer(2)
        steps = trace.active().steps
        assert [s["name"] for s in steps].count("outer") == 1
        assert {s.get("parent") for s in steps if s["name"] == "inner"} == {"outer"}
    finally:
        trace.end(t)


def test_llm_call_cost_and_tokens_come_from_the_provider_usage():
    manager = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "OPENSCHOLAR_BASE_URL": ""})
    usage = SimpleNamespace(prompt_tokens=1200, completion_tokens=80, model_extra={"cost": 0.00042},
                            prompt_tokens_details=SimpleNamespace(cached_tokens=1000))
    message = SimpleNamespace(content="Answer.", tool_calls=None)
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=usage)

    manager.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                     base_url="https://openrouter.ai/api/v1")
    t = trace.begin()
    try:
        manager.create_chat_completion(model="m", messages=[])
        call = trace.active().calls[0]
    finally:
        trace.end(t)
    assert (call["tokens_in"], call["tokens_out"], call["tokens_cached"], call["cost"]) == (1200, 80, 1000, 0.00042)
    assert seen["extra_body"] == {"usage": {"include": True}}  # OpenRouter reports the cost

    seen.clear()
    manager.create_chat_completion(model="m", messages=[])
    assert "extra_body" not in seen  # without a trace the call is as before


def test_usage_field_only_for_openrouter():
    manager = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://llm.hpc.rug.nl/", "OPENSCHOLAR_BASE_URL": ""})
    assert manager.usage_request(manager.client) == {}


def test_sources_say_why_a_chunk_was_not_sent(monkeypatch):
    many = [SimpleNamespace(text=f"text {i}", metadata={"title": f"t{i}"}) for i in range(5)]
    retriever = make_retriever(monkeypatch, many, lambda pairs: [0.9, 0.8, 0.3, 0.05, 0.7],
                               MAX_CHUNKS=5, MAX_CHUNKS_PER_DOC=0, ADAPTIVE_TOP_K=True, ADAPTIVE_TOP_K_RATIO=0.5,
                               ADAPTIVE_TOP_K_MIN=1)
    t = trace.begin()
    try:
        retriever.retrieve_and_rerank("q")
        sources = trace.active().info["sources"]
    finally:
        trace.end(t)
    by_title = {c["title"]: c for c in sources["chunks"]}
    assert [c["title"] for c in sources["chunks"]] == ["t0", "t1", "t4", "t2", "t3"]  # best first
    assert by_title["t0"]["sent"] and by_title["t0"]["n"] == 0
    assert by_title["t2"]["why"] == "below adaptive cut-off"  # 0.3 < 0.9 * 0.5
    assert by_title["t3"]["why"] == "below minimum relevance"
    assert sources["cutoff"] == 0.45 and sources["min_relevance"] == 0.1


def test_decision_call_keeps_probabilities_and_page_titles():
    t = trace.begin()
    try:
        trace.decision_call("cloudflare/clef", 0.0, {"ms": 300, "cost": 0.0002},
                            {"page_1": {"type": "noul", "instructions": "Would reading this help? Page: Get involved (https://forrt.org/x). ..."},
                             "route": {"type": "choice", "instructions": "Which kind?"}},
                            {"page_1": {"noul": 0.81}, "route": {"choice": "forrt", "probabilities": {"forrt": 0.7, "both": 0.3}}})
        call = trace.active().calls[0]
    finally:
        trace.end(t)
    assert call["questions"]["page_1"] == {"type": "noul", "label": "Get involved", "choice": None, "probabilities": None, "yes": 0.81}
    assert call["questions"]["route"]["probabilities"]["forrt"] == 0.7
    assert call["cost"] == 0.0002


def test_a_thread_pool_job_records_into_the_turn_when_given_the_context():
    t = trace.begin()
    try:
        job_step = trace.step("pages job")(lambda: trace.llm_call("m", 0.0, {"prompt_tokens": 5}))
        with ThreadPoolExecutor(1) as pool:
            pool.submit(contextvars.copy_context().run, job_step).result()
        tr = trace.active()
        assert [s["name"] for s in tr.steps] == ["pages job"]
        assert tr.calls[0]["step"] == "pages job" and tr.calls[0]["tokens_in"] == 5
    finally:
        trace.end(t)


def test_export_sums_cost_and_counts_calls_without_one():
    t = trace.begin()
    try:
        trace.llm_call("a", 0.0, {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.001})
        trace.llm_call("self-hosted", 0.0, {"prompt_tokens": 10, "completion_tokens": 2})
        out = trace.active().export({"total_s": 1.5})
    finally:
        trace.end(t)
    assert out["totals"] == {"ms": 1500, "cost": 0.001, "cost_missing": 1, "tokens_in": 20, "tokens_out": 4,
                             "tokens_cached": 0, "calls": 2}
