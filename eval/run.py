"""Run the full chat pipeline on the eval questions and write one CSV per run.

Runs in the web container (it needs the index, the models and Redis):

    docker compose exec web python eval/run.py --model openai/gpt-oss-20b
    docker compose exec web python eval/run.py --model openai/gpt-oss-20b --limit 5

--model changes the answer model (CITATION_MODEL). The classify/rephrase model
(GENERAL_MODEL) stays as configured unless --general-model is given, so a run
compares answer models only. Output: eval/results/run_<YYMMDD-HHMM>_<model>.csv
"""

import argparse
import csv
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_config  # noqa: E402
from just_os.chat_manager import ChatManager  # noqa: E402
from just_os.messages import all_texts  # noqa: E402
from just_os.rag_service import create_rag_service  # noqa: E402

FIELDS = [
    "id", "lang", "expect", "outcome", "correct", "hit", "n_citations",
    "citations_valid", "seconds", "prompt_tokens", "completion_tokens", "cost_usd",
    "retrieved_dois", "question", "answer", "passages",
]


def outcome_of(final):
    if final.get("status") == "error":
        return "error"
    # Refusals are in the language of the question (config/refusals.csv)
    text = final.get("message", "")
    if any(t in text for t in all_texts("off_topic")):
        return "refused"
    if any(t in text for t in all_texts("no_sources")):
        return "no_sources"
    return "answered"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="answer model (CITATION_MODEL)")
    parser.add_argument("--general-model", help="classify/rephrase model (GENERAL_MODEL)")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    args = parser.parse_args()

    config = get_config()
    if args.model:
        config["CITATION_MODEL"] = args.model
    if args.general_model:
        config["GENERAL_MODEL"] = args.general_model
    qualle = create_rag_service(config, ChatManager())

    # Record what each step did, without changing the pipeline
    seen = {}
    retrieve = qualle.document_retriever.retrieve_and_rerank
    generate = qualle.response_generator.generate_response
    complete = qualle.client_manager.create_chat_completion

    def record_retrieve(query):
        seen["ranked"], all_nodes = retrieve(query)
        return seen["ranked"], all_nodes

    def record_generate(*a, **kw):
        seen["raw"] = generate(*a, **kw)
        return seen["raw"]

    def record_complete(**kw):
        response = complete(**kw)
        usage = getattr(response, "usage", None)
        if usage:
            seen["prompt_tokens"] += usage.prompt_tokens or 0
            seen["completion_tokens"] += usage.completion_tokens or 0
            seen["cost"] += getattr(usage, "cost", 0) or 0
        return response

    qualle.document_retriever.retrieve_and_rerank = record_retrieve
    qualle.response_generator.generate_response = record_generate
    qualle.client_manager.create_chat_completion = record_complete

    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    questions = questions[: args.limit] if args.limit else questions

    out = Path("eval/results") / (
        f"run_{datetime.now():%y%m%d-%H%M}_{config['CITATION_MODEL'].replace('/', '__')}.csv"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for q in questions:
            seen.clear()
            seen.update(ranked=[], raw=None, prompt_tokens=0, completion_tokens=0, cost=0.0)
            start = time.time()
            final = list(qualle.get_response(q["question"], f"eval-{uuid.uuid4()}"))[-1]
            seconds = time.time() - start

            outcome = outcome_of(final)
            ranked_dois = [str(n.metadata.get("doi", "")).lower() for n in seen["ranked"]]
            expected = [d.lower() for d in q.get("expected_dois", [])]
            refs = [int(n) for n in re.findall(r"\[(\d+)\]", seen["raw"] or "")]
            writer.writerow({
                "id": q["id"],
                "lang": q.get("lang", "en"),
                "expect": q["expect"],
                "outcome": outcome,
                "correct": int((outcome == "answered") == (q["expect"] == "answer") and outcome != "error"),
                "hit": int(any(d in ranked_dois for d in expected)) if expected else "",
                "n_citations": len(refs),
                # The model sees sources numbered 0..len-1
                "citations_valid": int(all(0 <= r < len(seen["ranked"]) for r in refs)) if refs else "",
                "seconds": round(seconds, 1),
                "prompt_tokens": seen["prompt_tokens"],
                "completion_tokens": seen["completion_tokens"],
                "cost_usd": round(seen["cost"], 6),
                "retrieved_dois": " ".join(ranked_dois),
                "question": q["question"],
                "answer": (seen["raw"] or "")[:2000],
                # what the answer model saw, for eval/judge.py
                "passages": json.dumps([" ".join(n.text.split())[:800] for n in seen["ranked"]]),
            })
            f.flush()
            print(f"{q['id']:6} {outcome:10} {seconds:5.1f}s")

    print(f"wrote {out}")
    from compare import summarize  # same folder

    print(summarize([out]))


if __name__ == "__main__":
    main()
