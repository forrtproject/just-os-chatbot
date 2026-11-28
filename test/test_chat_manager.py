"""just_os/chat_manager.py: the chat memory in Redis stays bounded."""

import fakeredis
import pytest

from just_os.chat_manager import ChatManager


class Down(fakeredis.FakeRedis):
    def pipeline(self, *a, **k):
        from redis.exceptions import ConnectionError

        raise ConnectionError("down")


def test_history_keeps_only_the_newest_messages_with_the_ttl():
    redis = fakeredis.FakeRedis()
    manager = ChatManager(redis)
    manager.max_messages = 6
    for i in range(10):
        manager.add_message("c1", {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"})
    history = manager.get_history("c1")
    assert [m["content"] for m in history] == ["m4", "m5", "m6", "m7", "m8", "m9"]  # oldest first, newest kept
    assert redis.llen("chat:c1") == 6
    assert 0 < redis.ttl("chat:c1") <= manager.message_ttl


def test_default_bound_comes_from_the_settings():
    from config.settings import DEFAULT_CONFIG

    manager = ChatManager(fakeredis.FakeRedis())
    assert manager.max_messages == DEFAULT_CONFIG["MAX_HISTORY_MESSAGES"] == 20
    for i in range(50):
        manager.add_message("c", {"role": "user", "content": str(i)})
    assert len(manager.get_history("c")) == 20


def test_a_redis_error_is_reported_not_raised():
    assert ChatManager(Down()).add_message("c", {"role": "user", "content": "q"}) is False


def test_redis_calls_time_out_instead_of_hanging(monkeypatch):
    """A Redis that stops answering (node lost, paused) must fail fast: /ready then gives 503 and the rate
    limiter's swallow_errors lets requests through, instead of every thread waiting for TCP."""
    from just_os import database

    monkeypatch.setattr(database, "_redis_client", None)
    client = database.get_redis_client()
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 2
    monkeypatch.setattr(database, "_redis_client", None)


def silent_server():
    """A TCP server that accepts connections and never answers: a hung Redis. Returns (socket, accepted list)."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(50)
    accepted = []

    def accept():
        while True:
            try:
                accepted.append(server.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    return server, accepted


def test_a_hung_redis_is_asked_once_not_retried(monkeypatch):
    """redis-py retries a timed-out command with backoff by default (11 connections, ~5 s at a 0.1 s timeout):
    the shared options make one try, so a request or probe waits REDIS_TIMEOUT once."""
    import time

    from redis import Redis
    from redis.exceptions import TimeoutError as RedisTimeout
    from limits.storage import RedisStorage

    from just_os import database

    monkeypatch.setitem(database.DEFAULT_CONFIG, "REDIS_TIMEOUT", 0.1)
    server, accepted = silent_server()
    try:
        port = server.getsockname()[1]
        client = Redis(host="127.0.0.1", port=port, **database.redis_timeouts())
        start = time.monotonic()
        with pytest.raises(RedisTimeout):
            client.ping()
        assert len(accepted) == 1 and time.monotonic() - start < 1
        # the rate limiter's client gets the same options (app.RateLimitManager storage_options)
        limiter = RedisStorage(f"redis://127.0.0.1:{port}/0", **database.redis_timeouts())
        with pytest.raises(RedisTimeout):
            limiter.storage.ping()
        assert len(accepted) == 2
    finally:
        server.close()


def test_a_question_and_its_answer_are_kept_in_one_transaction():
    redis = fakeredis.FakeRedis()
    manager = ChatManager(redis)
    calls = []
    pipeline = redis.pipeline

    def recording_pipeline(*a, **k):
        calls.append(k)
        return pipeline(*a, **k)

    redis.pipeline = recording_pipeline
    assert manager.add_turn("c", "What is open data?", "Data anyone may reuse.")
    assert manager.add_turn("c", "And open code?", "Code anyone may reuse.")
    assert calls == [{"transaction": True}] * 2  # one MULTI per turn: two requests cannot interleave the messages
    assert [m["content"] for m in manager.get_history("c")] == [
        "What is open data?", "Data anyone may reuse.", "And open code?", "Code anyone may reuse."]
    assert [m["role"] for m in manager.get_history("c")] == ["user", "assistant"] * 2
    assert ChatManager(Down()).add_turn("c", "q", "a") is False


def test_the_rate_limiter_gets_the_same_timeouts():
    from just_os.app import FlaskApp

    flask_app = FlaskApp()
    storage = flask_app.rate_limit_manager.limiter.storage
    kwargs = storage.storage.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 2
