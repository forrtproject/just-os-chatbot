from types import SimpleNamespace

import pytest

from just_os import qualle


class FakeRetriever:
    def __init__(self, nodes):
        self.nodes = nodes

    def retrieve(self, query):
        return self.nodes


def make_retriever(monkeypatch, nodes, predict):
    monkeypatch.setattr(
        qualle, "CrossEncoder", lambda name: SimpleNamespace(predict=predict)
    )
    config = {"RERANK_MODEL": "fake", "MAX_CHUNKS": 2, "MIN_RELEVANCE": 0.1}
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
