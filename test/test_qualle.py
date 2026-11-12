import json
from types import SimpleNamespace

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
    retriever.retrieve_and_rerank = lambda query: (ranked, all_nodes)
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
    assert manager.client.max_retries == 1


def test_openscholar_has_its_own_time_limit():
    manager = qualle.OpenAIClientManager({
        "LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "LLM_TIMEOUT": 60,
        "OPENSCHOLAR_BASE_URL": "http://openscholar.test/v1", "OPENSCHOLAR_API_KEY": "os", "OPENSCHOLAR_TIMEOUT": 600,
    })
    assert (manager.openscholar_client.timeout, manager.openscholar_client.max_retries) == (600, 0)
    assert (manager.client.timeout, manager.client.max_retries) == (60, 1)


# --- Answers are streamed (same for OpenScholar and OpenRouter) and joined into one completion
def stream_chunks(*texts, usage=None):
    from openai.types.chat import ChatCompletionChunk

    chunks = [
        ChatCompletionChunk(
            id="c1", created=1, model="m", object="chat.completion.chunk",
            choices=[{"index": 0, "delta": {"content": t}, "finish_reason": None}],
        )
        for t in texts
    ]
    chunks[-1].choices[0].finish_reason = "length"
    chunks.append(ChatCompletionChunk(
        id="c1", created=1, model="m", object="chat.completion.chunk", choices=[], usage=usage,
    ))
    return chunks


def streaming_manager(chunks, timeout=60):
    manager = qualle.OpenAIClientManager(
        {"LLM_API_KEY": "k", "BASE_URL": "https://openrouter.ai/api/v1", "OPENSCHOLAR_BASE_URL": "", "LLM_TIMEOUT": timeout}
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return iter(chunks)

    manager.client.chat.completions.create = create
    return manager, calls


def test_streamed_answer_is_joined_with_usage():
    usage = {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": 0.002}
    manager, calls = streaming_manager(stream_chunks("Hello", " world", usage=usage))
    response = manager.create_chat_completion(model="m", messages=[], stream=True)
    assert calls[0]["stream"] is True and calls[0]["stream_options"] == {"include_usage": True}
    assert response.choices[0].message.content == "Hello world"
    assert response.choices[0].finish_reason == "length"
    assert response.usage.completion_tokens == 3
    assert response.usage.cost == 0.002  # OpenRouter's extra field, read by eval/run.py


def test_stream_that_runs_past_the_time_limit_fails():
    manager, _ = streaming_manager(stream_chunks("a", "b"), timeout=-1)
    assert manager.create_chat_completion(model="m", messages=[], stream=True) is None


def test_answers_are_streamed():
    client = FakeClient(completion(content="x"))
    qualle.ResponseGenerator(client, CONFIG, None).generate_response("question", "[0] Title: T Text: t")
    assert client.calls[0]["stream"] is True
