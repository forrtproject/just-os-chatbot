"""Decision-model router and FORRT page router (#15, #34): offline, no index or network."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from just_os import decisions, forrt_checks, qualle
from just_os.forrt_pages import ForrtPages, extract, trim
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
    assert [(s["n"], s["title"], s["url"]) for s in result["sources"]] == [(1, "Teams", "https://forrt.org/about/teams/")]
    assert "Team Credit" in result["sources"][0]["excerpt"]  # the page text the model read (eval/run.py saves it)
    assert "forrt.org/about/teams" not in result["text"]  # the page goes to the Sources box, not the text
    assert "Team Credit" in client.calls[0]["messages"][1]["content"]  # the page text reached the model


def test_a_typical_long_page_reaches_the_model_whole(tmp_path):
    # /about/us/ is ~8,400 characters; with a 6,000 limit the trim kept the blocks sharing words with
    # "When was FORRT founded?" and dropped the History section, which says "initiated", not "founded"
    pages, client = make_pages(tmp_path, ["FORRT was initiated at the 2018 SIPS meeting [1]."], [0.95, 0.1])
    mission = "".join(f"<p>FORRT supports educators who teach open and reproducible science, point {i}. "
                      + "It builds pedagogical infrastructure, community and teaching resources. " * 5 + "</p>"
                      for i in range(20))
    history = ("<h2>History</h2><p>This project was initiated at the 2018 meeting of the Society for the Improvement of "
               "Psychological Science. " + "The initial framework was developed by a working group of researchers. " * 12 + "</p>")
    pages.http.pages["https://forrt.org/about/teams/"] = f"<html><body><main>{mission}{history}</main></body></html>"
    pages.answer("When was FORRT founded?")
    assert "initiated at the 2018 meeting" in client.calls[0]["messages"][1]["content"]


def test_a_huge_list_keeps_the_entry_the_question_asks_about():
    # /contributors/ is ~212,000 characters in one block (a list without blank lines): the trim kept
    # only the intro, so "What has Rohan contributed to FORRT?" got "not found"
    entries = "\n".join(f"- **[Person {i}](https://orcid.org/{i})** contributed to\n  - Project {i} with *Writing*"
                        for i in range(3000))
    target = "- **[Rohan V. Tondlekar](https://orcid.org/x)** contributed to\n  - FLoRA Extractor with *Software*"
    markdown = "FORRT is driven by a large community of contributors.\n\n" + entries.replace(
        "- **[Person 2500]", target + "\n- **[Person 2500]")
    kept = trim(markdown, "What has Rohan contributed to FORRT?", 12000)
    assert len(kept) < 13000 and "Rohan V. Tondlekar" in kept and "FLoRA Extractor" in kept


def test_placeholder_citations_are_removed():
    # Llama 3.1 8B wrote "[no specific page number]" after each bullet instead of [1]
    text = forrt_checks.clean_citations("FLoRA Extractor with *Software* [no specific page number]\n* Zotero plugin [1]", 1)
    assert "no specific page number" not in text and "Zotero plugin [1]" in text


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
    q.document_retriever.retrieve_and_rerank = lambda query, *timings: (_ for _ in ()).throw(AssertionError("no paper search"))
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    assert final["status"] == "complete" and final["outcome"] == "forrt"
    assert final["metadata"]["references"][0]["url"] == "https://forrt.org/about/teams/"  # in the Sources box
    assert final["metadata"]["sources"] == "[1] Teams. https://forrt.org/about/teams/"


def test_both_route_adds_forrt_links_to_the_paper_answer(tmp_path):
    from test_qualle import node
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.config = {**CONFIG, "DECISION_ROUTER": True}
    q.decisions = SimpleNamespace(route=lambda model, query: ("both", 0.8, {}))
    q.forrt_pages = pages
    final = list(q.get_response("How can I learn more about credit with FORRT?", "chat"))[-1]
    refs = final["metadata"]["references"]
    assert final["outcome"] == "both" and "Paper" in final["metadata"]["sources"]
    assert refs[-1]["url"] == "https://forrt.org/about/teams/" and refs[-1]["number"] == len(refs)  # after the papers
    assert "https://forrt.org/about/teams/" in final["metadata"]["sources"]


def test_a_moved_page_is_read_at_its_new_address(tmp_path):
    pages, _ = make_pages(tmp_path, [], [])
    stub = "<html><head><meta http-equiv=refresh content=\"0; url=https://forrt.org/glossary/english/\"></head></html>"
    pages.http = FakeWeb({"https://forrt.org/glossary/": stub,
                          "https://forrt.org/glossary/english/": "<html><body><main><p>Phase 2 is open.</p></main></body></html>"})
    assert pages.fetch("https://forrt.org/glossary/")["markdown"] == "Phase 2 is open."
    pages.records = [{"url": "https://forrt.org/glossary/", "title": "Glossary"},
                     {"url": "https://forrt.org/glossary/english/", "title": "Glossary"}]
    pages.select = lambda question, candidates: pages.records
    pages.retrieve = lambda question: []
    pages.client_manager.create_chat_completion = lambda **kw: completion(content="Phase 2 is open [1].")
    assert [s["url"] for s in pages.answer("How can I contribute to the glossary?")["sources"]] == ["https://forrt.org/glossary/"]


def test_small_talk_gets_the_introduction_without_a_topic_check():
    for text in ["Hello", "hi!", "Who are you?", "Hello, what can you do?", "thanks", "Wer bist du?"]:
        assert qualle.small_talk(text), text
    for text in ["What is open science?", "Hi, what is preregistration?", "Can you help me with my preregistration?",
                 "Who are the FORRT team leads?", "", "?!"]:
        assert not qualle.small_talk(text), text
    q = make_qualle(True, [], [], "unused")
    q.route = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no topic check"))
    final = list(q.get_response("Hello", "chat"))[-1]
    assert final["outcome"] == "small_talk" and "JUST-OS" in final["message"]


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


def test_short_questions_do_not_force_a_guessed_language():
    # lingua read "what is forrt" as Hungarian (confidence 0.07) and the whole answer came out in Hungarian
    assert forrt_checks.question_language("what is forrt") is None
    assert "language of the question" in forrt_checks.language_name(None)
    assert forrt_checks.question_language("Wie kann ich bei FORRT mitmachen?") == "de"
    assert forrt_checks.question_language("我想看之前那个关于元科学AI的在线会议回放") == "zh"


def test_what_is_forrt_is_not_answered_in_hungarian(tmp_path):
    # the FORRT route told the model "write the whole answer in Hungarian" for "what is forrt"
    pages, client = make_pages(tmp_path, ["FORRT is a framework for open and reproducible research training [1]."], [0.95, 0.1])
    pages.answer("what is forrt")
    prompt = client.calls[0]["messages"][0]["content"] + client.calls[0]["messages"][1]["content"]
    assert "Hungarian" not in prompt and "language of the question" in prompt


def test_bare_urls_become_links():
    text = "Join here: https://join.slack.com/t/forrt/x. Or see [Get involved](https://forrt.org/about/get-involved/) or <https://forrt.org/>."
    out = forrt_checks.autolink(text)
    assert "<https://join.slack.com/t/forrt/x>." in out  # the full stop stays outside the link
    assert "[Get involved](https://forrt.org/about/get-involved/)" in out and "<https://forrt.org/>" in out
    assert out.count("<https://forrt.org/>") == 1  # an existing autolink is not wrapped twice
    html = qualle.markdown.markdown(out)
    assert 'href="https://join.slack.com/t/forrt/x"' in html


def test_book_chapter_urls_keep_their_html_ending():
    """forrt.org/replication-handbook/planning.html/ is a 404: the index must keep the file URL."""
    from scripts.build_forrt_pages import norm_url

    assert norm_url("https://forrt.org/replication-handbook/planning.html") == "https://forrt.org/replication-handbook/planning.html"
    assert norm_url("https://forrt.org/replication-handbook/index.html") == "https://forrt.org/replication-handbook/"
    assert norm_url("/replication-hub#x") == "https://forrt.org/replication-hub/"


# --- FORRT_IN_PAPERS: forrt.org pages next to the papers


def test_extra_sources_need_a_close_page_and_a_clear_yes(tmp_path):
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    found = pages.extra_sources("Which teams can I join?", min_score=0.5)
    assert [p["url"] for p in found] == ["https://forrt.org/about/teams/"] and "Team Credit" in found[0]["text"]
    asked = []
    pages.decisions = SimpleNamespace(decide=lambda *a: asked.append(a) or ({}, {}))
    assert pages.extra_sources("Which teams can I join?", min_score=5.0) == [] and not asked  # no close page: no call
    for answers in ({"page_1": {"noul": 0.5}, "page_2": {"noul": 0.3}}, None):  # unsure or failed: nothing added
        pages.decisions = SimpleNamespace(decide=lambda *a, answers=answers: (answers, {}))
        assert pages.extra_sources("Which teams can I join?", min_score=0.0) == []


def forrt_in_papers_qualle(tmp_path, route, answer="Join a team [1] and read the paper [0]."):
    from test_qualle import node
    pages, _ = make_pages(tmp_path, [], [0.95, 0.1])
    q = make_qualle(True, [node("Paper")], [node("Paper")], answer)
    q.config = {**CONFIG, "DECISION_ROUTER": True, "FORRT_IN_PAPERS": True, "FORRT_IN_PAPERS_MIN_SCORE": 0.5}
    q.decisions = SimpleNamespace(route=lambda model, query: (route, 0.9, {}))
    q.forrt_pages = pages
    return q


def test_papers_route_reads_a_matching_forrt_page_next_to_the_papers(tmp_path):
    q = forrt_in_papers_qualle(tmp_path, "open_science")
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    prompt = q.response_generator.client_manager.calls[0]["messages"][-1]["content"]
    assert "[0] Title: Paper" in prompt and "[1] Title: Teams" in prompt and "Team Credit" in prompt
    urls = [r["url"] for r in final["metadata"]["references"]]
    assert final["outcome"] == "answered" and "https://forrt.org/about/teams/" in urls and "https://x" in urls
    q.config = {**q.config, "FORRT_IN_PAPERS": False}  # off: the papers alone
    q.forrt_pages.extra_sources = lambda *a: (_ for _ in ()).throw(AssertionError("not asked"))
    list(q.get_response("Which teams can I join?", "chat2"))


def test_both_route_reads_the_forrt_page_instead_of_only_linking_it(tmp_path):
    q = forrt_in_papers_qualle(tmp_path, "both")
    final = list(q.get_response("Which teams can I join?", "chat"))[-1]
    assert "Team Credit" in q.response_generator.client_manager.calls[0]["messages"][-1]["content"]  # the page was read
    urls = [r["url"] for r in final["metadata"]["references"]]
    assert urls.count("https://forrt.org/about/teams/") == 1  # and cited once, not linked again
