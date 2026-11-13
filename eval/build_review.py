"""Data for the human review page /review (#8, #54): what was asked, what the bot did, and where it got it.

    python eval/build_review.py data/answers/answers_X.jsonl [more stores or run CSVs]
        --questions eval/human_review_questions.jsonl [--out eval/human_review_items.json]

One item per stored answer (eval/answers.py; a run CSV is turned into answers first), so the same question
can be reviewed for several models or settings: its category, what the bot should have done and did, the
answer as the bot wrote it (with its [n] citations), every source the bot read, numbered as the answer
cites them, with its title, DOI or URL, the passage or page text and whether the answer cites it, and the
question's rubric when it has one (the page's rubric setting). Each item has an opaque `key` for the page;
the answer_id, which can name the model, stays in this file, so reviewers score blind, and no judge score
is included. Reviewers save score rows (just_os.scores) into SCORES_DIR (data/scores/).
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answers as store  # noqa: E402  same folder
from judge_sheet import bot_did  # noqa: E402  same folder


def key(answer_id: str) -> str:
    """A short id for the page that does not show the answer_id."""
    return hashlib.sha1(answer_id.encode("utf-8")).hexdigest()[:10]


def items(records, questions):
    by_id = {q["id"]: q for q in questions}
    out = []
    for r in records:
        q = by_id.get(r["question_id"], {})
        used = {int(n) for n in re.findall(r"\[(\d+)\]", r["answer"] or "")}
        sources = []
        for s in r["sources"]:
            link = f"https://doi.org/{s['doi']}" if s.get("doi") else s.get("url", "")
            sources.append({"n": s.get("n"), "title": s.get("title") or "untitled", "doi": s.get("doi", ""), "link": link,
                            "passage": " ".join((s.get("passage") or "").split()), "cited": s.get("n") in used})
        out.append({"key": key(r["answer_id"]), "answer_id": r["answer_id"], "id": r["question_id"],
                    "category": q.get("category") or q.get("cluster") or q.get("route", ""), "question": r["question"],
                    "expected": q.get("expect") or r.get("expect") or "answer", "bot_did": bot_did(r), "answered_from": r["answered_from"],
                    "answer": (r["answer"] or "").strip(), "sources": sources, "rubric": q.get("rubric", [])})
    return out


def load_records(paths):
    records = []
    for p in paths:
        records += store.from_run(p) if p.suffix == ".csv" else [json.loads(line) for line in open(p, encoding="utf-8")]
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("answers", type=Path, nargs="+", help="data/answers/answers_X.jsonl files or eval/run.py CSVs")
    parser.add_argument("--questions", required=True)
    parser.add_argument("--out", type=Path, default=Path("eval/human_review_items.json"))
    args = parser.parse_args()
    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    data = items(load_records(args.answers), questions)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}: {len(data)} answers")


if __name__ == "__main__":
    main()
