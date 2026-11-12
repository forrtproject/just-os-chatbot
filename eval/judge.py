"""LLM judge (issue E2, #8): do the cited sources support the answer?

    docker compose exec web python eval/judge.py eval/results/run_X.csv [--model openai/gpt-oss-20b]

For each answered row of a run CSV (made by eval/run.py, which saves the passages the
answer model saw), a judge model returns the share of cited sentences that their source
supports (0-1). The column judge_support is added to the same CSV; eval/compare.py shows
its mean. Check about 20 judge results by hand before you trust the numbers.
"""

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402
from just_os.qualle import OpenAIClientManager, QueryProcessor  # noqa: E402

PROMPT = """You check the citations of an answer. The sources are numbered from 0.
For every sentence of the answer that cites a source, such as [2], decide whether that
source supports what the sentence says.

Sources:
{sources}

Answer:
{answer}

Return a JSON object with a single number entry "supported_share": the share (0 to 1) of
cited sentences that their source supports. Use 0 if no sentence cites a source."""


def judge_row(processor: QueryProcessor, row: dict):
    """judge_support for one row, or "" when there is nothing to judge or the judge fails."""
    passages = json.loads(row.get("passages") or "[]")
    if row.get("outcome") != "answered" or not passages or not row.get("answer"):
        return ""
    sources = "\n".join(f"[{i}] {text}" for i, text in enumerate(passages))
    value = processor._structured_output(PROMPT.format(sources=sources, answer=row["answer"]), "supported_share", "number")
    try:
        return round(min(max(float(value), 0.0), 1.0), 2)
    except (TypeError, ValueError):
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv")
    parser.add_argument("--model", default="openai/gpt-oss-20b", help="judge model (OpenRouter id)")
    args = parser.parse_args()

    config = {**get_config(), "GENERAL_MODEL": args.model, "TEMPERATURE_GENERAL": 0.0}
    processor = QueryProcessor(OpenAIClientManager(config), config, chat_manager=None)
    rows = list(csv.DictReader(open(args.run_csv, encoding="utf-8")))
    if rows and "passages" not in rows[0]:
        sys.exit("This run has no passages column: run eval/run.py again (it saves them since Nov 2026).")
    # 8 at a time: the judge is an API call, and a full run has ~170 answers
    with ThreadPoolExecutor(8) as pool:
        for row, score in zip(rows, pool.map(lambda r: judge_row(processor, r), rows)):
            row["judge_support"] = score
            print(f"{row['id']:6} {score}", flush=True)
    fields = list(rows[0].keys()) if rows else []
    with open(args.run_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"judge_support added to {args.run_csv} (judge: {args.model})")


if __name__ == "__main__":
    main()
