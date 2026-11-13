"""Follow-up questions (#14): how well does each context method answer what the user meant?

    docker compose exec web python eval/context_eval.py                       # none,rephrase,history,oracle; 2 runs
    docker compose exec web python eval/context_eval.py --methods rephrase,hybrid --runs 1 --limit 5
    docker compose exec web python eval/context_eval.py --model meta-llama/llama-3.1-8b-instruct@groq

Each chat of eval/context_questions.jsonl has earlier user turns, a follow-up as typed, and `gold`: the
follow-up written out so it stands alone; `split` is "tune" (change a method while looking at these) or
"report" (held out: the numbers to publish). A method is "none" (the follow-up alone, no earlier turns),
"oracle" (gold alone: the best any method can do) or a CONTEXT_METHOD value (the earlier turns are
asked first in the same chat). A judge model (--judge-model) scores each answer against gold and the
chat's must-keep details: 2 answers what was meant, 1 partly, 0 not (a different or the earlier
question, generic, refused); for off-topic follow-ups 2 = refused. Also per answer: route as labelled,
and the share of the oracle's sources (papers or forrt.org pages) the method used.
Output: eval/results/context_<YYMMDD-HHMM>.csv and the tables below it.
"""

import argparse
import csv
import json
import re
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_config  # noqa: E402
from just_os.chat_manager import ChatManager  # noqa: E402
from just_os.rag_service import create_rag_service  # noqa: E402
from run import doi_of, outcome_of, pin_provider, split_provider  # noqa: E402

JUDGE = """You grade one answer from an open-science chatbot. The user asked a follow-up question in a chat.

Earlier user turns:
{history}
Follow-up as typed: {question}
What the user meant: {gold}
{keep}
Answer:
<<<
{answer}
>>>

Score:
2 = answers what the user meant{keep2}
1 = on the right topic but only partly answers it, or misses a must-keep detail
0 = answers a different question (e.g. only the earlier one), is generic, says it found nothing, or refuses
Judge only whether it answers what the user meant, not style or length.
Reply as JSON: {{"score": 0|1|2, "reason": "<one sentence>"}}"""

JUDGE_REFUSE = """An open-science chatbot should politely decline questions outside open science and FORRT.
Earlier user turns:
{history}
Question: {question}
Answer:
<<<
{answer}
>>>
Score 2 if the answer declines, 0 if it answers the question.
Reply as JSON: {{"score": 0|2, "reason": "<one sentence>"}}"""


def judge_prompt(q, answer):
    history = "\n".join(f"- {h}" for h in q["history"]) or "- (none)"
    answer = answer[:3500] or "(empty)"
    if q["expect"] == "refuse":
        return JUDGE_REFUSE.format(history=history, question=q["question"], answer=answer)
    keep = f"Must keep: {'; '.join(q['must_keep'])}" if q.get("must_keep") else ""
    return JUDGE.format(history=history, question=q["question"], gold=q["gold"], keep=keep, answer=answer,
                        keep2=" and keeps every must-keep detail" if keep else "")


def parse_score(text):
    """{"score": 2, ...} anywhere in the judge's reply -> (2, reason); (None, text) when unreadable."""
    try:
        v = json.loads(re.search(r"\{.*\}", text or "", re.S).group(0))
        return int(v["score"]), str(v.get("reason", ""))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None, (text or "")[:200]


def source_recall(sources, oracle_sources):
    """Share of the oracle's sources that the method also used; None when the oracle used none."""
    oracle = set(oracle_sources)
    return len(set(sources) & oracle) / len(oracle) if oracle else None


def mean(xs):
    xs = [float(x) for x in xs if x not in ("", None)]
    return statistics.mean(xs) if xs else None


def summary(rows, methods):
    """Markdown tables: per method overall, judge score per group, and per run (run-to-run noise)."""
    fmt = lambda x, spec=".2f": "–" if x is None else format(x, spec)  # noqa: E731
    out = ["| Method | Judge (0-2) | Full marks | Route as labelled | Oracle's sources used | Mean s | USD / 1k |",
           "|---|---|---|---|---|---|---|"]
    for m in methods:
        rs = [r for r in rows if r["method"] == m]
        out.append(f"| {m} | {fmt(mean(r['score'] for r in rs))} | {fmt(mean(int(r['score'] == 2) for r in rs if r['score'] != ''), '.0%')} "
                   f"| {fmt(mean(r['route_ok'] for r in rs), '.0%')} | {fmt(mean(r['recall'] for r in rs), '.0%')} "
                   f"| {fmt(mean(r['seconds'] for r in rs), '.1f')} | {fmt(mean(1000 * float(r['cost_usd']) for r in rs))} |")
    groups = list(dict.fromkeys(r["group"] for r in rows))
    out += ["", "| Group | n | " + " | ".join(methods) + " |", "|---|---|" + "---|" * len(methods)]
    for g in groups:
        n = len({r["id"] for r in rows if r["group"] == g})
        out.append(f"| {g} | {n} | " + " | ".join(fmt(mean(r["score"] for r in rows if r["method"] == m and r["group"] == g)) for m in methods) + " |")
    runs = sorted({r["run"] for r in rows})
    out += ["", "| Method | " + " | ".join(f"run {k}" for k in runs) + " |", "|---|" + "---|" * len(runs)]
    for m in methods:
        out.append(f"| {m} | " + " | ".join(fmt(mean(r["score"] for r in rows if r["method"] == m and r["run"] == k)) for k in runs) + " |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--methods", default="none,rephrase,history,oracle")
    p.add_argument("--runs", type=int, default=2, help="answers vary between runs: repeat to see the noise")
    p.add_argument("--questions", default="eval/context_questions.jsonl")
    p.add_argument("--split", choices=["tune", "report"], help="only the chats of this split: improve a method on "
                   "'tune', report the final numbers on 'report' (held out)")
    p.add_argument("--limit", type=int)
    p.add_argument("--model", help="answer model (CITATION_MODEL), optionally model@provider")
    p.add_argument("--judge-model", default="openai/gpt-oss-120b@groq")
    p.add_argument("--out", help="output CSV (default eval/results/context_<YYMMDD-HHMM>.csv)")
    args = p.parse_args()
    methods = args.methods.split(",")
    chats = [c for c in map(json.loads, open(args.questions, encoding="utf-8")) if c.get("split") == args.split or not args.split]
    chats = chats[: args.limit]

    config = get_config()
    provider = None
    if args.model:
        config["CITATION_MODEL"], provider = split_provider(args.model)
    qualle = create_rag_service(config, ChatManager())
    if provider:
        pin_provider(qualle, config["CITATION_MODEL"], provider)

    seen = {}  # what the scored turn did, recorded without changing the pipeline
    route, retrieve = qualle.route, qualle.document_retriever.retrieve_and_rerank
    generate, complete = qualle.response_generator.generate_response, qualle.client_manager.create_chat_completion
    qualle.route = lambda query, router=None: seen.update(route=route(query, router)) or seen["route"]
    qualle.document_retriever.retrieve_and_rerank = lambda query, *a: seen.update(ranked=retrieve(query, *a)[0]) or (seen["ranked"], [])
    qualle.response_generator.generate_response = lambda *a, **kw: seen.update(raw=generate(*a, **kw)) or seen["raw"]

    def counted(**kw):
        response = complete(**kw)
        seen["cost"] = seen.get("cost", 0) + (getattr(getattr(response, "usage", None), "cost", 0) or 0)
        return response
    qualle.client_manager.create_chat_completion = counted
    if qualle.forrt_pages is not None:
        forrt = qualle.forrt_pages.answer
        qualle.forrt_pages.answer = lambda *a, **kw: seen.update(forrt=forrt(*a, **kw)) or seen["forrt"]

    rows = []
    for run in range(1, args.runs + 1):
        for method in methods:
            if method not in ("none", "oracle"):
                qualle.config = {**qualle.config, "CONTEXT_METHOD": method}
            for q in chats:
                chat_id = f"context-eval-{uuid.uuid4()}"
                if method not in ("none", "oracle"):
                    for turn in q["history"]:
                        list(qualle.get_response(turn, chat_id))
                seen.clear()
                start = time.time()
                final = list(qualle.get_response(q["gold"] if method == "oracle" else q["question"], chat_id))[-1]
                pages = [s["url"] for s in (seen.get("forrt") or {}).get("sources", [])]
                rows.append({"run": run, "method": method, "id": q["id"], "group": q["group"], "route": seen.get("route") or "",
                             "route_ok": int(seen.get("route") in q["route"]), "outcome": outcome_of(final),
                             "sources": " ".join(pages + [doi_of(n) for n in seen.get("ranked", [])]),
                             "answer": seen.get("raw") or re.sub(r"<[^>]+>", " ", final.get("message", "")).strip(),
                             "seconds": round(time.time() - start, 1), "cost_usd": round(seen.get("cost", 0), 6)})
                print(f"run {run} {method:9} {q['id']} {rows[-1]['route']:13} {rows[-1]['outcome']}")

    judge_model, judge_provider = split_provider(args.judge_model)
    by_id = {c["id"]: c for c in chats}

    def judge(r):
        response = qualle.client_manager.client.chat.completions.create(
            model=judge_model, temperature=0, messages=[{"role": "user", "content": judge_prompt(by_id[r["id"]], r["answer"])}],
            **({"extra_body": {"provider": judge_provider}} if judge_provider else {}))
        score, r["reason"] = parse_score(response.choices[0].message.content)
        r["score"] = "" if score is None else score

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(judge, rows))
    oracle = {(r["run"], r["id"]): r["sources"].split() for r in rows if r["method"] == "oracle"}
    for r in rows:
        r["recall"] = "" if r["method"] == "oracle" else source_recall(r["sources"].split(), oracle.get((r["run"], r["id"]), []))

    out = Path(args.out or f"eval/results/context_{datetime.now():%y%m%d-%H%M}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}\n\n{summary(rows, methods)}")


if __name__ == "__main__":
    main()
