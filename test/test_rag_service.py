"""just_os/rag_service.py: create_retriever wires SEARCH_MODE to the retriever (#48)."""

from types import SimpleNamespace

from just_os import rag_service


def test_create_retriever_reads_the_docstore_only_for_bm25_and_hybrid(monkeypatch):
    docs = {"n1": SimpleNamespace(get_content=lambda: "open data", node_id="n1"),
            "n2": SimpleNamespace(get_content=lambda: "HARKing", node_id="n2")}
    vector = object()
    index = SimpleNamespace(docstore=SimpleNamespace(docs=docs), as_retriever=lambda similarity_top_k: vector)
    monkeypatch.setattr(rag_service.FaissVectorStore, "from_persist_dir", lambda path: object())
    monkeypatch.setattr(rag_service.StorageContext, "from_defaults", lambda **kwargs: object())
    monkeypatch.setattr(rag_service, "load_index_from_storage", lambda **kwargs: index)
    seen = {}

    def search_retriever(mode, retriever, nodes, top_k):
        seen[mode] = (retriever, nodes, top_k)
        return mode

    monkeypatch.setattr(rag_service, "search_retriever", search_retriever)
    for mode in ("vector", "bm25", "hybrid"):
        assert rag_service.create_retriever({"VECTOR_STORE": "x", "RETRIEVER_TOP_K": 20, "SEARCH_MODE": mode}, None) == mode
    assert seen["vector"] == (vector, [], 20)
    assert seen["bm25"][1] == list(docs.values()) and seen["hybrid"][1] == list(docs.values())
