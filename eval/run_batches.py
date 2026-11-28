"""Run eval/run.py for several answer models in batches, and resume after a stop.

Runs on the host. Each batch is a fresh `docker compose run` process with at most BATCH
questions: one long process grows past the Docker VM's memory (~47 questions in 7.6 GB).
run.py writes a row per finished question, so stopping loses only the question in progress.
A run series is one label (model, cfg-<name>, with __route-<route>) and one --since. Its manifest
(eval/results/batch_<label>__since-<since>.json, not in git) records its questions, run.py arguments and
settings (a value whose key may name a credential only as a hash) and the exact run files its batches wrote.
On the next start with the same --since, questions already in those files are skipped; a resume with other
questions or settings stops instead of mixing two setups. When every question has a row, the series' files
are merged into its first one. Other files, even with the same label, are never counted, merged or removed.

    python eval/run_batches.py --since 261112-1246 openai/gpt-oss-20b qwen/qwen3-14b ...
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.settings import DEFAULT_CONFIG  # noqa: E402
RESULTS = ROOT / "eval/results"
ENV_FILE = ROOT / ".env"
BATCH = 30
TMP = ROOT / "eval/tmp_batch.jsonl"


STAMP = re.compile(r"run_(\d{6}-\d{4})(\d{2})?_")
# --set values of these keys are credentials (or may be): the manifest keeps a hash, never the value
SECRET_KEY = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL", re.IGNORECASE)


def run_stamp(path) -> str:
    """A run file's time as YYMMDD-HHMMSS, for sorting files named before (YYMMDD-HHMM) and after (with
    seconds, so two batches in one minute get two files) Nov 2026 alike; "" for another name."""
    m = STAMP.match(Path(path).name)
    return f"{m.group(1)}{m.group(2) or '00'}" if m else ""


def slug(label) -> str:
    return label.replace("/", "__")


def run_files(label, since):
    """Run CSVs of exactly this label (run_<stamp>_<label>.csv: not cfg-<name>__<label> nor <label>__route-...)
    made at or after `since` (YYMMDD-HHMM or YYMMDD-HHMMSS), oldest first."""
    name = re.compile(rf"run_\d{{6}}-\d{{4}}(\d{{2}})?_{re.escape(slug(label))}\.csv")
    files = sorted((f for f in RESULTS.glob("run_*.csv") if name.fullmatch(f.name)), key=run_stamp)
    return [f for f in files if run_stamp(f) >= since.ljust(13, "0") and f.stat().st_size > 0]


def manifest_path(label, since):
    return RESULTS / f"batch_{slug(label)}__since-{since}.json"


def recorded_settings(env):
    """The settings as the manifest keeps them: a key that may name a credential (SECRET_KEY) gets a hash of its
    value, so a resume still notices a changed value (MAX_ANSWER_TOKENS) and no secret is written to disk."""
    return {k: (f"sha256:{hashlib.sha256(str(v).encode('utf-8')).hexdigest()[:16]}" if SECRET_KEY.search(k) else str(v))
            for k, v in (env or {}).items()}


def save_manifest(label, since, manifest):
    path = manifest_path(label, since)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    tmp.replace(path)


def effective_settings(env):
    """Effective container settings: .env values overlaid with explicit --set overrides, with secrets hashed."""
    merged = {}
    if ENV_FILE.exists():
        for k, v in dotenv_values(ENV_FILE).items():
            if v not in (None, ""):
                merged[k] = v
    for k, v in (env or {}).items():
        merged[k] = v
    return recorded_settings(merged)


def open_series(label, since, lines, run_args, env):
    """The manifest of this series (label, since): new, or the recorded one when its questions, run.py arguments
    and settings (including .env) are the same; other ones stop the run. Same-label run files the series did not
    write are named and left alone."""
    identity = {"label": label, "since": since, "questions": hashlib.sha256("".join(lines).encode("utf-8")).hexdigest(),
                "run_args": list(run_args), "settings": effective_settings(env)}
    path = manifest_path(label, since)
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        changed = [k for k in ("questions", "run_args", "settings") if manifest.get(k) != identity[k]]
        if changed:
            raise SystemExit(f"{label}: the series since {since} was run with other {', '.join(changed)} ({path.name}); "
                             f"start a new series (--since now) or use the same setup")
    else:
        manifest = {**identity, "files": []}
        save_manifest(label, since, manifest)
    unlisted = [f.name for f in run_files(label, since) if f.name not in manifest["files"]]
    if unlisted:
        print(f"{label}: not counted, merged or removed (not written by this series, {path.name}): "
              f"{', '.join(unlisted)}", flush=True)
    return manifest


def series_files(manifest, order):
    """The run files this series wrote that exist, oldest first; a file with a question the series does not ask
    stops the run (it cannot be this series' batch)."""
    files = [RESULTS / name for name in manifest["files"]]
    files = sorted((f for f in files if f.exists() and f.stat().st_size > 0), key=run_stamp)
    asked = {str(i) for i in order}
    for f in files:
        extra = set(pd.read_csv(f, dtype=str, keep_default_na=False)["id"]) - asked
        if extra:
            raise SystemExit(f"{f.name}: rows for questions this series does not ask ({', '.join(sorted(extra)[:5])})")
    return files


def done_ids(files):
    """The question ids with a row, as text (a questions file may give numbers)."""
    return set().union(*(set(pd.read_csv(f, dtype=str, keep_default_na=False)["id"]) for f in files)) if files else set()


def merge(files, order):
    """All rows into the first file (in question order); the other files are removed."""
    # as text, so a count in a column with empty cells stays 1 and does not become 1.0
    df = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in files]).drop_duplicates("id", keep="last")
    order = [str(i) for i in order]  # the ids are read as text above; a questions file may give numbers
    df = df.set_index("id").loc[[i for i in order if i in set(df["id"])]].reset_index()
    df.to_csv(files[0], index=False)
    for f in files[1:]:
        f.unlink()
    return files[0]


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--since", required=True, help="first run to count, YYMMDD-HHMM")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--general-model", default=DEFAULT_CONFIG["GENERAL_MODEL"],
                        help="classify/rephrase model (default: GENERAL_MODEL of config/settings.py)")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="a setting for this run's containers only, e.g. RERANK=true (the live bot keeps its own)")
    parser.add_argument("--route", choices=["open_science", "forrt"],
                        help="every question one way (eval/pairs.py); files are run_*_<model>__route-<route>.csv")
    return parser


def main():
    args = build_parser().parse_args()
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
    """Run eval/run.py in batches until every question has a row in this series' run files (label, since; the
    manifest lists them), then merge them. env: settings for this run, passed to the container
    (eval/scorecard.py)."""
    settings = [x for key, value in (env or {}).items() for x in ("-e", f"{key}={value}")]
    tmp = TMP.with_name(f"tmp_batch_{slug(label)}__since-{since}.jsonl")  # one per series, safe for concurrent runs
    manifest = open_series(label, since, lines, run_args, env)
    while True:
        done = done_ids(series_files(manifest, order))
        todo = [line for line, i in zip(lines, order) if str(i) not in done]
        if not todo:
            break
        print(f"{label}: {len(order) - len(todo)}/{len(order)} done, next {min(BATCH, len(todo))}", flush=True)
        tmp.write_text("".join(todo[:BATCH]), encoding="utf-8")
        out = batch_out(label, manifest)
        manifest["files"].append(out.name)  # before the batch: a stopped batch's rows still belong to the series
        save_manifest(label, since, manifest)
        subprocess.run(
            ["docker", "compose", "run", "--rm", "-T", "-e", "OMP_NUM_THREADS=8", *settings, "web", "python",
             "eval/run.py", *run_args, "--cache-retrieval", "--questions", relative(tmp), "--out", relative(out)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if len(done_ids(series_files(manifest, order))) == len(order) - len(todo):
            if out.exists() and out.stat().st_size == 0:
                out.unlink(missing_ok=True)
                manifest["files"] = [n for n in manifest["files"] if n != out.name]
                save_manifest(label, since, manifest)
            raise SystemExit(f"{label}: the batch finished no question; stopping")
    tmp.unlink(missing_ok=True)
    merged = merge(series_files(manifest, order), order)
    manifest["files"] = [merged.name]
    save_manifest(label, since, manifest)
    print(f"{label}: complete -> {merged.name}", flush=True)
    return merged


def batch_out(label, manifest):
    """Atomically reserve a new run file for the next batch via exclusive create ('x'), so concurrent series with
    the same label can never claim the same output CSV."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    while True:
        out = RESULTS / f"run_{datetime.now():%y%m%d-%H%M%S}_{slug(label)}.csv"
        if out.name not in manifest["files"]:
            try:
                with open(out, "x", encoding="utf-8"):
                    pass
                return out
            except FileExistsError:
                pass
        time.sleep(1)


def relative(path) -> str:
    """A path as the container sees it (relative to the repository), or as it is outside the repository."""
    path = Path(path)
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


if __name__ == "__main__":
    main()
