from types import SimpleNamespace

from llama_index.core.schema import NodeWithScore, TextNode

from just_os import qualle
import pytest

from just_os.hybrid import BM25, HybridRetriever, KeywordRetriever, reciprocal_rank_fusion, search_retriever, vector_cosine


# --- N2 (#20): at most MAX_CHUNKS_PER_DOC chunks of one paper


def chunk(doi):
    return SimpleNamespace(text="t", metadata={"doi": doi, "title": doi})


def retriever(max_per_doc, max_chunks=7):
    r = object.__new__(qualle.DocumentRetriever)
    r.n_context_items, r.max_per_doc = max_chunks, max_per_doc
    return r


def test_per_paper_cap_keeps_variety():
    nodes = [chunk("10.1234/a")] * 7 + [chunk("10.1234/b"), chunk("10.1234/c")]
    kept = retriever(2).limit_per_document(nodes)
    assert [n.metadata["doi"] for n in kept] == ["10.1234/a", "10.1234/a", "10.1234/b", "10.1234/c"]


def test_no_cap_by_default():
    nodes = [chunk("10.1234/a")] * 9
    assert len(retriever(0).limit_per_document(nodes)) == 7


# --- N1 (#19): BM25 + vector search


def test_bm25_finds_exact_terms():
    bm25 = BM25(["preregistration of studies", "HARKing is hypothesizing after results", "open data"])
    assert bm25.top("what is HARKing", 3) == [1]
    assert bm25.top("nothing matches zzz", 3) == []


def test_reciprocal_rank_fusion_rewards_both_lists():
    assert reciprocal_rank_fusion(["a", "b", "c"], ["c", "d"])[0] == "c"


def test_hybrid_adds_keyword_hits_to_vector_hits():
    nodes = [TextNode(id_=f"n{i}", text=t) for i, t in enumerate(["open science", "CRediT taxonomy roles", "data sharing"])]

    class Vector:
        def retrieve(self, query):
            return [NodeWithScore(node=nodes[0], score=0.9)]

    hits = HybridRetriever(Vector(), nodes, top_k=5).retrieve("CRediT roles")
    ids = [h.node.node_id for h in hits]
    assert set(ids) == {"n0", "n1"}
    assert hits[ids.index("n0")].score == 0.9  # vector hit keeps its score
    assert hits[ids.index("n1")].score is None  # a keyword hit has no vector score


def test_keyword_retriever_returns_bm25_hits_best_first():
    nodes = [TextNode(id_=f"n{i}", text=t) for i, t in enumerate(["open data", "HARKing and HARKing", "HARKing once"])]
    hits = KeywordRetriever(nodes, top_k=5).retrieve("HARKing")
    assert [h.node.node_id for h in hits] == ["n1", "n2"]
    assert hits[0].score > hits[1].score > 0


def test_search_mode_picks_the_retriever():
    vector = object()
    nodes = [TextNode(id_="n0", text="open data")]
    assert search_retriever("vector", vector, [], 5) is vector
    assert isinstance(search_retriever("bm25", vector, nodes, 5), KeywordRetriever)
    assert search_retriever("bm25", vector, nodes, 5).vector_retriever is vector  # for the cosine router
    assert isinstance(search_retriever("hybrid", vector, nodes, 5), HybridRetriever)
    with pytest.raises(ValueError, match="SEARCH_MODE"):
        search_retriever("vectors", vector, nodes, 5)


def test_vector_cosine_from_faiss_l2_distance():
    hits = [NodeWithScore(node=TextNode(text="a"), score=0.9), NodeWithScore(node=TextNode(text="b"), score=None),
            NodeWithScore(node=TextNode(text="c"), score=0.6)]
    assert vector_cosine(hits) == pytest.approx(0.7)  # best match: squared distance 0.6
    assert vector_cosine(hits[1:2]) is None  # keyword hits only
