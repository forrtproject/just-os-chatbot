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


def test_an_empty_streamed_answer_falls_back_to_the_call_with_retries():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.response_generator.stream_response = lambda *a, **k: iter(())  # the stream gave nothing
    final = list(q.get_response("What is open data?", "chat", stream=True))[-1]
    assert final["outcome"] == "answered" and "Answer" in final["message"]
