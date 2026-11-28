import json
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from just_os import qualle

CONFIG = {
    "GENERAL_MODEL": "general",
    "CITATION_MODEL": "citation",
    "TEMPERATURE": 0.3,
    "TEMPERATURE_GENERAL": 0.15,
}


def completion(content=None, tool_arguments=None):
    tool_calls = (
        [SimpleNamespace(function=SimpleNamespace(arguments=tool_arguments))]
        if tool_arguments is not None
        else None
    )
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Returns the queued responses in order; None means an API error."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeChatManager:
    def __init__(self):
        self.messages = []

    def get_history(self, chat_id):
        return []

    def add_message(self, chat_id, message):
        self.messages.append(message)


def node(title, text="some text"):
    return SimpleNamespace(
        text=text,
        metadata={"title": title, "creators": "Author", "timestamp": "2020", "link_to_resource": "https://x"},
    )


def processor(client):
    return qualle.QueryProcessor(client, CONFIG, FakeChatManager())


# --- P6: JSON fallback when the model does not make a tool call


def test_classify_uses_tool_call():
    client = FakeClient(completion(tool_arguments='{"concerns_open_science": true}'))
    assert processor(client).classify_query("q") is True
    assert len(client.calls) == 1


def test_classify_falls_back_to_plain_json():
    client = FakeClient(
        completion(content="no tools here"),
        completion(content='Sure: {"concerns_open_science": false}'),
    )
    assert processor(client).classify_query("q") is False
    assert "tools" not in client.calls[1]


def test_classify_api_error_is_none_not_false():
    assert processor(FakeClient(None, None)).classify_query("q") is None


def test_rephrase_keeps_query_on_failure():
    assert processor(FakeClient(None, None)).rephrase_query("my question", "chat") == "my question"


def test_rephrase_names_the_referent_but_drops_a_rewrite_that_pulls_in_the_answer():
    named = '{"reformulated_query": "Where can I publish a data paper in ecology?"}'
    assert processor(FakeClient(completion(tool_arguments=named))).rephrase_query(
        "where can I publish one in ecology?", "chat") == "Where can I publish a data paper in ecology?"
    # Llama 3.1 8B, 25 Nov 2026: the previous answer's findings copied into the rewrite
    pasted = ('{"reformulated_query": "Why did Simmons, Nelson and Simonsohn kick off the crisis in psychology because '
              'undisclosed flexibility in data collection and analysis allows researchers to present almost any result as '
              'statistically significant and the authors demonstrated that the practice found allows it?"}')
    question = "Why did Simmons, Nelson and Simonsohn kick off the crisis in psychology?"
    assert processor(FakeClient(completion(tool_arguments=pasted))).rephrase_query(question, "chat") == question


# --- P9 and P10: get_response


def make_qualle(classification, ranked, all_nodes, answer):
    q = object.__new__(qualle.Qualle)
    q.config = CONFIG
    q.chat_manager = FakeChatManager()
    q.answer_cache = None
    q.forrt_lookup = None
    q.query_processor = SimpleNamespace(
        classify_query=lambda query: classification, rephrase_query=lambda query, chat_id: query
    )
    retriever = object.__new__(qualle.DocumentRetriever)
    retriever.retrieve_and_rerank = lambda query, *timings: (ranked, all_nodes)
    q.document_retriever = retriever
    q.reference_processor = qualle.ReferenceProcessor()
    q.response_generator = qualle.ResponseGenerator(
        FakeClient(*[completion(content=answer)] * 3), CONFIG, q.reference_processor
    )
    return q


def test_citations_use_ranked_nodes():
    ranked = [node("Ranked paper")]
    all_nodes = [node("Other paper"), ranked[0]]  # pre-rerank order differs
    q = make_qualle(True, ranked, all_nodes, "Answer [0].")

    final = list(q.get_response("question", "chat"))[-1]

    assert final["status"] == "complete"
    assert "Ranked paper" in final["metadata"]["sources"]
    assert "Other paper" not in final["metadata"]["sources"]
    link = BeautifulSoup(final["message"], "html.parser").find("a", class_="reference-link")
    assert json.loads(link["data-reference"])["title"] == "Ranked paper"


def test_answer_without_citations_is_asked_again_once():
    q = make_qualle(True, [node("Ranked paper")], [], "unused")
    client = FakeClient(completion(content="Replikation ist wichtig."), completion(content="Replikation ist wichtig [0]."))
    q.response_generator.client_manager = client
    final = list(q.get_response("Was ist Replikation?", "chat"))[-1]
    assert len(client.calls) == 2
    assert BeautifulSoup(final["message"], "html.parser").find("a", class_="reference-link")

    q = make_qualle(True, [node("Ranked paper")], [], "unused")
    client = FakeClient(*[completion(content="No sources cited.")] * 2)
    q.response_generator.client_manager = client
    assert list(q.get_response("question", "chat"))[-1]["outcome"] == "answered"  # kept after one retry
    assert len(client.calls) == 2

    # a slow first answer is kept: no second wait
    q = make_qualle(True, [node("Ranked paper")], [], "unused")
    q.config = {**CONFIG, "LLM_TIMEOUT": 0}
    client = FakeClient(completion(content="Replikation ist wichtig."))
    q.response_generator.client_manager = client
    assert list(q.get_response("Was ist Replikation?", "chat"))[-1]["outcome"] == "answered"
    assert len(client.calls) == 1


# --- #41 streaming


@pytest.mark.parametrize(
    "raw, marked, shown",
    [
        ("Let me think. [Response_St", True, ""),  # nothing before the marker
        ("Let me think. [Response_Start] Open data", True, " Open data"),
        ("[Response_Start] Open data is good [", True, " Open data is good "),  # citation still open
        ("[Response_Start] Good [0]. Done.[Response_End] trailing", True, " Good [0]. Done."),
        ("[Response_Start] Good [0]. Done.[Respon", True, " Good [0]. Done."),  # end marker still open
        ("Short style has no markers [1", False, "Short style has no markers "),
    ],
)
def test_visible_answer_holds_back_until_it_is_safe(raw, marked, shown):
    assert qualle.visible_answer(raw, marked) == shown


class StreamClient(FakeClient):
    def __init__(self, pieces):
        super().__init__()
        self.pieces = pieces

    def stream_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        yield from self.pieces


def test_streamed_answer_shows_pieces_and_ends_like_the_unstreamed_one():
    pieces = ["Thinking about it. ", "[Response_St", "art]Open data is good [", "0]. More", " text.[Response_End]x"]
    q = make_qualle(True, [node("Ranked paper")], [], "".join(pieces))
    unstreamed = list(q.get_response("question", "chat"))[-1]

    q = make_qualle(True, [node("Ranked paper")], [], "unused")
    q.response_generator.client_manager = StreamClient(pieces)
    messages = list(q.get_response("question", "chat", stream=True))
    partial = [m["delta"] for m in messages if m["status"] == "partial"]
    assert "".join(partial) == "Open data is good [0]. More text."
    assert not any("Thinking" in p or "Response" in p for p in partial)
    without_times = lambda m: {k: v for k, v in m.items() if k != "timings"}  # noqa: E731
    assert without_times(messages[-1]) == without_times(unstreamed)
    assert set(messages[-1]["timings"]) >= {"classify_s", "answer_s", "total_s"}  # the fake retriever times nothing


def test_answer_length_is_capped():
    client = FakeClient(completion(content="x [0]."))
    generator = qualle.ResponseGenerator(client, {**CONFIG, "MAX_ANSWER_TOKENS": 50}, None)
    generator.generate_response("question", "[0] Title: T Text: t")
    assert client.calls[0]["max_tokens"] == 50


def test_classify_error_is_not_a_refusal():
    q = make_qualle(None, [], [], "unused")
    final = list(q.get_response("question", "chat"))[-1]
    assert final["status"] == "error"
    assert "only able to answer" not in final["message"]


def test_off_topic_is_a_refusal():
    q = make_qualle(False, [], [], "unused")
    final = list(q.get_response("question", "chat"))[-1]
    assert final["status"] == "complete"
    assert "only able to answer" in final["message"]


# --- Arena


def test_arena_answers_with_each_model_from_same_sources():
    ranked = [node("Ranked paper")]
    q = make_qualle(True, ranked, ranked, "Answer [0].")

    final = list(q.get_arena_response("question", ["model-a", "model-b"]))[-1]

    assert [r["model"] for r in final["responses"]] == ["model-a", "model-b"]
    assert all("Ranked paper" in r["sources"] for r in final["responses"])
    used = sorted(c["model"] for c in q.response_generator.client_manager.calls)
    assert used == ["model-a", "model-b"]
    assert q.chat_manager.messages == []  # arena is single turn: nothing stored


# --- Self-hosted OpenScholar: its model goes to its own server, others stay on BASE_URL
def test_openscholar_model_uses_its_own_server():
    manager = qualle.OpenAIClientManager(
        {
            "LLM_API_KEY": "main-key",
            "BASE_URL": "https://openrouter.ai/api/v1",
            "OPENSCHOLAR_BASE_URL": "http://openscholar.test/v1",
            "OPENSCHOLAR_API_KEY": "os-key",
            "OPENSCHOLAR_MODEL": "openscholar-8b",
        }
    )
    assert str(manager._client_for("openscholar-8b").base_url).startswith("http://openscholar.test/v1")
    assert manager._client_for("openscholar-8b").api_key == "os-key"
    assert str(manager._client_for("other/model").base_url).startswith("https://openrouter.ai/api/v1")


def test_openscholar_off_when_no_url():
    manager = qualle.OpenAIClientManager(
        {"LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "OPENSCHOLAR_BASE_URL": ""}
    )
    assert manager.openscholar_client is None
    assert manager._client_for("openscholar-8b") is manager.client


def test_llm_calls_have_a_time_limit():
    manager = qualle.OpenAIClientManager(
        {"LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "OPENSCHOLAR_BASE_URL": "", "LLM_TIMEOUT": 7}
    )
    assert manager.client.timeout == 7
    assert manager.client.max_retries == 0  # create_chat_completion retries (LLM_RETRIES)


def test_openscholar_has_its_own_time_limit():
    manager = qualle.OpenAIClientManager({
        "LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "LLM_TIMEOUT": 60,
        "OPENSCHOLAR_BASE_URL": "http://openscholar.test/v1", "OPENSCHOLAR_API_KEY": "os", "OPENSCHOLAR_TIMEOUT": 600,
    })
    assert (manager.openscholar_client.timeout, manager.openscholar_client.max_retries) == (600, 0)
    assert (manager.client.timeout, manager.client.max_retries) == (60, 0)


# --- topic check per request (Qualle.route router=...)


class FakeDecisions:
    def __init__(self, route):
        self.result, self.models = route, []

    def route(self, model, question):
        self.models.append(model)
        return self.result, 0.3, {"ms": 1}


def routed(classification=True, decision=None):
    q = make_qualle(classification, [], [], "unused")
    q.config = {**CONFIG, "DECISION_ROUTER": True}
    q.decisions = FakeDecisions(decision)
    return q


def test_router_choices():
    assert routed().route("anything", "none") == "both"  # no check
    q = routed(decision="forrt")
    assert q.route("How do I join FORRT?", "jev") == "forrt"  # the chosen model decides, even at p=0.3
    assert q.decisions.models == ["typesafe/jev-1.14"]
    q = routed(classification=False, decision=None)
    assert q.route("pizza?", "clef") == "off_topic"  # decision call failed: the LLM classifier decides
    q = routed(classification=True, decision="neither")
    assert q.route("What is open data?", "llm") == "open_science" and q.decisions.models == []  # LLM only
    assert routed(decision="forrt").route("q") == "open_science"  # default: p=0.3 is below the minimum


def test_cosine_router_thresholds():
    import numpy as np

    class Faiss:
        def __init__(self, cosine):
            self.cosine = cosine

        def search(self, q, k):
            return np.array([[2 - 2 * self.cosine]]), np.array([[0]])  # squared L2 of unit vectors

    def cosine_qualle(paper, page):
        q = make_qualle(True, [], [], "unused")
        q.config = CONFIG
        q._embed_model = SimpleNamespace(get_query_embedding=lambda text: [1.0, 0.0])
        q._retriever = SimpleNamespace(_index=SimpleNamespace(vector_store=SimpleNamespace(_faiss_index=Faiss(paper))))
        q.forrt_pages = SimpleNamespace(vectors=np.array([[page, (1 - page ** 2) ** 0.5]], dtype=np.float32))
        return q

    assert cosine_qualle(0.70, 0.40).route("q", "cosine") == "open_science"
    assert cosine_qualle(0.55, 0.60).route("q", "cosine") == "forrt"
    assert cosine_qualle(0.70, 0.75).route("q", "cosine") == "forrt"  # both above: the closer one
    assert cosine_qualle(0.55, 0.45).route("q", "cosine") == "off_topic"


def test_banded_router_refuses_and_answers_without_a_model_call_and_asks_in_between():
    bands = {"BAND_PAPER_LOW": 0.5, "BAND_PAPER_HIGH": 0.8, "BAND_PAGE_LOW": 0.4, "BAND_PAGE_HIGH": 0.7, "BAND_MIDDLE_ROUTER": "jev"}

    def banded(paper, page, middle="forrt"):
        q = routed(decision=middle)
        q.config = {**q.config, **bands}
        q.similarities = lambda query: (paper, page)
        q.forrt_pages = object()  # loaded, so the page similarity is measured
        return q

    q = banded(0.45, 0.35)
    assert q.route("pizza?", "banded") == "off_topic" and q.decisions.models == []  # low band: no call
    q = banded(0.85, 0.30)
    assert q.route("What is open data?", "banded") == "open_science" and q.decisions.models == []  # high band
    # close to a FORRT page: never routed by similarity alone, the middle router decides
    q = banded(0.60, 0.75, middle="forrt")
    assert q.route("q", "banded") == "forrt" and q.decisions.models == ["typesafe/jev-1.14"]
    q = banded(0.85, 0.72, middle="open_science")  # paper high, but close to FORRT too
    assert q.route("q", "banded") == "open_science" and q.decisions.models == ["typesafe/jev-1.14"]
    q = banded(0.60, 0.50, middle="neither")
    assert q.route("Write my preregistration", "banded") == "off_topic"  # middle band: Jev decides
    assert q.decisions.models == ["typesafe/jev-1.14"]
    assert banded(0.45, 0.50).route("q", "banded") == "forrt"  # one source above its low: not refused


def test_banded_router_edges():
    def banded(paper, page, config, middle="forrt"):
        q = routed(decision=middle)
        q.config = {**q.config, **config}
        q.similarities = lambda query: (paper, page)
        q.forrt_pages = object()
        return q

    # an empty BAND_MIDDLE_ROUTER means Jev, not ROUTER (which would be banded again, without end)
    q = banded(0.60, 0.50, {"ROUTER": "banded", "BAND_MIDDLE_ROUTER": ""})
    assert q.route("q") == "forrt" and q.decisions.models == ["typesafe/jev-1.14"]
    # without FORRT pages the page similarity is not measured: no refusal by similarity
    q = banded(0.40, -1.0, {"BAND_MIDDLE_ROUTER": "jev"})
    q.forrt_pages = None
    assert q.route("q", "banded") == "forrt" and q.decisions.models == ["typesafe/jev-1.14"]
    # a config without the BAND_* keys uses the defaults of config/settings.py, not "always ask"
    q = banded(0.50, 0.30, {})
    for key in ("BAND_PAPER_LOW", "BAND_PAPER_HIGH", "BAND_PAGE_LOW", "BAND_PAGE_HIGH"):
        q.config.pop(key, None)
    assert q.route("pizza?", "banded") == "off_topic" and q.decisions.models == []


def test_reasoning_is_switched_off_only_for_the_listed_models():
    manager = qualle.OpenAIClientManager.__new__(qualle.OpenAIClientManager)
    manager.config = {"NO_REASONING_MODELS": "qwen/qwen3.7-flash, x/y"}
    assert manager.no_reasoning("qwen/qwen3.7-flash") == {"extra_body": {"reasoning": {"enabled": False}}}
    assert manager.no_reasoning("openai/gpt-oss-20b") == {}


def fake_manager(create, **config):
    from types import SimpleNamespace
    manager = qualle.OpenAIClientManager.__new__(qualle.OpenAIClientManager)
    manager.config = {"OPENSCHOLAR_MODEL": "openscholar-8b", **config}
    manager._client_for = lambda model: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return manager


def test_an_empty_answer_at_the_token_cap_is_asked_again_with_low_reasoning(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(qualle.time, "sleep", lambda s: None)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        empty = len(calls) == 1
        message = SimpleNamespace(content="" if empty else "Answer [1].")
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="length" if empty else "stop", message=message)])

    manager = fake_manager(create)
    response = manager.create_chat_completion("openai/gpt-oss-20b", [{"role": "user", "content": "q"}], max_tokens=1500)
    assert response.choices[0].message.content == "Answer [1]." and len(calls) == 2
    assert calls[1]["extra_body"] == {"reasoning": {"effort": "low"}}


def test_a_failing_model_is_tried_three_more_times_before_the_error(monkeypatch):
    from types import SimpleNamespace
    pauses = []
    monkeypatch.setattr(qualle.time, "sleep", pauses.append)
    calls = []

    def flaky(**kwargs):  # provider errors twice, then answers
        calls.append(kwargs)
        if len(calls) < 3:
            raise ConnectionError("provider 502")
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Answer."))])

    q = [{"role": "user", "content": "q"}]
    assert fake_manager(flaky).create_chat_completion("m/x", q).choices[0].message.content == "Answer."
    assert len(calls) == 3 and pauses == [1, 2]

    calls.clear()
    def down(**kwargs):
        calls.append(kwargs)
        raise ConnectionError("provider down")

    assert fake_manager(down, LLM_RETRIES=3).create_chat_completion("m/x", q) is None
    assert len(calls) == 4  # the first try and 3 retries, then the user sees the error and Try again
    calls.clear()
    assert fake_manager(down).create_chat_completion("openscholar-8b", q) is None and len(calls) == 1  # minutes per answer

    calls.clear()
    class Unauthorized(Exception):
        status_code = 401

    def wrong_key(**kwargs):
        calls.append(kwargs)
        raise Unauthorized("LiteLLM Virtual Key expected")

    assert fake_manager(wrong_key, LLM_RETRIES=3).create_chat_completion("m/x", q) is None
    assert len(calls) == 1  # a wrong key stays wrong: the user gets the error at once, not after 4 tries


def test_an_empty_streamed_answer_falls_back_to_the_call_with_retries():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.response_generator.stream_response = lambda *a, **k: iter(())  # the stream gave nothing
    final = list(q.get_response("What is open data?", "chat", stream=True))[-1]
    assert final["outcome"] == "answered" and "Answer" in final["message"]


# --- prod reliability: CPU threads, LLM slots, Retry-After, broken streams, failed turns, private logs


def test_without_the_reranker_omp_num_threads_is_left_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(qualle.torch, "set_num_threads", calls.append)
    monkeypatch.setattr(qualle, "CrossEncoder", lambda name: f"model {name}")
    base = {"RERANK_MODEL": "rr", "MAX_CHUNKS": 7, "MIN_RELEVANCE": 0.1, "RERANK_THREADS": 6}
    qualle.DocumentRetriever({**base, "RERANK": False}, retriever=None)
    assert calls == []  # prod: OMP_NUM_THREADS=2 stays 2
    retriever = qualle.DocumentRetriever({**base, "RERANK": True}, retriever=None)
    assert calls == [6] and retriever.reranker == "model rr"
    qualle.DocumentRetriever({**base, "RERANK": False, "VERIFY_CITATIONS": True}, retriever=None)
    assert calls == [6, 6]


def answer(content="Answer."):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])


def test_max_concurrent_llm_calls_caps_calls_and_streams_across_threads():
    import threading
    import time as real_time

    manager = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://example.org/v1",
                                          "OPENSCHOLAR_BASE_URL": "", "MAX_CONCURRENT_LLM_CALLS": 2, "LLM_TIMEOUT": 5})
    lock, state = threading.Lock(), {"now": 0, "most": 0}

    def busy():
        with lock:
            state["now"] += 1
            state["most"] = max(state["most"], state["now"])
        real_time.sleep(0.05)
        with lock:
            state["now"] -= 1

    def create(stream=False, **kwargs):
        if stream:
            def pieces():
                busy()
                yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))])
                busy()
            return pieces()
        busy()
        return answer()

    manager._client_for = lambda model: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    jobs = [lambda: manager.create_chat_completion("m", [{"role": "user", "content": "q"}]),
            lambda: list(manager.stream_chat_completion("m", [{"role": "user", "content": "q"}]))] * 4
    threads = [threading.Thread(target=job) for job in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert state["most"] == 2
    assert manager._llm_slots._value == 2  # every slot was given back

    unlimited = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://example.org/v1", "OPENSCHOLAR_BASE_URL": ""})
    assert unlimited._llm_slots is None  # default 0: no limit


def test_a_stream_the_reader_abandons_gives_its_slot_back():
    manager = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://example.org/v1",
                                          "OPENSCHOLAR_BASE_URL": "", "MAX_CONCURRENT_LLM_CALLS": 1})
    chunk = SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))])
    manager._client_for = lambda model: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: iter([chunk] * 5))))
    stream = manager.stream_chat_completion("m", [])
    assert next(stream) == "Hi" and manager._llm_slots._value == 0
    stream.close()  # the browser went away
    assert manager._llm_slots._value == 1


def test_http_429_waits_as_long_as_retry_after_says_capped(monkeypatch):
    pauses = []
    monkeypatch.setattr(qualle.time, "sleep", pauses.append)

    class RateLimited(Exception):
        status_code = 429

        def __init__(self, retry_after):
            super().__init__("429 Too Many Requests")
            self.response = SimpleNamespace(headers={"retry-after": retry_after} if retry_after is not None else {})

    for header, expected in (("3", 3.0), ("120", qualle.MAX_RETRY_AFTER), ("Wed, 21 Oct 2026 07:28:00 GMT", 1),
                             (None, 1), ("-5", 0.0)):
        pauses.clear()
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RateLimited(header)
            return answer()

        assert fake_manager(create).create_chat_completion("m/x", [{"role": "user", "content": "q"}]) is not None
        assert pauses == [expected], header
    assert qualle.MAX_RETRY_AFTER <= 10


def test_a_stream_that_breaks_after_some_text_raises_instead_of_ending_quietly():
    chunk = lambda text: SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])  # noqa: E731

    def broken(**kwargs):
        yield chunk("Open data is")
        raise ConnectionError("connection reset")

    manager = fake_manager(lambda **kw: broken(**kw))
    got = []
    with pytest.raises(qualle.StreamInterrupted):
        for piece in manager.stream_chat_completion("m/x", []):
            got.append(piece)
    assert got == ["Open data is"]

    def refused(**kwargs):  # an error before any text: an empty stream, as before (the caller falls back)
        raise ConnectionError("refused")

    assert list(fake_manager(refused).stream_chat_completion("m/x", [])) == []


class BrokenStreamClient(FakeClient):
    """Streams some text, then the connection breaks; create_chat_completion answers from the queue."""

    def stream_chat_completion(self, **kwargs):
        yield "[Response_Start]Open data is free to reuse "
        yield "and the half sentence"
        raise qualle.StreamInterrupted("connection reset")


class RecordingCache:
    def __init__(self):
        self.stored = []

    def store(self, *args):
        self.stored.append(args)


def test_a_broken_stream_is_answered_again_and_never_kept_half():
    q = make_qualle(True, [node("Paper")], [], "unused")
    q.response_generator.client_manager = BrokenStreamClient(completion(content="Open data can be reused by anyone [0]."))
    messages = list(q.get_response("What is open data?", "chat", stream=True))
    statuses = [m["status"] for m in messages]
    first_after_partials = statuses.index("partial") + statuses[statuses.index("partial"):].index("in-progress")
    assert messages[first_after_partials]["message"] == "Generating response"  # the page drops the half draft
    final = messages[-1]
    assert final["status"] == "complete" and "reused by anyone" in final["message"] and "half sentence" not in final["message"]
    assert [m["content"] for m in q.chat_manager.messages] == ["What is open data?", "Open data can be reused by anyone [0]."]


def test_a_broken_stream_without_a_second_answer_is_an_error_not_remembered_or_cached():
    q = make_qualle(True, [node("Paper")], [], "unused")
    q.response_generator.client_manager = BrokenStreamClient(None, None)  # the fallback call fails too
    q.answer_cache = RecordingCache()
    q.answer_cache.lookup = lambda query, model: None
    final = list(q.get_response("What is open data?", "chat", stream=True))[-1]
    assert final["outcome"] == "error" and "half sentence" not in final["message"]
    assert q.chat_manager.messages == [] and q.answer_cache.stored == []


def test_a_failed_answer_is_not_written_into_the_chat_history():
    q = make_qualle(True, [node("Paper")], [], None)  # every call returns no text
    final = list(q.get_response("What is open data?", "chat"))[-1]
    assert final["outcome"] == "error"
    assert q.chat_manager.messages == []  # Try again then asks afresh, not as a follow-up to the error


def test_a_failed_forrt_pages_answer_is_not_written_into_the_chat_history():
    q = make_qualle(True, [node("Paper")], [], "unused")
    q.config = {**CONFIG, "DECISION_ROUTER": False, "ROUTER": "llm"}
    q.query_processor.classify_intent = lambda query: "forrt"
    q.route = lambda query, router=None: "forrt"
    q.forrt_pages = SimpleNamespace(answer=lambda *a, **k: {"text": None, "sources": [], "found": False})
    final = list(q.get_response("Which FORRT teams can I join?", "chat"))[-1]
    assert final["outcome"] == "error" and q.chat_manager.messages == []


def test_prod_logs_hold_no_question_text(caplog):
    import hashlib
    import logging

    secret = "Is my unpublished dataset on depression in Leipzig open?"
    q = make_qualle(True, [], [], "unused")
    q.config = {**CONFIG, "PROD_MODE": True}
    with caplog.at_level(logging.INFO, logger="just_os.qualle"):
        final = list(q.get_response(secret, "chat"))[-1]
    assert final["outcome"] == "no_sources"
    assert secret not in caplog.text and "Leipzig" not in caplog.text
    assert f"<{len(secret)} chars, sha256 {hashlib.sha256(secret.encode()).hexdigest()[:12]}>" in caplog.text

    caplog.clear()
    q.config = CONFIG  # dev: the question is logged for debugging
    with caplog.at_level(logging.INFO, logger="just_os.qualle"):
        list(q.get_response(secret, "chat"))
    assert "Leipzig" in caplog.text


def test_prod_logs_hold_no_rewritten_question(caplog):
    import logging

    grown = "open data " * 40
    p = qualle.QueryProcessor(FakeClient(completion(tool_arguments=json.dumps({"reformulated_query": grown}))),
                              {**CONFIG, "PROD_MODE": True}, FakeChatManager())
    with caplog.at_level(logging.WARNING, logger="just_os.qualle"):
        assert p.rephrase_query("And for Leipzig data?", "chat") == "And for Leipzig data?"
    assert "open data open data" not in caplog.text and "chars, sha256" in caplog.text

    retriever = object.__new__(qualle.DocumentRetriever)
    retriever.config, retriever.search_mode, retriever.min_vector_similarity = {"PROD_MODE": True}, "vector", 0.55
    with caplog.at_level(logging.INFO, logger="just_os.qualle"):
        assert retriever.search_order("Leipzig depression data", [SimpleNamespace(score=1.9, node=None)]) == []
    assert "Leipzig" not in caplog.text


def test_forrt_pages_next_to_papers_use_one_shared_pool(monkeypatch):
    def no_new_pools(*a, **k):
        raise AssertionError("a thread pool per request")

    monkeypatch.setattr(qualle, "ThreadPoolExecutor", no_new_pools)
    q = object.__new__(qualle.Qualle)
    q.config = {"FORRT_IN_PAPERS": True, "FORRT_IN_PAPERS_TIMEOUT": 5}
    q.forrt_pages = SimpleNamespace(extra_sources=lambda query, min_score: [
        {"title": "Teams", "url": "https://forrt.org/about/teams/", "text": f"{query} {min_score}"}])
    jobs = [q.start_forrt_in_papers(f"q{i}", "open_science") for i in range(20)]
    assert all(job.result(5)[0]["text"].startswith(f"q{i} ") for i, job in enumerate(jobs))
    assert len(q.forrt_in_papers_result(q.start_forrt_in_papers("q", "both"), {})) == 1
    assert qualle.FORRT_IN_PAPERS_POOL._max_workers >= 1


def test_a_slot_that_never_comes_free_ends_the_retries(monkeypatch):
    monkeypatch.setattr(qualle.time, "sleep", lambda s: None)
    manager = qualle.OpenAIClientManager({"LLM_API_KEY": "k", "BASE_URL": "https://example.org/v1", "OPENSCHOLAR_BASE_URL": "",
                                          "MAX_CONCURRENT_LLM_CALLS": 1, "LLM_TIMEOUT": 7, "LLM_RETRIES": 3})
    waits, calls = [], []

    class Busy:  # every slot stays taken by other requests
        def acquire(self, timeout):
            waits.append(timeout)
            return False

    manager._llm_slots = Busy()
    manager._client_for = lambda model: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: calls.append(kw))))
    assert manager.create_chat_completion("m", [{"role": "user", "content": "q"}]) is None
    assert waits == [7] and calls == []  # one wait of LLM_TIMEOUT, then the error: not 4 waits past WEB_TIMEOUT
