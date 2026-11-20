import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import calibrate_embedding  # noqa: E402
from just_os import rag_service, voyage  # noqa: E402


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, model, input, extra_body):
        self.calls.append(extra_body["input_type"])
        return SimpleNamespace(data=[SimpleNamespace(embedding=[3.0, 4.0]) for _ in input], usage=None)


def fake_voyage():
    v = voyage.Voyage("mongodb/voyage-4-large", api_key="test")
    v.client = SimpleNamespace(embeddings=FakeEmbeddings())
    return v


def test_voyage_sends_input_type_and_normalizes():
    v = fake_voyage()
    assert np.allclose(v.documents(["a", "b", "c"], batch=2), [[0.6, 0.8]] * 3)
    assert np.allclose(v.query("q"), [0.6, 0.8])
    assert sorted(v.client.embeddings.calls) == ["document", "document", "query"]


def test_create_embedding_model_picks_voyage_for_voyage_ids(monkeypatch):
    monkeypatch.setattr(rag_service, "Voyage", lambda model: fake_voyage())
    model = rag_service.create_embedding_model({"EMBEDDING_MODEL": "mongodb/voyage-4-large"})
    assert isinstance(model, rag_service.VoyageEmbedding)
    assert np.allclose(model.get_query_embedding("q"), [0.6, 0.8])
    assert not voyage.is_voyage("BAAI/bge-m3")


def test_matched_threshold_cuts_the_same_share():
    old, new = np.array([0.4, 0.5, 0.6, 0.7]), np.array([0.1, 0.2, 0.3, 0.4])
    share, value = calibrate_embedding.matched(0.55, old, new)
    assert share == 0.5 and np.mean(new < value) == 0.5
