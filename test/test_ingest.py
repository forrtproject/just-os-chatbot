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
