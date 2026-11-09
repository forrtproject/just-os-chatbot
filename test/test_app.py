import json

import fakeredis
import pytest
from flask import request

from config import settings
from just_os.app import FlaskApp


class FakeRag:
    def get_arena_response(self, query, models):
        yield {"status": "in-progress", "message": "Generating responses"}
        yield {
            "status": "complete",
            "responses": [
                {"model": m, "message": f"<p>answer {i}</p>", "sources": "", "seconds": 1.0}
                for i, m in enumerate(models)
            ],
        }


@pytest.fixture
def app():
    flask_app = FlaskApp()
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app._rag_service = FakeRag()
    flask_app.config.update(ARENA_ENABLED=True, ARENA_MODELS="m1,m2", RATE_LIMIT="1000/minute")
    flask_app.rate_limit_manager.limiter.enabled = False
    return flask_app


def test_up(app):
    assert app.app.test_client().get("/up").status_code == 200


def test_arena_off_by_default(app):
    app.config["ARENA_ENABLED"] = False
    client = app.app.test_client()
    assert client.get("/arena").status_code == 404
    assert client.post("/arena/chat", json={"message": "question"}).status_code == 404


def test_arena_hides_models_until_vote(app):
    client = app.app.test_client()
    lines = client.post("/arena/chat", json={"message": "What is open data?"}).data.decode().splitlines()
    final = json.loads(lines[-1])

    assert [r["label"] for r in final["responses"]] == ["A", "B"]
    assert all("model" not in r for r in final["responses"])

    vote = client.post("/arena/vote", json={"battle_id": final["battle_id"], "vote": "a"}).get_json()
    assert sorted(vote["models"]) == ["m1", "m2"]

    again = client.post("/arena/vote", json={"battle_id": final["battle_id"], "vote": "b"})
    assert again.status_code == 404  # one vote per battle

    votes = client.get("/arena/votes").get_json()
    assert len(votes) == 1
    assert votes[0]["vote"] == "a"
    assert votes[0]["model_a"] == vote["models"][0]
    assert votes[0]["question"] == "What is open data?"


def test_arena_rejects_bad_vote(app):
    client = app.app.test_client()
    assert client.post("/arena/vote", json={"battle_id": "x", "vote": "maybe"}).status_code == 400


# --- finding 13: ProxyFix only when configured


def client_ip(flask_app):
    """The IP the app sees for a request that came through a proxy."""
    flask_app.app.add_url_rule("/ip", "ip", lambda: request.remote_addr)
    response = flask_app.app.test_client().get("/ip", headers={"X-Forwarded-For": "203.0.113.7"})
    return response.get_data(as_text=True)


def test_proxy_fix_uses_forwarded_ip(monkeypatch):
    monkeypatch.setitem(settings.DEFAULT_CONFIG, "PROXY_FIX_X_FOR", 1)
    assert client_ip(FlaskApp()) == "203.0.113.7"


def test_no_proxy_fix_by_default(app):
    assert client_ip(app) != "203.0.113.7"  # a client cannot fake its IP
