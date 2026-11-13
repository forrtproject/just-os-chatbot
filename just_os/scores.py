"""Score rows (#54) and how far their scorers agree, for eval/scores.py and the /eval page.

A score row says what one scorer gave one answer on one criterion: {answer_id, question_id, criterion,
score, scale, scorer_kind (person, llm or metric), scorer, setting, time, note}. `scale` is [low, high] for
a number and empty for the decision (right, should_refuse, should_answer, unsure). Rows live in
data/scores/scores_*.jsonl, answers in data/answers/ (eval/answers.py).
"""

import json
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from just_os import criteria

SCALE = [criteria.SCALE[0], criteria.SCALE[-1]]
UNIT = [0, 1]
PEOPLE = "people"


def row(answer_id, question_id, criterion, score, scale, kind, scorer, time="", note="", setting="default") -> Dict:
    return {"answer_id": answer_id, "question_id": question_id, "criterion": criterion, "score": score,
            "scale": scale, "scorer_kind": kind, "scorer": scorer, "setting": setting, "time": time, "note": note}


def load(folder, skip=None) -> List[Dict]:
    """The rows of every scores_*.jsonl file in `folder` but `skip`; none for a missing folder. A scorer's
    newest row per answer and criterion replaces the older ones (by `time`): /review writes every score
    of the page to a new file on each save."""
    newest: Dict = {}
    for path in sorted(Path(folder).glob("scores_*.jsonl")):
        if skip is None or path.resolve() != Path(skip).resolve():
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    key = (r["scorer_kind"], r["scorer"], r["answer_id"], r["criterion"])
                    if key not in newest or (r.get("time") or "") >= (newest[key].get("time") or ""):
                        newest[key] = r
    return list(newest.values())


def unit(r: Dict) -> float:
    low, high = r["scale"]
    return (r["score"] - low) / (high - low)


def ranks(xs: List[float]) -> List[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(xs, ys) -> Optional[float]:
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(ranks(xs), ranks(ys))


def weighted_kappa(xs, ys, low, high) -> Optional[float]:
    """Quadratic weighted kappa of two scorers on the same integer scale: 1 full agreement, 0 what chance gives."""
    if len(xs) < 2:
        return None
    k, n = high - low + 1, len(xs)
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(xs, ys):
        observed[x - low][y - low] += 1 / n
    px = [sum(observed[i]) for i in range(k)]
    py = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    disagreement = sum(w[i][j] * observed[i][j] for i in range(k) for j in range(k))
    chance = sum(w[i][j] * px[i] * py[j] for i in range(k) for j in range(k))
    return None if chance == 0 else 1 - disagreement / chance


def _mean(values) -> Optional[float]:
    values = list(values)
    return statistics.mean(values) if values else None


def _by_scorer(rows: Iterable[Dict]) -> Dict:
    """(criterion, scorer, or "people" for every person) -> {answer_id: [rows]}; rubric items are left out."""
    by: Dict = defaultdict(dict)
    for r in rows:
        if r["criterion"].startswith("rubric:"):
            continue
        key = (r["criterion"], PEOPLE if r["scorer_kind"] == "person" else r["scorer"])
        by[key].setdefault(r["answer_id"], []).append(r)
    return by


def agreement(rows: List[Dict]) -> Dict[str, List[Dict]]:
    """People against each judge or metric on the answers both scored, and each pair of reviewers.

    against: {criterion, scorer, n, spearman (or same, for the decision), people, scorer_mean, difference}
    reviewers: {criterion, a, b, n, kappa, exact, within_one}"""
    by = _by_scorer(rows)
    against = []
    for criterion, scorer in sorted(k for k in by if k[1] != PEOPLE):
        people, other = by.get((criterion, PEOPLE), {}), by[(criterion, scorer)]
        common = sorted(set(people) & set(other))
        if not common:
            continue
        if criterion == "decision":
            same = [sum(p["score"] == other[a][0]["score"] for p in people[a]) / len(people[a]) for a in common]
            against.append({"criterion": criterion, "scorer": scorer, "n": len(common), "same": statistics.mean(same)})
            continue
        xs = [statistics.mean(unit(p) for p in people[a]) for a in common]
        ys = [unit(other[a][0]) for a in common]
        against.append({"criterion": criterion, "scorer": scorer, "n": len(common), "spearman": spearman(xs, ys),
                        "people": statistics.mean(xs), "scorer_mean": statistics.mean(ys),
                        "difference": statistics.mean(y - x for x, y in zip(xs, ys))})
    reviewers = []
    for criterion in criteria.REVIEW:
        scored: Dict = defaultdict(dict)
        for answer, rs in by.get((criterion, PEOPLE), {}).items():
            for r in rs:
                if r["scale"] == SCALE:
                    scored[r["scorer"]][answer] = r["score"]
        for a, b in combinations(sorted(scored), 2):
            common = sorted(set(scored[a]) & set(scored[b]))
            if not common:
                continue
            xs, ys = [scored[a][i] for i in common], [scored[b][i] for i in common]
            reviewers.append({"criterion": criterion, "a": a, "b": b, "n": len(common),
                              "kappa": weighted_kappa(xs, ys, *SCALE),
                              "exact": sum(x == y for x, y in zip(xs, ys)) / len(xs),
                              "within_one": sum(abs(x - y) <= 1 for x, y in zip(xs, ys)) / len(xs)})
    return {"against": against, "reviewers": reviewers}


def config_label(config: Dict) -> str:
    """A short name for what produced an answer: answer model, retrieval and forced route when known."""
    parts = [config.get("answer_model") or "unknown model"]
    parts += [v for v in (config.get("retrieval"), config.get("route") and f"route {config['route']}") if v]
    return ", ".join(parts)


def by_config(rows: List[Dict], answers: Dict[str, Dict]) -> List[Dict]:
    """Per configuration (from the answer store) the mean of each criterion on 0-1, by people and by each
    judge or metric: {config, answers, scores: {criterion: {scorer: (mean, n)}}}. Answers missing from the
    store count under "unknown model"."""
    groups: Dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    seen: Dict = defaultdict(set)
    for (criterion, scorer), by_answer in _by_scorer(rows).items():
        if criterion == "decision":
            continue
        for answer_id, rs in by_answer.items():
            label = config_label(answers.get(answer_id, {}).get("config", {}))
            groups[label][criterion][scorer].append(statistics.mean(unit(r) for r in rs))
            seen[label].add(answer_id)
    return [{"config": label, "answers": len(seen[label]),
             "scores": {c: {s: (_mean(v), len(v)) for s, v in sorted(by_s.items(), key=lambda x: (x[0] != PEOPLE, x[0]))}
                        for c, by_s in by_c.items()}}
            for label, by_c in sorted(groups.items())]
