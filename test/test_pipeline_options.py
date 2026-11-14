"""Chat model choice, memory (#14), citation check (#23), FORRT lookup (#15)."""

import json
from types import SimpleNamespace

import fakeredis
from bs4 import BeautifulSoup

from just_os import qualle
from just_os.answer_cache import AnswerCache
from just_os.forrt_lookup import ForrtLookup
from test_qualle import CONFIG, FakeChatManager, FakeClient, completion, make_qualle, node


class HistoryChatManager(FakeChatManager):
    def __init__(self, history):
        super().__init__()
        self.history = history

    def get_history(self, chat_id):
        return self.history


# --- chat model dropdown: the chosen model writes the answer


def test_chosen_model_writes_the_answer():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    list(q.get_response("question", "chat", model="chosen/model"))
    assert q.response_generator.client_manager.calls[-1]["model"] == "chosen/model"


def test_answer_cache_is_per_model():
    settings = {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9, "ANSWER_CACHE_MAX_ITEMS": 5, "CITATION_MODEL": "a"}
    embed = SimpleNamespace(get_query_embedding=lambda q: [1.0, 0.0])
    cache = AnswerCache(fakeredis.FakeRedis(), embed, settings)
    cache.store("q", {"message": "from b"}, "t", model="b")
    assert cache.lookup("q") is None
    assert cache.lookup("q", model="b")["response"]["message"] == "from b"



def test_answer_cache_is_per_relevance_cut_reranker_and_search_depth():
    """MIN_RELEVANCE, RERANK_MODEL and RETRIEVER_TOP_K decide which chunks reach the answer."""
    base = {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9, "ANSWER_CACHE_MAX_ITEMS": 5,
            "MIN_RELEVANCE": 0.1, "RERANK_MODEL": "a", "RETRIEVER_TOP_K": 20}
    embed = SimpleNamespace(get_query_embedding=lambda q: [1.0, 0.0])
    key = AnswerCache(fakeredis.FakeRedis(), embed, base).key
    for change in ({"MIN_RELEVANCE": 0.2}, {"RERANK_MODEL": "b"}, {"RETRIEVER_TOP_K": 40}):
        assert AnswerCache(fakeredis.FakeRedis(), embed, {**base, **change}).key != key, change


# --- #14: the history keeps the user's words; CONTEXT_METHOD=history


def test_history_stores_the_question_the_user_typed():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.chat_manager = HistoryChatManager([{"role": "user", "content": "What is open data?"}])
    q.query_processor.rephrase_query = lambda query, chat_id: "Does open data have disadvantages?"
    list(q.get_response("Any disadvantages?", "chat"))
    assert q.chat_manager.messages[0] == {"role": "user", "content": "Any disadvantages?"}


def test_history_method_passes_earlier_turns_and_skips_rephrase():
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.config = {**CONFIG, "CONTEXT_METHOD": "history"}
    history = [{"role": "user", "content": "What is open data?"}, {"role": "assistant", "content": "It is ..."}]
    q.chat_manager = HistoryChatManager(history)
    q.query_processor.rephrase_query = lambda *a: (_ for _ in ()).throw(AssertionError("no rephrase"))
    seen = {}
    retrieve = q.document_retriever.retrieve_and_rerank
    q.document_retriever.retrieve_and_rerank = lambda query, *timings: (seen.setdefault("query", query), retrieve(query))[1]

    list(q.get_response("Any disadvantages?", "chat"))

    messages = q.response_generator.client_manager.calls[-1]["messages"]
    assert [m["content"] for m in messages[1:3]] == ["What is open data?", "It is ..."]
    assert seen["query"] == "What is open data? Any disadvantages?"


def test_hybrid_method_searches_the_rephrased_question_and_answers_with_the_chat():
    """CONTEXT_METHOD=hybrid: rephrase keeps topic switches and off-topic follow-ups apart (history joins
    them), and the answer model still sees the user's words ("single-blind" became "double-blind")."""
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.config = {**CONFIG, "CONTEXT_METHOD": "hybrid"}
    q.chat_manager = HistoryChatManager([{"role": "user", "content": "What is peer review?"},
                                         {"role": "assistant", "content": "It is ..."}])
    q.query_processor.rephrase_query = lambda query, chat_id: "What is double-blind peer review?"
    seen = {}
    q.route = lambda query, router=None: seen.setdefault("routed", query) and "open_science"
    retrieve = q.document_retriever.retrieve_and_rerank
    q.document_retriever.retrieve_and_rerank = lambda query, *timings: (seen.setdefault("searched", query), retrieve(query))[1]

    list(q.get_response("The one where the reviewer knows the author but not the reverse?", "chat"))

    assert seen == {"routed": "What is double-blind peer review?", "searched": "What is double-blind peer review?"}
    messages = q.response_generator.client_manager.calls[-1]["messages"]
    assert [m["content"] for m in messages[1:3]] == ["What is peer review?", "It is ..."]
    assert "The one where the reviewer knows the author" in messages[-1]["content"]
    assert "(Meaning: What is double-blind peer review?)" in messages[-1]["content"]  # long chats: the rewrite too


# --- #23: citation check


def checker(scores):
    r = object.__new__(qualle.DocumentRetriever)
    r.reranker = SimpleNamespace(predict=lambda pairs: scores[: len(pairs)])
    r.verify_min_score = 0.1
    return r


def test_unsupported_citations():
    nodes = [node("A", "open data text"), node("B", "unrelated text")]
    text = "Open data helps reuse [0]. The moon is cheese [1]."
    assert checker([0.9, 0.01]).unsupported_citations(text, nodes) == {1}
    assert checker([0.9]).unsupported_citations("No citations here.", nodes) == set()


def test_unverified_source_is_marked():
    nodes = [node("A"), node("B")]
    processor = qualle.ReferenceProcessor()
    html, used = processor.process_markdown_with_references("X [0]. Y [1].", nodes, {1})
    flags = [json.loads(a["data-reference"])["unverified"] for a in BeautifulSoup(html, "html.parser").find_all("a")]
    assert flags == [False, True]
    assert processor.references_from_nodes(nodes, used, {1}).splitlines()[1].endswith("[not verified]")


# --- #15: FORRT lookup mode


def test_classify_intent():
    processor = qualle.QueryProcessor(FakeClient(completion(tool_arguments='{"category": "forrt_lookup"}')), CONFIG, FakeChatManager())
    assert processor.classify_intent("Where is the FORRT glossary?") == "forrt_lookup"
    processor = qualle.QueryProcessor(FakeClient(completion(tool_arguments='{"category": "weather"}')), CONFIG, FakeChatManager())
    assert processor.classify_intent("q") is None


def test_lookup_question_gets_links_not_a_summary():
    q = make_qualle(True, [], [], "unused")
    q.config = {**CONFIG, "FORRT_LOOKUP": True}
    q.query_processor.classify_intent = lambda query: "forrt_lookup"
    q.forrt_lookup = SimpleNamespace(answer=lambda query: "Here are FORRT resources:\n\n- [Glossary](https://forrt.org/glossary)")
    final = list(q.get_response("Where is the glossary?", "chat"))[-1]
    assert final["status"] == "complete"
    assert 'href="https://forrt.org/glossary"' in final["message"]
    assert q.response_generator.client_manager.calls == []  # no answer-model call


def test_forrt_lookup_search_and_escaping(tmp_path):
    sheet = tmp_path / "sheet.csv"
    sheet.write_text(
        "Exclude,Title,URL/DOI (x),DOI,Abstract,Material Type (x),FORRT Clusters (x),User Tags (x)\n"
        ',"Glossary of open science <b>terms</b>",https://forrt.org/glossary,,A glossary of terms,Reading,Glossary,\n'
        ',Preregistration course,https://doi.org/10.1234/prereg,,How to preregister,Course,Preregistration,\n'
        'TRUE,Hidden row,https://example.org,,glossary,Reading,,\n',
        encoding="utf-8",
    )
    lookup = ForrtLookup(str(sheet), top_k=3)
    assert [r["title"] for r in lookup.search("glossary")] == ["Glossary of open science <b>terms</b>"]
    answer = lookup.answer("Where is the glossary?")
    assert "&lt;b&gt;" in answer and "<b>" not in answer  # titles cannot inject HTML
    assert "(https://forrt.org/glossary)" in answer
    assert "get involved" in lookup.answer("How can I contribute to the glossary?")
