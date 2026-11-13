"""Topic check comparison (issue E3, #9): which check decides best where a question goes?

    docker compose exec web python eval/classify.py --routers jev,clef-flash,llm,cosine,none \
        --questions eval/questions.jsonl,eval/forrt_questions.jsonl
    docker compose exec web python eval/classify.py --models openai/gpt-oss-20b,qwen/qwen3.7-flash
    docker compose exec web python eval/classify.py --models ... --intent   # 3 classes (FORRT_LOOKUP)

Runs only the topic check (no retrieval, no answer). --routers runs the whole check
(Qualle.route), one ROUTERS strategy at a time, scored against the 4 "route" labels; a
question without "route" counts as forrt. --models runs only the LLM classifier
(GENERAL_MODEL) with each model: "expect": answer → should be open science; refuse →
should not. With --intent, an optional "intent" field gives the gold class instead.
Prints a Markdown table: accuracy, false refusals, false answers, errors, time, cost,
and writes eval/results/classify_<YYMMDD-HHMM>.csv for the /eval page.
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402
from just_os.eval_report import REFUSE_LABELS, TASK  # noqa: E402
from just_os.qualle import OpenAIClientManager, QueryProcessor  # noqa: E402


def gold(question: dict, intent: bool) -> str:
    if question.get("kind") == TASK:
        return TASK
    if intent and question.get("intent"):
        return question["intent"]
    return "open_science" if question["expect"] == "answer" else "off_topic"


def predict(processor: QueryProcessor, text: str, intent: bool):
    if intent:
        return processor.classify_intent(text)
    result = processor.classify_query(text)
    return None if result is None else ("open_science" if result else "off_topic")


def summarize(model: str, results: list) -> str:
    """results: (gold, predicted or None, seconds, cost_usd) per question. Questions with gold TASK (an
    in-scope topic, a task the bot should not do) are left out of the accuracy and counted apart: how
    many of them the check let through, which the answer step has to decline."""
    tasks = [p for g, p, _, _ in results if g == TASK]
    let_through = f"{sum(p is not None and p not in REFUSE_LABELS for p in tasks)}/{len(tasks)}" if tasks else "–"
    timed, results = results, [r for r in results if r[0] != TASK]
    n = len(results)
    errors = sum(p is None for _, p, _, _ in results)
    correct = sum(g == p for g, p, _, _ in results)
    # same counting as the /eval page: refusing = off_topic (classifier) or neither (router)
    false_refusals = sum(g not in REFUSE_LABELS and p in REFUSE_LABELS for g, p, _, _ in results)
    false_answers = sum(g in REFUSE_LABELS and p is not None and p not in REFUSE_LABELS for g, p, _, _ in results)
    seconds = mean(s for _, _, s, _ in timed)
    cost = sum(c for *_, c in timed) / len(timed) * 1000
    return (f"| {model} | {n} | {correct / n:.2f} | {false_refusals} | {false_answers} | {errors} | {let_through} "
            f"| {seconds:.1f} | {cost:.2f} |")


# Qualle.route answers off_topic (and forrt_lookup with FORRT_LOOKUP); the gold labels are the router's
TO_ROUTE = {"off_topic": "neither", "forrt_lookup": "forrt", "small_talk": "neither"}  # small talk is not answered
_qualle = None


def route_gold(question: dict) -> str:
    """The route label; without one (eval/forrt_questions.jsonl) from expect, else forrt; TASK for a
    task the bot should decline on an in-scope topic (kind decline_task)."""
    if question.get("kind") == TASK:
        return TASK
    return question.get("route") or {"answer": "open_science", "refuse": "neither"}.get(question.get("expect"), "forrt")


def run_router(name: str, questions: list) -> list:
    """(gold, predicted or None, seconds, cost_usd) per question for one ROUTERS strategy."""
    global _qualle
    if _qualle is None:  # the whole service: the cosine router needs the index and the FORRT pages
        from just_os.decisions import DecisionClient
        from just_os.rag_service import create_rag_service
        _qualle = create_rag_service(get_config(), None)
        _qualle.decisions = _qualle.decisions or DecisionClient(_qualle.config)
        cost = {"usd": 0.0}
        complete, decide = _qualle.client_manager.create_chat_completion, _qualle.decisions.decide

        def counted_complete(**kwargs):
            response = complete(**kwargs)
            usage = getattr(response, "usage", None)
            cost["usd"] += (getattr(usage, "cost", 0) or 0) if usage else 0
            return response

        def counted_decide(*a, **kw):
            answers, info = decide(*a, **kw)
            cost["usd"] += info.get("cost") or 0
            return answers, info

        _qualle.client_manager.create_chat_completion = counted_complete
        _qualle.decisions.decide = counted_decide
        _qualle.cost = cost
    results = []
    for q in questions:
        _qualle.cost["usd"], start = 0.0, time.time()
        predicted = _qualle.route(q["question"], name)
        results.append((route_gold(q), TO_ROUTE.get(predicted, predicted), time.time() - start, _qualle.cost["usd"]))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", help="comma separated OpenRouter ids (the LLM classifier, GENERAL_MODEL)")
    parser.add_argument("--routers", help="comma separated ROUTERS keys (clef-flash,clef,jev,llm,cosine,none): "
                        "the whole topic check, scored against the 4 route labels")
    parser.add_argument("--questions", default="eval/questions.jsonl", help="comma separated .jsonl files")
    parser.add_argument("--intent", action="store_true", help="3 classes (open_science, forrt_lookup, off_topic)")
    args = parser.parse_args()
    if not (args.models or args.routers):
        parser.error("give --models or --routers")

    questions = [json.loads(line) for path in args.questions.split(",") for line in open(path, encoding="utf-8")]
    # One row per model and question, for the /eval page (just_os/eval_report.py)
    out = Path("eval/results") / f"classify_{datetime.now():%y%m%d-%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    f = open(out, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)
    writer.writerow(["model", "id", "gold", "predicted", "seconds", "usd"])
    print("| Classifier | n | Accuracy | False refusals | False answers | Errors | Tasks let through | Mean s | USD / 1k q |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name in [r.strip() for r in (args.routers or "").split(",") if r.strip()]:
        results = run_router(name, questions)
        print(summarize(f"router: {name}", results), flush=True)
        writer.writerows([f"router: {name}", q.get("id", ""), g, p or "", round(s, 2), c]
                         for q, (g, p, s, c) in zip(questions, results))
        f.flush()
    for model in [m.strip() for m in (args.models or "").split(",") if m.strip()]:
        config = {**get_config(), "GENERAL_MODEL": model}
        manager = OpenAIClientManager(config)
        cost = {"usd": 0.0}
        complete = manager.create_chat_completion

        def counted(**kwargs):
            response = complete(**kwargs)
            usage = getattr(response, "usage", None)
            cost["usd"] += (getattr(usage, "cost", 0) or 0) if usage else 0
            return response

        manager.create_chat_completion = counted
        processor = QueryProcessor(manager, config, chat_manager=None)
        results = []
        for q in questions:
            cost["usd"], start = 0.0, time.time()
            predicted = predict(processor, q["question"], args.intent)
            results.append((gold(q, args.intent), predicted, time.time() - start, cost["usd"]))
        print(summarize(model, results), flush=True)
        writer.writerows([model, q["id"], g, p or "", round(s, 2), c] for q, (g, p, s, c) in zip(questions, results))
        f.flush()
    f.close()
    print(f"-> {out}")


if __name__ == "__main__":
    main()
