"""One question embedding per turn (QueryEmbeddings): the answer cache, the cosine router, the FORRT page search,
the vector search and the cluster boost used to embed the same question up to five times."""

from collections import Counter
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
