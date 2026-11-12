"""Run eval/run.py for several answer models in batches, and resume after a stop.

Runs on the host. Each batch is a fresh `docker compose run` process with at most BATCH
questions: one long process grows past the Docker VM's memory (~47 questions in 7.6 GB).
run.py writes a row per finished question, so stopping loses only the question in progress.
On the next start, questions already in a model's run files (made since --since) are
skipped. When a model has every question, its files are merged into the first one.

    python eval/run_batches.py --since 261112-1246 openai/gpt-oss-20b qwen/qwen3-14b ...
"""

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval/results"
BATCH = 30
TMP = ROOT / "eval/tmp_batch.jsonl"


def run_files(model, since):
    """This model's run CSVs made at or after `since` (YYMMDD-HHMM), oldest first."""
    files = sorted(RESULTS.glob(f"run_*_{model.replace('/', '__')}.csv"))
    return [f for f in files if f.name[4:15] >= since and f.stat().st_size > 0]


def done_ids(files):
    return set().union(*(set(pd.read_csv(f)["id"]) for f in files)) if files else set()


def merge(files, order):
    """All rows into the first file (in question order); the other files are removed."""
    df = pd.concat([pd.read_csv(f) for f in files]).drop_duplicates("id", keep="last")
    df = df.set_index("id").loc[[i for i in order if i in set(df["id"])]].reset_index()
    df.to_csv(files[0], index=False)
    for f in files[1:]:
        f.unlink()
    return files[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--since", required=True, help="first run to count, YYMMDD-HHMM")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--general-model", default="meta-llama/llama-3.1-8b-instruct")
    args = parser.parse_args()
    lines = open(ROOT / args.questions, encoding="utf-8").readlines()
    order = [json.loads(line)["id"] for line in lines]

    for model in args.models:
        while True:
            files = run_files(model, args.since)
            todo = [line for line, i in zip(lines, order) if i not in done_ids(files)]
            if not todo:
                break
            print(f"{model}: {len(order) - len(todo)}/{len(order)} done, next {min(BATCH, len(todo))}", flush=True)
            TMP.write_text("".join(todo[:BATCH]), encoding="utf-8")
            subprocess.run(
                ["docker", "compose", "run", "--rm", "-T", "-e", "OMP_NUM_THREADS=8", "web", "python", "eval/run.py",
                 "--model", model, "--general-model", args.general_model, "--questions", TMP.relative_to(ROOT).as_posix()],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            if len(done_ids(run_files(model, args.since))) == len(order) - len(todo):
                raise SystemExit(f"{model}: the batch finished no question; stopping")
        print(f"{model}: complete -> {merge(run_files(model, args.since), order).name}", flush=True)
    TMP.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
