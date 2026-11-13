"""eval/tune_bands.py: the strict rule for the banded topic check's thresholds."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import tune_bands  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def row(label, paper, page):
    return {"label": label, "paper": paper, "page": page}


def test_high_sits_above_every_off_topic_question_and_low_refuses_few_in_scope_ones():
    rows = [row("papers", p / 100, 0.2) for p in range(50, 100)]  # 50 in scope: 0.50 .. 0.99
    rows += [row("pages", 0.3, p / 100) for p in range(40, 90)]  # 50 in scope: 0.40 .. 0.89
    rows += [row("off_topic", 0.72, 0.55), row("off_topic", 0.60, 0.61)]
    t = tune_bands.thresholds(rows, margin=0.01, max_refused=0.02)
    assert t == {"BAND_PAPER_LOW": 0.51, "BAND_PAGE_LOW": 0.41, "BAND_PAPER_HIGH": 0.73, "BAND_PAGE_HIGH": 0.62}
    assert sum(r["paper"] < t["BAND_PAPER_LOW"] for r in rows if r["label"] == "papers") == 1  # 2% of 50
    assert all(tune_bands.band(r["paper"], r["page"], t) != "high" for r in rows if r["label"] == "off_topic")



def test_a_low_threshold_never_rounds_up_past_the_share_it_may_refuse():
    rows = [row("papers", v, 0.2) for v in (0.5004, 0.5006, 0.6, 0.7)]  # cut at 0.5006 leaves 1 below
    t = tune_bands.thresholds(rows + [row("pages", 0.3, 0.5), row("off_topic", 0.4, 0.3)], 0.01, 0.25)
    assert t["BAND_PAPER_LOW"] == 0.5  # rounding up to 0.501 would refuse 2 of 4
    assert sum(r["paper"] < t["BAND_PAPER_LOW"] for r in rows) <= 1


def test_max_refused_is_a_share_below_one():
    import pytest
    assert tune_bands.share("0.02") == 0.02
    for bad in ("1", "-0.1", "2"):
        with pytest.raises(Exception):
            tune_bands.share(bad)

def test_tuning_questions_leave_out_the_report_files():
    report = {q[3] for q in tune_bands.report_questions()}
    tuning = tune_bands.tuning_questions()
    assert not report & {q[3] for q in tuning}
    assert {q[2] for q in tuning} == {"papers", "pages", "off_topic"}
    with open(ROOT / "eval/refusal_questions.jsonl", encoding="utf-8") as f:
        assert sum(q[0] == "refusal" for q in tuning) == sum(1 for line in f if json.loads(line))
