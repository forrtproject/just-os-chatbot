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
from datetime import datetime
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
        run_all(model, ["--model", model, "--general-model", args.general_model], args.since, lines, order)
    TMP.unlink(missing_ok=True)


def run_all(label, run_args, since, lines, order, env=None):
    """Run eval/run.py in batches until every question has a row in run_*_<label>.csv files made since
    `since`, then merge them. env: settings for this run, passed to the container (eval/scorecard.py)."""
    settings = [x for key, value in (env or {}).items() for x in ("-e", f"{key}={value}")]
    while True:
        files = run_files(label, since)
        todo = [line for line, i in zip(lines, order) if i not in done_ids(files)]
        if not todo:
            break
        print(f"{label}: {len(order) - len(todo)}/{len(order)} done, next {min(BATCH, len(todo))}", flush=True)
        TMP.write_text("".join(todo[:BATCH]), encoding="utf-8")
        out = f"eval/results/run_{datetime.now():%y%m%d-%H%M}_{label.replace('/', '__')}.csv"
        subprocess.run(
            ["docker", "compose", "run", "--rm", "-T", "-e", "OMP_NUM_THREADS=8", *settings, "web", "python",
             "eval/run.py", *run_args, "--questions", TMP.relative_to(ROOT).as_posix(), "--out", out],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if len(done_ids(run_files(label, since))) == len(order) - len(todo):
            raise SystemExit(f"{label}: the batch finished no question; stopping")
    merged = merge(run_files(label, since), order)
    print(f"{label}: complete -> {merged.name}", flush=True)
    return merged


if __name__ == "__main__":
    main()
