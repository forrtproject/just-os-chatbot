"""XSS defence in depth: the server-side sanitizer, citation links, link stripping, request validation,
PROD_MODE router lockdown, ALLOWED_ORIGINS parsing and self-hosted frontend assets."""

import glob
import json
import os
import re

import pytest
from bs4 import BeautifulSoup

from config.settings import env_value
from just_os import forrt_checks, qualle
from just_os.sanitize import render_markdown, safe_href, sanitize_html, valid_reference_data

from test_app import app, read_jsonl  # noqa: F401  (fixture)
from test_references import chunk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tags(html):
    return [t.name for t in BeautifulSoup(html, "html.parser").find_all(True)]


# ---------- sanitize_html ----------

@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>",
    "<SCRIPT src=//evil.example/x.js></SCRIPT>",
    "<iframe src='https://evil.example'>inner</iframe>",
    "<style>body{display:none}</style>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)><circle/></svg>",
    "<object data='x'></object><embed src='x'>",
    "<!-- <script>alert(1)</script> -->",
])
def test_dangerous_tags_and_their_content_are_dropped(payload):
    out = sanitize_html(f"<p>before {payload} after</p>")
    assert out.startswith("<p>before ") and out.endswith(" after</p>")
    assert not set(tags(out)) - {"p"}
    for word in ("alert", "script", "iframe", "onerror", "onload", "display:none", "inner"):
        assert word not in out.lower()


@pytest.mark.parametrize("href", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\tscript:alert(1)", " javascript:alert(1)",
    "&#106;avascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "//evil.example",
    "/relative", "#",
])
def test_unsafe_or_relative_hrefs_are_removed(href):
    out = sanitize_html(f'<a href="{href}" onclick="alert(1)" style="x">label</a>')
    assert out == "<a>label</a>"


@pytest.mark.parametrize("href", ["https://forrt.org/a?b=1&c=2", "http://example.org", "mailto:x@example.org"])
def test_safe_hrefs_are_kept(href):
    a = BeautifulSoup(sanitize_html(f'<a href="{href}">x</a>'), "html.parser").a
    assert a["href"] == href


def test_safe_href():
    assert safe_href("https://a.org") == "https://a.org"
    assert safe_href("#") is None and safe_href("#", allow_fragment=True) == "#"
    assert safe_href("javascript:x") is None and safe_href(None) is None


def test_markdown_tags_survive_and_events_do_not():
    html = ("<h2 onclick=x>T</h2><p><strong>b</strong> <em>i</em> <code>c</code> <sup>1</sup> <sub>2</sub></p>"
            "<ul><li>a</li></ul><ol start='3'><li>b</li></ol><blockquote>q</blockquote><pre>p</pre><hr>"
            "<table><thead><tr><th colspan='2'>h</th></tr></thead><tbody><tr><td>d</td></tr></tbody></table>"
            "<span class='x' onmouseover='y'>s</span><br>")
    out = sanitize_html(html)
    assert set(tags(out)) == {"h2", "p", "strong", "em", "code", "sup", "sub", "ul", "li", "ol", "blockquote",
                              "pre", "hr", "table", "thead", "tr", "th", "tbody", "td", "span", "br"}
    assert "onclick" not in out and "onmouseover" not in out and 'class="x"' not in out
    assert '<ol start="3">' in out and '<th colspan="2">' in out


def test_escaped_text_stays_text_and_output_is_balanced():
    assert sanitize_html("<p>&lt;img onerror=alert(1)&gt;</p>") == "<p>&lt;img onerror=alert(1)&gt;</p>"
    assert sanitize_html("<p><strong>open") == "<p><strong>open</strong></p>"
    assert sanitize_html("<p>a</strong></p>") == "<p>a</p>"
    # not an HTML element: the text was meant literally ("x<y and z>w")
    assert sanitize_html("<p>x<y and z>w</p>") == "<p>x&lt;y and z&gt;w</p>"


def test_reference_links_keep_their_attributes_only_when_allowed():
    link = '<a href="#" class="reference-link" data-reference="{&quot;title&quot;:&quot;T&quot;}">[1]</a>'
    assert sanitize_html(link) == "<a>[1]</a>"
    kept = BeautifulSoup(sanitize_html(link, allow_references=True), "html.parser").a
    assert kept["href"] == "#" and kept["class"] == ["reference-link"]
    assert json.loads(kept["data-reference"]) == {"title": "T"}
    # Other classes or a javascript: href stay stripped even then
    assert sanitize_html('<a href="#" class="evil">x</a>', allow_references=True) == "<a>x</a>"
    other = sanitize_html('<a href="javascript:x" class="reference-link">x</a>', allow_references=True)
    assert "javascript" not in other


def ref_link(data_reference):
    return f'<a href="#" class="reference-link" data-reference="{data_reference}">[1]</a>'


@pytest.mark.parametrize("data_reference", [
    "", "not json", "{&quot;title&quot;:", "[1, 2]", "&quot;a string&quot;", "123", "null", "{}",
    "{&quot;title&quot;:{&quot;a&quot;:1}}",  # nested object
    "{&quot;title&quot;:[&quot;a&quot;]}",  # list value
    "{&quot;title&quot;:&quot;T&quot;,&quot;onclick&quot;:&quot;x&quot;}",  # unknown field
])
def test_reference_links_with_invalid_data_lose_class_href_and_data(data_reference):
    assert sanitize_html(ref_link(data_reference), allow_references=True) == "<a>[1]</a>"
    assert not valid_reference_data(BeautifulSoup(ref_link(data_reference), "html.parser").a.get("data-reference"))


def test_reference_link_without_data_reference_is_not_kept():
    assert sanitize_html('<a href="#" class="reference-link">[1]</a>', allow_references=True) == "<a>[1]</a>"


def test_real_reference_data_passes_validation():
    """What ReferenceProcessor.reference_data() writes (paper and forrt.org page) must survive the sanitizer."""
    processor = qualle.ReferenceProcessor()
    page = chunk("FORRT glossary", "", text="")
    page.metadata.update(creators="", link_to_resource="https://forrt.org/glossary/")
    for node, unverified in ((chunk("Paper", "10.1/p", text="a < b"), False), (page, True)):
        data = processor.reference_data(node, unverified)
        assert valid_reference_data(json.dumps(data))
        (link,) = reference_links(answer_html("Claim [0].", [node]))
        assert link["href"] == "#" and json.loads(link["data-reference"])["title"] == data["title"]


def test_render_markdown_sanitizes_raw_html_and_links():
    out = render_markdown("Hi <script>alert(1)</script> [click](javascript:alert(1)) <b onclick=x>b</b>")
    assert "script" not in out and "javascript" not in out and "onclick" not in out
    assert "<a>click</a>" in out and "<b>b</b>" in out
    assert "<table>" in render_markdown("| a |\n|---|\n| 1 |", extensions=["tables"])


def test_every_answer_in_qualle_goes_through_the_sanitizer():
    source = open(os.path.join(ROOT, "just_os", "qualle.py"), encoding="utf-8").read()
    assert "markdown.markdown(" not in source and "import markdown" not in source
    assert source.count("render_markdown(") >= 17


# ---------- citation links ----------

def answer_html(text, nodes=None):
    html, _ = qualle.ReferenceProcessor().process_markdown_with_references(text, nodes or [chunk("T", "10.1/t")])
    return html


def reference_links(html):
    return BeautifulSoup(html, "html.parser").find_all("a", class_="reference-link")


@pytest.mark.parametrize("text, visible", [
    ("A<B [0]", "A<B [1]"),
    ("x<y [0]", "x<y [1]"),
    ("x<y [0] and z>w", "x<y [1] and z>w"),
    ("&lt;img onerror=alert(1)&gt; [0]", "<img onerror=alert(1)> [1]"),
    ("a & b [0] c", "a & b [1] c"),
])
def test_citations_never_corrupt_text_or_create_tags(text, visible):
    html = answer_html(text)
    soup = BeautifulSoup(html, "html.parser")
    assert soup.get_text() == visible
    assert set(tags(html)) == {"p", "a"}
    (link,) = reference_links(html)
    assert link["href"] == "#" and link.text == "[1]"
    assert json.loads(link["data-reference"])["title"] == "T"


def test_citation_html_payloads_are_neutralised():
    html = answer_html("<img src=x onerror=alert(1)> <script>alert(2)</script> [click](javascript:alert(3)) [0]")
    assert "onerror" not in html and "script" not in html and "javascript" not in html
    assert len(reference_links(html)) == 1


def test_model_cannot_forge_reference_links():
    forged = '<a class="reference-link" href="#" data-reference=\'{"title":"Fake","url":"javascript:x"}\'>[9]</a>'
    html = answer_html(forged + " real [0]")
    links = reference_links(html)
    assert len(links) == 1 and json.loads(links[0]["data-reference"])["title"] == "T"
    assert "Fake" not in html


def test_tooltip_data_with_quotes_and_tags_round_trips():
    node = chunk('He said "<script>alert(1)</script>"', "10.1/q", text="a < b & 'c'")
    (link,) = reference_links(answer_html("Claim [0].", [node]))
    data = json.loads(link["data-reference"])
    assert data["title"] == 'He said "<script>alert(1)</script>"' and data["text"] == "a < b & 'c'"


def test_adjacent_citations_of_one_paper_still_collapse():
    nodes = [chunk("Manual", "10.1/m", "first"), chunk("Manual", "10.1/m", "second")]
    html = answer_html("A [0][1]. B<C [1].", nodes)
    assert [a.text for a in reference_links(html)] == ["[1]", "[1]"]
    assert BeautifulSoup(html, "html.parser").get_text() == "A [1]. B<C [1]."


def test_reference_fallback_is_sanitized(monkeypatch):
    def boom(_):
        raise ValueError("broken metadata")

    monkeypatch.setattr(qualle, "paper_key", boom)
    html, used = qualle.ReferenceProcessor().process_markdown_with_references(
        "<script>alert(1)</script> [x](javascript:alert(1)) text [0]", [chunk("T", "10.1/t")])
    assert used == [] and "script" not in html and "javascript" not in html and "text [0]" in html


# ---------- FORRT page answers: links ----------

PAGES = [{"url": "https://forrt.org/glossary/", "excerpt": ""}]


@pytest.mark.parametrize("answer, expected", [
    ("[click](javascript:alert(1))", "click"),
    ("See [click](javascript:alert(1)) now", "See click now"),
    ("[https://forrt.org](javascript:alert(1))", ""),
    ("[www.forrt.org](data:text/html,x)", ""),
    ("[home](/relative/page)", "home"),
    ("[x](vbscript:msgbox)", "x"),
])
def test_unsafe_markdown_links_become_their_label(answer, expected):
    text, removed = forrt_checks.strip_unsupported_links(answer, PAGES)
    assert text == expected and removed == []


def test_supported_links_are_kept():
    text, _ = forrt_checks.strip_unsupported_links("[Glossary](https://forrt.org/glossary/)", PAGES)
    assert text == "[Glossary](https://forrt.org/glossary/)"


@pytest.mark.parametrize("answer", [
    '[label](https://evil.example "title")',
    "[label](https://evil.example 'title')",
    "[label](https://evil.example (title))",
    '[label](<https://evil.example> "title")',
    "[label](<https://evil.example>)",
    '[label](https://evil.example\n"title")',
    '[label]( https://evil.example  "title" )',
    '[label](javascript:alert(1) "title")',
    "[label](<javascript:alert(1)>)",
])
def test_titled_and_bracketed_links_to_unsupported_urls_are_removed(answer):
    text, removed = forrt_checks.strip_unsupported_links(f"See {answer} now", PAGES)
    assert text == "See label now"
    assert removed in ([], ["https://evil.example"])
    # Nothing the page would render as a link is left
    assert not BeautifulSoup(render_markdown(text), "html.parser").find_all("a", href=True)


@pytest.mark.parametrize("answer", [
    '[l](https://evil.example "a "b" c")',  # quote inside the title
    '[a [b] c](https://evil.example)',  # brackets inside the label
    '[a\nb](https://evil.example "t")',  # label across a line break
    '[l](https://evil.example "a \\" b")',  # escaped quote
    "[l](HTTPS://evil.example)",
    '[l](mailto:x@evil.example "a "b"")',
])
def test_links_the_patterns_do_not_parse_still_lose_unsupported_urls(answer):
    text, removed = forrt_checks.strip_unsupported_links(answer, PAGES)
    assert len(removed) == 1 and "evil.example" not in text
    assert not BeautifulSoup(render_markdown(text), "html.parser").find_all("a", href=True)


@pytest.mark.parametrize("answer", [
    '[Glossary](https://forrt.org/glossary/ "FORRT glossary")',
    "[Glossary](https://forrt.org/glossary/ 'FORRT glossary')",
    '[Glossary](<https://forrt.org/glossary/> "FORRT glossary")',
    "[Glossary](<https://forrt.org/glossary/>)",
])
def test_titled_links_to_supported_urls_are_kept(answer):
    text, removed = forrt_checks.strip_unsupported_links(answer, PAGES)
    assert text == "[Glossary](https://forrt.org/glossary/)" and removed == []
    hrefs = [a["href"] for a in BeautifulSoup(render_markdown(text), "html.parser").find_all("a", href=True)]
    assert hrefs == ["https://forrt.org/glossary/"]


# ---------- home page: bg_color ----------

@pytest.mark.parametrize("value, shown", [
    ("#abc", "#abc"), ("#A1B2C3", "#A1B2C3"), ("#a1b2c3d4", "#a1b2c3d4"),
    ("red", "#fefdf6"), ("#12345", "#fefdf6"), ("#abc\n", "#fefdf6"), ("abc", "#fefdf6"),
    ("#fff;}</style><script>alert(1)</script>", "#fefdf6"),
    ("red;}</style><script>alert(1)</script>", "#fefdf6"),
    ("expression(alert(1))", "#fefdf6"),
])
def test_bg_color_is_a_hex_colour_or_the_default(app, value, shown):  # noqa: F811
    html = app.app.test_client().get("/", query_string={"bg_color": value}).get_data(as_text=True)
    assert f"background-color: {shown};" in html
    assert "alert(1)" not in html


def test_bg_color_default(app):  # noqa: F811
    html = app.app.test_client().get("/").get_data(as_text=True)
    assert "background-color: #fefdf6;" in html


# ---------- /chat and /arena/chat: malformed requests ----------

class OkRag:
    def __init__(self):
        self.options = []

    def get_response(self, query, chat_id, model, **options):
        self.options.append(options)
        yield {"status": "complete", "message": "<p>ok</p>", "outcome": "answered"}


@pytest.mark.parametrize("body", [
    "not json",
    "[1, 2]",
    '"a string"',
    "null",
    json.dumps({"message": 123, "chat_id": "c"}),
    json.dumps({"message": ["What is open data?"], "chat_id": "c"}),
    json.dumps({"message": "What is open data?", "chat_id": 5}),
    json.dumps({"message": "What is open data?", "chat_id": {"a": 1}}),
    json.dumps({"message": "What is open data?"}),
    json.dumps({"message": "What is open data?", "chat_id": "c", "router": ["cosine"]}),
    json.dumps({"message": "What is open data?", "chat_id": "c", "router": {"a": 1}}),
    json.dumps({"message": "What is open data?", "chat_id": "c", "model": ["m1"]}),
])
def test_malformed_chat_requests_get_400(app, body):  # noqa: F811
    app._rag_service = OkRag()
    response = app.app.test_client().post("/chat", data=body, content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


@pytest.mark.parametrize("body", [
    "not json",
    "[1]",
    json.dumps({"message": 1}),
    json.dumps({"message": "What is open data?", "models": [["m1"]]}),
    json.dumps({"message": "What is open data?", "models": [{"m": 1}]}),
    json.dumps({"message": "What is open data?", "models": "m1"}),
    json.dumps({"message": "What is open data?", "models": ["m1"], "router": ["cosine"]}),
    json.dumps({"message": "What is open data?", "models": ["m1"], "router": {"a": 1}}),
])
def test_malformed_arena_requests_get_400(app, body):  # noqa: F811
    response = app.app.test_client().post("/arena/chat", data=body, content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


@pytest.mark.parametrize("path", ["/chat/feedback", "/review/save", "/recommend/save", "/arena/rate"])
@pytest.mark.parametrize("body", ["[]", "[1]", '"hi"', "123", "true", "null", "not json"])
def test_non_object_json_gets_400_on_every_json_endpoint(app, tmp_path, path, body):  # noqa: F811
    app.config.update(RECOMMENDATIONS_FILE=str(tmp_path / "recommendations.jsonl"),
                      REVIEW_ITEMS_FILE=str(tmp_path / "items.json"), SCORES_DIR=str(tmp_path / "scores"))
    (tmp_path / "items.json").write_text("[]")
    response = app.app.test_client().post(path, data=body, content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_prod_mode_ignores_the_router_choice(app):  # noqa: F811
    rag = app._rag_service = OkRag()
    app.config.update(PROD_MODE=True, CITATION_MODEL="m1")
    client = app.app.test_client()
    for router in ("cosine", "none", "bogus"):
        response = client.post("/chat", json={"message": "What is open data?", "chat_id": "c", "router": router})
        assert response.status_code == 200
        response.get_data()
    assert rag.options == [{}, {}, {}]
    # Outside PROD_MODE the choice still counts
    app.config["PROD_MODE"] = False
    client.post("/chat", json={"message": "What is open data?", "chat_id": "c", "router": "cosine"}).get_data()
    assert rag.options[-1] == {"router": "cosine"}


# ---------- settings ----------

def test_list_settings_are_parsed_from_comma_separated_env_strings():
    assert env_value("https://a.org, https://b.org ,,", ["https://forrt.org"]) == ["https://a.org", "https://b.org"]
    assert env_value("https://a.org", []) == ["https://a.org"]
    assert env_value("true", False) is True and env_value("0", True) is False
    assert env_value("7", 1) == 7 and env_value("0.5", 1.0) == 0.5 and env_value("x", "y") == "x"


def test_allowed_origins_from_env_is_a_list():
    import subprocess
    import sys

    env = {**os.environ, "ALLOWED_ORIGINS": "https://a.org, https://b.org", "PYTHONPATH": ROOT}
    out = subprocess.run(
        [sys.executable, "-c", "from config.settings import ALLOWED_ORIGINS as o; import json; print(json.dumps(o))"],
        env=env, capture_output=True, text=True, check=True, cwd=ROOT,
    ).stdout
    assert json.loads(out) == ["https://a.org", "https://b.org"]


# ---------- templates and frontend assets ----------

TEMPLATES = sorted(glob.glob(os.path.join(ROOT, "just_os", "templates", "*.html")))
EXTERNAL = re.compile(
    r"""<script[^>]*\bsrc\s*=\s*["']?(?:https?:)?//"""
    r"""|<link[^>]*\bhref\s*=\s*["']?(?:https?:)?//"""
    r"""|@import\s+(?:url\()?\s*["']?(?:https?:)?//"""
    r"""|url\(\s*["']?(?:https?:)?//""",
    re.I,
)


@pytest.mark.parametrize("path", TEMPLATES, ids=os.path.basename)
def test_templates_load_no_external_scripts_styles_or_fonts(path):
    text = open(path, encoding="utf-8").read()
    assert not EXTERNAL.search(text), EXTERNAL.search(text).group(0)
    for host in ("cdnjs.cloudflare.com", "cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com", "unpkg.com"):
        assert host not in text


def test_external_pattern_catches_cdns():
    assert EXTERNAL.search('<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>')
    assert EXTERNAL.search('<link href="//fonts.googleapis.com/css2" rel="stylesheet">')
    assert EXTERNAL.search("@import url('https://fonts.googleapis.com/x');")
    assert not EXTERNAL.search('<a href="https://forrt.org/">FORRT</a>')


SAFE_FILTER = re.compile(r"\|\s*safe\b")


@pytest.mark.parametrize("path", TEMPLATES, ids=os.path.basename)
def test_templates_use_no_safe_filter(path):
    text = open(path, encoding="utf-8").read()
    assert not SAFE_FILTER.search(text), SAFE_FILTER.search(text).group(0)


def test_safe_filter_pattern():
    for text in ("{{ x|safe }}", "{{ x | safe }}", "{{ x |\n safe }}", "{{ x|safe|e }}"):
        assert SAFE_FILTER.search(text), text
    assert not SAFE_FILTER.search("const link = safeUrl(r.url) || safeUrl(r.doi);")


def test_home_page_has_body_vendor_css_and_an_accurate_about_box(app):  # noqa: F811
    template = open(os.path.join(ROOT, "just_os", "templates", "index.html"), encoding="utf-8").read()
    assert "message_history" not in template
    html = app.app.test_client().get("/").get_data(as_text=True)
    soup = BeautifulSoup(html, "html.parser")
    assert html.index("</head>") < html.index("<body>") < html.index('id="header-bar"')
    assert any("css/vendor" in (link.get("href") or "") for link in soup.find_all("link"))
    about = soup.find(id="info-modal").get_text()
    assert "Open Scholar" not in about and "OpenScholar" not in about and "Unpaywall" not in about
    assert "open-access" not in about and "abstract cards" in about and "licence permits" in about
    assert soup.find(id="info-modal").find("a", href="https://github.com/forrtproject/just-os-chatbot")


def test_arena_page_uses_the_vendor_css(app):  # noqa: F811
    html = app.app.test_client().get("/arena").get_data(as_text=True)
    assert "css/vendor" in html and "cdnjs" not in html


@pytest.mark.parametrize("path", TEMPLATES, ids=os.path.basename)
def test_templates_link_static_files_with_static_url_for(path):
    text = open(path, encoding="utf-8").read()
    assert not re.search(r"(?<!static_)url_for\(\s*['\"]static['\"]", text)
    assert "'/images/qualle.png'" not in text and '"/images/qualle.png"' not in text


def test_static_url_for_uses_the_digest_manifest(app, monkeypatch):  # noqa: F811
    from just_os.extensions import flask_static_digest

    client = app.app.test_client()
    manifest = {}  # whatever `flask digest compile` left in public/ on this machine is ignored
    monkeypatch.setitem(flask_static_digest.manifests, "static", manifest)
    html = client.get("/").get_data(as_text=True)
    assert 'href="/css/vendor.css"' in html and 'src="/js/app.js"' in html  # no manifest: plain names
    monkeypatch.setitem(manifest, "css/vendor.css", "css/vendor-0123abcd.css")
    monkeypatch.setitem(manifest, "js/app.js", "js/app-89efcdab.js")
    html = client.get("/").get_data(as_text=True)
    assert 'href="/css/vendor-0123abcd.css"' in html and 'src="/js/app-89efcdab.js"' in html


def test_review_page_links_only_http_sources(app, tmp_path):  # noqa: F811
    items = [{"key": "k1", "answer_id": "a#q1", "id": "q1", "category": "c", "question": "Q?", "expected": "answer",
              "bot_did": "answered", "answered_from": "papers", "answer": "A",
              "sources": [{"n": 0, "title": "Evil source", "doi": "", "link": "javascript:alert(1)", "cited": True},
                          {"n": 1, "title": "Good source", "doi": "", "link": "https://example.org/p", "cited": False}],
              "rubric": []}]
    (tmp_path / "items.json").write_text(json.dumps(items))
    app.config.update(REVIEW_ITEMS_FILE=str(tmp_path / "items.json"))
    html = app.app.test_client().get("/review").get_data(as_text=True)
    assert "javascript:" not in html and "Evil source" in html
    assert 'href="https://example.org/p"' in html


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_frontend_bundles_and_uses_dompurify_and_marked():
    sanitize = read("assets", "js", "sanitize.js")
    assert 'from "dompurify"' in sanitize and 'from "marked"' in sanitize
    assert "data-reference" in sanitize and "ALLOWED_URI_REGEXP" in sanitize
    app_js, arena_js = read("assets", "js", "app.js"), read("assets", "js", "arena.js")
    assert './sanitize.js"' in app_js and './sanitize.js"' in arena_js
    assert "window.DOMPurify" not in app_js and "window.marked" not in app_js
    assert "innerHTML = message;" not in app_js and "innerHTML = response.message" not in arena_js
    assert "innerHTML = data.message" not in arena_js
    assert "requestBody" not in app_js and "document.createElement('style')" not in app_js
    assert re.search(r"/\^https\?:\\/\\//i\.test\(c\.url", read("assets", "js", "debug.js"))


def test_frontend_packages_are_pinned_and_locked():
    deps = json.loads(read("assets", "package.json"))["dependencies"]
    lock = read("assets", "yarn.lock")
    for name in ("dompurify", "marked", "@fortawesome/fontawesome-free", "@fontsource/roboto-mono"):
        assert re.fullmatch(r"\d+\.\d+\.\d+", deps[name]), name
        assert f"{name}@{deps[name]}" in lock, name
    config = read("assets", "esbuild.config.mjs")
    assert "css/vendor" in config and '"fonts/' in config


def test_cached_answers_from_before_the_sanitizer_are_cleaned_on_the_way_out():
    from test_answer_cache import cache
    from test_qualle import make_qualle, node

    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.answer_cache = cache()
    link = '<a href="#" class="reference-link" data-reference="{&quot;title&quot;:&quot;T&quot;}">[1]</a>'
    old = {"status": "complete", "message": f"<p>Old <script>alert(1)</script><img src=x onerror=alert(2)> {link}</p>"}
    q.answer_cache.store("What is preregistration?", old, "Old")
    final = list(q.get_response("what is preregistration", "chat-1"))[-1]
    assert "script" not in final["message"] and "onerror" not in final["message"]
    (kept,) = reference_links(final["message"])
    assert json.loads(kept["data-reference"]) == {"title": "T"}
    assert "script" in old["message"]  # the stored entry itself is not changed in place


def test_cached_answers_with_broken_reference_data_lose_the_citation_link():
    from test_answer_cache import cache
    from test_qualle import make_qualle, node

    q = make_qualle(True, [node("Paper")], [node("Paper")], "Answer [0].")
    q.answer_cache = cache()
    broken = '<a href="#" class="reference-link" data-reference="{&quot;title&quot;:">[1]</a>'
    q.answer_cache.store("What is preregistration?", {"status": "complete", "message": f"<p>Old {broken}</p>"}, "Old")
    final = list(q.get_response("what is preregistration", "chat-1"))[-1]
    assert final["message"] == "<p>Old <a>[1]</a></p>"


def test_draft_sanitizer_drops_citation_attributes_and_answer_sanitizer_keeps_them():
    sanitize = read("assets", "js", "sanitize.js")
    draft = re.search(r"const DRAFT_CONFIG = \{(.*?)\n\};", sanitize, re.S).group(1)
    answer = re.search(r"const ANSWER_CONFIG = \{(.*?)\n\};", sanitize, re.S).group(1)
    allowed = re.search(r"ALLOWED_ATTR:\s*\[([^\]]*)\]", draft).group(1)
    assert '"class"' not in allowed and '"data-reference"' not in allowed
    assert re.search(r'FORBID_ATTR:\s*\["class", "data-reference"\]', draft)
    assert '"data-reference"' in re.search(r"ALLOWED_ATTR:\s*\[([^\]]*)\]", answer).group(1)
    assert "return sanitizeDraft(marked.parse(" in sanitize  # the streaming draft
    assert "box.innerHTML = sanitizeDraft(html)" in sanitize  # text only
    app_js = read("assets", "js", "app.js")
    assert "innerHTML = markdownToHtml(" in app_js and "innerHTML = sanitizeAnswer(message)" in app_js
    assert "sanitizeHtml" not in app_js + read("assets", "js", "arena.js")


def test_reference_tooltip_ignores_malformed_data():
    """referenceData() returns null for broken or non-object data-reference instead of throwing."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    source = read("assets", "js", "references.js")
    script = source + """
const link = (value) => ({ getAttribute: () => value });
const cases = [null, "", "not json", "{", "[1]", '"s"', "1", "null", "true", '{"title":"T"}'];
console.log(JSON.stringify(cases.map((c) => referenceData(link(c)))));
"""
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [None] * 9 + [{"title": "T"}]


def test_stream_stops_after_the_final_frame_and_only_the_newest_request_resets_controls():
    app_js = read("assets", "js", "app.js")
    assert "const requestId = ++activeRequestId;" in app_js
    assert "const isCurrent = () => requestId === activeRequestId;" in app_js
    end_stream = re.search(r"function endStream\(\) \{(.*?)\n  \}", app_js, re.S).group(1)
    # once per request; the interval always stops, the controls only for the newest request
    assert end_stream.index("if (ended) return;") < end_stream.index("clearInterval(messageInterval)")
    assert end_stream.index("clearInterval(messageInterval)") < end_stream.index("if (!isCurrent()) return;")
    assert end_stream.index("if (!isCurrent()) return;") < end_stream.index("messageInput.disabled = false")
    assert "while (!finished)" in app_js and "if (finished) break reading;" in app_js
    assert "reader?.cancel().catch(() => {})" in app_js
    assert "if (isCurrent()) showDraft(draft);" in app_js and "if (current) removeDraft();" in app_js


def test_dompurify_config_keeps_reference_data_and_table_attributes():
    sanitize = read("assets", "js", "sanitize.js")
    # DOMPurify checks non-URI-safe attribute values against ALLOWED_URI_REGEXP: JSON would be stripped
    safe = re.search(r"ADD_URI_SAFE_ATTR:\s*\[([^\]]*)\]", sanitize).group(1)
    for name in ("data-reference", "colspan", "rowspan", "start"):
        assert f'"{name}"' in safe


def test_send_button_ignores_short_input():
    assert "message.trim().length < 3) return" in read("assets", "js", "app.js")


def test_valid_reference_data_rejects_nan_and_wrong_field_types():
    from just_os.sanitize import valid_reference_data

    assert not valid_reference_data('{"title": "T", "year": NaN}')
    assert not valid_reference_data('{"title": "T", "year": Infinity}')
    assert not valid_reference_data('{"title": "T", "unverified": "false"}')
    assert not valid_reference_data('{"title": "T", "unverified": 1}')
    assert not valid_reference_data('{"title": 123}')
    assert not valid_reference_data('{"title": "T", "url": "javascript:alert(1)"}')
    assert not valid_reference_data('{"title": "T", "url": ""}')
    assert not valid_reference_data('{"title": "T", "url": "   "}')
    assert valid_reference_data('{"title": "T", "authors": "A", "year": "2024", "url": "https://example.org", "text": "", "unverified": false}')
    assert valid_reference_data('{"title": "T", "year": 2024, "url": null, "unverified": true}')


def test_forrt_checks_preserves_allowed_paren_url_with_bracketed_label():
    from just_os.forrt_checks import strip_unsupported_links

    url = "https://en.wikipedia.org/wiki/Replication_(statistics)"
    pages = [{"url": "https://forrt.org/p", "excerpt": f"See {url} and https://example.org/fn() and https://example.org/a(b"}]
    md = f"Read [guide [v2]]({url}) now, plus https://example.org/fn() and https://example.org/a(b."
    cleaned, removed = strip_unsupported_links(md, pages)
    assert url in cleaned and not removed
    assert "<https://example.org/fn()>" in cleaned
    assert "<https://example.org/a(b>" in cleaned


def test_new_chat_aborts_active_stream_and_ignores_stale_chat_replies():
    app_js = read("assets", "js", "app.js")
    assert "const chatIdAtStart = window.chatId;" in app_js
    assert "if (!isSameChat()) return;" in app_js
    assert "activeAbortControllers.add(controller);" in app_js
    assert "for (const c of activeAbortControllers) c.abort();" in app_js
    assert "removeDraft();" in app_js
    assert "data.unverified === true" in read("assets", "js", "references.js")
