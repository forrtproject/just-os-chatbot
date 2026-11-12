"""E4 (#32): run named configurations with one command each, judge them, and print the scorecard.

Runs on the host, like eval/run_batches.py (batches in fresh containers, resumable):

    python eval/scorecard.py router-jev                 # run, judge, print the table
    python eval/scorecard.py baseline no-rerank --limit 10
    python eval/scorecard.py --table                    # only the table of the latest run per configuration

A configuration is a name in eval/configs.json with the settings (config/settings.py keys) that
differ from .env, for example {"ROUTER": "jev", "CITATION_MODEL": "openai/gpt-oss-20b"} for a
topic check + answer model pair. The run files are eval/results/run_<YYMMDD-HHMM>_cfg-<name>.csv;
after a stop, the same command with --since <YYMMDD-HHMM of the first batch> resumes.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare  # noqa: E402
import run_batches  # noqa: E402

ROOT = run_batches.ROOT
CONFIGS = ROOT / "eval/configs.json"


def label(name: str) -> str:
    return f"cfg-{name}"


def latest_runs(names):
    """The newest run file of each configuration that has one."""
    paths = []
    for name in names:
        files = sorted(run_batches.RESULTS.glob(f"run_*_{label(name)}.csv"))
        if files:
            paths.append(files[-1])
    return paths


def main():
    configs = json.loads(CONFIGS.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help=f"configurations in eval/configs.json: {', '.join(configs)}")
    parser.add_argument("--since", default=f"{datetime.now():%y%m%d-%H%M}", help="resume runs made since YYMMDD-HHMM")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--no-judge", action="store_true", help="skip eval/judge.py")
    parser.add_argument("--table", action="store_true", help="only print the table")
    args = parser.parse_args()
    unknown = [n for n in args.names if n not in configs]
    if unknown:
        raise SystemExit(f"not in {CONFIGS.name}: {', '.join(unknown)}")

    lines = open(ROOT / args.questions, encoding="utf-8").readlines()[: args.limit]
    order = [json.loads(line)["id"] for line in lines]
    for name in [] if args.table else args.names:
        path = run_batches.run_all(label(name), [], args.since, lines, order, configs[name])
        if not args.no_judge:
            subprocess.run(["docker", "compose", "run", "--rm", "-T", "web", "python", "eval/judge.py",
                            path.relative_to(ROOT).as_posix()], cwd=ROOT, check=False)
    run_batches.TMP.unlink(missing_ok=True)
    print(compare.summarize(latest_runs(args.names or configs)))


if __name__ == "__main__":
    main()
