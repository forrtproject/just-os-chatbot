import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from compare import summarize  # noqa: E402
from run import FIELDS, answer_source, hit_of, outcome_of  # noqa: E402


def test_summarize_counts_outcomes(tmp_path):
    rows = [
        {"expect": "answer", "outcome": "answered", "correct": 1, "hit": 1, "citations_valid": 1},
        {"expect": "answer", "outcome": "error", "correct": 0, "hit": "", "citations_valid": ""},
        {"expect": "refuse", "outcome": "refused", "correct": 1, "hit": "", "citations_valid": ""},
    ]
    path = tmp_path / "run_x_model.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for i, r in enumerate(rows):
            writer.writerow({
                **{k: "" for k in FIELDS}, **r, "id": i, "seconds": 2.0,
                "prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.001,
            })

    line = summarize([path]).splitlines()[-1]

    assert "| x_model | 3 | 0.67 | 1/2 | 1/1 | 1 | 1.00 | 1.00 |" in line
    assert line.endswith("| 150 | 1.00 |")


def test_answer_source_checks_citations_against_the_right_sources():
    papers = {"ranked": ["p0", "p1"], "forrt": None}
    assert answer_source(papers, [0, 1]) == ("papers", True)
    assert answer_source(papers, [2]) == ("papers", False)
    # forrt.org pages are numbered from 1, and the papers step did not run
    forrt = {"ranked": [], "forrt": {"text": "t [1][2]", "sources": [{"n": 1}, {"n": 2}]}}
    assert answer_source(forrt, [1, 2]) == ("forrt pages", True)
    assert answer_source(forrt, [0]) == ("forrt pages", False)
    assert answer_source({"ranked": [], "forrt": None}, []) == ("", True)  # refused before any source


def test_hit_counts_expected_dois_in_papers_and_expected_urls_in_forrt_pages():
    forrt = {"sources": [{"n": 1, "title": "Teams", "url": "https://forrt.org/about/teams/"}]}
    assert hit_of({"expected_urls": ["https://forrt.org/about/teams"]}, [], forrt) == 1  # trailing slash ignored
    assert hit_of({"expected_urls": ["https://forrt.org/glossary/"]}, [], forrt) == 0
    assert hit_of({"expected_dois": ["10.1/A"]}, ["10.1/a"], None) == 1
    assert hit_of({"id": "x"}, ["10.1/a"], forrt) == ""


def test_an_answer_model_that_returned_nothing_is_an_error_not_an_answer():
    from just_os.messages import message
    assert outcome_of({"status": "complete", "message": f"<p>{message('generation_error')}</p>"}) == "error"
    assert outcome_of({"status": "complete", "message": "<p>Open data is [1].</p>"}) == "answered"
