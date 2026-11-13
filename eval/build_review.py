"""Data for the human review page /review (#8): what was asked, what the bot did, and where it got it.

    python eval/build_review.py eval/results/human_review_X.csv --questions eval/human_review_questions.jsonl
        [--out eval/human_review_items.json]

One item per question of the run: its category, what the bot should have done and did, the answer as
the bot wrote it (with its [n] citations), and every source the bot read, numbered as the answer cites
them, with its title, DOI or URL, the passage or page text, and whether the answer cites it. The LLM
judge's score is left out, so reviewers score blind. Reviewers save their scores from the page into
REVIEW_DIR (data/reviews/).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_sheet import bot_did, source_items  # noqa: E402  same folder


def items(run_csv, questions):
    categories = {q["id"]: q.get("category", "") for q in questions}
    out = []
    for row in csv.DictReader(open(run_csv, encoding="utf-8")):
        sources = []
        for s in source_items(row):
            link = f"https://doi.org/{s['doi']}" if s["doi"] else s["url"]
            sources.append({"n": s["n"], "title": s["title"] or "untitled", "doi": s["doi"], "link": link,
                            "passage": " ".join(s["passage"].split()), "cited": s["cited"]})
        out.append({"id": row["id"], "category": categories.get(row["id"], row.get("route", "")), "question": row["question"],
                    "expected": row["expect"], "bot_did": bot_did(row), "answered_from": row.get("answered_from", ""),
                    "answer": (row.get("answer") or "").strip(), "sources": sources})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv", type=Path)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--out", type=Path, default=Path("eval/human_review_items.json"))
    args = parser.parse_args()
    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    data = items(args.run_csv, questions)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}: {len(data)} questions")


if __name__ == "__main__":
    main()
