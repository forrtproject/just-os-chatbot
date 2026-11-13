"""Numbers for the /eval page, read from the CSVs in EVAL_RESULTS_DIR (eval/results):

    run_<YYMMDD-HHMM>_<model>.csv   eval/run.py: one row per question, full pipeline
      ..._<model>__route-<route>.csv  every question forced to the papers or the FORRT pages (eval/pairs.py)
      ..._cfg-<name>[...].csv         a named configuration of eval/configs.json (eval/scorecard.py)
    pairs_<YYMMDD-HHMM>.csv         eval/pairs.py: one row per topic check x answer model
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
    return sorted(rows, key=lambda r: -r["accuracy"])


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


def best_defaults(folder: str, routers: Iterable[str]) -> Dict[str, str]:
    """The eval winners as the bot's defaults (AUTO_DEFAULTS): {"CITATION_MODEL": ..., "ROUTER": ...}.

    Answer model: the best judge score among the papers runs (eval/pairs.py input, the newest per model)
    that cover the whole question set without errors, so a partial or failing run cannot win.
    Topic check: the most accurate router in the newest classify run with at least two routers (all
    scored on the same questions); a tie goes to the cheaper, then the faster one (banded and Jev tie at
    154 of 172; banded needs no model call for a third of the questions). A key is missing when nothing qualifies.
    """
    out: Dict[str, str] = {}
    papers = by_model([r for r in answer_runs(folder) if r["kind"] == "papers" and not r["config"]], "judge")
    full = max((r["n"] for r in papers), default=0)
    qualified = [r for r in papers if r["n"] == full and r["errors"] == 0 and r["judge"] is not None]
    if qualified:
        out["CITATION_MODEL"] = max(qualified, key=lambda r: r["judge"])["model"]
    known = set(routers) - {""}
    for path in sorted(Path(folder).glob("classify_*.csv"), reverse=True):
        rows = [r for r in classifier_runs_of(path) if r["model"].removeprefix("router: ") in known
                and r["model"].startswith("router: ") and not r["errors"]]
        if len(rows) >= 2:
            # a tie goes to the cheaper check (fewer model calls), then the faster one
            best = min(rows, key=lambda r: (-r["accuracy"], r["usd_per_1k"], r["mean_s"] or 0))
            out["ROUTER"] = best["model"].removeprefix("router: ")
            break
    return out
