"""Classifier comparison (issue E3, #9): which GENERAL_MODEL decides best what to answer?

    docker compose exec web python eval/classify.py --models openai/gpt-oss-20b,qwen/qwen3.7-flash
    docker compose exec web python eval/classify.py --models ... --intent   # 3 classes (FORRT_LOOKUP)

Runs only the classify step (no retrieval, no index needed) on eval/questions.jsonl.
"expect": answer → should be open science; refuse → should not. With --intent, an
optional "intent" field in a question gives the gold class (default: from "expect").
Prints a Markdown table: accuracy, false refusals, false answers, errors, time, cost.
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
from just_os.qualle import OpenAIClientManager, QueryProcessor  # noqa: E402


def gold(question: dict, intent: bool) -> str:
    if intent and question.get("intent"):
        return question["intent"]
    return "open_science" if question["expect"] == "answer" else "off_topic"


def predict(processor: QueryProcessor, text: str, intent: bool):
    if intent:
        return processor.classify_intent(text)
    result = processor.classify_query(text)
    return None if result is None else ("open_science" if result else "off_topic")


def summarize(model: str, results: list) -> str:
    """results: (gold, predicted or None, seconds, cost_usd) per question."""
    n = len(results)
    errors = sum(p is None for _, p, _, _ in results)
    correct = sum(g == p for g, p, _, _ in results)
    false_refusals = sum(g == "open_science" and p not in (None, "open_science") for g, p, _, _ in results)
    false_answers = sum(g != "open_science" and p == "open_science" for g, p, _, _ in results)
    seconds = mean(s for _, _, s, _ in results)
    cost = sum(c for *_, c in results) / n * 1000
    return f"| {model} | {n} | {correct / n:.2f} | {false_refusals} | {false_answers} | {errors} | {seconds:.1f} | {cost:.2f} |"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, help="comma separated OpenRouter ids")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--intent", action="store_true", help="3 classes (open_science, forrt_lookup, off_topic)")
    args = parser.parse_args()

    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    # One row per model and question, for the /eval page (just_os/eval_report.py)
    out = Path("eval/results") / f"classify_{datetime.now():%y%m%d-%H%M}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    f = open(out, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)
    writer.writerow(["model", "id", "gold", "predicted", "seconds", "usd"])
    print("| Classifier | n | Accuracy | False refusals | False answers | Errors | Mean s | USD / 1k q |")
    print("|---|---|---|---|---|---|---|---|")
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
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
