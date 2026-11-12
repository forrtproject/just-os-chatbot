"""Set the thresholds of the banded topic check (ROUTER=banded) on held-out questions.

    docker compose exec web python eval/tune_bands.py [--margin 0.01] [--max-refused 0.02]

The banded check refuses a question whose similarity to the nearest paper chunk and to the
nearest FORRT page are both below their LOW threshold, and answers from the papers one at or
above BAND_PAPER_HIGH that is below BAND_PAGE_HIGH, both with no model call; it asks
BAND_MIDDLE_ROUTER about the rest, including every question close to a FORRT page
(Qualle.banded_route).

Tuning questions, none of them in the files the topic check is reported on
(eval/questions.jsonl, eval/forrt_questions.jsonl):
- papers, in scope: eval/retrieval_questions.jsonl and the open_science_general questions of
  eval/forrt_sim_questions.jsonl
- FORRT pages, in scope: the other eval/forrt_sim_questions.jsonl questions that should not be
  refused, without the 32 hand-written ones, which are eval/forrt_questions.jsonl
- off topic: eval/refusal_questions.jsonl and the eval/forrt_sim_questions.jsonl questions that
  should be refused

The rule is strict, since answering an off-topic question is the worse error: each HIGH
threshold sits --margin above the closest off-topic tuning question, so none of them is answered
without a model call (BAND_PAGE_HIGH then sends questions that close to a FORRT page to the
middle router); each LOW threshold leaves at most --max-refused of the in-scope tuning
questions of its source below it.

Writes eval/results/bands_<YYMMDD>.csv (file, id, label, paper, page for every tuning and report
question) and prints the settings and the share of each set in each band.
"""

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402

REPORT_FILES = ("eval/questions.jsonl", "eval/forrt_questions.jsonl")


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def tuning_questions():
    """(file, id, label, question) with label papers, pages or off_topic."""
    out = [("retrieval", q["id"], "papers", q["question"]) for q in load("eval/retrieval_questions.jsonl")]
    for q in load("eval/forrt_sim_questions.jsonl"):
        if q["should_refuse"]:
            label = "off_topic"
        elif q["category"] == "open_science_general":
            label = "papers"
        elif q["category"] == "hand_written":  # the same 32 as eval/forrt_questions.jsonl
            continue
        else:
            label = "pages"
        out.append(("forrt_sim", q["id"], label, q["question"]))
    out += [("refusal", q["id"], "off_topic", q["question"]) for q in load("eval/refusal_questions.jsonl")]
    return out


def report_questions():
    """(file, id, gold route, question) for the files the topic check is reported on."""
    out = []
    for path in REPORT_FILES:
        for q in load(path):
            out.append((Path(path).stem, q["id"], q.get("route") or "forrt", q["question"]))
    return out


def low_threshold(values, max_refused):
    """The highest cut that leaves at most max_refused of values below it."""
    values = sorted(values)
    return values[math.floor(len(values) * max_refused)]


def thresholds(rows, margin, max_refused):
    """BAND_* settings from tuning rows (label, paper, page)."""
    off = [r for r in rows if r["label"] == "off_topic"]
    return {
        "BAND_PAPER_LOW": round(low_threshold([r["paper"] for r in rows if r["label"] == "papers"], max_refused), 3),
        "BAND_PAGE_LOW": round(low_threshold([r["page"] for r in rows if r["label"] == "pages"], max_refused), 3),
        "BAND_PAPER_HIGH": round(max(r["paper"] for r in off) + margin, 3),
        "BAND_PAGE_HIGH": round(max(r["page"] for r in off) + margin, 3),
    }


def band(paper, page, t):
    if paper < t["BAND_PAPER_LOW"] and page < t["BAND_PAGE_LOW"]:
        return "low"
    if paper >= t["BAND_PAPER_HIGH"] and page < t["BAND_PAGE_HIGH"]:
        return "high"
    return "middle"


def shares(rows, t, key):
    """Per group: n and the share of questions in the low, middle and high band."""
    groups = {}
    for r in rows:
        groups.setdefault(r[key], []).append(band(r["paper"], r["page"], t))
    return {g: (len(b), *(round(b.count(x) / len(b), 2) for x in ("low", "middle", "high"))) for g, b in sorted(groups.items())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--margin", type=float, default=0.01)
    parser.add_argument("--max-refused", type=float, default=0.02)
    args = parser.parse_args()

    from just_os.rag_service import create_rag_service

    qualle = create_rag_service(get_config(), None)
    rows = []
    for kind, questions in (("tune", tuning_questions()), ("report", report_questions())):
        for source, qid, label, question in questions:
            paper, page = qualle.similarities(question)
            rows.append({"set": kind, "file": source, "id": qid, "label": label,
                         "paper": round(paper, 4), "page": round(page, 4)})
    out = Path("eval/results") / f"bands_{datetime.now():%y%m%d}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    tune = [r for r in rows if r["set"] == "tune"]
    t = thresholds(tune, args.margin, args.max_refused)
    print("Settings:", " ".join(f"{k}={v}" for k, v in t.items()))
    print("Band shares (n, low, middle, high):")
    for name, key, part in (("tuning, by label", "label", tune), ("report, by gold route", "label",
                                                                    [r for r in rows if r["set"] == "report"])):
        print(f"  {name}")
        for group, values in shares(part, t, key).items():
            print(f"    {group:14} {values}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
