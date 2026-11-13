"""Compare an expert's grades from the grading page with the generators' choices and the LLM judge.

    python eval/grading_report.py --key DIR/grading_key.csv \
        --part1 grading_part1_X.csv --part2 grading_part2_X.csv [--runs eval/results]

Part 1, per generator: share of questions the expert finds good, share of rubric items
essential, nice to have or not needed, share not in the definition, and how often the
generator's core/detail label matches the expert (core = essential, detail = nice to have).

Part 2: the expert's 1-5 scores against the judge's (rubric_scores in
eval/results/glossary_<generator>_<mode>.csv): exact and within-one agreement per
rubric item, the correlation of answer coverage, and mean coverage with and without the
library by both. Without --part2 rows, it still prints the judge's coverage per
generator and condition.
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def share(rows, field, value):
    return f"{sum(r[field] == value for r in rows) / len(rows):.2f}" if rows else "-"


def part1_report(key, rows):
    by_gen = defaultdict(list)
    for r in rows:
        by_gen[key[r["key"]]["generator"]].append(r)
    print("Part 1: items (per generator)")
    print(f"{'generator':32} {'questions ok':>12} {'essential':>9} {'nice':>6} {'not':>6} {'not in def':>10} {'label match':>11}")
    for gen, rs in sorted(by_gen.items()):
        questions = list({r["key"]: r for r in rs}.values())
        rated = [r for r in rs if r["need"]]
        match = [r for r in rated if r["need"] != "not"]
        label = sum((r["generator_type"] == "core") == (r["need"] == "essential") for r in match) / len(match) if match else 0
        print(f"{gen:32} {share(questions, 'question_ok', 'yes'):>12} {share(rated, 'need', 'essential'):>9} "
              f"{share(rated, 'need', 'nice'):>6} {share(rated, 'need', 'not'):>6} "
              f"{share(rated, 'not_in_definition', '1'):>10} {label:>11.2f}")


def judge_scores(runs, generator, mode):
    path = Path(runs) / f"glossary_{generator.replace('/', '__')}_{mode}.csv"
    return {r["id"]: json.loads(r["rubric_scores"]) for r in read(path) if r.get("rubric_scores")}


def part2_report(key, rows, runs):
    expert = defaultdict(dict)
    for r in rows:
        if r["score"] != "":
            expert[r["key"]][r["rubric_id"]] = int(r["score"])
    pairs, coverage, by_mode = [], [], defaultdict(lambda: ([], []))
    cache = {}
    for k, scores in expert.items():
        info = key[k]
        judged = cache.setdefault((info["generator"], info["condition"]),
                                  judge_scores(runs, info["generator"], info["condition"])).get(info["item"])
        if not judged or set(scores) != set(judged):
            continue
        pairs += [(scores[i], judged[i]) for i in scores]
        e, j = (sum(scores.values()) - len(scores)) / (4 * len(scores)), (sum(judged.values()) - len(judged)) / (4 * len(judged))
        coverage.append((e, j))
        by_mode[info["condition"]][0].append(e)
        by_mode[info["condition"]][1].append(j)
    print(f"\nPart 2: expert against judge, {len(coverage)} answers, {len(pairs)} rubric items")
    if not pairs:
        return
    print(f"exact agreement {sum(a == b for a, b in pairs) / len(pairs):.2f}, "
          f"within one {sum(abs(a - b) <= 1 for a, b in pairs) / len(pairs):.2f}, "
          f"judge minus expert {statistics.mean(b - a for a, b in pairs):+.2f} points")
    if len(coverage) > 2:
        print(f"coverage correlation (Pearson) {statistics.correlation(*zip(*coverage)):.2f}")
    for mode, (e, j) in sorted(by_mode.items()):
        print(f"{mode:12} expert {statistics.mean(e):.3f}  judge {statistics.mean(j):.3f}  (n={len(e)})")


def judge_overview(generators, runs):
    print("\nJudge coverage over all answered items")
    for gen in generators:
        for mode in ("library", "noretrieval"):
            path = Path(runs) / f"glossary_{gen.replace('/', '__')}_{mode}.csv"
            if path.exists():
                values = [float(r["rubric_coverage"]) for r in read(path) if r.get("rubric_coverage")]
                if values:
                    print(f"{gen:32} {mode:12} {statistics.mean(values):.3f} (n={len(values)})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--part1")
    parser.add_argument("--part2")
    parser.add_argument("--runs", default="eval/results")
    args = parser.parse_args()
    key = {r["key"]: r for r in read(args.key)}
    if args.part1:
        part1_report(key, read(args.part1))
    if args.part2:
        part2_report(key, read(args.part2), args.runs)
    judge_overview(sorted({r["generator"] for r in key.values()}), args.runs)


if __name__ == "__main__":
    main()
