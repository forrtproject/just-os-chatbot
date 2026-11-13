"""Score rows (#54): what people, LLM judges and gold metrics said about each answer, in one format,
and how far they agree.

    python eval/scores.py eval/results/human_review_261113.csv [--reviews data/reviews]
        [--arena data/arena/ratings.jsonl] [--out data/scores/scores_<run>.jsonl]

One row per answer, criterion and scorer: {answer_id, question_id, criterion, score, scale, scorer_kind
(person, llm or metric), scorer, setting, time, note}. `scale` is [low, high] for a number and empty for
the decision (right, should_refuse, should_answer, unsure). Until the answer store of #54 exists, an
answer of an eval run is "<run file stem>#<question id>" and an arena answer "arena:<battle id>:<model>".

Sources: the run CSV gives the gold decision (outcome against expect), hit@7 (source relevance),
citations valid (citation format: every [n] points to a source) and the support judge (citation support) and rubric judge (rubric items, completeness);
the reviews of that run (data/reviews/, the last save of each reviewer per question) give people's
decision and five criteria; arena ratings give the arena's three criteria, kept apart as arena_<name>
since each covers two shared criteria.

The report compares, per shared criterion, people with each automated scorer on the answers both scored
(Spearman rank correlation, and the mean difference on 0-1), and the reviewers with each other
(quadratic weighted kappa: 1 full agreement, 0 what chance gives).
"""

import argparse
import csv
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from just_os import criteria  # noqa: E402
from just_os.scores import SCALE, UNIT, load, ranks, row, spearman, weighted_kappa, agreement  # noqa: E402,F401


def gold_decision(r):
    """The decision a reviewer should give, from the run's outcome and the question's expect."""
    answered = r["outcome"] == "answered"
    if answered == (r["expect"] == "answer"):
        return "right"
    return "should_refuse" if answered else "should_answer"


def run_rows(run_csv):
    """Gold metrics and LLM judge scores of an eval/run.py CSV."""
    run, out = Path(run_csv).stem, []
    for r in csv.DictReader(open(run_csv, encoding="utf-8")):
        a = f"{run}#{r['id']}"
        if r.get("outcome") in ("answered", "refused", "no_sources"):
            out.append(row(a, r["id"], "decision", gold_decision(r), None, "metric", "outcome vs expect"))
        if r.get("hit") not in (None, ""):
            out.append(row(a, r["id"], "source_relevance", int(float(r["hit"])), UNIT, "metric", "hit@7"))
        if r.get("citations_valid") not in (None, ""):
            # format only (every [n] points to a source), so not filed under citation support
            out.append(row(a, r["id"], "citation_format", int(float(r["citations_valid"])), UNIT, "metric", "citations valid"))
        if r.get("judge_support") not in (None, ""):
            out.append(row(a, r["id"], "citation_support", float(r["judge_support"]), UNIT, "llm", "support judge"))
        if r.get("rubric_scores"):
            for item, s in json.loads(r["rubric_scores"]).items():
                out.append(row(a, r["id"], f"rubric:{item}", s, SCALE, "llm", "rubric judge", setting="rubric"))
            out.append(row(a, r["id"], "completeness", float(r["rubric_coverage"]), UNIT, "llm", "rubric judge"))
    return out


def review_rows(run_csv, reviews_dir):
    """People's scores from /review, the last save of each reviewer per question (files are named by time)."""
    run, latest = Path(run_csv).stem, {}
    for path in sorted(glob.glob(os.path.join(reviews_dir, "review_*.csv"))):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            latest[(r["reviewer"], r["item_id"])] = r
    out = []
    for (reviewer, item), r in latest.items():
        a = f"{run}#{item}"
        if r.get("decision"):
            out.append(row(a, item, "decision", r["decision"], None, "person", reviewer, r.get("saved_at", ""), r.get("note", "")))
        for c in criteria.REVIEW:
            if r.get(c, "") not in ("", "n/a"):
                out.append(row(a, item, c, int(r[c]), SCALE, "person", reviewer, r.get("saved_at", "")))
    return out


def arena_rows(ratings_jsonl):
    """Arena ratings, one row per answer and arena criterion."""
    out = []
    if not os.path.exists(ratings_jsonl):
        return out
    for line in open(ratings_jsonl, encoding="utf-8"):
        r = json.loads(line)
        for c in criteria.ARENA:
            if c in r:
                out.append(row(f"arena:{r['battle_id']}:{r['model']}", "", f"arena_{c}", r[c], SCALE, "person",
                               "arena", r.get("time", "")))
    return out


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


def report(rows):
    """Markdown: people against each automated scorer, and reviewers against each other (just_os.scores)."""
    result = agreement(rows)
    lines = ["| Criterion | People against | n answers | Agreement | People mean (0-1) | Scorer mean (0-1) |",
             "|---|---|---|---|---|---|"]
    for a in result["against"]:
        if a["criterion"] == "decision":
            lines.append(f"| decision | {a['scorer']} | {a['n']} | {fmt(a['same'])} same decision | – | – |")
        else:
            lines.append(f"| {a['criterion']} | {a['scorer']} | {a['n']} | {fmt(a['spearman'])} Spearman | "
                         f"{fmt(a['people'])} | {fmt(a['scorer_mean'])} |")
    lines += ["", "| Criterion | Reviewers | n answers | Weighted kappa | Exact | Within 1 |", "|---|---|---|---|---|---|"]
    for r in result["reviewers"]:
        lines.append(f"| {r['criterion']} | {r['a']} / {r['b']} | {r['n']} | {fmt(r['kappa'])} | "
                     f"{fmt(r['exact'])} | {fmt(r['within_one'])} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_csv")
    parser.add_argument("--reviews", default="data/reviews")
    parser.add_argument("--arena", default="data/arena/ratings.jsonl")
    parser.add_argument("--out", help="score rows (default data/scores/scores_<run>.jsonl)")
    args = parser.parse_args()
    rows = run_rows(args.run_csv) + review_rows(args.run_csv, args.reviews) + arena_rows(args.arena)
    out = Path(args.out or f"data/scores/scores_{Path(args.run_csv).stem}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    # rows other scorers wrote for the same answers, such as eval/criteria_judge.py
    ids = {r["answer_id"] for r in rows}
    rows += [r for r in load(out.parent, skip=out) if r["answer_id"] in ids]
    print(report(rows))
    print(f"\n{len(rows)} score rows ({out} and the other files of {out.parent} for these answers)")


if __name__ == "__main__":
    main()
