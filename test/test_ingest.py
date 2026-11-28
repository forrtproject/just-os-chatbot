import importlib
import io

import pandas as pd

from ingest import helpers


# --- finding 17: Unpaywall title search must match the title


def result(title):
    return {"response": {"title": title, "doi": "10.1234/x"}}


def test_best_title_match_accepts_close_title_only():
    results = [result("A different paper about replication"), result("Preregistering Qualitative Research.")]
    assert helpers.best_title_match("Preregistering qualitative research", results)["title"].startswith("Preregistering")
    assert helpers.best_title_match("Open science in ecology", results) is None
    assert helpers.best_title_match("Anything", []) is None


# --- finding 18: only real PDFs are saved


def fake_urlopen(content):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return lambda url, timeout=60: Response(content)


def test_download_saves_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers.urllib.request, "urlopen", fake_urlopen(b"%PDF-1.7 data"))
    name = helpers.download_and_save_pdf("https://x/paper.pdf", "10.1234/x", tmp_path)
    assert (tmp_path / name).read_bytes().startswith(b"%PDF")


def test_download_rejects_html(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers.urllib.request, "urlopen", fake_urlopen(b"<html>paywall</html>"))
    assert helpers.download_and_save_pdf("https://x/paper", "10.1234/x", tmp_path) is None
    assert list(tmp_path.iterdir()) == []


# --- issue 24: one metadata row per doi_hash


def test_unique_metadata_keeps_plain_values():
    embed = importlib.import_module("scripts.embed")
    metadata = pd.DataFrame(
        {"doi_hash": ["a", "a", "b"], "title": ["First", "Duplicate", "Other"]}
    ).set_index("doi_hash")
    unique = embed.unique_metadata(metadata)
    assert unique.loc["a"].to_dict() == {"title": "First"}  # a plain value, not {"a": ...}
    assert len(unique) == 2


# --- finding 16: gunicorn config without distutils


def test_gunicorn_reload_flag(monkeypatch):
    monkeypatch.setenv("WEB_RELOAD", "true")
    gunicorn_config = importlib.reload(importlib.import_module("config.gunicorn"))
    assert gunicorn_config.reload is True
    monkeypatch.setenv("WEB_RELOAD", "false")
    assert importlib.reload(gunicorn_config).reload is False


def test_curate_reports_every_row_and_writes_markdown_for_new_ones(tmp_path, monkeypatch):
    from scripts import curate

    rows = tmp_path / "rows.csv"
    rows.write_text("title,link_to_resource\nKnown paper,https://doi.org/10.1234/KNOWN\n"
                    "New paper,https://doi.org/10.1234/new\nA web guide,https://example.org/guide\n", encoding="utf-8")
    monkeypatch.setattr(curate, "pdf_markdown", lambda row, work: ("converted", "# New paper\n\nText."))
    monkeypatch.setattr(curate, "web_markdown", lambda row: ("web_page_too_short", ""))
    parsed = curate.read_rows(str(rows))
    assert [r["doi"] for r in parsed] == ["10.1234/known", "10.1234/new", ""]  # DOI taken from the link
    report, metadata = curate.curate(parsed, {"10.1234/known"}, tmp_path)
    assert [r["outcome"] for r in report] == ["already_indexed", "converted", "web_page_too_short"]
    assert [m["doi"] for m in metadata] == ["10.1234/new"]
    assert (tmp_path / "markdown" / f"{metadata[0]['doi_hash']}.md").read_text(encoding="utf-8").startswith("# New paper")


def test_pdf_sources_tries_every_open_copy_and_keeps_only_real_pdfs(monkeypatch):
    import httpx
    from ingest import pdf_sources

    monkeypatch.setattr(pdf_sources, "EMAIL", "team@example.org")
    pdf = b"%PDF-1.7" + b"x" * 6000

    def handler(request):
        url = str(request.url)
        if "unpaywall" in url:
            return httpx.Response(200, json={"oa_locations": [{"url_for_pdf": "https://pub.example/a.pdf", "license": "cc-by"},
                                                              {"url_for_pdf": "https://repo.example/a.pdf", "license": "cc-by"}]})
        if "openalex" in url:
            return httpx.Response(200, json={"locations": [{"pdf_url": "https://repo.example/a.pdf"}]})  # a duplicate
        if "semanticscholar" in url:
            return httpx.Response(200, json={"openAccessPdf": {"url": "https://s2.example/a.pdf"}})
        if "europepmc" in url and "search" in url:
            return httpx.Response(200, json={"resultList": {"result": [{"pmcid": "PMC1"}]}})
        if "doi.org" in url:
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<meta name="citation_pdf_url" content="/full.pdf">')
        if url == "https://pub.example/a.pdf":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>paywall</html>")
        return httpx.Response(200, content=pdf)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    found = list(pdf_sources.candidates(http, "10.31234/osf.io/ab12c"))
    assert [s for _, s, _ in found] == ["osf", "unpaywall", "unpaywall", "semanticscholar", "europepmc", "landing_page"]
    assert found[1][2] == "cc-by" and found[-1][0] == "https://doi.org/full.pdf"
    assert pdf_sources.download(http, "https://pub.example/a.pdf") is None  # HTML, not a PDF
    assert pdf_sources.download(http, "https://repo.example/a.pdf") == pdf


def test_title_check_keeps_the_wrong_paper_out():
    from ingest.pdf_sources import title_matches

    assert title_matches("Registered Reports: A Method to Increase the Credibility", "registered reports a method to increase credibility of science")
    assert not title_matches("Registered Reports: A Method to Increase the Credibility", "Bird migration over the Alps")
    assert title_matches("", "anything")


def test_curate_tries_the_next_copy_when_one_is_the_wrong_paper(tmp_path, monkeypatch):
    from ingest import pdf_sources
    from scripts import convert_cluster_pdfs, curate

    copies = [("https://a.example/x.pdf", "unpaywall", "cc-by"), ("https://b.example/y.pdf", "openalex", "cc-by-sa")]
    monkeypatch.setattr(pdf_sources, "candidates", lambda http, doi, link: iter(copies))
    monkeypatch.setattr(pdf_sources, "download", lambda http, url: b"%PDF " + url.encode())
    monkeypatch.setattr(curate, "is_public_url", lambda url: True)  # no DNS lookups in tests
    monkeypatch.setattr(convert_cluster_pdfs, "grobid_tei", lambda pdf, key: pdf.read_bytes().decode())
    titles = {"https://a.example/x.pdf": "Something else entirely", "https://b.example/y.pdf": "Open data in psychology"}
    monkeypatch.setattr(convert_cluster_pdfs, "tei_to_markdown",
                        lambda tei: ({"title": titles[tei[5:]]}, "# t\n\n" + "text " * 500))
    row = {"doi": "10.1/x", "title": "Open data in psychology", "link_to_resource": "", "conditions_of_use": "", "creators": ""}
    outcome, markdown = curate.pdf_markdown(row, tmp_path, http=object())
    assert outcome == "converted" and row["conditions_of_use"] == "cc-by-sa"  # the second copy, with its licence
    row2 = dict(row, title="Unrelated title words")
    assert curate.pdf_markdown(row2, tmp_path, http=object())[0] == "wrong_document"


def test_curate_reads_recommendations(tmp_path):
    from scripts import curate

    path = tmp_path / "recommendations.jsonl"
    path.write_text('{"time": "t", "doi": "10.1234/abc", "link_to_resource": "", "note": "n", "name": ""}\n'
                    '{"time": "t", "doi": "", "link_to_resource": "https://osf.io/abcd1/", "note": "", "name": "A"}\n',
                    encoding="utf-8")
    rows = curate.read_rows(None, recommendations=str(path))
    assert [(r["doi"], r["link_to_resource"], r["title"]) for r in rows] == [("10.1234/abc", "", ""), ("", "https://osf.io/abcd1/", "")]


def test_web_page_needs_running_text(monkeypatch):
    from scripts import curate, fetch_web_resources

    menu = "\n".join(["Home", "People", "Dataset", "Download", "Terms of Use"] * 60)
    prose = "\n".join(["Open data lets other researchers check and reuse the results of a study."] * 20)
    for text, outcome in ((menu, "web_page_too_short"), (prose, "converted")):
        monkeypatch.setattr(fetch_web_resources, "fetch", lambda url: "")
        monkeypatch.setattr(fetch_web_resources, "main_text", lambda html, t=text: t)
        assert curate.web_markdown({"title": "T", "link_to_resource": "https://x.org"})[0] == outcome
