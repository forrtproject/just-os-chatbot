"""Numbers for the /eval page, read from the CSVs in EVAL_RESULTS_DIR (eval/results):

    run_<YYMMDD-HHMM>_<model>.csv   eval/run.py: one row per question, full pipeline
      ..._<model>__route-<route>.csv  every question forced to the papers or the FORRT pages (eval/pairs.py)
      ..._cfg-<name>[...].csv         a named configuration of eval/configs.json (eval/scorecard.py)
    pairs_<YYMMDD-HHMM>.csv         eval/pairs.py: one row per topic check x answer model
    classify_<YYMMDD-HHMM>.csv      eval/classify.py: model, id, gold, predicted, seconds, usd (gold decline_task: scored apart)
    embeddings_<YYMMDD>.csv         eval/compare_embeddings.py: one row per model and language

A missing folder or file gives empty tables (the production image has no eval/ folder).

people_and_judges reads score rows (data/scores) and the answer store (data/answers) instead (#54).
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional

# A classifier "refuses" with these labels (classify_query: off_topic; router: neither)
REFUSE_LABELS = {"off_topic", "neither"}
TASK = "decline_task"  # gold label of an in-scope topic with a task the bot should decline (eval/classify.py)


def _rows(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mean(values: Iterable, digits: int = 2) -> Optional[float]:
    numbers = [float(v) for v in values if v not in ("", None)]
    return round(mean(numbers), digits) if numbers else None


def _p95(values: List[float]) -> float:
    values = sorted(values)
    return round(values[int(0.95 * (len(values) - 1))], 1)


KINDS = {None: "full pipeline", "open_science": "papers", "forrt": "FORRT pages"}


def run_label(name: str) -> Dict[str, str]:
    """What a run file holds: "openai__gpt-oss-20b__route-forrt" -> model openai/gpt-oss-20b, kind
    "FORRT pages"; "cfg-search-bm25__route-open_science" -> config search-bm25, kind "papers"."""
    base, _, route = name.partition("__route-")
    config = base.removeprefix("cfg-") if base.startswith("cfg-") else ""
    return {"model": config or base.replace("__", "/"), "kind": KINDS.get(route or None, route), "config": config}


def answer_runs(folder: str) -> List[Dict]:
    """One row per eval/run.py run, newest first."""
    out = []
    for path in sorted(Path(folder).glob("run_*.csv"), reverse=True):
        match = re.match(r"run_(\d{6}-\d{4})_(.+)\.csv$", path.name)
        rows = _rows(path) if match else []
        if not rows:
            continue
        answer = [r for r in rows if r["expect"] == "answer"]
        refuse = [r for r in rows if r["expect"] != "answer"]
        seconds = [float(r["seconds"]) for r in rows]
        out.append({
            "run": match.group(1),
            **run_label(match.group(2)),
            "n": len(rows),
            "correct": _mean(r["correct"] for r in rows),
            "answered": f"{sum(r['outcome'] == 'answered' for r in answer)}/{len(answer)}",
            "refused": f"{sum(r['outcome'] == 'refused' for r in refuse)}/{len(refuse)}",
            "errors": sum(r["outcome"] == "error" for r in rows),
            "no_sources": sum(r["outcome"] == "no_sources" for r in answer),
            "hit": _mean(r["hit"] for r in rows),
            "citations_valid": _mean(r["citations_valid"] for r in rows),
            "judge": _mean(r.get("judge_support") for r in rows),
            "rubric": _mean(r.get("rubric_coverage") for r in rows),
            "mean_s": round(mean(seconds), 1),
            "p95_s": _p95(seconds),
            # mean seconds per step (runs from 12 Nov on; older runs: None)
            **{k: _mean((r.get(k) for r in rows), 1) for k in ("classify_s", "search_s", "rerank_s", "answer_s")},
            "tokens": round(mean(int(r["prompt_tokens"] or 0) + int(r["completion_tokens"] or 0) for r in rows)),
            "usd_per_1k": round(mean(float(r["cost_usd"] or 0) for r in rows) * 1000, 3),
        })
    return out


def classifier_runs(folder: str) -> List[Dict]:
    """One row per model and eval/classify.py run, newest run first, best accuracy first."""
    out = []
    for path in sorted(Path(folder).glob("classify_*.csv"), reverse=True):
        out += classifier_runs_of(path)
    return out


def classifier_runs_of(path: Path) -> List[Dict]:
    """The rows of one eval/classify.py run, best accuracy first."""
    by_model: Dict[str, List[Dict[str, str]]] = {}
    for row in _rows(path):
        by_model.setdefault(row["model"], []).append(row)
    rows = []
    for model, timed in by_model.items():
        # tasks to decline leave the accuracy: a topic check cannot refuse them by design
        tasks = [r for r in timed if r["gold"] == TASK and r["predicted"]]  # a failed call is an error, not a decline
        items = [r for r in timed if r["gold"] != TASK]
        done = [r for r in items if r["predicted"]]
        rows.append({
            "run": path.stem.removeprefix("classify_"),
            "model": model,
            "n": len(items),
            "accuracy": round(sum(r["gold"] == r["predicted"] for r in items) / len(items), 2) if items else None,
            "tasks_let_through": f"{sum(r['predicted'] not in REFUSE_LABELS for r in tasks)}/{len(tasks)}" if tasks else "",
            "false_refusals": sum(r["gold"] not in REFUSE_LABELS and r["predicted"] in REFUSE_LABELS for r in done),
            "false_answers": sum(r["gold"] in REFUSE_LABELS and r["predicted"] not in REFUSE_LABELS for r in done),
            "errors": sum(not r["predicted"] for r in timed),
            "mean_s": _mean((r["seconds"] for r in timed), 1),
            "usd_per_1k": round(mean(float(r["usd"] or 0) for r in timed) * 1000, 3),
        })
    return sorted(rows, key=lambda r: -(r["accuracy"] or 0))


def by_model(runs: List[Dict], score: str) -> List[Dict]:
    """One row per model: its newest run (runs come newest first) plus how many runs it has,
    best `score` first. A newer pipeline can change a model's numbers, so the newest run is
    the fair one to compare; the run history keeps the rest."""
    latest: Dict[str, Dict] = {}
    for run in runs:
        if run["model"] in latest:
            latest[run["model"]]["runs"] += 1
        else:
            latest[run["model"]] = {**run, "runs": 1}
    return sorted(latest.values(), key=lambda r: -(r[score] or 0))


def embedding_runs(folder: str) -> List[Dict]:
    """The "all languages" row of each model in the newest embeddings_*.csv."""
    files = sorted(Path(folder).glob("embeddings_*.csv"))
    if not files:
        return []
    return [
        {"model": r["name"], "dim": r["dim"], "hit5": float(r["hit@5"]), "hit20": float(r["hit@20"]),
         "mrr20": float(r["mrr@20"]), "ms": round(float(r["ms_per_query"]))}
        for r in _rows(files[-1]) if r["lang"] == "all"
    ]


def pair_results(folder: str) -> Dict:
    """The newest eval/pairs.py table: rows best first, and a grid {answer model: {topic check: row}}."""
    files = sorted(Path(folder).glob("pairs_*.csv"))
    if not files:
        return {}
    rows = _rows(files[-1])
    if not rows:  # an empty table (no model had both runs) shows as "no pair table yet"
        return {}
    for r in rows:
        for key in ("correct", "hit", "citations_valid", "judge_support", "mean_s", "usd_per_1k"):
            r[key] = float(r[key]) if r[key] not in ("", None) else None
    grid: Dict[str, Dict[str, Dict]] = {}
    for r in rows:
        grid.setdefault(r["answer_model"], {})[r["topic_check"]] = r
    checks = sorted({r["topic_check"] for r in rows},
                    key=lambda c: -mean(r["correct"] or 0 for r in rows if r["topic_check"] == c))
    models = sorted(grid, key=lambda m: -max(r["correct"] or 0 for r in grid[m].values()))
    return {"run": files[-1].stem.removeprefix("pairs_"), "rows": rows, "grid": grid, "checks": checks, "models": models}


def score(run: Dict) -> Optional[float]:
    """The answer-model score: (2 x judge + rubric coverage) / 3, both 0-1. Citation support counts
    double: a cited sentence its source does not support misleads more than a missing point, and the
    judge covers ~160 answers per model while the rubric covers the 25 glossary questions. None when
    the run lacks either number."""
    if run.get("judge") is None or run.get("rubric") is None:
        return None
    return round((2 * run["judge"] + run["rubric"]) / 3, 3)


def question_spread(eval_dir: str) -> Dict:
    """What the answer eval asks: counts per route, language, type and extra checks, from the question files."""
    def load(name):
        path = Path(eval_dir) / name
        return [json.loads(line) for line in open(path, encoding="utf-8")] if path.is_file() else []

    main, forrt = load("questions.jsonl"), load("forrt_questions.jsonl")
    count = lambda items, key: sorted(Counter(q.get(key) or "–" for q in items).items(), key=lambda kv: -kv[1])  # noqa: E731
    return {
        "main": {"n": len(main), "routes": count(main, "route"), "expect": count(main, "expect"),
                 "languages": count(main, "lang"), "types": count(main, "type"),
                 "clusters": len({q.get("cluster") for q in main if q.get("cluster")}),
                 "with_dois": sum(bool(q.get("expected_dois")) for q in main),
                 "with_urls": sum(bool(q.get("expected_urls")) for q in main),
                 "with_rubric": sum("rubric" in q for q in main),
                 "multi_turn": sum(bool(q.get("history")) for q in main)},
        "forrt": {"n": len(forrt), "kinds": count(forrt, "kind")},
    } if main else {}


def best_defaults(folder: str, routers: Iterable[str]) -> Dict[str, str]:
    """The eval winners as the bot's defaults (AUTO_DEFAULTS): {"CITATION_MODEL": ..., "ROUTER": ...}.

    Answer model: the best score() among the papers runs (eval/pairs.py input, the newest per model)
    that cover the whole question set without errors, so a partial or failing run cannot win; while no
    run has a rubric score yet, the best judge score.
    Topic check: the most accurate router in the newest classify run with at least two routers (all
    scored on the same questions); a tie goes to the cheaper, then the faster one (banded and Jev tie at
    154 of 172; banded needs no model call for a third of the questions). A key is missing when nothing qualifies.
    """
    out: Dict[str, str] = {}
    papers = by_model([r for r in answer_runs(folder) if r["kind"] == "papers" and not r["config"]], "judge")
    full = max((r["n"] for r in papers), default=0)
    qualified = [r for r in papers if r["n"] == full and r["errors"] == 0 and r["judge"] is not None]
    scored = [r for r in qualified if score(r) is not None]
    if scored:
        out["CITATION_MODEL"] = max(scored, key=lambda r: (score(r), r["judge"]))["model"]
    elif qualified:
        out["CITATION_MODEL"] = max(qualified, key=lambda r: r["judge"])["model"]
    known = set(routers) - {""}
    for path in sorted(Path(folder).glob("classify_*.csv"), reverse=True):
        rows = [r for r in classifier_runs_of(path) if r["model"].removeprefix("router: ") in known
                and r["model"].startswith("router: ") and not r["errors"]]
        if len(rows) >= 2:
            # a tie goes to the cheaper check (fewer model calls), then the faster one
            best = min(rows, key=lambda r: (-(r["accuracy"] or 0), r["usd_per_1k"], r["mean_s"] or 0))
            out["ROUTER"] = best["model"].removeprefix("router: ")
            break
    return out


def people_and_judges(scores_dir: str, answers_dir: str) -> Dict:
    """People against each judge and metric, reviewers against each other, and each criterion per
    configuration (just_os.scores), from the score rows and the answer store; empty without rows."""
    from just_os import criteria, scores

    rows = scores.load(scores_dir)
    answers: Dict[str, Dict] = {}
    for path in sorted(Path(answers_dir).glob("answers_*.jsonl")):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                record = json.loads(line)
                answers[record["answer_id"]] = record
    if not rows:
        return {}
    result = scores.agreement(rows)
    configs = scores.by_config(rows, answers)
    scorers = sorted({s for c in configs for by_s in c["scores"].values() for s in by_s}, key=lambda s: (s != scores.PEOPLE, s))
    return {**result, "configs": configs, "scorers": scorers, "rows": len(rows),
            "criteria": [c for c in criteria.CRITERIA if any(c in x["scores"] for x in configs)],
            "labels": {"decision": "Decision", **{c: d["label"] for c, d in criteria.DEFINITIONS["criteria"].items()}}}

