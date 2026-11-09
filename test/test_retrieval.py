from types import SimpleNamespace

from llama_index.core.schema import NodeWithScore, TextNode

from just_os import qualle
from just_os.hybrid import BM25, HybridRetriever, reciprocal_rank_fusion


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
