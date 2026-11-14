"""Answer store (#54): every answer the bot gave, from eval runs, the arena and the chat, in one format.

    python eval/answers.py [eval/results/run_X.csv ...] [--rounds data/arena/rounds.jsonl]
        [--chats data/chats/chats.jsonl] [--out data/answers]

Writes one JSON line per answer to data/answers/answers_<source>.jsonl (one file per run, one for the
arena, one for the chat), so that people and judges score the same stored answers (eval/scores.py):

- answer_id: "<run file stem>#<question id>", "arena:<battle id>:<model>" or "chat:<turn id>"
- question_id: the eval question's id; empty for a question typed in the arena or the chat
- question, origin (run, arena, chat), time
- config: what produced the answer (answer model, topic check, retrieval, forced route, run)
- expect: what the bot should have done (answer, refuse), for eval questions
- outcome (answered, refused, no_sources, error, small_talk; empty when the source does not say) and
  answered_from (papers, forrt pages), in the terms of eval/run.py; the chat log's are mapped (CHAT_OUTCOMES)
- answer: the text as the bot wrote it; sources: [{n, title, doi, url, passage}], numbered as the
  answer cites them (arena sources are the reference list as shown)
- seconds, cost_usd (empty when the source does not record them)
- complete: false when the run kept only the first 2,000 characters of the answer and 800 of each
  passage (eval/run.py without --full-answers)
"""

import argparse
import csv
import json
import os
import re
from pathlib import Path


def record(answer_id, origin, question, config, answer, *, question_id="", time="", outcome="", answered_from="",
           sources=(), seconds="", cost_usd="", complete=True, expect=""):
    return {"answer_id": answer_id, "question_id": question_id, "origin": origin, "time": time, "question": question,
            "config": config, "expect": expect, "outcome": outcome, "answered_from": answered_from, "answer": answer,
            "sources": list(sources), "seconds": seconds, "cost_usd": cost_usd, "complete": complete}


def run_model(stem):
    """The answer model and forced route from a run file name, run_<YYMMDD-HHMM>_<model, / as __>[__route-<route>]
    [_noretrieval]; for runs written before eval/run.py had an answer_model column."""
    m = re.match(r"run_\d{6}-\d{4}_(.+)$", stem)
    if not m:
        return "", ""
    name = re.sub(r"_noretrieval$", "", m.group(1))
    route = ""
    if "__route-" in name:
        name, route = name.rsplit("__route-", 1)
    return name.replace("__", "/"), route


def from_run(run_csv):
    stem = Path(run_csv).stem
    model, route = run_model(stem)
    out = []
    for r in csv.DictReader(open(run_csv, encoding="utf-8")):
        sources = json.loads(r.get("sources") or "[]")
        passages = json.loads(r.get("passages") or "[]")
        for s, p in zip(sources, passages):
            s["passage"] = p
        answer = r.get("answer", "")
        # without --full-answers run.py cuts the answer at 2,000 characters and each passage at 800
        complete = len(answer) != 2000 and all(len(p) != 800 for p in passages)
        config = {"run": stem, "answer_model": r.get("answer_model") or model, "retrieval": r.get("retrieval", ""),
                  "route": route}
        out.append(record(f"{stem}#{r['id']}", "run", r["question"], config, answer, question_id=r["id"],
                          outcome=r.get("outcome", ""), answered_from=r.get("answered_from", ""), sources=sources,
                          expect=r.get("expect", ""),
                          seconds=float(r["seconds"]) if r.get("seconds") else "",
                          cost_usd=float(r["cost_usd"]) if r.get("cost_usd") else "", complete=complete))
    return out


def from_rounds(rounds_jsonl):
    out = []
    if not os.path.exists(rounds_jsonl):
        return out
    for line in open(rounds_jsonl, encoding="utf-8"):
        r = json.loads(line)
        for a in r["answers"].values():
            sources = [{"n": i + 1, "title": text} for i, text in
                       enumerate(t.strip() for t in re.split(r"\n?\[\d+\]\s*", a.get("sources", "")) if t.strip())]
            out.append(record(f"arena:{r['battle_id']}:{a['model']}", "arena", r["question"],
                              {"answer_model": a["model"]}, a.get("answer", ""), time=r.get("time", ""),
                              sources=sources, seconds=a.get("seconds", "")))
    return out


# The chat log's outcome is the pipeline's (just_os/qualle.py): (outcome, answered_from) in the run's terms;
# a cached answer logs the topic label instead (open_science, forrt, both)
CHAT_OUTCOMES = {"answered": ("answered", "papers"), "forrt": ("answered", "forrt pages"),
                 "forrt_lookup": ("answered", "forrt pages"), "off_topic": ("refused", ""),
                 "open_science": ("answered", ""), "both": ("answered", "")}


def from_chats(chats_jsonl):
    out = []
    if not os.path.exists(chats_jsonl):
        return out
    for line in open(chats_jsonl, encoding="utf-8"):
        r = json.loads(line)
        sources = [{"n": s.get("number"), "title": s.get("title", ""), "url": s.get("url", ""),
                    "passage": s.get("snippet", "")} for s in r.get("references", [])]
        outcome, answered_from = CHAT_OUTCOMES.get(r.get("outcome", ""), (r.get("outcome", ""), ""))
        out.append(record(f"chat:{r['turn_id']}", "chat", r["question"],
                          {"answer_model": r.get("model", ""), "router": r.get("router", "")}, r.get("answer", ""),
                          time=r.get("time", ""), outcome=outcome, answered_from=answered_from, sources=sources,
                          seconds=r.get("timings", {}).get("total_s", "")))
    return out


def write(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"{len(records):5} answers -> {path}")


def load(folder="data/answers"):
    """Every stored answer by answer_id."""
    out = {}
    for path in sorted(Path(folder).glob("answers_*.jsonl")):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            out[r["answer_id"]] = r
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="*", help="eval/run.py CSVs")
    parser.add_argument("--rounds", default="data/arena/rounds.jsonl")
    parser.add_argument("--chats", default="data/chats/chats.jsonl")
    parser.add_argument("--out", default="data/answers")
    args = parser.parse_args()
    out = Path(args.out)
    for run in args.runs:
        write(from_run(run), out / f"answers_{Path(run).stem}.jsonl")
    # a missing source file leaves the stored answers as they are
    if os.path.exists(args.rounds):
        write(from_rounds(args.rounds), out / "answers_arena.jsonl")
    if os.path.exists(args.chats):
        write(from_chats(args.chats), out / "answers_chat.jsonl")


if __name__ == "__main__":
    main()
