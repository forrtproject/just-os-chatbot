import json
import os

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


def test_no_proxy_fix_by_default(monkeypatch):
    # set here, not read from .env: a server behind a proxy sets PROXY_FIX_X_FOR=1 there
    monkeypatch.setitem(settings.DEFAULT_CONFIG, "PROXY_FIX_X_FOR", 0)
    assert client_ip(FlaskApp()) != "203.0.113.7"  # a client cannot fake its IP


def test_arena_page_keeps_criteria_order(app):
    html = app.app.test_client().get("/arena").get_data(as_text=True)
    start = html.index("data-criteria='") + len("data-criteria='")
    keys = [key for key, _ in json.loads(html[start:html.index("'", start)])]
    assert keys == ["correct", "references", "clarity"]  # same order as the table headers
    assert "data-scale='[1, 2, 3, 4, 5]'" in html  # the scale of the review page too (#54)


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


def test_prod_mode_saves_nothing_and_hides_team_pages(app):
    app.config.update(PROD_MODE=True, CITATION_MODEL="m2", ARENA_MODELS="m1,m2")
    app._rag_service = ChatRag({"status": "complete", "message": "<p>answer</p>", "outcome": "answered"})
    client = app.app.test_client()
    final = chat(client)
    assert final["message"] == "<p>answer</p>" and "turn_id" not in final  # no turn_id: no feedback buttons
    assert not app.chat_manager.redis.keys("chat:turn:*")
    assert not (os.path.exists(app.config["CHAT_LOG_FILE"]) or os.path.exists(app.config["CHAT_FEEDBACK_FILE"]))
    for path in ("/eval", "/review", "/topics", "/topics/map", "/arena", "/arena/leaderboard"):
        assert client.get(path).status_code == 404, path
    assert client.post("/chat/feedback", json={"turn_id": "x", "rating": "good"}).status_code == 404
    assert client.post("/chat", json={"message": "What is open data?", "chat_id": "c", "model": "m1"}).status_code == 400
    html = client.get("/").get_data(as_text=True)
    assert 'id="model-select"' not in html and "top-nav" not in html and "are not saved" in html
    assert "JUSTOS_DEBUG_PANEL = false" in html
    assert html.count('class="suggestion"') == 11  # one example question per FORRT cluster, in prod too
    assert client.get("/up").status_code == 200


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


def test_review_page_shows_answers_blind_and_saves_score_rows(app, tmp_path):
    items = [{"key": "k1", "answer_id": "run_261113-0800_openai__gpt-oss-20b#q1", "id": "q1", "category": "open science",
              "question": "What is open data?", "expected": "answer", "bot_did": "answered from the papers",
              "answered_from": "papers", "answer": "Open data is [0].",
              "sources": [{"n": 0, "title": "Paper", "doi": "10.1/a", "link": "https://doi.org/10.1/a",
                           "passage": "Open data are free.", "cited": True}],
              "rubric": [{"id": "r1", "criterion": "Says data are free to reuse", "type": "core"}]}]
    (tmp_path / "items.json").write_text(json.dumps(items))
    app.config.update(REVIEW_ITEMS_FILE=str(tmp_path / "items.json"), SCORES_DIR=str(tmp_path / "scores"))
    client = app.app.test_client()
    html = client.get("/review").get_data(as_text=True)
    assert "What is open data?" in html and "DOI 10.1/a" in html and "Open data are free." in html
    assert "Scores 1-5:" in html and '<option value="0">' not in html  # the arena's scale (#54)
    assert "gpt-oss" not in html and 'data-id="k1"' in html  # blind: the answer_id stays on the server
    assert "Says data are free to reuse" in html and 'id="review-setting"' in html and '<option value="rubric">' in html
    scores = {"k1": {"decision": "right", "correctness": "4", "citation_support": "5", "source_relevance": "n/a",
                     "completeness": "3", "clarity": "4", "note": "=HYPERLINK(x)", "rubric": {}}}
    assert client.post("/review/save", json={"reviewer": "", "scores": scores}).status_code == 400  # name needed
    assert client.post("/review/save", json={"reviewer": "A", "scores": {"zz": {}}}).status_code == 400  # unknown key
    assert client.post("/review/save", json={"reviewer": "A", "scores": {"k1": {"correctness": "9"}}}).status_code == 400
    first = client.post("/review/save", json={"reviewer": "Ada L.", "scores": scores}).get_json()
    second = client.post("/review/save", json={"reviewer": "Bo", "rubric": True,
                                               "scores": {"k1": {"rubric": {"r1": "2"}}}}).get_json()
    assert first["file"] != second["file"] and first["file"].startswith("scores_review_ada-l_") and first["rows"] == 1
    rows = [json.loads(line) for line in open(tmp_path / "scores" / first["file"], encoding="utf-8")]
    assert {r["answer_id"] for r in rows} == {"run_261113-0800_openai__gpt-oss-20b#q1"} and len(rows) == 5
    assert rows[0]["criterion"] == "decision" and rows[0]["note"] == "=HYPERLINK(x)"  # JSON, no spreadsheet formula
    (rubric_row,) = [json.loads(line) for line in open(tmp_path / "scores" / second["file"], encoding="utf-8")]
    assert (rubric_row["criterion"], rubric_row["score"], rubric_row["setting"]) == ("rubric:r1", 2, "rubric")
    app.config["REVIEW_ITEMS_FILE"] = str(tmp_path / "missing.json")
    assert client.get("/review").status_code == 404


def test_parallel_log_writes_keep_whole_lines(app, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = str(tmp_path / "log.jsonl")
    big = ["x" * 50000]  # longer than one write call
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: app._append_jsonl(path, [json.dumps({"i": i, "text": big[0]})]), range(40)))
    assert sorted(json.loads(line)["i"] for line in open(path, encoding="utf-8")) == list(range(40))


# --- debug panel (DEBUG_PANEL, just_os/trace.py)


class DebugRag:
    def __init__(self):
        self.options = None

    def get_response(self, message, chat_id, model, **options):
        self.options = options
        yield {"status": "complete", "message": "<p>answer</p>", "outcome": "answered"}


def test_debug_panel_is_on_by_default_and_the_setting_turns_it_off(app):
    client = app.app.test_client()
    assert b"JUSTOS_DEBUG_PANEL = true" in client.get("/").data
    rag = app._rag_service = DebugRag()
    client.post("/chat", json={"message": "a question", "chat_id": "c", "debug": True}).get_data()
    assert rag.options == {"debug": True}

    app.config["DEBUG_PANEL"] = False
    assert b"JUSTOS_DEBUG_PANEL = false" in client.get("/").data
    client.post("/chat", json={"message": "a question", "chat_id": "c", "debug": True}).get_data()
    assert rag.options == {}  # the call is as before


def test_widget_request_without_debug_is_unchanged(app):
    rag = app._rag_service = DebugRag()
    app.app.test_client().post("/chat", json={"message": "a question", "chat_id": "c"}).get_data()
    assert rag.options == {}


def test_eval_page_shows_no_accuracy_for_a_run_of_tasks_to_decline_only(app, tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "classify_261113-1000.csv").write_text(
        "model,id,gold,predicted,seconds,usd\nrouter: jev,1,decline_task,neither,0.3,0\n", encoding="utf-8")
    app.config.update(EVAL_RESULTS_DIR=str(tmp_path / "results"))
    html = app.app.test_client().get("/eval").get_data(as_text=True)
    assert "router: jev" in html and "None" not in html


def test_eval_page_shows_people_and_judges(app, tmp_path):
    (tmp_path / "scores").mkdir()
    rows = [{"answer_id": "r#a", "question_id": "a", "criterion": "clarity", "score": s, "scale": sc,
             "scorer_kind": k, "scorer": n, "setting": "default", "time": "", "note": ""}
            for s, sc, k, n in [(4, [1, 5], "person", "Ann"), (5, [1, 5], "person", "Bo"), (1.0, [0, 1], "llm", "judge")]]
    (tmp_path / "scores" / "scores_r.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    app.config.update(EVAL_RESULTS_DIR=str(tmp_path / "none"), SCORES_DIR=str(tmp_path / "scores"),
                      ANSWERS_DIR=str(tmp_path / "none"))
    html = app.app.test_client().get("/eval").get_data(as_text=True)
    assert 'id="people"' in html and "Ann / Bo" in html and "unknown model" in html
    people = html[html.index('id="people"'):]
    assert "<td>judge</td>" in people and "<td>1.00</td>" in people  # the LLM judge is shown with its score
    app.config["SCORES_DIR"] = str(tmp_path / "none")
    assert "No score rows yet" in app.app.test_client().get("/eval").get_data(as_text=True)


def test_recommend_saves_each_doi_or_link_and_rejects_the_rest(app, tmp_path):
    app.config["RECOMMENDATIONS_FILE"] = str(tmp_path / "curation" / "recommendations.jsonl")
    client = app.app.test_client()
    assert client.get("/recommend").status_code == 200
    sent = client.post("/recommend/save", json={"items": "https://doi.org/10.1177/2515245917747646\n\nhttps://osf.io/abcd1/",
                                                 "note": "Registered reports", "name": "Ana"})
    assert sent.status_code == 200
    rows = read_jsonl(app.config["RECOMMENDATIONS_FILE"])
    assert [(r["doi"], r["link_to_resource"]) for r in rows] == [
        ("10.1177/2515245917747646", "https://doi.org/10.1177/2515245917747646"), ("", "https://osf.io/abcd1/")]
    assert rows[0]["note"] == "Registered reports" and rows[1]["name"] == "Ana"
    assert client.post("/recommend/save", json={"items": "just some words"}).status_code == 400
    assert client.post("/recommend/save", json={"items": "\n".join(["10.1/a"] * 21)}).status_code == 400
    app.config["PROD_MODE"] = True
    assert client.get("/recommend").status_code == 404  # a team page


def test_articles_page_counts_the_list_and_why_resources_are_missing(app, tmp_path):
    import csv
    from just_os import article_list

    path = tmp_path / "forrt_article_list.csv"
    rows = [{"title": "Indexed paper", "category": "Article", "in_index": "yes", "in_index_as": "full text"},
            {"title": "A card", "category": "Article", "in_index": "yes", "in_index_as": "abstract card"},
            {"title": "<script>x</script>", "category": "Website / web resource", "in_index": "no",
             "last_try": "web_page_too_short"},
            {"title": "Closed paper", "category": "Article", "in_index": "no", "last_try": "no_open_access_pdf"},
            {"title": "Excluded", "category": "Article", "in_index": "no", "excluded_in_source": "yes"}]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=article_list.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    s = article_list.summary(article_list.load(str(path)))
    assert (s["wanted"], s["in_index"], s["missing"], s["missing_web"], s["excluded"]) == (4, 2, 2, 1, 1)
    assert s["by_category"]["Article"] == {"full text": 1, "abstract card": 1, "missing": 1}
    assert s["missing_by_try"] == {"web_page_too_short": 1, "no_open_access_pdf": 1}

    app.config["CLUSTERS_FILE"] = str(path)
    client = app.app.test_client()
    html = client.get("/articles").get_data(as_text=True)
    assert "Articles</a>" in html and "no_open_access_pdf" in html
    assert "<script>x</script>" not in html  # the rows go to the page as escaped JSON
    assert client.get("/articles.csv").status_code == 200
    app.config["CLUSTERS_FILE"] = str(tmp_path / "missing.csv")
    assert client.get("/articles").status_code == 404
    app.config["PROD_MODE"] = True
    assert client.get("/articles.csv").status_code == 404


def test_architecture_page_shows_this_servers_settings_prompts_and_prod_values(app):
    import html as html_lib
    from just_os import qualle

    app.config.update(MAX_CHUNKS=5, ROUTER="banded")
    client = app.app.test_client()
    html = html_lib.unescape(client.get("/architecture").get_data(as_text=True))
    assert 'href="/architecture" aria-current="page"' in html
    assert "at most 5 passages" in html  # the running config, not a copy
    assert "Rewrite the new message as one question" in html and "Which journals offer them?" in html  # live prompt
    assert qualle.LANGUAGE_RULE in html and qualle.OPEN_SCIENCE_SCOPE.splitlines()[0] in html
    assert "gemma-4-31B-it" in html  # prod value from deploy/kubernetes/just-os.yaml
    assert 'id="q-topic"' in html and 'id="i-chunks"' in html and 'id="arch-filter"' in html
    assert app.config["LLM_API_KEY"] is None or app.config["LLM_API_KEY"] not in html
    app.config["PROD_MODE"] = True
    assert client.get("/architecture").status_code == 404


def test_architecture_page_names_only_existing_settings_and_explains_every_option():
    """Fails when the pipeline changes and the page does not: update templates/architecture.html and
    just_os/architecture.py with it."""
    import re
    from just_os import architecture, qualle
    from just_os.decisions import ROUTERS
    from just_os.hybrid import SEARCH_MODES

    assert set(architecture.ROUTER_TEXT) == set(ROUTERS), "explain every ROUTER option on /architecture"
    assert set(architecture.SEARCH_MODE_TEXT) == set(SEARCH_MODES), "explain every SEARCH_MODE on /architecture"
    template = (architecture.ROOT / "just_os" / "templates" / "architecture.html").read_text(encoding="utf-8")
    names = set(re.findall(r"s\.value\('([A-Z0-9_]+)'\)", template))
    names |= {n for block in re.findall(r"cfg\(\[([^\]]*)\]\)", template) for n in re.findall(r'"([A-Z0-9_]+)"', block)}
    named_in_text = set(re.findall(r"<code>([A-Z][A-Z0-9_]{3,})</code>", template))
    defaults = architecture.code_defaults()
    assert len(names) > 50 and names <= set(defaults), names - set(defaults)
    unknown = {n for n in named_in_text if n not in defaults and not hasattr(qualle, n)}
    assert not unknown, f"/architecture names {unknown}: neither a setting nor a qualle constant"
    try:
        architecture.Settings({}).value("NO_SUCH_SETTING")
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown setting must break the page")


# --- readiness, Redis outages, request checks (prod reliability)


class FakeChatRag:
    def __init__(self):
        self.chat_ids = []

    def get_response(self, query, chat_id, model=None, **options):
        self.chat_ids.append(chat_id)
        yield {"status": "complete", "message": "<p>ok</p>", "outcome": "answered"}


def test_ready_needs_the_loaded_service_and_redis(app, monkeypatch):
    from just_os import rag_service

    monkeypatch.setattr(rag_service, "_rag_service_instance", None)
    monkeypatch.setattr(rag_service, "_rag_init_error", None)
    client = app.app.test_client()
    assert client.get("/ready").status_code == 200 and client.get("/ready").get_json()["status"] == "ready"

    app._rag_service = None  # still loading
    response = client.get("/ready")
    assert response.status_code == 503 and response.get_json() == {"status": "not ready", "rag": "loading", "redis": "ok"}
    app._rag_init_error = "OSError: no index"  # the load failed
    assert client.get("/ready").get_json()["rag"] == "failed"
    assert "no index" not in client.get("/ready").get_data(as_text=True)  # the reason stays in the log
    app._rag_init_error = None
    monkeypatch.setattr(rag_service, "_rag_init_error", "OSError: no index")  # failed in the gunicorn preload
    assert client.get("/ready").get_json()["rag"] == "failed"

    app._rag_service = FakeRag()

    def down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(app.chat_manager.redis, "ping", down)
    response = client.get("/ready")
    assert response.status_code == 503 and response.get_json()["redis"] == "unreachable"
    assert client.get("/up").status_code == 200  # liveness does not depend on Redis


def test_ready_never_starts_or_waits_for_a_load(app, monkeypatch):
    from just_os import rag_service

    monkeypatch.setattr(rag_service, "_rag_service_instance", None)
    monkeypatch.setattr(rag_service, "_rag_init_error", None)

    def no_load(*a, **k):
        raise AssertionError("/ready must not load the service")

    monkeypatch.setattr(rag_service, "create_rag_service", no_load)
    app._rag_service = None
    assert rag_service._rag_lock.acquire(blocking=False)  # a load in progress holds the lock
    try:
        assert app.app.test_client().get("/ready").status_code == 503
    finally:
        rag_service._rag_lock.release()
    rag_service._rag_service_instance = object()  # loaded by the gunicorn preload
    assert app.app.test_client().get("/ready").status_code == 200


def memory_limited_app(monkeypatch, tmp_path, **limiter_options):
    """A FlaskApp whose rate limiter is on and counts in memory instead of Redis."""
    from just_os import app as app_module

    real = app_module.Limiter
    monkeypatch.setattr(app_module, "Limiter", lambda **kw: real(**{**kw, "storage_uri": "memory://", **limiter_options}))
    flask_app = FlaskApp()
    flask_app.config.update(ARENA_ENABLED=True, ARENA_MODELS="m1,m2", ROUTER="", RATE_LIMIT="1000/minute",
                            ARENA_RATINGS_FILE=str(tmp_path / "ratings.jsonl"), ARENA_ROUNDS_FILE=str(tmp_path / "rounds.jsonl"),
                            CHAT_LOG_FILE=str(tmp_path / "chats.jsonl"))
    flask_app.chat_manager.redis = fakeredis.FakeRedis()
    flask_app._rag_service = FakeChatRag()
    return flask_app


def test_a_redis_outage_does_not_fail_rate_limited_requests(monkeypatch, tmp_path):
    def broken_storage(flask_app):
        def boom(*a, **k):
            raise ConnectionError("Redis unreachable")

        storage = flask_app.rate_limit_manager.limiter.storage
        for name in ("incr", "get", "get_expiry", "check"):
            if hasattr(storage, name):
                monkeypatch.setattr(storage, name, boom)

    body = {"message": "What is open data?", "chat_id": "c1"}
    flask_app = memory_limited_app(monkeypatch, tmp_path)
    assert flask_app.rate_limit_manager.limiter._swallow_errors is True
    broken_storage(flask_app)
    response = flask_app.app.test_client().post("/chat", json=body)
    assert response.status_code == 200 and json.loads(response.data.decode().splitlines()[-1])["status"] == "complete"

    # the same outage without swallow_errors: every /chat request failed with HTTP 500
    flask_app = memory_limited_app(monkeypatch, tmp_path, swallow_errors=False)
    broken_storage(flask_app)
    assert flask_app.app.test_client().post("/chat", json=body).status_code == 500


def test_chat_id_must_be_short_printable_text(app):
    app._rag_service = rag = FakeChatRag()
    client = app.app.test_client()
    post = lambda chat_id: client.post("/chat", json={"message": "What is open data?", "chat_id": chat_id})  # noqa: E731
    for bad in ("x" * 129, "", "has space", "tab\there", {"a": 1}, ["c"], None, True, "ü-not-ascii"):
        response = post(bad)
        assert response.status_code == 400 and "chat_id" in response.get_json()["message"], bad
    assert rag.chat_ids == []
    for good in ("3f2a6c1e-8b4d-4c3a-9f1e-2d7b5a9c0e11", "x" * 128, "widget:abc_1.2", 1732800000000):
        assert post(good).status_code == 200, good
    assert rag.chat_ids[-1] == "1732800000000"  # a number from a widget becomes the same key every time
    assert client.post("/chat", json={"message": ["What is open data?"], "chat_id": "c"}).status_code == 400


def test_an_unknown_label_leaves_the_battle_to_rate_again(app):
    client = app.app.test_client()
    battle = ask(client)[1]["battle_id"]
    bad = client.post("/arena/rate", json={"battle_id": battle, "ratings": {"Z": scores()}})
    assert bad.status_code == 400 and bad.get_json()["message"] == "Unknown answer label."
    assert app.chat_manager.redis.get(f"arena:battle:{battle}") is not None  # not used up by the bad request
    good = client.post("/arena/rate", json={"battle_id": battle, "ratings": {"A": scores()}})
    assert good.status_code == 200 and set(good.get_json()["models"].values()) == {"m1", "m2"}
    assert client.post("/arena/rate", json={"battle_id": battle, "ratings": {"A": scores()}}).status_code == 404  # once


def test_arena_rating_is_rate_limited(monkeypatch, tmp_path):
    flask_app = memory_limited_app(monkeypatch, tmp_path)
    flask_app.config["RATE_LIMIT"] = "2/minute"
    client = flask_app.app.test_client()
    codes = [client.post("/arena/rate", json={"battle_id": "x", "ratings": {"A": scores()}}).status_code for _ in range(3)]
    assert codes == [404, 404, 429]


def test_two_review_saves_in_the_same_second_both_save(app, tmp_path, monkeypatch):
    from datetime import datetime as real_datetime, timezone
    from just_os import app as app_module

    class SameMoment(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 28, 12, 0, 0, 123456, tzinfo=timezone.utc)

    monkeypatch.setattr(app_module, "datetime", SameMoment)
    items = [{"key": "k1", "answer_id": "a#q1", "id": "q1", "question": "Q?", "answer": "A [0].", "sources": [], "rubric": []}]
    (tmp_path / "items.json").write_text(json.dumps(items))
    app.config.update(REVIEW_ITEMS_FILE=str(tmp_path / "items.json"), SCORES_DIR=str(tmp_path / "scores"))
    client = app.app.test_client()
    body = {"reviewer": "Ada", "scores": {"k1": {"decision": "right", "correctness": "4"}}}
    first, second = client.post("/review/save", json=body), client.post("/review/save", json=body)
    assert first.status_code == second.status_code == 200
    assert first.get_json()["file"] != second.get_json()["file"]
    assert len(list((tmp_path / "scores").iterdir())) == 2
