"""Rubric judge for questions with a rubric (the FORRT glossary items): how much of it does an answer cover?

    docker compose exec web python eval/rubric_judge.py eval/results/run_X.csv \
        [--items eval/questions.jsonl] [--model google/gemini-3.8-flash]

For each answered row whose question has a rubric in --items, a judge model scores every
rubric item from 1 (not covered) to 5 (fully covered): the five levels of ResearchQA's 0-4 on the
1-5 scale every score uses (config/criteria.json, #54). Columns
added to the run CSV (empty for questions without a rubric):
- rubric_coverage: mean of (score - 1) / 4 over all items (0-1, the same value as ResearchQA's score / 4)
- rubric_core: the same over the "core" items only
- rubric_scores: the scores per item id, as JSON
- doi_recall: share of the item's expected_dois among the sources the answer cites
  (from the [n] markers and retrieved_dois; empty for runs without sources)
--controls also scores each item's reference answer (should be near 1) and the
reference answer of another item (should be near 0), to check the judge itself.
Check about 20 judge results by hand before you trust the numbers.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_grading_page import shown_answer  # noqa: E402  same folder
from glossary_items import parse_json  # noqa: E402  same folder

from config.settings import get_config  # noqa: E402
from just_os import criteria  # noqa: E402
from just_os.qualle import OpenAIClientManager  # noqa: E402

PROMPT = """You grade an answer against a rubric. For each rubric item, decide how fully the
answer covers it, whatever the language of the answer:
{levels}.
Judge only what the answer says; citation markers such as [2] do not matter.

Question: {question}

Answer:
{answer}

Rubric:
{rubric}

Return a JSON object {{"scores": {{"<item id>": <{low}-{high}>, ...}}}} with one entry per item."""
LEVELS = ", ".join(f"{k} {v}" for k, v in criteria.RUBRIC_LEVELS.items())


def judge(manager, model, question, answer, rubric, cost):
    """Scores per rubric item id (1-5), or None when the judge fails."""
    items = "\n".join(f"{r['id']}: {r['criterion']}" for r in rubric)
    try:
        response = manager.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT.format(question=question, answer=answer, rubric=items, levels=LEVELS,
                                                                    low=criteria.SCALE[0], high=criteria.SCALE[-1])}],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_body={"usage": {"include": True}},
        )
        cost[0] += getattr(response.usage, "cost", 0) or 0
        scores = parse_json(response.choices[0].message.content)["scores"]
        return {r["id"]: min(max(int(scores[r["id"]]), criteria.SCALE[0]), criteria.SCALE[-1]) for r in rubric}
    except Exception as e:  # noqa: BLE001  a failed judgement leaves the row empty, the run goes on
        print(f"judge failed: {e}")
        return None


def coverage(scores, rubric, kind=None):
    ids = [r["id"] for r in rubric if kind in (None, r["type"])]
    return round(sum(scores[i] - criteria.SCALE[0] for i in ids) / ((criteria.SCALE[-1] - criteria.SCALE[0]) * len(ids)), 3) if ids else ""


def doi_recall(row, item):
    """Share of expected DOIs among the cited sources; the model sees sources numbered from 0."""
    retrieved = row.get("retrieved_dois", "").split()
    if not retrieved or not item.get("expected_dois"):
        return ""
    cited = {retrieved[int(n)] for n in re.findall(r"\[(\d+)\]", row.get("answer", "")) if int(n) < len(retrieved)}
    return round(sum(d in cited for d in item["expected_dois"]) / len(item["expected_dois"]), 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv")
    parser.add_argument("--items", default="eval/questions.jsonl", help="questions; only those with a rubric are judged")
    # A judge from a family that generated none of the items (gpt-4.1-mini, Claude, Qwen)
    parser.add_argument("--model", default=criteria.JUDGES["rubric"]["model"], help="judge model (default from config/criteria.json)")
    parser.add_argument("--controls", action="store_true", help="also score reference answers")
    args = parser.parse_args()

    with open(args.items, encoding="utf-8") as f:
        items = {i["id"]: i for i in map(json.loads, f) if i.get("rubric")}
    manager = OpenAIClientManager(get_config())
    cost = [0.0]
    with open(args.run_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        item = items.get(row["id"])
        row.update(rubric_coverage="", rubric_core="", rubric_scores="", doi_recall="")
        if not item:  # a question without a rubric
            continue
        if row.get("outcome") != "answered" or not row.get("answer"):
            print(f"{row['id']:7} skipped ({row.get('outcome')})")
            continue
        # the answer as the app shows it, without passages the model echoed after [Response_End]
        scores = judge(manager, args.model, row["question"], shown_answer(row["answer"]), item["rubric"], cost)
        if scores:
            row.update(rubric_coverage=coverage(scores, item["rubric"]), rubric_core=coverage(scores, item["rubric"], "core"),
                       rubric_scores=json.dumps(scores))
        row["doi_recall"] = doi_recall(row, item)
        print(f"{row['id']:7} coverage {row['rubric_coverage']} core {row['rubric_core']} doi {row['doi_recall']}")
    fields = list(rows[0].keys()) if rows else []
    with open(args.run_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    if args.controls:
        english = [i for i in items.values() if i["lang"] == "en"]
        own, other = [], []
        for n, item in enumerate(english):
            wrong = english[(n + 1) % len(english)]
            for answer, out in ((item["reference_answer"], own), (wrong["reference_answer"], other)):
                scores = judge(manager, args.model, item["question"], answer, item["rubric"], cost)
                if scores:
                    out.append(coverage(scores, item["rubric"]))
        print(f"controls: own reference answer {sum(own) / len(own):.3f} (n={len(own)}), "
              f"another item's answer {sum(other) / len(other):.3f} (n={len(other)})")
    print(f"rubric columns added to {args.run_csv} (judge: {args.model}), cost ${cost[0]:.4f}")


if __name__ == "__main__":
    main()
