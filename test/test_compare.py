import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from compare import summarize  # noqa: E402
from run import FIELDS  # noqa: E402


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
