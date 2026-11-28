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
from typing import Dict, Iterable, List, Optional, Tuple

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
        match = re.match(r"run_(\d{6}-\d{4}(?:\d{2})?)_(.+)\.csv$", path.name)  # seconds since Nov 2026
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
            "judge_non_en": _mean(r.get("judge_support") for r in rows if r.get("lang", "en") != "en"),
            "tok_in": round(mean(int(r["prompt_tokens"] or 0) for r in rows)),
            "tok_out": round(mean(int(r["completion_tokens"] or 0) for r in rows)),
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


# Credits per 1M tokens (input / output) on uniGPT Münster, https://gpt.uni-muenster.de/docs/available-models/
# (checked 2026-11-19). Keyed by the OpenRouter id without "@provider"; a model not listed there shows NA.
UNI_PRICES = {
    "deepseek/deepseek-v4-flash": "0.14 / 0.28",
    "openai/gpt-oss-120b": "0.15 / 0.6",
    "openai/gpt-6-luna": "0.1 / 0.5",  # external model (OpenAI cloud), not on university servers
    "google/gemma-4-31b-it": "0.09 / 0.16",
    "mistralai/mistral-small-2603": "0.15 / 0.2",  # uniGPT calls it mistral-small-4
    "qwen/qwen3.8-27b": "2 / 6",
    "meta/muse-glimmer-30b": "offered, no cost listed",
}

# Embedding id in eval/compare_embeddings.py -> (several languages?, USD per 1M tokens on OpenRouter;
# None = runs locally, no API cost). Prices from openrouter.ai/api/v1/embeddings/models, 2026-11-19.
EMBEDDING_INFO = {
    "E1": (False, None), "E2": (True, None), "E3": (True, None), "E4": (True, None),
    "E5": (True, 0.02), "E6": (True, 0.01), "E7": (False, None), "E8": (False, None), "E9": (True, None),
    "E10": (True, 0.12), "E11": (True, 0.12),  # E11: library with -large, questions with local voyage-4-nano
}


# One line per embedding model for /eval's "Why" column (docs/evaluation.md 3.1, 3.19, 3.21, deployment-checklist task 8)
EMBEDDING_WHY = {
    "E1": "English-only and small: good in English, far behind in German, Spanish and Dutch.",
    "E2": "Small multilingual model; below bge-m3 in every language.",
    "E3": "In use: multilingual, runs locally (no question leaves the server, no cost), and in the full bot "
          "better than Voyage (3.21).",
    "E4": "Small local Qwen; below bge-m3 outside English, and slow on CPU.",
    "E5": "Close to bge-m3 but an API call per question.",
    "E6": "Slightly above bge-m3 in English, level elsewhere; 3 s per question through the API.",
    "E7": "OpenScholar's retriever: English-only, meant to sit before OpenScholar's re-ranker; below bge-m3 even "
          "in English. No query prefix was missing.",
    "E8": "Trained to match citation sentences to the cited paper, not questions to passages; English-only. "
          "No query prefix was missing.",
    "E9": "Does not load with the installed transformers.",
    "E10": "Best search alone, but in the full bot lower than bge-m3 for 4 of 5 answer models (3.21); "
           "every question goes to an API.",
    "E11": "Half of Voyage's gain with questions embedded locally; needs custom model code in the image.",
}

# One line per answer model for /eval's "Why" column (docs/evaluation.md 3.20, 3.21, deployment-checklist task 2)
ANSWER_WHY = {
    "google/gemma-4-31b-it": "Production choice: within 0.03 of the best, fastest of the leaders, best non-English "
                             "answers, short answers, on uniGPT Münster.",
    "meta/muse-glimmer-30b": "Best score, but 2.6x slower than Gemma 4 and the longest answers.",
    "openai/gpt-6-luna": "Good, but on uniGPT only in the web chat (external, not through the API).",
    "deepseek/deepseek-v4-flash": "Best rubric coverage; lower citation support than the top two on today's search.",
    "qwen/qwen3.7-flash": "Cheap and fast, but uniGPT does not offer it.",
    "qwen/qwen3.8-27b": "uniGPT's successor to Qwen 3.7: no better, 3x slower.",
    "mistralai/mistral-small-2603": "Mistral Small 4 on uniGPT: level with 3.2, lowest citation support of the "
                                    "uniGPT models.",
    "google/gemma-3-27b-it": "Retired on uniGPT; Gemma 4 replaces it.",
    "mistralai/mistral-small-3.2-24b-instruct": "Not offered by uniGPT.",
    "openai/gpt-oss-120b@groq": "Fastest (3 s), but the lowest citation support of the ten.",
    "meta-llama/llama-3.1-8b-instruct": "The old default; last in 3.20 (invented references, irrelevant passages).",
    "openscholar-8b": "OpenScholar on its own server: slow on CPU, below the general models (3.12).",
    "openai/gpt-oss-120b@deepinfra/bf16": "The same gpt-oss-120b through another provider: 10x slower than on Groq.",
    "google/gemma-3-12b-it": "The default of 13 Nov (3.12); 4 errors here, and uniGPT does not offer it.",
}
DEFAULTS_SINCE = "261114"  # docs/evaluation.md 3.18: vector search without the re-ranker from 14 Nov 2026
TODAY_SETTING = "bge-m3 · vector"
CONFIGS_FILE = Path(__file__).resolve().parent.parent / "eval" / "configs.json"


def _configs() -> Dict[str, Dict]:
    try:
        return json.loads(CONFIGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def setting(run: Dict, configs: Optional[Dict] = None) -> Dict[str, str]:
    """What produced a run: its answer model and "embedding · search" (+ re-ranker, paper cap, adaptive top-k).
    A configuration run (eval/configs.json) says so itself; a plain run had the defaults of its day."""
    cfg = (configs if configs is not None else _configs()).get(run.get("config") or "", {})
    new = run["run"] >= DEFAULTS_SINCE
    parts = ["Voyage-4-large" if "voyage" in str(cfg.get("EMBEDDING_MODEL", "")).lower() else "bge-m3",
             cfg.get("SEARCH_MODE", "vector" if new else "hybrid") + (" + re-ranker" if cfg.get("RERANK", not new) else "")]
    if "glossary" in str(cfg.get("VECTOR_STORE", "")):
        parts[0] += " + FORRT glossary"
    if cfg.get("MAX_CHUNKS_PER_DOC"):
        parts.append(f"≤ {cfg['MAX_CHUNKS_PER_DOC']} chunks per paper")
    if cfg.get("ADAPTIVE_TOP_K"):
        parts.append(f"{cfg.get('ADAPTIVE_TOP_K_MIN', 3)}-{cfg.get('MAX_CHUNKS', 7)} chunks (adaptive)")
    return {"answer_model": cfg.get("CITATION_MODEL") or run["model"], "setting": " · ".join(parts)}


def answer_model_rows(runs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """The papers runs (every question answered from the papers), newest per answer model and setting, best
    score first: (on today's setting, other settings and older runs). Search-setting runs are left out."""
    configs = _configs()
    latest: Dict[Tuple[str, str], Dict] = {}
    for run in runs:  # newest first
        if run["kind"] != "papers" or run["config"].startswith("search-"):
            continue
        row = {**run, **setting(run, configs)}
        row["score"] = run.get("score") if run.get("score") is not None else score(run)
        row["uni_credits"] = unigpt_credits_per_1k(row)
        row["why"] = (EMBEDDING_WHY["E10"] if row["setting"].startswith("Voyage")
                      else ANSWER_WHY.get(row["answer_model"], ""))
        # a newer run without a score (part of the questions, no rubric judge: an A/B run) must not hide a scored one
        kept = latest.get((row["answer_model"], row["setting"]))
        if kept is None or (kept.get("score") is None and row["score"] is not None):
            latest[(row["answer_model"], row["setting"])] = row
    rows = sorted(latest.values(), key=lambda r: -(r.get("score") or -1))
    return [r for r in rows if r["setting"] == TODAY_SETTING], [r for r in rows if r["setting"] != TODAY_SETTING]


# uniGPT Münster's API (https://gpt.uni-muenster.de/docs/api-usage/, checked 2026-11-25): one flat rate for its six
# on-premises chat models, in credits per 1M tokens (input, output); the web-chat prices above differ
UNIGPT_API_RATE = (0.5, 1.0)
UNIGPT_API_MODELS = {"deepseek/deepseek-v4-flash", "qwen/qwen3.8-27b", "google/gemma-4-31b-it", "openai/gpt-oss-120b",
                     "mistralai/mistral-small-2603", "meta/muse-glimmer-30b"}


def unigpt_credits_per_1k(run: Dict) -> Optional[float]:
    """uniGPT API credits for 1,000 questions at the run's mean input/output tokens; None when the API does not
    offer the model (GPT-6 Luna is web chat only there)."""
    if run.get("answer_model", run.get("model", "")).split("@")[0] not in UNIGPT_API_MODELS or run.get("tok_in") is None:
        return None
    return round((run["tok_in"] * UNIGPT_API_RATE[0] + run["tok_out"] * UNIGPT_API_RATE[1]) / 1000, 2)


def uni_price(model: str) -> str:
    """uniGPT Münster credits per 1M tokens (input / output), or NA when the university does not offer it."""
    return UNI_PRICES.get(model.split("@")[0], "NA")


def embedding_runs(folder: str) -> List[Dict]:
    """The "all languages" row of each model in the newest embeddings_*.csv."""
    files = sorted(Path(folder).glob("embeddings_*.csv"))
    if not files:
        return []
    rows = _rows(files[-1])
    english = {r["model"]: float(r["hit@5"]) for r in rows if r["lang"] == "en"}

    def interval(r):  # 95% bootstrap interval of hit@5 (eval/compare_embeddings.py, runs from 25 Nov 2026)
        lo, hi = r.get("hit@5_lo"), r.get("hit@5_hi")
        return f"{float(lo):.2f}-{float(hi):.2f}" if lo not in (None, "") and hi not in (None, "") else ""

    return sorted((
        {"id": r["model"], "model": r["name"], "dim": r["dim"], "hit5": round(float(r["hit@5"]), 2),
         "hit20": round(float(r["hit@20"]), 2), "mrr20": round(float(r["mrr@20"]), 2), "ms": round(float(r["ms_per_query"])),
         "hit5_en": None if english.get(r["model"]) is None else round(english[r["model"]], 2),
         "ci": interval(r), "prefix": r.get("query_prefix") or "", "why": EMBEDDING_WHY.get(r["model"], ""),
         "multilingual": EMBEDDING_INFO.get(r["model"], (None, None))[0],
         "usd_per_1m": EMBEDDING_INFO.get(r["model"], (None, None))[1]}
        for r in rows if r["lang"] == "all"), key=lambda r: -r["hit5"])


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


# The best pair (docs/deployment-checklist.md task 2): eligible for production, good enough on quality and speed,
# then the best balance of quality, answers outside English and cost
PAIR_CORRECT_MARGIN = 0.01  # Correct within this of the best eligible pair (run-to-run spread of a topic check: 0.009)
PAIR_SCORE_MARGIN = 0.06    # answer score within this of the best eligible answer model (decided 25 Nov)
PAIR_P95_TARGET = 15.0      # seconds: 95% of answers faster than this (#13)


def best_pair(pairs: Dict, answer_today: List[Dict]) -> Dict:
    """The topic check + answer model pair, decided on several factors rather than one number.

    1. Eligible: uniGPT's API runs the answer model (production), its papers run on today's setting has a score and
       answered every question without errors, and the topic check is a real one (not "none").
    2. Good enough: the pair handles questions correctly (answer or refuse) within PAIR_CORRECT_MARGIN of the best
       eligible pair; the answer model's score is within PAIR_SCORE_MARGIN of the best eligible one; and 95% of its
       answers take at most PAIR_P95_TARGET seconds. Speed is a requirement, not a race: past the target, a faster
       answer is not a better one.
    3. Balance: 2 x quality (score / best score) + outside English (citation judge on the non-English questions /
       best) + cost (lowest uniGPT credits per 1,000 answers / these). Quality counts double, as the citation judge
       does in the score.
    4. The same answer model with two topic checks: the cheaper topic check (fewer calls to OpenRouter's decision
       models, so less question text leaves the university), then the higher Correct.
    Returns {"best", "shortlist" (the good-enough pairs, best first, with their balance), "excluded" {reason: n}}."""
    if not pairs or not answer_today:
        return {"best": None, "shortlist": [], "excluded": {}}
    models = {r["answer_model"]: r for r in answer_today}
    full = max(r["n"] for r in answer_today)
    excluded: Dict[str, int] = Counter()
    eligible = []
    for p in pairs["rows"]:
        m = models.get(p["answer_model"])
        if m is None or m.get("score") is None:
            excluded["no answer score on today's setting"] += 1
        elif p["answer_model"].split("@")[0] not in UNIGPT_API_MODELS:
            excluded["answer model not on uniGPT's API"] += 1
        elif m["errors"] or m["n"] < full:
            excluded["errors or an unfinished run"] += 1
        elif p["topic_check"] == "none" or p["correct"] is None:
            excluded["no topic check"] += 1
        else:
            eligible.append({**p, "score": m["score"], "judge_non_en": m.get("judge_non_en"),
                             "uni_credits": m.get("uni_credits"), "p95_s": m.get("p95_s")})
    if not eligible:
        return {"best": None, "shortlist": [], "excluded": dict(excluded)}
    top_correct = max(p["correct"] for p in eligible)
    top_score = max(p["score"] for p in eligible)
    good = []
    for p in eligible:
        if p["correct"] < top_correct - PAIR_CORRECT_MARGIN - 1e-9 or p["score"] < top_score - PAIR_SCORE_MARGIN - 1e-9:
            excluded["quality not near the best"] += 1
        elif (p["p95_s"] or 0) > PAIR_P95_TARGET:
            excluded[f"95% of answers slower than {PAIR_P95_TARGET:g} s"] += 1
        else:
            good.append(p)
    if not good:
        return {"best": None, "shortlist": [], "excluded": dict(excluded)}
    best_lang = max(p["judge_non_en"] or 0 for p in good) or 1
    cheapest = min(p["uni_credits"] or 0 for p in good) or 1
    for p in good:
        p["balance"] = round(2 * p["score"] / top_score + (p["judge_non_en"] or 0) / best_lang
                             + cheapest / (p["uni_credits"] or cheapest), 3)
    good.sort(key=lambda p: (-p["balance"], p["usd_per_1k"] or 0, -p["correct"]))
    return {"best": good[0], "shortlist": good, "excluded": {k: v for k, v in excluded.items() if v},
            "top_correct": top_correct, "top_score": top_score}


def apply_auto_defaults(config: Dict, routers: Iterable[str]) -> Dict[str, str]:
    """AUTO_DEFAULTS: put the eval winners into config (in place) and return them ({} when off or no results).
    The one place both the app and the preloaded RAG service (config/gunicorn.py) take them from."""
    if not config.get("AUTO_DEFAULTS"):
        return {}
    folder = config.get("EVAL_RESULTS_DIR", "eval/results")
    chosen = best_defaults(folder, routers)
    top = top_answer_models(folder)
    if top:  # the chat and arena model lists follow the eval too, instead of the fixed ARENA_MODELS
        chosen["ARENA_MODELS"] = ",".join(top)
    config.update(chosen)
    return chosen


TOP_ANSWER_MODELS = 10


def top_answer_models(folder: str, n: int = TOP_ANSWER_MODELS) -> List[str]:
    """The n best-scored answer models on today's setting (the /eval table's order), without provider pins
    such as "@groq", which the chat client does not understand."""
    rows = answer_model_rows(answer_runs(folder))[0]
    return list(dict.fromkeys(r["answer_model"].split("@")[0] for r in rows if r.get("score") is not None))[:n]


def best_defaults(folder: str, routers: Iterable[str]) -> Dict[str, str]:
    """The eval winners as the bot's defaults (AUTO_DEFAULTS): {"CITATION_MODEL": ..., "ROUTER": ...}.

    With a pair table: both from best_pair (quality, time, cost, language, uniGPT). Without one, as before:

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
    # without a provider pin such as "@groq", which the chat client does not understand (top_answer_models)
    if scored:
        out["CITATION_MODEL"] = max(scored, key=lambda r: (score(r), r["judge"]))["model"].split("@")[0]
    elif qualified:
        out["CITATION_MODEL"] = max(qualified, key=lambda r: r["judge"])["model"].split("@")[0]
    known = set(routers) - {""}
    pair = best_pair(pair_results(folder), answer_model_rows(answer_runs(folder))[0])["best"]
    if pair and pair["topic_check"] in known:  # the pair rule decides both, when there is a pair table
        out["CITATION_MODEL"] = pair["answer_model"].split("@")[0]
        out["ROUTER"] = pair["topic_check"]
        return out
    for path in sorted(Path(folder).glob("classify_*.csv"), reverse=True):
        rows = [r for r in classifier_runs_of(path) if r["model"].removeprefix("router: ") in known
                and r["model"].startswith("router: ") and not r["errors"] and r["accuracy"] is not None]
        if len(rows) >= 2:
            # a tie goes to the cheaper check (fewer model calls), then the faster one
            best = min(rows, key=lambda r: (-r["accuracy"], r["usd_per_1k"], r["mean_s"] or 0))
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

