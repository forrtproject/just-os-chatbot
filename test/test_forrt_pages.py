"""Decision-model router and FORRT page router (#15, #34): offline, no index or network."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from just_os import decisions, forrt_checks, qualle
from just_os.forrt_pages import ForrtPages, extract
from test_qualle import CONFIG, completion, make_qualle


# --- extraction


def test_extract_drops_menus_keeps_headings_links_and_meta():
    html = """<html><head><title>Teams | FORRT</title><meta name="description" content="unused"></head><body>
      <nav><a href="/about/">About FORRT</a> Awards Calendar</nav>
      <section><h3>Team Credit</h3><p>Recognise contributions. <a href="https://forrt.slack.com/x">Join Us</a></p></section>
      <footer>footer text</footer></body></html>"""
    page = extract(html, "https://forrt.org/about/teams/")
    assert page["title"] == "Teams"
    assert "### Team Credit" in page["markdown"]
    assert "[Join Us](https://forrt.slack.com/x)" in page["markdown"]
    assert "About FORRT" not in page["markdown"] and "footer text" not in page["markdown"]
    app = extract('<html><head><title>FReD Explorer</title><meta name="description" content="Browse the FORRT '
                  'Replication Database."></head><body><div id="app"></div></body></html>', "https://forrt.org/explorer/")
    assert "Browse the FORRT Replication Database." in app["markdown"]  # JavaScript app: meta description kept


# --- checks in code


def test_links_not_in_the_pages_are_removed_and_citations_cleaned():
    pages = [{"n": 1, "url": "https://forrt.org/about/teams/",
              "excerpt": "Join [Slack](https://join.slack.com/t/forrt/abc). Mail ombuds@forrt.org"}]
    answer = ("Join [Slack](https://join.slack.com/t/forrt/abc) or https://forrt.org/slack. "
              "Mail [ombuds](mailto:ombuds@forrt.org) or [x](mailto:fake@forrt.org) 【1】 [7]")
    text, removed = forrt_checks.strip_unsupported_links(answer, pages)
    text = forrt_checks.clean_citations(text, 1)
    assert removed == ["mailto:fake@forrt.org", "https://forrt.org/slack"]
    assert "(https://join.slack.com/t/forrt/abc)" in text and "mailto:ombuds@forrt.org" in text
    assert "[1]" in text and "[7]" not in text and "【" not in text


def test_past_events_called_upcoming_are_flagged():
    flagged = forrt_checks.past_events_called_upcoming(
        "The upcoming conference takes place 28–30 September 2026. Another is on 3 March 2027 and upcoming.",
        date(2026, 11, 12))
    assert len(flagged) == 1 and "September" in flagged[0]


# --- decision router


def test_decision_route(monkeypatch):
    reply = {"answers": {"route": {"choice": "forrt", "probabilities": {"forrt": 0.9, "open_science": 0.1}}},
             "usage": {"cost": 0.0001}}
    monkeypatch.setattr(decisions.httpx, "post", lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None, json=lambda: reply))
    route, p, info = decisions.DecisionClient({"LLM_API_KEY": "k"}).route("cloudflare/clef", "Which teams can I join?")
    assert (route, p, info["cost"]) == ("forrt", 0.9, 0.0001)


def test_unsure_or_failed_decision_falls_back_to_the_llm_classifier():
    q = make_qualle(True, [], [], "unused")
    q.config = {**CONFIG, "DECISION_ROUTER": True, "DECISION_ROUTER_MIN_CONFIDENCE": 0.5}
    q.decisions = SimpleNamespace(route=lambda model, query: ("forrt", 0.3, {}))
    assert q.route("question") == "open_science"  # 0.3 < 0.5: classify_query (True) decides
    q.decisions = SimpleNamespace(route=lambda model, query: ("neither", 0.95, {}))
    assert q.route("weather?") == "off_topic"
    q.decisions = SimpleNamespace(route=lambda model, query: (None, 0.0, {"error": "HTTP 500"}))
    assert q.route("question") == "open_science"


# --- FORRT page router


def make_pages(tmp_path, answers, probs):
    records = [
        {"url": "https://forrt.org/about/teams/", "title": "Teams", "section": "about", "summary": "All FORRT teams",
         "use_when": "join a team", "example_questions": ["Which teams can I join?"]},
        {"url": "https://forrt.org/post/2026-10-presentations/", "title": "FORRT at BTSCON2026", "section": "post",
         "date": (date.today() - timedelta(days=36)).isoformat(), "summary": "talks", "use_when": "", "example_questions": []},
    ]
    (tmp_path / "index.json").write_text(json.dumps(records))
    np.save(tmp_path / "vectors.npy", np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    config = {**CONFIG, "FORRT_PAGES_DIR": str(tmp_path), "FORRT_TOP_K": 2}
    client = SimpleNamespace(calls=[], create_chat_completion=None)
    queue = list(answers)

    def chat(**kwargs):
        client.calls.append(kwargs)
        return completion(content=queue.pop(0))

    client.create_chat_completion = chat
    decide = lambda model, state, questions: ({f"page_{i + 1}": {"noul": p} for i, p in enumerate(probs)}, {})  # noqa: E731
    embed = SimpleNamespace(get_query_embedding=lambda q: [1.0, 0.0])
    pages = ForrtPages(config, embed, client, SimpleNamespace(decide=decide))
    pages.http = FakeWeb(LIVE_PAGES)  # pages are always read live: a fake forrt.org
    return pages, client


LIVE_PAGES = {
    "https://forrt.org/about/teams/": "<html><body><main><h3>Team Credit</h3><p>Recognise contributions. "
                                      "<a href='https://forrt.slack.com/x'>Join Us</a></p></main></body></html>",
    "https://forrt.org/post/2026-10-presentations/": "<html><body><main><p>FORRT presented at BTSCON 2026 "
                                                     "(1 October 2026).</p></main></body></html>",
}


class FakeWeb:
    def __init__(self, pages):
        self.pages, self.calls = dict(pages), []

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise ConnectionError("forrt.org unreachable")
        return SimpleNamespace(raise_for_status=lambda: None, text=self.pages[url])


def test_forrt_answer_from_the_picked_page(tmp_path):
    pages, client = make_pages(tmp_path, ["Join Team Credit on [Slack](https://forrt.slack.com/x) [1] or forrt.org/slack."],
                               [0.95, 0.1])
    result = pages.answer("Which teams can I join?")
    assert result["found"] and result["trace"]["selected"] == ["https://forrt.org/about/teams/"]
    assert "https://forrt.slack.com/x" in result["text"]
    assert result["text"].rstrip().endswith("1. [Teams](https://forrt.org/about/teams/)")  # source list
    assert "Team Credit" in client.calls[0]["messages"][1]["content"]  # the page text reached the model


def test_nothing_relevant_gives_the_no_sources_message(tmp_path):
    pages, client = make_pages(tmp_path, [], [0.05, 0.02])
    result = pages.answer("Who won the world cup?")
    assert not result["found"] and client.calls == []


def test_wrong_language_and_stale_dates_get_one_rewrite(tmp_path):
    english = "FORRT presented its work at the Big Team Science Conference, see the Zenodo community for all the talks [1]."
    dutch = "FORRT presenteerde zijn werk op de Big Team Science Conference; alle presentaties staan op Zenodo [1]."
    pages, client = make_pages(tmp_path, [english, dutch], [0.95, 0.9])
    result = pages.answer("Waar kan ik de presentaties van FORRT op de Big Team Science Conference vinden?")
    assert len(client.calls) == 2 and "Dutch" in client.calls[1]["messages"][1]["content"]
    assert result["text"].startswith("FORRT presenteerde")


def test_forrt_route_in_get_response_does_not_call_the_paper_path(tmp_path):
    pages, _ = make_pages(tmp_path, ["See the teams page [1]."], [0.95, 0.1])
    q = make_qualle(True, [], [], "unused")
    q.config = {**CONFIG, "DECISION_ROUTER": True}
    q.decisions = SimpleNamespace(route=lambda model, query: ("forrt", 0.9, {}))
    q.forrt_pages = pages
    q.document_retriever.retrieve_and_rerank = lambda query: (_ for _ in ()).throw(AssertionError("no paper search"))
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    assert final["status"] == "complete" and final["outcome"] == "forrt"
    assert 'href="https://forrt.org/about/teams/"' in final["message"]


def test_both_route_adds_forrt_links_to_the_paper_answer(tmp_path):
    from test_qualle import node
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.config = {**CONFIG, "DECISION_ROUTER": True}
    q.decisions = SimpleNamespace(route=lambda model, query: ("both", 0.8, {}))
    q.forrt_pages = pages
    final = list(q.get_response("How can I learn more about credit with FORRT?", "chat"))[-1]
    assert final["outcome"] == "both" and "On forrt.org" in final["message"] and "Paper" in final["metadata"]["sources"]


def test_pages_are_read_live_cached_and_skipped_when_unreachable(tmp_path):
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    url = "https://forrt.org/about/teams/"
    assert pages.fetch(url)["status"] == "live" and pages.fetch(url)["status"] == "cache"
    assert pages.http.calls == [url]  # the second read came from the in-memory cache
    pages.config = {**pages.config, "FORRT_CACHE_TTL": 0}
    pages.http.pages.clear()  # forrt.org goes down
    got = pages.fetch(url)
    assert got["status"] == "cache (expired)" and "Team Credit" in got["markdown"]
    assert pages.fetch("https://forrt.org/never-fetched/") == {"markdown": "", "status": "failed"}
    assert pages.fetch("https://example.org/page/")["status"] == "failed"  # other domains are never fetched


def test_qualle_class_defaults_keep_the_old_paths():
    assert qualle.Qualle.forrt_pages is None and qualle.Qualle.decisions is None
