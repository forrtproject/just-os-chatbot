"""LLM judge for the shared criteria (#54): correctness, completeness, source relevance and clarity.

    docker compose run --rm -T -v "$PWD/data/scores:/app/data/scores" web \\
        python eval/criteria_judge.py data/answers/answers_X.jsonl [--model google/gemini-3.8-flash]

For each answered record of the answer store (eval/answers.py), one call scores the criteria listed under
judges.criteria in config/criteria.json, on the shared scale, with the definitions people see on /review;
the prompt is the file named there (config/prompts/criteria_judge.txt). Citation support
has its own judge (eval/judge.py) and rubric items theirs (eval/rubric_judge.py). Writes score rows
(eval/scores.py) to data/scores/scores_criteria-judge_<store file>_<model>.jsonl. Check about 20 results by
hand before you trust the numbers; people's scores on the same answers are the check (eval/scores.py).
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_grading_page import shown_answer  # noqa: E402  same folder
from glossary_items import parse_json  # noqa: E402  same folder
from scores import SCALE, row  # noqa: E402  same folder

from config.settings import get_config  # noqa: E402
from just_os import criteria  # noqa: E402
from just_os.qualle import OpenAIClientManager  # noqa: E402

SCORER = "criteria judge"

CONFIG = criteria.JUDGES["criteria"]
JUDGED = CONFIG["criteria"]
PROMPT = (Path(__file__).resolve().parent.parent / CONFIG["prompt"]).read_text(encoding="utf-8")


def plain(text):
    """The answer's text without HTML tags (the arena and the chat store HTML). Only tag-shaped text
    goes, so "p < 0.05 and r > 0.3" stays."""
    return unescape(re.sub(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>", " ", text)).strip()


def default_out(store, model):
    """data/scores/scores_criteria-judge_<store>_<model>.jsonl: one file per judge model, so a second
    model does not overwrite the first one's rows."""
    stem = Path(store).stem.removeprefix("answers_")
    return Path(f"data/scores/scores_criteria-judge_{stem}_{model.replace('/', '__')}.jsonl")


def prompt(record, limit=800):
    sources = "\n".join(
        f"[{s.get('n')}] {s.get('title', '')} {s.get('doi') or s.get('url') or ''}\n    {(s.get('passage') or '')[:limit]}"
        for s in record["sources"]) or "(none)"
    return PROMPT.format(
        low=SCALE[0], high=SCALE[1],
        labels=", ".join(f"{k} {v}" for k, v in criteria.SCALE_LABELS.items()),
        criteria="\n".join(f"- {key}: {criteria.CRITERIA[key]}" for key in JUDGED),
        question=record["question"], answer=plain(shown_answer(record["answer"])), sources=sources,
        keys=", ".join(f'"{k}": <{SCALE[0]}-{SCALE[1]}>' for k in JUDGED))


def judge(manager, model, record, cost):
    """{criterion: score} for one answer, or None when the judge fails."""
    try:
        response = manager.client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt(record)}], temperature=0.0,
            response_format={"type": "json_object"}, extra_body={"usage": {"include": True}})
        cost[0] += getattr(response.usage, "cost", 0) or 0
        scores = parse_json(response.choices[0].message.content)["scores"]
        return {k: min(max(int(scores[k]), SCALE[0]), SCALE[1]) for k in JUDGED}
    except Exception as e:  # noqa: BLE001  a failed judgement leaves no rows, the run goes on
        print(f"judge failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("store", help="data/answers/answers_X.jsonl")
    parser.add_argument("--model", default=CONFIG["model"], help="judge model (default from config/criteria.json)")
    parser.add_argument("--out", help="default data/scores/scores_criteria-judge_<store>_<model>.jsonl")
    args = parser.parse_args()
    records = [json.loads(line) for line in open(args.store, encoding="utf-8")]
    manager, cost, rows = OpenAIClientManager(get_config()), [0.0], []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in records:
        if r["outcome"] != "answered" or not r["answer"]:
            continue
        scores = judge(manager, args.model, r, cost)
        if scores:
            rows += [row(r["answer_id"], r["question_id"], k, v, SCALE, "llm", f"{SCORER} ({args.model})", now)
                     for k, v in scores.items()]
        print(f"{r['answer_id']:40} {scores}")
    out = Path(args.out) if args.out else default_out(args.store, args.model)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(f"{len(rows)} score rows -> {out} (judge: {args.model}, cost ${cost[0]:.4f})")


if __name__ == "__main__":
    main()
