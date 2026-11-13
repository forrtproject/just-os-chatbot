"""Score every topic check x answer model pair without running each pair (E3 #9, M1 #10).

    python eval/pairs.py [--classify eval/results/classify_X.csv]

The topic check only decides where a question goes: refused, the papers or the FORRT pages. So
each answer model runs twice, every question forced one way (`eval/run_batches.py --route
open_science` and `--route forrt`), and each topic check's decision per question
(`eval/classify.py --routers ...` on the same questions) picks which of the two answers the pair
would have given. A refusal (neither) or a failed topic check needs no answer. Seconds and cost
add the topic check's own. Output: eval/results/pairs_<YYMMDD-HHMM>.csv and a Markdown table.
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

RESULTS = Path(__file__).resolve().parent / "results"
REFUSE = {"neither", "off_topic", "small_talk"}
FIELDS = ["topic_check", "answer_model", "n", "correct", "answered", "should_answer", "refused", "should_refuse",
          "hit", "citations_valid", "judge_support", "mean_s", "usd_per_1k"]


def routed_runs(results=RESULTS):
    """{answer model: {"open_science": path, "forrt": path}} for the models with both forced runs (newest)."""
    runs = {}
    for path in sorted(results.glob("run_*__route-*.csv")):
        m = re.match(r"run_\d{6}-\d{4}_(.+)__route-(open_science|forrt)\.csv$", path.name)
        if m:
            runs.setdefault(m.group(1).replace("__", "/"), {})[m.group(2)] = path
    return {model: r for model, r in runs.items() if len(r) == 2}


def read(path):
    return {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score(decisions, papers, forrt):
    """One pair: decisions {id: (route or None, seconds, usd)}, papers/forrt {id: run row}."""
    rows = []
    for qid, (route, seconds, usd) in decisions.items():
        if qid not in papers:
            continue
        expect = papers[qid]["expect"]
        if route is None:
            row, outcome = None, "error"
        elif route in REFUSE:
            row, outcome = None, "refused"
        else:
            row = (forrt if route == "forrt" else papers).get(qid)
            outcome = row["outcome"] if row else "error"
        answered = row is not None and outcome == "answered"
        rows.append({"expect": expect, "outcome": outcome,
                     "correct": int((outcome == "answered") == (expect == "answer") and outcome != "error"),
                     "hit": num(row.get("hit")) if answered else None,
                     "valid": num(row.get("citations_valid")) if answered else None,
                     "judge": num(row.get("judge_support")) if answered else None,
                     "seconds": seconds + ((num(row.get("seconds")) or 0) if row else 0),
                     "usd": usd + ((num(row.get("cost_usd")) or 0) if row else 0)})

    def avg(key):
        values = [r[key] for r in rows if r[key] is not None]
        return round(mean(values), 3) if values else ""

    return {"n": len(rows), "correct": avg("correct"),
            "answered": sum(r["outcome"] == "answered" for r in rows if r["expect"] == "answer"),
            "should_answer": sum(r["expect"] == "answer" for r in rows),
            "refused": sum(r["outcome"] == "refused" for r in rows if r["expect"] == "refuse"),
            "should_refuse": sum(r["expect"] == "refuse" for r in rows),
            "hit": avg("hit"), "citations_valid": avg("valid"), "judge_support": avg("judge"),
            "mean_s": avg("seconds"), "usd_per_1k": round(mean(r["usd"] for r in rows) * 1000, 3) if rows else ""}


def decisions_by_router(classify_csv):
    """{router: {id: (route or None, seconds, usd)}} from an eval/classify.py --routers CSV."""
    out = {}
    for r in csv.DictReader(open(classify_csv, encoding="utf-8")):
        route = r["predicted"] if r["predicted"] not in ("", "None") else None
        out.setdefault(r["model"].removeprefix("router: "), {})[r["id"]] = (route, num(r["seconds"]) or 0, num(r["usd"]) or 0)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--classify", help="classify CSV (default: the newest eval/results/classify_*.csv)")
    args = parser.parse_args()
    classify_csv = Path(args.classify) if args.classify else sorted(RESULTS.glob("classify_*.csv"))[-1]
    runs = routed_runs()
    if not runs:
        sys.exit("no answer model has both forced runs (eval/run_batches.py --route open_science / forrt)")
    table = []
    for router, decisions in decisions_by_router(classify_csv).items():
        for model, paths in sorted(runs.items()):
            table.append({"topic_check": router, "answer_model": model,
                          **score(decisions, read(paths["open_science"]), read(paths["forrt"]))})
    if not table:
        sys.exit(f"no topic check in {classify_csv.name} shares questions with the answer runs")
    table.sort(key=lambda r: (-(r["correct"] or 0), -(r["judge_support"] or 0)))
    out = RESULTS / f"pairs_{datetime.now():%y%m%d-%H%M}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(table)
    print("| Topic check | Answer model | Correct | Answered | Refused | hit | Citations valid | Judge | Mean s | USD / 1k q |\n"
          "|---|---|---|---|---|---|---|---|---|---|")
    for r in table:
        print(f"| {r['topic_check']} | {r['answer_model']} | {r['correct']} | {r['answered']}/{r['should_answer']} "
              f"| {r['refused']}/{r['should_refuse']} | {r['hit']} | {r['citations_valid']} | {r['judge_support']} "
              f"| {r['mean_s']} | {r['usd_per_1k']} |")
    print(f"-> {out} (topic checks from {classify_csv.name})")


if __name__ == "__main__":
    main()
