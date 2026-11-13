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
def app(tmp_path):
    flask_app = FlaskApp()
    flask_app.config["ARENA_RATINGS_FILE"] = str(tmp_path / "arena" / "ratings.jsonl")
    flask_app.config["ARENA_ROUNDS_FILE"] = str(tmp_path / "arena" / "rounds.jsonl")
    flask_app.config["CHAT_LOG_FILE"] = str(tmp_path / "chats" / "chats.jsonl")
    flask_app.config["CHAT_FEEDBACK_FILE"] = str(tmp_path / "chats" / "feedback.jsonl")
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app._rag_service = FakeRag()
    # ROUTER "": the tests must not depend on the default topic check in .env
    flask_app.config.update(ARENA_ENABLED=True, ARENA_MODELS="m1,m2", RATE_LIMIT="1000/minute", ROUTER="")
    flask_app.rate_limit_manager.limiter.enabled = False
    return flask_app


def test_up(app):
    assert app.app.test_client().get("/up").status_code == 200


def test_arena_off_by_default(app):
    app.config["ARENA_ENABLED"] = False
    client = app.app.test_client()
    assert client.get("/arena").status_code == 404
    assert client.post("/arena/chat", json={"message": "question"}).status_code == 404


def ask(client, models=None):
    body = {"message": "What is open data?"}
    if models is not None:
        body["models"] = models
    response = client.post("/arena/chat", json=body)
    return response, json.loads(response.data.decode().splitlines()[-1])


def scores(correct=4, references=3, clarity=5):
    return {"correct": correct, "references": references, "clarity": clarity}


def test_arena_asks_chosen_models_and_shows_names(app):
    app.config["ARENA_MODELS"] = "m1,m2,m3"
    _, final = ask(app.app.test_client(), ["m1", "m3"])
    assert [r["label"] for r in final["responses"]] == ["A", "B"]
    assert sorted(r["model"] for r in final["responses"]) == ["m1", "m3"]


def test_blind_arena_hides_names_until_rated(app):
    app.config["ARENA_BLIND"] = True
    _, final = ask(app.app.test_client(), ["m1", "m2"])
    assert all("model" not in r for r in final["responses"])


def test_arena_rejects_unknown_or_too_many_models(app):
    client = app.app.test_client()
    assert ask(client, ["m1", "not-a-model"])[0].status_code == 400
    app.config["ARENA_MAX_MODELS"] = 1
    assert ask(client, ["m1", "m2"])[0].status_code == 400


def test_arena_hides_openscholar_without_its_server(app):
    app.config.update(ARENA_MODELS="m1,openscholar-8b", OPENSCHOLAR_MODEL="openscholar-8b", OPENSCHOLAR_BASE_URL="")
    assert app.arena_models() == ["m1"]
    app.config["OPENSCHOLAR_BASE_URL"] = "http://openscholar.test/v1"
    assert app.arena_models() == ["m1", "openscholar-8b"]


def test_arena_rating_reveals_models_and_builds_leaderboard(app):
    client = app.app.test_client()
    _, final = ask(client)  # no "models": all available (m1, m2)
    battle = final["battle_id"]

    rated = client.post("/arena/rate", json={"battle_id": battle, "ratings": {"A": scores(5, 5, 5), "B": scores(1, 2, 3)}})
    models = rated.get_json()["models"]
    assert sorted(models.values()) == ["m1", "m2"]
    assert client.post("/arena/rate", json={"battle_id": battle, "ratings": {"A": scores()}}).status_code == 404

    board = client.get("/arena/leaderboard").get_json()
    assert [row["model"] for row in board] == [models["A"], models["B"]]  # best overall first
    assert board[0] == {"model": models["A"], "ratings": 1, "correct": 5.0, "references": 5.0,
                        "clarity": 5.0, "overall": 5.0, "seconds": 1.0}
    assert board[1]["overall"] == 2.0
    rows = client.get("/arena/ratings").get_json()
    assert rows[0]["question"] == "What is open data?"
    # the rated text is kept, so a low score can be read next to the answer
    assert {r["answer"] for r in rows} == {"<p>answer 0</p>", "<p>answer 1</p>"}
    assert all("sources" in r for r in rows)

    with open(app.config["ARENA_RATINGS_FILE"], encoding="utf-8") as file:
        saved = [json.loads(line) for line in file]
    assert saved == client.get("/arena/ratings").get_json()  # same rows as Redis
    # every round is logged, and its ratings point back to it
    [round_row] = read_jsonl(app.config["ARENA_ROUNDS_FILE"])
    assert round_row["question"] == "What is open data?" and set(round_row["answers"]) == {"A", "B"}
    assert {r["battle_id"] for r in saved} == {round_row["battle_id"]} == {battle}


def test_arena_rejects_bad_ratings(app):
    client = app.app.test_client()
    for ratings in ({}, {"A": {"correct": 6, "references": 3, "clarity": 3}},
                    {"A": {"correct": 3}}, {"A": {"correct": True, "references": 3, "clarity": 3}}):
        assert client.post("/arena/rate", json={"battle_id": "x", "ratings": ratings}).status_code == 400


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


def test_arena_page_keeps_criteria_order(app):
    html = app.app.test_client().get("/arena").get_data(as_text=True)
    start = html.index("data-criteria='") + len("data-criteria='")
    keys = [key for key, _ in json.loads(html[start:html.index("'", start)])]
    assert keys == ["correct", "references", "clarity"]  # same order as the table headers


def test_chat_rejects_unknown_model(app):
    response = app.app.test_client().post("/chat", json={"message": "What is open data?", "chat_id": "c", "model": "not-a-model"})
    assert response.status_code == 400


def test_chat_page_offers_models_with_default_first(app):
    app.config.update(CITATION_MODEL="m2", ARENA_MODELS="m1,m2")
    assert app.chat_models() == ["m2", "m1"]
    html = app.app.test_client().get("/").get_data(as_text=True)
    assert '<select id="model-select">' in html and "m2 (default)" in html


def test_chat_stream_error_in_the_language_of_the_question(app):
    class BrokenRag:
        def get_response(self, query, chat_id, model):
            raise RuntimeError("broken")
            yield

    app._rag_service = BrokenRag()
    question = "Akademide kariyer ilerlemesi için hangi beceriler gereklidir?"
    response = app.app.test_client().post("/chat", json={"message": question, "chat_id": "c"})
    final = json.loads(response.data.decode().splitlines()[-1])
    assert final["status"] == "error"
    assert final["message"] == "İsteğiniz işlenirken beklenmeyen bir hata oluştu."
    assert read_jsonl(app.config["CHAT_LOG_FILE"])[0]["outcome"] == "error"


# --- chat log and feedback


def read_jsonl(path):
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file]


class ChatRag:
    def __init__(self, *finals):
        self.finals = list(finals)

    def get_response(self, query, chat_id, model):
        yield {"status": "in-progress", "message": "Finding relevant sources"}
        yield self.finals.pop(0)


def chat(client, message="What is open data?"):
    response = client.post("/chat", json={"message": message, "chat_id": "c1"})
    return json.loads(response.data.decode().splitlines()[-1])


def test_every_chat_turn_is_logged_with_its_outcome(app):
    refs = [{"number": 1, "title": "Open data", "snippet": "Open data is free."}]
    app._rag_service = ChatRag(
        {"status": "complete", "message": "<p>Open data is [1].</p>", "outcome": "answered", "metadata": {"references": refs}},
        {"status": "complete", "message": "<p>Sorry, I'm only able to answer questions related to Open Science and FORRT.</p>", "outcome": "off_topic"},
        {"status": "complete", "message": "<p>cached</p>"},  # cached answers carry no outcome
    )
    client = app.app.test_client()
    finals = [chat(client), chat(client, "Best pizza in town?"), chat(client)]
    assert all(f["turn_id"] for f in finals)
    rows = read_jsonl(app.config["CHAT_LOG_FILE"])
    assert [r["outcome"] for r in rows] == ["answered", "off_topic", "answered"]
    assert rows[0]["question"] == "What is open data?" and rows[0]["references"] == refs
    assert rows[1]["answer"].startswith("<p>Sorry") and rows[1]["chat_id"] == "c1"
    assert [r["turn_id"] for r in rows] == [f["turn_id"] for f in finals]
    assert "lang" in rows[0] and rows[1]["answer_lang"] == "en"  # languages of question and answer


def test_feedback_is_stored_once_with_the_question_and_answer(app):
    app._rag_service = ChatRag({"status": "complete", "message": "<p>answer</p>", "outcome": "answered"})
    client = app.app.test_client()
    turn = chat(client)["turn_id"]
    sent = client.post("/chat/feedback", json={"turn_id": turn, "rating": "bad", "comment": " Wrong source. "})
    assert sent.status_code == 200
    again = client.post("/chat/feedback", json={"turn_id": turn, "rating": "good"})
    assert again.status_code == 404  # one feedback per answer
    [row] = read_jsonl(app.config["CHAT_FEEDBACK_FILE"])
    assert (row["rating"], row["comment"], row["question"], row["answer"]) == ("bad", "Wrong source.", "What is open data?", "<p>answer</p>")


class StreamingRag:
    def __init__(self):
        self.options = []

    def get_response(self, query, chat_id, model, **options):
        self.options.append(options)
        yield {"status": "partial", "delta": "Open data "}
        yield {"status": "partial", "delta": "is good."}
        yield {"status": "complete", "message": "<p>Open data is good [1].</p>", "outcome": "answered"}


def test_partial_messages_only_on_request_and_never_logged(app):
    rag = app._rag_service = StreamingRag()
    client = app.app.test_client()
    lines = client.post("/chat", json={"message": "What is open data?", "chat_id": "c1", "stream": True}).data.decode().splitlines()
    assert [json.loads(line)["status"] for line in lines] == ["partial", "partial", "complete"]
    client.post("/chat", json={"message": "What is open data?", "chat_id": "c1"}).data  # the widget sends no flag
    assert rag.options == [{"stream": True}, {}]
    assert [r["outcome"] for r in read_jsonl(app.config["CHAT_LOG_FILE"])] == ["answered", "answered"]


def test_feedback_rejects_bad_input(app):
    client = app.app.test_client()
    for body in ({"turn_id": "x", "rating": "meh"}, {"turn_id": "x", "rating": "good", "comment": "x" * 2001},
                 {"turn_id": "x", "rating": "good", "comment": 5}):
        assert client.post("/chat/feedback", json=body).status_code == 400
    assert client.post("/chat/feedback", json={"turn_id": ["x"], "rating": "good"}).status_code == 404


def test_every_page_links_to_the_others_and_marks_itself(app):
    client = app.app.test_client()
    for path in ("/", "/arena", "/eval"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="top-nav"' in html and 'href="/eval"' in html and 'href="/arena"' in html, path
        assert f'href="{path}" aria-current="page"' in html, path
    app.config["ARENA_ENABLED"] = False  # production: no link to a page that is off
    assert 'href="/arena"' not in client.get("/").get_data(as_text=True)


def test_topic_check_choice_is_checked_and_passed_on(app):
    class RouterRag:
        def __init__(self):
            self.options = []

        def get_response(self, query, chat_id, model, **options):
            self.options.append(options)
            yield {"status": "complete", "message": "<p>ok</p>", "outcome": "answered"}

    rag = app._rag_service = RouterRag()
    client = app.app.test_client()
    client.post("/chat", json={"message": "What is open data?", "chat_id": "c", "router": "cosine"}).data
    client.post("/chat", json={"message": "What is open data?", "chat_id": "c"}).data  # the widget: as before
    assert rag.options == [{"router": "cosine"}, {}]
    assert client.post("/chat", json={"message": "What is open data?", "chat_id": "c", "router": "bogus"}).status_code == 400
    assert [r["router"] for r in read_jsonl(app.config["CHAT_LOG_FILE"])] == ["cosine", "default"]
    html = client.get("/").get_data(as_text=True)
    assert 'id="router-select"' in html and 'value="jev"' in html and 'value="none"' in html


def test_review_page_and_save_keep_every_reviewer_in_its_own_csv(app, tmp_path):
    import csv
    items = [{"id": "q1", "category": "open science", "question": "What is open data?", "expected": "answer",
              "bot_did": "answered from the papers", "answered_from": "papers", "answer": "Open data is [0].",
              "sources": [{"n": 0, "title": "Paper", "doi": "10.1/a", "link": "https://doi.org/10.1/a",
                           "passage": "Open data are free.", "cited": True}]}]
    (tmp_path / "items.json").write_text(json.dumps(items))
    app.config.update(REVIEW_ITEMS_FILE=str(tmp_path / "items.json"), REVIEW_DIR=str(tmp_path / "reviews"))
    client = app.app.test_client()
    html = client.get("/review").get_data(as_text=True)
    assert "What is open data?" in html and "DOI 10.1/a" in html and "Open data are free." in html
    scores = {"q1": {"decision": "right", "correctness": "4", "citation_support": "5", "source_relevance": "n/a",
                     "completeness": "3", "clarity": "4", "note": "=HYPERLINK(x)"}}
    assert client.post("/review/save", json={"reviewer": "", "scores": scores}).status_code == 400  # name needed
    assert client.post("/review/save", json={"reviewer": "A", "scores": {"zz": {}}}).status_code == 400  # unknown id
    assert client.post("/review/save", json={"reviewer": "A", "scores": {"q1": {"correctness": "9"}}}).status_code == 400
    first = client.post("/review/save", json={"reviewer": "Ada L.", "scores": scores}).get_json()
    second = client.post("/review/save", json={"reviewer": "Bo", "scores": scores}).get_json()
    assert first["file"] != second["file"] and first["file"].startswith("review_ada-l_")
    rows = list(csv.DictReader(open(tmp_path / "reviews" / first["file"], encoding="utf-8")))
    assert rows[0]["citation_support"] == "5" and rows[0]["note"] == "'=HYPERLINK(x)"  # no formula in a spreadsheet
    app.config["REVIEW_ITEMS_FILE"] = str(tmp_path / "missing.json")
    assert client.get("/review").status_code == 404


def test_parallel_log_writes_keep_whole_lines(app, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = str(tmp_path / "log.jsonl")
    big = ["x" * 50000]  # longer than one write call
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: app._append_jsonl(path, [json.dumps({"i": i, "text": big[0]})]), range(40)))
    assert sorted(json.loads(line)["i"] for line in open(path, encoding="utf-8")) == list(range(40))
