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
    # as text, so a count in a column with empty cells stays 1 and does not become 1.0
    df = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in files]).drop_duplicates("id", keep="last")
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
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="a setting for this run's containers only, e.g. RERANK=true (the live bot keeps its own)")
    parser.add_argument("--route", choices=["open_science", "forrt"],
                        help="every question one way (eval/pairs.py); files are run_*_<model>__route-<route>.csv")
    args = parser.parse_args()
    lines = read_questions(args.questions)
    order = [json.loads(line)["id"] for line in lines]

    for model in args.models:
        route = ["--route", args.route] if args.route else []
        label = f"{model}__route-{args.route}" if args.route else model
        run_all(label, ["--model", model, "--general-model", args.general_model, *route], args.since, lines, order,
                dict(kv.split("=", 1) for kv in args.set))


def read_questions(files):
    """The question lines of one file or of several, comma-separated (eval/questions.jsonl,eval/forrt_questions.jsonl)."""
    return [line.rstrip("\n") + "\n"
            for f in files.split(",") for line in open(ROOT / f, encoding="utf-8") if line.strip()]


def run_all(label, run_args, since, lines, order, env=None):
    """Run eval/run.py in batches until every question has a row in run_*_<label>.csv files made since
    `since`, then merge them. env: settings for this run, passed to the container (eval/scorecard.py)."""
    settings = [x for key, value in (env or {}).items() for x in ("-e", f"{key}={value}")]
    tmp = TMP.with_name(f"tmp_batch_{label.replace('/', '__')}.jsonl")  # one per run, so runs can go in parallel
    while True:
        files = run_files(label, since)
        todo = [line for line, i in zip(lines, order) if i not in done_ids(files)]
        if not todo:
            break
        print(f"{label}: {len(order) - len(todo)}/{len(order)} done, next {min(BATCH, len(todo))}", flush=True)
        tmp.write_text("".join(todo[:BATCH]), encoding="utf-8")
        out = f"eval/results/run_{datetime.now():%y%m%d-%H%M}_{label.replace('/', '__')}.csv"
        subprocess.run(
            ["docker", "compose", "run", "--rm", "-T", "-e", "OMP_NUM_THREADS=8", *settings, "web", "python",
             "eval/run.py", *run_args, "--cache-retrieval", "--questions", tmp.relative_to(ROOT).as_posix(), "--out", out],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if len(done_ids(run_files(label, since))) == len(order) - len(todo):
            raise SystemExit(f"{label}: the batch finished no question; stopping")
    tmp.unlink(missing_ok=True)
    merged = merge(run_files(label, since), order)
    print(f"{label}: complete -> {merged.name}", flush=True)
    return merged


if __name__ == "__main__":
    main()
