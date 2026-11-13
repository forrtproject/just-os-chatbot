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


def test_adaptive_top_k_keeps_chunks_near_the_best_score(monkeypatch):
    many = [SimpleNamespace(text=f"text {i}", metadata={"title": f"t{i}"}) for i in range(6)]
    scores = lambda pairs: [0.9, 0.8, 0.3, 0.2, 0.15, 0.05]  # noqa: E731
    settings = {"MAX_CHUNKS": 5, "ADAPTIVE_TOP_K_RATIO": 0.5, "ADAPTIVE_TOP_K_MIN": 1}
    targeted, _ = make_retriever(monkeypatch, many, scores, ADAPTIVE_TOP_K=True, **settings).retrieve_and_rerank("q")
    assert targeted == many[:2]  # 0.3 < 0.9 * 0.5
    at_least, _ = make_retriever(monkeypatch, many, scores, ADAPTIVE_TOP_K=True,
                                 **{**settings, "ADAPTIVE_TOP_K_MIN": 3}).retrieve_and_rerank("q")
    assert at_least == many[:3]
    fixed, _ = make_retriever(monkeypatch, many, scores, **settings).retrieve_and_rerank("q")
    assert fixed == many[:5]  # off (default): up to MAX_CHUNKS above MIN_RELEVANCE


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



def test_rerank_off_without_the_setting_uses_the_default_vector_similarity(monkeypatch):
    far = scored([1.0, 1.2])  # best cosine 0.50, below the default 0.55 of config/settings.py
    assert make_retriever(monkeypatch, far, None, RERANK=False).retrieve_and_rerank("q")[0] == []

def test_bm25_search_has_no_vector_similarity_check(monkeypatch):
    hits = scored([3.5, 1.2])  # BM25 scores, on no fixed scale
    retriever = make_retriever(monkeypatch, hits, None, RERANK=False, SEARCH_MODE="bm25", MIN_VECTOR_SIMILARITY=0.55)
    assert retriever.retrieve_and_rerank("q")[0] == hits[:2]


def test_verify_citations_loads_the_reranker_without_reranking(monkeypatch, nodes):
    retriever = make_retriever(monkeypatch, nodes, lambda pairs: [0.9] * len(pairs), RERANK=False, VERIFY_CITATIONS=True)
    assert retriever.reranker is not None
    assert retriever.unsupported_citations("Claim [0].", nodes) == set()
