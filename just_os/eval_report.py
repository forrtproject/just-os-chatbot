"""Numbers for the /eval page, read from the CSVs in EVAL_RESULTS_DIR (eval/results):

    run_<YYMMDD-HHMM>_<model>.csv   eval/run.py: one row per question, full pipeline
    classify_<YYMMDD-HHMM>.csv      eval/classify.py: model, id, gold, predicted, seconds, usd
    embeddings_<YYMMDD>.csv         eval/compare_embeddings.py: one row per model and language

A missing folder or file gives empty tables (the production image has no eval/ folder).
"""

import csv
import re
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional

# A classifier "refuses" with these labels (classify_query: off_topic; router: neither)
REFUSE_LABELS = {"off_topic", "neither"}


def _rows(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mean(values: Iterable, digits: int = 2) -> Optional[float]:
    numbers = [float(v) for v in values if v not in ("", None)]
    return round(mean(numbers), digits) if numbers else None


def _p95(values: List[float]) -> float:
    values = sorted(values)
    return round(values[int(0.95 * (len(values) - 1))], 1)


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
            "model": match.group(2).replace("__", "/"),
            "n": len(rows),
            "correct": _mean(r["correct"] for r in rows),
            "answered": f"{sum(r['outcome'] == 'answered' for r in answer)}/{len(answer)}",
            "refused": f"{sum(r['outcome'] == 'refused' for r in refuse)}/{len(refuse)}",
            "errors": sum(r["outcome"] == "error" for r in rows),
            "hit": _mean(r["hit"] for r in rows),
            "citations_valid": _mean(r["citations_valid"] for r in rows),
            "judge": _mean(r.get("judge_support") for r in rows),
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
        by_model: Dict[str, List[Dict[str, str]]] = {}
        for row in _rows(path):
            by_model.setdefault(row["model"], []).append(row)
        rows = []
        for model, items in by_model.items():
            done = [r for r in items if r["predicted"]]
            rows.append({
                "run": path.stem.removeprefix("classify_"),
                "model": model,
                "n": len(items),
                "accuracy": round(sum(r["gold"] == r["predicted"] for r in items) / len(items), 2),
                "false_refusals": sum(r["gold"] not in REFUSE_LABELS and r["predicted"] in REFUSE_LABELS for r in done),
                "false_answers": sum(r["gold"] in REFUSE_LABELS and r["predicted"] not in REFUSE_LABELS for r in done),
                "errors": len(items) - len(done),
                "mean_s": _mean((r["seconds"] for r in items), 1),
                "usd_per_1k": round(mean(float(r["usd"] or 0) for r in items) * 1000, 3),
            })
        out += sorted(rows, key=lambda r: -r["accuracy"])
    return out


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
