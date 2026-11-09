import importlib.util
from pathlib import Path
from types import SimpleNamespace

# Load eval/coverage.py by path: the name "coverage" is also a well-known package
spec = importlib.util.spec_from_file_location(
    "eval_coverage", Path(__file__).resolve().parent.parent / "eval" / "coverage.py"
)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def row(doi=float("nan"), url=None, title="T", excluded=False):
    return SimpleNamespace(doi=doi, url=url, title=title, excluded=excluded, key=doi if isinstance(doi, str) else title.lower())


def test_reasons():
    indexed, seen, oa = {"10.1234/in"}, {"10.1234/in", "10.1234/closed"}, {"10.1234/in"}
    assert coverage.reason(row("10.1234/in"), indexed, seen, oa) == "indexed"
    assert coverage.reason(row("10.1234/closed"), indexed, seen, oa) == "doi_not_open_access"
    assert coverage.reason(row("10.1234/new"), indexed, seen, oa) == "doi_not_processed"
    assert coverage.reason(row(url="https://www.youtube.com/watch?v=x"), indexed, seen, oa) == "video"
    assert coverage.reason(row(url="https://osf.io/abc/"), indexed, seen, oa) == "code_or_osf"
    assert coverage.reason(row(url="https://carpentries.org/x"), indexed, seen, oa) == "web_page"
    assert coverage.reason(row(), indexed, seen, oa) == "no_link"  # NaN DOI is "no DOI"
    assert coverage.reason(row("10.1234/new", excluded=True), indexed, seen, oa) == "excluded"
