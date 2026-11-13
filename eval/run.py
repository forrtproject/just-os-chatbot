"""Run the full chat pipeline on the eval questions and write one CSV per run.

Runs in the web container (it needs the index, the models and Redis):

    docker compose exec web python eval/run.py --model openai/gpt-oss-20b
    docker compose exec web python eval/run.py --model openai/gpt-oss-20b --limit 5

--no-retrieval asks the answer model the question directly, with no sources and no
classifier, to measure what the model knows without the library. --skip-classifier
treats every question as open science, so items about research methods are answered
while the classifier is being changed; use it only for questions that all expect an answer.

--model changes the answer model (CITATION_MODEL). The classify/rephrase model
(GENERAL_MODEL) stays as configured unless --general-model is given, so a run
compares answer models only. Output: eval/results/run_<YYMMDD-HHMM>_<model>.csv
"""

import argparse
import csv
import hashlib
import json
import pickle
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
from just_os.references import normalize_doi, plain_metadata  # noqa: E402

FIELDS = [
    "id", "lang", "cluster", "type", "route", "expect", "outcome", "answered_from", "correct", "hit", "n_citations",
    "citations_valid", "seconds", "classify_s", "search_s", "rerank_s", "answer_s",
    "prompt_tokens", "completion_tokens", "cost_usd", "retrieval",
    "retrieved_dois", "question", "answer", "passages", "sources",
]


def retrieval_label(config):
    """The search and ranking a run used, such as "hybrid+rerank" or "vector, cos>=0.55"."""
    mode = config.get("SEARCH_MODE", "vector")
    if config.get("RERANK", True):
        return f"{mode}+rerank"
    gate = config.get("MIN_VECTOR_SIMILARITY", 0) if mode != "bm25" else 0
    return f"{mode}, cos>={gate}" if gate else mode


def outcome_of(final):
    if final.get("status") == "error":
        return "error"
    # Refusals are in the language of the question (config/refusals.csv)
    text = final.get("message", "")
    if any(t in text for t in all_texts("off_topic")):
        return "refused"
    if any(t in text for t in all_texts("about")):  # the self-introduction for small talk
        return "small_talk"
    if any(t in text for t in all_texts("no_sources")):
        return "no_sources"
    if any(t in text for t in all_texts("generation_error") + all_texts("unexpected_error")):
        return "error"  # the answer model returned nothing: was counted as answered
    return "answered"


def answer_source(seen, refs):
    """Where the answer came from ("forrt pages", "papers" or "") and whether every [n] in it
    points to one of its sources: forrt.org pages are numbered from 1, while the answer model
    sees the papers numbered 0..len-1."""
    if seen.get("forrt") is not None:
        return "forrt pages", all(1 <= r <= len(seen["forrt"]["sources"]) for r in refs)
    return ("papers" if seen["ranked"] else ""), all(0 <= r < len(seen["ranked"]) for r in refs)


def hit_of(q, ranked_dois, forrt):
    """1 when an expected DOI is among the ranked papers or an expected URL among the FORRT pages the
    answer used (eval/forrt_questions.jsonl has expected_urls only); "" when the question expects neither."""
    expected = [d.lower() for d in q.get("expected_dois", [])]
    urls = {u.rstrip("/").lower() for u in q.get("expected_urls", [])}
    if not expected and not urls:
        return ""
    pages = {s["url"].rstrip("/").lower() for s in (forrt or {}).get("sources", [])}
    return int(any(d in ranked_dois for d in expected) or bool(urls & pages))


def passages_of(seen, limit=800):
    """The text each [n] of the answer points to: the paper chunks (numbered from 0) or, for an answer
    from the FORRT pages, the page excerpts (numbered from 1). limit 0 keeps the whole text."""
    if seen.get("forrt") is not None:
        texts = [s.get("excerpt", "") for s in seen["forrt"]["sources"]]
    else:
        texts = [n.text for n in seen["ranked"]]
    return [" ".join(t.split())[: limit or None] for t in texts]


def sources_of(seen):
    if seen.get("forrt") is not None:
        return [{"n": s["n"], "title": s["title"], "url": s["url"]} for s in seen["forrt"]["sources"]]
    out = []
    for i, node in enumerate(seen["ranked"]):
        meta = plain_metadata(node.metadata)
        out.append({"n": i, "title": meta.get("title", ""), "doi": doi_of(node), "url": meta.get("link_to_resource", "")})
    return out


def doi_of(node) -> str:
    """The node's bare DOI, or "". Unwraps the dict values of the 10 documents from #24,
    which would otherwise never match an expected DOI and contain a space."""
    return normalize_doi(plain_metadata(node.metadata).get("doi")) or ""


DIRECT_PROMPT = (
    "You answer questions about open science and research methods. Answer in about "
    "150-250 words, in the language of the question."
)


def answer_directly(qualle, config, question, seen):
    """The answer model alone, with no sources: the baseline for what the library adds."""
    response = qualle.client_manager.create_chat_completion(
        model=config["CITATION_MODEL"],
        messages=[{"role": "system", "content": DIRECT_PROMPT}, {"role": "user", "content": question}],
        temperature=config["TEMPERATURE"],
    )
    if response is None:
        return {"status": "error", "message": ""}
    seen["raw"] = response.choices[0].message.content or ""
    return {"message": seen["raw"]}


def split_provider(model):
    """"openai/gpt-oss-120b@deepinfra/bf16" -> ("openai/gpt-oss-120b", OpenRouter provider routing that
    allows only that provider); a model without "@" -> (model, None)."""
    base, _, provider = model.partition("@")
    return base, ({"order": [provider], "allow_fallbacks": False} if provider else None)


def pin_provider(qualle, model, provider):
    """Send every call for `model` (answers and FORRT-page answers) to one OpenRouter provider only."""
    completions = qualle.client_manager.client.chat.completions
    create = completions.create

    def pinned(*args, **kwargs):
        if kwargs.get("model") == model:
            kwargs["extra_body"] = {**(kwargs.get("extra_body") or {}), "provider": provider}
        return create(*args, **kwargs)

    completions.create = pinned


def skip_classifier(qualle, route="open_science"):
    """Send every question one way (the papers, or with route="forrt" the FORRT pages), with no
    call to the decision model or the classifier. eval/pairs.py combines one run per way with each
    topic check's decisions (eval/classify.py), so every topic check x answer model pair is scored."""
    qualle.route = lambda query, router=None: route


def cache_retrieval(qualle, config, folder=Path("eval/.retrieval_cache")):
    """Keep the ranked chunks per question and retrieval settings on disk, so the re-ranker
    (4-15 s per question on CPU) runs once for all answer models. Cached questions have no
    search_s/rerank_s, so their seconds are answer time only."""
    retrieve = qualle.document_retriever.retrieve_and_rerank
    settings = json.dumps([retrieval_label(config), config.get("VECTOR_STORE"), config.get("RETRIEVER_TOP_K"),
                           config.get("MAX_CHUNKS"), config.get("MIN_RELEVANCE"), config.get("MAX_CHUNKS_PER_DOC"),
                           config.get("ADAPTIVE_TOP_K"), config.get("EMBEDDING_MODEL")])
    folder.mkdir(parents=True, exist_ok=True)

    def cached(query, *args, **kwargs):
        path = folder / f"{hashlib.sha1((settings + query).encode('utf-8')).hexdigest()}.pkl"
        if path.exists():
            return pickle.loads(path.read_bytes())
        result = retrieve(query, *args, **kwargs)
        path.write_bytes(pickle.dumps(result))
        return result

    qualle.document_retriever.retrieve_and_rerank = cached


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="answer model (CITATION_MODEL)")
    parser.add_argument("--general-model", help="classify/rephrase model (GENERAL_MODEL)")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--no-retrieval", action="store_true", help="answer without sources")
    parser.add_argument("--full-answers", action="store_true",
                        help="keep the whole answer (default: the first 2000 characters)")
    parser.add_argument("--out", help="output CSV (default eval/results/run_<time>_<model>.csv)")
    parser.add_argument("--skip-classifier", action="store_true", help="treat every question as open science")
    parser.add_argument("--route", choices=["open_science", "forrt"], help="send every question this way (no topic check)")
    parser.add_argument("--cache-retrieval", action="store_true", help="reuse ranked chunks across runs (eval/.retrieval_cache)")
    args = parser.parse_args()

    config = get_config()
    if args.model:
        config["CITATION_MODEL"], provider = split_provider(args.model)
    if args.general_model:
        config["GENERAL_MODEL"] = args.general_model
    qualle = create_rag_service(config, ChatManager())
    if args.model and provider:
        pin_provider(qualle, config["CITATION_MODEL"], provider)
    if args.skip_classifier or args.route:
        skip_classifier(qualle, args.route or "open_science")
    if args.cache_retrieval:
        cache_retrieval(qualle, config)

    # Record what each step did, without changing the pipeline
    seen = {}
    retrieve = qualle.document_retriever.retrieve_and_rerank
    generate = qualle.response_generator.generate_response
    complete = qualle.client_manager.create_chat_completion

    def record_retrieve(query, *args, **kwargs):
        seen["ranked"], all_nodes = retrieve(query, *args, **kwargs)
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

    # A question the topic check sends to forrt.org is answered by ForrtPages, not by the
    # answer step above: record its text and sources too
    if qualle.forrt_pages is not None:
        forrt_answer = qualle.forrt_pages.answer

        def record_forrt(*a, **kw):
            seen["forrt"] = forrt_answer(*a, **kw)
            seen["raw"] = seen["forrt"]["text"]
            return seen["forrt"]

        qualle.forrt_pages.answer = record_forrt

    questions = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    questions = questions[: args.limit] if args.limit else questions

    out = Path(args.out) if args.out else Path("eval/results") / (
        f"run_{datetime.now():%y%m%d-%H%M}_{(args.model or config['CITATION_MODEL']).replace('/', '__')}"
        f"{'_noretrieval' if args.no_retrieval else ''}.csv"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for q in questions:
            q.setdefault("expect", "answer")  # eval/forrt_questions.jsonl: every question should be answered
            chat_id = f"eval-{uuid.uuid4()}"
            # Multi-turn questions: the earlier turns go first in the same chat (not scored)
            for turn in q.get("history", []):
                list(qualle.get_response(turn, chat_id))
            seen.clear()
            seen.update(ranked=[], raw=None, forrt=None, prompt_tokens=0, completion_tokens=0, cost=0.0)
            start = time.time()
            if args.no_retrieval:
                final = answer_directly(qualle, config, q["question"], seen)
            else:
                final = list(qualle.get_response(q["question"], chat_id))[-1]
            seconds = time.time() - start

            outcome = outcome_of(final)
            ranked_dois = [doi_of(n) for n in seen["ranked"]]
            refs = [int(n) for n in re.findall(r"\[(\d+)\]", seen["raw"] or "")]
            answered_from, valid = answer_source(seen, refs)
            writer.writerow({
                "id": q["id"],
                "lang": q.get("lang", "en"),
                "cluster": q.get("cluster", ""),
                "type": q.get("type", ""),
                "route": q.get("route", ""),
                "expect": q["expect"],
                "outcome": outcome,
                "answered_from": answered_from if outcome == "answered" else "",
                "correct": int((outcome == "answered") == (q["expect"] == "answer") and outcome != "error"),
                "hit": hit_of(q, ranked_dois, seen["forrt"]),
                "n_citations": len(refs),
                "citations_valid": int(valid) if refs else "",
                "seconds": round(seconds, 1),
                # the bot's own step times (Qualle.get_response "timings"); empty when a step did not run
                **{k: final.get("timings", {}).get(k, "") for k in ("classify_s", "search_s", "rerank_s", "answer_s")},
                "prompt_tokens": seen["prompt_tokens"],
                "completion_tokens": seen["completion_tokens"],
                "cost_usd": round(seen["cost"], 6),
                "retrieval": retrieval_label(config),
                "retrieved_dois": " ".join(ranked_dois),
                "question": q["question"],
                "answer": (seen["raw"] or "") if args.full_answers else (seen["raw"] or "")[:2000],
                # what the answer model saw, for eval/judge.py
                "passages": json.dumps(passages_of(seen, 0 if args.full_answers else 800)),
                # per passage its title and DOI or URL, numbered as the answer cites them (human review)
                "sources": json.dumps(sources_of(seen)),
            })
            f.flush()
            print(f"{q['id']:6} {outcome:10} {seconds:5.1f}s")

    print(f"wrote {out}")
    from compare import summarize  # same folder

    print(summarize([out]))


if __name__ == "__main__":
    main()
