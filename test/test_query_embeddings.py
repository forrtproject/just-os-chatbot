"""One question embedding per turn (QueryEmbeddings): the answer cache, the cosine router, the FORRT page search,
the vector search and the cluster boost used to embed the same question up to five times."""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import fakeredis
import numpy as np
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

from just_os import clusters, qualle
from just_os.answer_cache import AnswerCache
from just_os.hybrid import HybridRetriever, retrieve_with_vector
from test_forrt_pages import make_pages
from test_qualle import CONFIG, make_qualle

VECTOR = [0.8, 0.6]  # page similarities 0.8 / 0.6 (make_pages), so the cosine router sends it to the papers


class CountingEmbed:
    def __init__(self):
        self.calls = Counter()

    def get_query_embedding(self, query):
        self.calls[query] += 1
        return list(VECTOR)


class VectorRetriever(BaseRetriever):
    """Like llama-index's VectorIndexRetriever: embeds the question unless the QueryBundle has its embedding."""

    def __init__(self, embed, nodes):
        super().__init__()
        self.embed, self.nodes, self.bundles = embed, nodes, []

    def _retrieve(self, query_bundle):
        self.bundles.append(query_bundle)
        if query_bundle.embedding is None:
            query_bundle.embedding = self.embed.get_query_embedding(query_bundle.query_str)
        return list(self.nodes)


class Faiss:
    def search(self, q, k):
        return np.array([[2 - 2 * 0.9]]), np.array([[0]])  # paper cosine 0.9


def paper_nodes():
    return [NodeWithScore(node=TextNode(text=f"Paper text number {i} about open science.",
                                        metadata={"title": f"Paper {i}", "link_to_resource": f"https://p/{i}"}), score=0.2 + i / 100)
            for i in range(3)]


def document_retriever(embed):
    retriever = object.__new__(qualle.DocumentRetriever)
    retriever.config = CONFIG
    retriever._retriever = VectorRetriever(embed, paper_nodes())
    retriever.rerank, retriever.search_mode, retriever.reranker = False, "vector", None
    retriever.min_vector_similarity, retriever.min_relevance = 0.0, 0.0
    retriever.n_context_items, retriever.max_per_doc = 7, 0
    retriever.skip_reference_chunks, retriever.excluded, retriever.adaptive_top_k = False, set(), False
    boost = object.__new__(clusters.ClusterBoost)
    boost.embed_model, boost.table, boost.bonus, boost.margin = embed, {}, 0.02, 0.02
    boost.centroids = np.zeros((len(clusters.CLUSTERS), 2))
    boost.centroids[0], boost.centroids[1] = [1.0, 0.0], [0.0, 1.0]
    retriever.cluster_boost = boost
    return retriever


def full_turn_qualle(tmp_path, embed, answer="Join a team [3] and read the paper [0]."):
    """Every embedding user on: answer cache, cosine router, FORRT_IN_PAPERS page search, vector search, cluster boost."""
    q = make_qualle(True, [], [], answer)
    q.config = {**CONFIG, "ROUTER": "cosine", "FORRT_IN_PAPERS": True, "FORRT_IN_PAPERS_MIN_SCORE": 0.5}
    q._embed_model = embed
    q._retriever = SimpleNamespace(_index=SimpleNamespace(vector_store=SimpleNamespace(_faiss_index=Faiss())))
    q.document_retriever = document_retriever(embed)
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    pages.embed_model = embed
    q.forrt_pages = pages
    q.answer_cache = AnswerCache(fakeredis.FakeRedis(), embed, {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.99,
                                                               "ANSWER_CACHE_MAX_ITEMS": 5, "CITATION_MODEL": "m"})
    return q


def test_a_paper_route_turn_embeds_the_question_once(tmp_path):
    embed = CountingEmbed()
    q = full_turn_qualle(tmp_path, embed)
    evidence = {}
    final = list(q.get_response("Which teams can I join?", "chat", evidence=evidence))[-1]

    assert final["status"] == "complete" and final["outcome"] == "answered"
    assert embed.calls == {"Which teams can I join?": 1}
    bundle = q.document_retriever._retriever.bundles[0]  # the vector search got the turn's embedding
    assert np.allclose(bundle.embedding, VECTOR)
    # every user really ran: the page search found the teams page, the cache stored the answer
    assert [n.metadata["link_to_resource"] for n in evidence["page_sources"]] == ["https://forrt.org/about/teams/"]
    assert q.answer_cache.redis.llen(q.answer_cache.key) == 1


def test_each_distinct_question_string_is_embedded_once(tmp_path):
    embed = CountingEmbed()
    q = full_turn_qualle(tmp_path, embed)
    list(q.get_response("Which teams can I join?", "chat-1"))
    list(q.get_response("How do I preregister?", "chat-2"))
    assert embed.calls == {"Which teams can I join?": 1, "How do I preregister?": 1}


def test_the_arena_embeds_the_question_once(tmp_path):
    embed = CountingEmbed()
    q = full_turn_qualle(tmp_path, embed, answer="Answer [0].")
    final = list(q.get_arena_response("Which teams can I join?", ["m"]))[-1]
    assert final["status"] == "complete" and embed.calls == {"Which teams can I join?": 1}


def test_components_still_embed_on_their_own_without_a_vector(tmp_path):
    embed = CountingEmbed()
    cache = AnswerCache(fakeredis.FakeRedis(), embed, {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9,
                                                       "ANSWER_CACHE_MAX_ITEMS": 5})
    cache.lookup("q")
    retriever = document_retriever(embed)
    retriever.retrieve_and_rerank("q")
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    pages.embed_model = embed
    pages.retrieve("q")
    assert embed.calls["q"] == 4  # cache, vector search, cluster boost, page search

    embed.calls.clear()
    vector = np.asarray(VECTOR, dtype=np.float32)
    cache.lookup("q", query_vector=vector)
    retriever.retrieve_and_rerank("q", query_vector=vector)
    pages.retrieve("q", query_vector=vector)
    assert not embed.calls


def test_query_embeddings_memo_and_without_a_model():
    embed = CountingEmbed()
    vectors = qualle.QueryEmbeddings(embed)
    assert vectors.get("a") is vectors.get("a") and embed.calls == {"a": 1}
    assert qualle.QueryEmbeddings(None).get("a") is None
    assert qualle.with_vector(None) == {} and "query_vector" in qualle.with_vector(np.zeros(2))


def test_similarities_do_not_change_the_shared_vector():
    q = make_qualle(True, [], [], "unused")
    q.config = CONFIG
    q._retriever = SimpleNamespace(_index=SimpleNamespace(vector_store=SimpleNamespace(_faiss_index=Faiss())))
    q.forrt_pages = None
    vector = np.asarray([3.0, 4.0], dtype=np.float32)
    q.similarities("q", query_vector=vector)
    assert vector.tolist() == [3.0, 4.0]  # normalised on a copy: the next user gets the raw embedding


def test_hybrid_search_passes_the_vector_to_its_vector_half():
    embed = CountingEmbed()
    nodes = [n.node for n in paper_nodes()]
    inner = VectorRetriever(embed, paper_nodes())
    hybrid = HybridRetriever(inner, nodes, top_k=3)
    retrieve_with_vector(hybrid, "open science", np.asarray(VECTOR, dtype=np.float32))
    assert not embed.calls and np.allclose(inner.bundles[0].embedding, VECTOR)
    # a retriever that is neither llama-index's nor ours gets the plain question
    plain = SimpleNamespace(retrieve=lambda query: [query])
    assert retrieve_with_vector(plain, "q", np.zeros(2)) == ["q"]


def test_a_failing_embedding_does_not_break_the_answer_cache_lookup():
    class Down:
        def get_query_embedding(self, query):
            raise ConnectionError("embedding API down")

    vectors = qualle.QueryEmbeddings(Down())
    assert vectors.get_or_none("q") is None
    cache = AnswerCache(fakeredis.FakeRedis(), Down(), {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9,
                                                        "ANSWER_CACHE_MAX_ITEMS": 5})
    assert cache.lookup("q", **qualle.with_vector(vectors.get_or_none("q"))) is None  # a miss, not an error


# --- lazy embedding: only a step that needs the vector makes it


class Down:
    def __init__(self):
        self.calls = 0

    def get_query_embedding(self, query):
        self.calls += 1
        raise ConnectionError("embedding API down")


def bm25_qualle(tmp_path, embed, route):
    """BM25 search with a decision router: the papers need no vector, only the optional FORRT pages do."""
    q = full_turn_qualle(tmp_path, embed, answer="Read the paper [0].")
    q.config = {**CONFIG, "DECISION_ROUTER": True, "FORRT_IN_PAPERS": True, "FORRT_IN_PAPERS_MIN_SCORE": 0.5}
    q.decisions = SimpleNamespace(route=lambda model, query: (route, 0.9, {}))
    q.document_retriever.search_mode = "bm25"
    q.document_retriever._retriever = SimpleNamespace(retrieve=lambda query: paper_nodes())  # keywords only
    q.forrt_pages.embed_model = embed
    return q


def test_a_failed_embedding_drops_only_the_optional_pages_of_a_bm25_answer(tmp_path):
    for route in ("open_science", "both"):  # both: the page links after the answer are optional too
        embed = Down()
        q = bm25_qualle(tmp_path, embed, route)
        evidence = {}
        final = list(q.get_response("Which teams can I join?", f"chat-{route}", evidence=evidence))[-1]
        assert final["status"] == "complete" and final["outcome"] == "answered", route
        assert evidence["page_sources"] == [] and len(evidence["nodes"]) == 3
        assert embed.calls >= 1  # the page job (and the cache) tried, inside their own error handling


def test_bm25_search_without_pages_embeds_nothing(tmp_path):
    embed = CountingEmbed()
    q = bm25_qualle(tmp_path, embed, "open_science")
    q.config = {**q.config, "FORRT_IN_PAPERS": False}
    q.answer_cache = None
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    assert final["outcome"] == "answered" and not embed.calls


def test_a_retrieval_cache_hit_embeds_nothing(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    import run

    embed = CountingEmbed()
    q = full_turn_qualle(tmp_path, embed)
    q.config = {**q.config, "FORRT_IN_PAPERS": False}
    q.answer_cache = None
    run.skip_classifier(q, "open_science")
    run.cache_retrieval(q, {}, folder=tmp_path / "cache")
    first = list(q.get_response("Which teams can I join?", "chat-1"))[-1]
    assert embed.calls == {"Which teams can I join?": 1}  # a miss: the vector search embedded it
    second = list(q.get_response("Which teams can I join?", "chat-2"))[-1]
    assert embed.calls == {"Which teams can I join?": 1}  # a hit: no embedding at all
    assert first["metadata"]["references"] == second["metadata"]["references"]
    assert not list((tmp_path / "cache").glob("*.tmp"))


class ByText(CountingEmbed):
    """A different vector for each question, so a vector reused for another string would show."""

    VECTORS = {"How do I join a FORRT team?": [0.8, 0.6], "And how?": [0.0, 1.0]}

    def get_query_embedding(self, query):
        self.calls[query] += 1
        return list(self.VECTORS.get(query, [0.6, 0.8]))


def test_a_rewritten_follow_up_embeds_the_rewrite_once_and_never_reuses_another_vector(tmp_path):
    embed = ByText()
    q = full_turn_qualle(tmp_path, embed)
    q.query_processor = SimpleNamespace(rephrase_query=lambda query, chat_id: "How do I join a FORRT team?")
    q.chat_manager.get_history = lambda chat_id: list(q.chat_manager.messages)  # a real chat: the follow-up is rewritten
    list(q.get_response("Which teams can I join?", "chat"))
    assert embed.calls == {"Which teams can I join?": 1}
    embed.calls.clear()
    bundles = q.document_retriever._retriever.bundles
    bundles.clear()

    final = list(q.get_response("And how?", "chat"))[-1]
    assert final["outcome"] == "answered"
    # the rewrite is embedded once and serves the router, the page search, the vector search and the boost; the
    # typed follow-up is not embedded at all (the answer cache only serves first questions)
    assert embed.calls == {"How do I join a FORRT team?": 1}
    assert [b.query_str for b in bundles] == ["How do I join a FORRT team?"]
    assert np.allclose(bundles[0].embedding, ByText.VECTORS["How do I join a FORRT team?"])


# --- a real FAISS index: the turn's vector gives the same search as the retriever's own embedding


def test_faiss_search_with_the_turns_vector_matches_the_uncached_search():
    import faiss
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.core.embeddings import BaseEmbedding
    from llama_index.vector_stores.faiss import FaissVectorStore

    def vector(text):
        rng = np.random.default_rng(sum(map(ord, text)))
        v = rng.normal(size=8).astype(np.float32)
        return (v / np.linalg.norm(v)).tolist()

    class StubEmbed(BaseEmbedding):
        query_calls: int = 0

        def _get_query_embedding(self, query):
            self.query_calls += 1
            return vector(query)

        async def _aget_query_embedding(self, query):
            return self._get_query_embedding(query)

        def _get_text_embedding(self, text):
            return vector(text)

    embed = StubEmbed()
    nodes = [TextNode(text=f"Chunk {i} on preregistration, replication and open data number {i * 7}.") for i in range(20)]
    store = FaissVectorStore(faiss_index=faiss.IndexFlatL2(8))
    index = VectorStoreIndex(nodes, storage_context=StorageContext.from_defaults(vector_store=store), embed_model=embed)
    retriever = index.as_retriever(similarity_top_k=5)

    query = "How do I preregister a replication?"
    uncached = retrieve_with_vector(retriever, query)
    assert embed.query_calls == 1
    vectors = qualle.QueryEmbeddings(embed)
    cached = retrieve_with_vector(retriever, query, vectors.get(query))
    assert embed.query_calls == 2  # QueryEmbeddings embedded it; the search did not embed it again
    assert [n.node.node_id for n in cached] == [n.node.node_id for n in uncached]
    assert np.allclose([n.score for n in cached], [n.score for n in uncached])


def test_two_question_strings_are_each_embedded_once_with_their_own_vector():
    embed = ByText()
    vectors = qualle.QueryEmbeddings(embed)
    original, rewrite = "And how?", "How do I join a FORRT team?"
    for _ in range(3):
        a, b = vectors.get(original), vectors.lazy(rewrite)()
    assert embed.calls == {original: 1, rewrite: 1}
    assert np.allclose(a, ByText.VECTORS[original]) and np.allclose(b, ByText.VECTORS[rewrite])
