"""Merge eval runs into one Markdown table (for the demo and for PR descriptions).

    python eval/compare.py                      # all eval/results/run_*.csv
    python eval/compare.py eval/results/run_A.csv eval/results/run_B.csv
"""

import csv
import sys
from pathlib import Path
from statistics import mean


def rate(rows, key):
    values = [int(r[key]) for r in rows if r[key] != ""]
    return f"{mean(values):.2f}" if values else "–"


def judge(rows):
    """Mean judge_support (eval/judge.py), "–" when the run was not judged."""
    values = [float(r["judge_support"]) for r in rows if r.get("judge_support") not in (None, "")]
    return f"{mean(values):.2f}" if values else "–"


def summarize(paths):
    lines = [
        "| Run | n | Correct | Answered (should answer) | Refused (should refuse) | Errors | hit@7 | Citations valid | Judge support | Mean s | p95 s | Tokens / q | USD / 1k q |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for path in paths:
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        if not rows:
            continue
        answer = [r for r in rows if r["expect"] == "answer"]
        refuse = [r for r in rows if r["expect"] == "refuse"]
        seconds = sorted(float(r["seconds"]) for r in rows)
        tokens = mean(int(r["prompt_tokens"]) + int(r["completion_tokens"]) for r in rows)
        cost = mean(float(r["cost_usd"]) for r in rows) * 1000
        lines.append(
            f"| {Path(path).stem.removeprefix('run_')} | {len(rows)} | {rate(rows, 'correct')} "
            f"| {sum(r['outcome'] == 'answered' for r in answer)}/{len(answer)} "
            f"| {sum(r['outcome'] == 'refused' for r in refuse)}/{len(refuse)} "
            f"| {sum(r['outcome'] == 'error' for r in rows)} "
            f"| {rate(rows, 'hit')} | {rate(rows, 'citations_valid')} | {judge(rows)} "
            f"| {mean(seconds):.1f} | {seconds[int(0.95 * (len(seconds) - 1))]:.1f} "
            f"| {tokens:.0f} | {cost:.2f} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(Path("eval/results").glob("run_*.csv"))
    print(summarize(paths))
