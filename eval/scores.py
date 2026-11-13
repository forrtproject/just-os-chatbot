"""Score rows (#54): what people, LLM judges and gold metrics said about each answer, in one format,
and how far they agree.

    python eval/scores.py eval/results/human_review_261113.csv [--reviews data/reviews]
        [--arena data/arena/ratings.jsonl] [--out data/scores/scores_<run>.jsonl]

One row per answer, criterion and scorer: {answer_id, question_id, criterion, score, scale, scorer_kind
(person, llm or metric), scorer, setting, time, note}. `scale` is [low, high] for a number and empty for
the decision (right, should_refuse, should_answer, unsure). Until the answer store of #54 exists, an
answer of an eval run is "<run file stem>#<question id>" and an arena answer "arena:<battle id>:<model>".

Sources: the run CSV gives the gold decision (outcome against expect), hit@7 (source relevance),
citations valid and the support judge (citation support) and rubric judge (rubric items, completeness);
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
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from just_os import criteria  # noqa: E402

SCALE = [criteria.SCALE[0], criteria.SCALE[-1]]
UNIT = [0, 1]


def row(answer_id, question_id, criterion, score, scale, kind, scorer, time="", note="", setting="default"):
    return {"answer_id": answer_id, "question_id": question_id, "criterion": criterion, "score": score,
            "scale": scale, "scorer_kind": kind, "scorer": scorer, "setting": setting, "time": time, "note": note}


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
            out.append(row(a, r["id"], "source_relevance", int(r["hit"]), UNIT, "metric", "hit@7"))
        if r.get("citations_valid") not in (None, ""):
            out.append(row(a, r["id"], "citation_support", int(r["citations_valid"]), UNIT, "metric", "citations valid"))
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


def written(folder, skip=None):
    """The score rows of every data/scores/scores_*.jsonl file but `skip`."""
    out = []
    for path in sorted(Path(folder).glob("scores_*.jsonl")):
        if skip is None or path.resolve() != Path(skip).resolve():
            out += [json.loads(line) for line in open(path, encoding="utf-8")]
    return out


def unit(r):
    low, high = r["scale"]
    return (r["score"] - low) / (high - low)


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(xs, ys):
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(ranks(xs), ranks(ys))


def weighted_kappa(xs, ys, low, high):
    """Quadratic weighted kappa of two scorers on the same integer scale."""
    if len(xs) < 2:
        return None
    k, n = high - low + 1, len(xs)
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(xs, ys):
        observed[x - low][y - low] += 1 / n
    px = [sum(observed[i]) for i in range(k)]
    py = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    disagreement = sum(w[i][j] * observed[i][j] for i in range(k) for j in range(k))
    chance = sum(w[i][j] * px[i] * py[j] for i in range(k) for j in range(k))
    return None if chance == 0 else 1 - disagreement / chance


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


def report(rows):
    """Markdown: people against each automated scorer, and reviewers against each other."""
    by = defaultdict(dict)  # (criterion, scorer or "people") -> {answer_id: [rows]}
    for r in rows:
        key = (r["criterion"], "people" if r["scorer_kind"] == "person" else r["scorer"])
        by[key].setdefault(r["answer_id"], []).append(r)
    lines = ["| Criterion | People against | n answers | Agreement | People mean (0-1) | Scorer mean (0-1) |",
             "|---|---|---|---|---|---|"]
    automated = sorted({k for k in by if k[1] != "people"})
    for criterion, scorer in automated:
        people, other = by.get((criterion, "people"), {}), by[(criterion, scorer)]
        common = sorted(set(people) & set(other))
        if not common:
            continue
        if criterion == "decision":
            agree = [sum(p["score"] == other[a][0]["score"] for p in people[a]) / len(people[a]) for a in common]
            lines.append(f"| decision | {scorer} | {len(common)} | {fmt(statistics.mean(agree))} same decision | – | – |")
            continue
        xs = [statistics.mean(unit(p) for p in people[a]) for a in common]
        ys = [unit(other[a][0]) for a in common]
        lines.append(f"| {criterion} | {scorer} | {len(common)} | {fmt(spearman(xs, ys))} Spearman | "
                     f"{fmt(statistics.mean(xs))} | {fmt(statistics.mean(ys))} |")
    lines += ["", "| Criterion | Reviewers | n answers | Weighted kappa | Exact | Within 1 |", "|---|---|---|---|---|---|"]
    for criterion in criteria.REVIEW:
        scored = defaultdict(dict)
        for answer, rs in by.get((criterion, "people"), {}).items():
            for r in rs:
                scored[r["scorer"]][answer] = r["score"]
        for a, b in combinations(sorted(scored), 2):
            common = sorted(set(scored[a]) & set(scored[b]))
            xs, ys = [scored[a][i] for i in common], [scored[b][i] for i in common]
            if not common:
                continue
            exact = sum(x == y for x, y in zip(xs, ys)) / len(xs)
            near = sum(abs(x - y) <= 1 for x, y in zip(xs, ys)) / len(xs)
            lines.append(f"| {criterion} | {a} / {b} | {len(common)} | {fmt(weighted_kappa(xs, ys, *SCALE))} | "
                         f"{fmt(exact)} | {fmt(near)} |")
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
    rows += [r for r in written(out.parent, skip=out) if r["answer_id"] in ids]
    print(report(rows))
    print(f"\n{len(rows)} score rows ({out} and the other files of {out.parent} for these answers)")


if __name__ == "__main__":
    main()
