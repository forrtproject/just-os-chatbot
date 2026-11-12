from types import SimpleNamespace

import pytest

from just_os import qualle


class FakeRetriever:
    def __init__(self, nodes):
        self.nodes = nodes

    def retrieve(self, query):
        return self.nodes


def make_retriever(monkeypatch, nodes, predict, **settings):
    monkeypatch.setattr(
        qualle, "CrossEncoder", lambda name: SimpleNamespace(predict=predict)
    )
    config = {"RERANK_MODEL": "fake", "MAX_CHUNKS": 2, "MIN_RELEVANCE": 0.1, **settings}
    return qualle.DocumentRetriever(config, FakeRetriever(nodes))


@pytest.fixture
def nodes():
    return [SimpleNamespace(text=f"text {i}", metadata={"title": f"t{i}"}) for i in range(3)]


def test_rerank_sorts_filters_and_limits(monkeypatch, nodes):
    retriever = make_retriever(monkeypatch, nodes, lambda pairs: [0.5, 0.05, 0.9])

    ranked, all_nodes = retriever.retrieve_and_rerank("q")

    assert ranked == [nodes[2], nodes[0]]
    assert all_nodes == nodes


def test_rerank_failure_falls_back_to_vector_order(monkeypatch, nodes):
    def broken(pairs):
        raise RuntimeError("reranker down")

    retriever = make_retriever(monkeypatch, nodes, broken)

    ranked, _ = retriever.retrieve_and_rerank("q")

    assert ranked == nodes[:2]


def no_reranker(name):
    raise AssertionError("the re-ranker should not be loaded")


def scored(distances):
    """Search hits with FAISS scores (squared L2 distance of unit vectors)."""
    return [SimpleNamespace(text=f"text {i}", metadata={"title": f"t{i}"}, score=d) for i, d in enumerate(distances)]


def test_rerank_off_keeps_search_order_without_loading_the_reranker(monkeypatch, nodes):
    monkeypatch.setattr(qualle, "CrossEncoder", no_reranker)
    config = {"RERANK_MODEL": "fake", "MAX_CHUNKS": 2, "MIN_RELEVANCE": 0.1, "RERANK": False, "MIN_VECTOR_SIMILARITY": 0}
    retriever = qualle.DocumentRetriever(config, FakeRetriever(nodes))

    ranked, all_nodes = retriever.retrieve_and_rerank("q")

    assert retriever.reranker is None
    assert ranked == nodes[:2] and all_nodes == nodes


def test_rerank_off_gives_no_sources_below_the_vector_similarity(monkeypatch):
    far, near = scored([1.0, 1.2]), scored([0.8, 1.0])  # best cosine 0.50 and 0.60
    for hits, kept in ((far, []), (near, near[:2])):
        retriever = make_retriever(monkeypatch, hits, None, RERANK=False, MIN_VECTOR_SIMILARITY=0.55)
        assert retriever.retrieve_and_rerank("q")[0] == kept


def test_bm25_search_has_no_vector_similarity_check(monkeypatch):
    hits = scored([3.5, 1.2])  # BM25 scores, on no fixed scale
    retriever = make_retriever(monkeypatch, hits, None, RERANK=False, SEARCH_MODE="bm25", MIN_VECTOR_SIMILARITY=0.55)
    assert retriever.retrieve_and_rerank("q")[0] == hits[:2]


def test_verify_citations_loads_the_reranker_without_reranking(monkeypatch, nodes):
    retriever = make_retriever(monkeypatch, nodes, lambda pairs: [0.9] * len(pairs), RERANK=False, VERIFY_CITATIONS=True)
    assert retriever.reranker is not None
    assert retriever.unsupported_citations("Claim [0].", nodes) == set()
