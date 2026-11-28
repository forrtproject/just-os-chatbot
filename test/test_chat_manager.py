"""just_os/chat_manager.py: the chat memory in Redis stays bounded."""

import fakeredis

from just_os.chat_manager import ChatManager


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
    class Down(fakeredis.FakeRedis):
        def pipeline(self, *a, **k):
            from redis.exceptions import ConnectionError

            raise ConnectionError("down")

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


def test_the_rate_limiter_gets_the_same_timeouts():
    from just_os.app import FlaskApp

    flask_app = FlaskApp()
    storage = flask_app.rate_limit_manager.limiter.storage
    kwargs = storage.storage.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == kwargs["socket_connect_timeout"] == 2
