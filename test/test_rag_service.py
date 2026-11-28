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


def test_concurrent_first_requests_load_the_service_once_and_a_failure_is_not_retried_at_once(monkeypatch):
    """Eight requests at start-up: one load (each holds ~4 GB), not eight; a failed load is not repeated by every
    request (an out-of-memory retry storm), only after INIT_RETRY_SECONDS."""
    import threading
    import time

    monkeypatch.setattr(rag_service, "_rag_service_instance", None)
    monkeypatch.setattr(rag_service, "_rag_init_error", None)
    monkeypatch.setattr(rag_service, "_rag_init_failed_at", 0.0)
    calls, gate = [], threading.Event()

    def failing_build(config, chat_manager):
        calls.append(1)
        gate.wait(2)
        raise MemoryError("index too big")

    monkeypatch.setattr(rag_service, "_build_rag_service", failing_build)
    errors = []

    def request():
        try:
            rag_service.create_rag_service({}, object())
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=request) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join(5)
    assert len(calls) == 1 and len(errors) == 8
    assert rag_service.rag_status() == (False, "MemoryError: index too big")

    # after INIT_RETRY_SECONDS one caller tries again; a success clears the error
    monkeypatch.setattr(rag_service, "_rag_init_failed_at", time.monotonic() - rag_service.INIT_RETRY_SECONDS - 1)
    service = object()
    monkeypatch.setattr(rag_service, "_build_rag_service", lambda config, chat_manager: calls.append(1) or service)
    assert rag_service.create_rag_service({}, object()) is service
    assert rag_service.create_rag_service({}, object()) is service and len(calls) == 2
    assert rag_service.rag_status() == (True, None)


def test_concurrent_first_requests_share_one_successful_load(monkeypatch):
    import threading

    monkeypatch.setattr(rag_service, "_rag_service_instance", None)
    monkeypatch.setattr(rag_service, "_rag_init_error", None)
    calls, service, gate = [], object(), threading.Event()

    def build(config, chat_manager):
        calls.append(1)
        gate.wait(2)
        return service

    monkeypatch.setattr(rag_service, "_build_rag_service", build)
    got = []
    threads = [threading.Thread(target=lambda: got.append(rag_service.create_rag_service({}, object()))) for _ in range(8)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert len(calls) == 1 and got == [service] * 8


def test_the_gunicorn_preload_goes_through_the_app(monkeypatch):
    """post_worker_init loads through the app gunicorn loaded, so the service shares its config and chat manager."""
    from types import SimpleNamespace
    from config import gunicorn

    loaded, logged = [], []
    flask_app = SimpleNamespace(get_rag_service=lambda: loaded.append(1) or object())
    worker = SimpleNamespace(wsgi=SimpleNamespace(extensions={"just_os": flask_app}), log=SimpleNamespace(error=logged.append))
    monkeypatch.setattr(rag_service, "create_rag_service", lambda *a, **k: (_ for _ in ()).throw(AssertionError("second config")))
    gunicorn.post_worker_init(worker)
    assert loaded == [1] and logged == []
    flask_app.get_rag_service = lambda: None  # the load failed: logged, the worker still starts
    gunicorn.post_worker_init(worker)
    assert logged and "/ready" in logged[0]


def test_the_app_registers_itself_for_the_preload():
    import fakeredis
    from just_os.app import FlaskApp

    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    assert flask_app.app.extensions["just_os"] is flask_app
