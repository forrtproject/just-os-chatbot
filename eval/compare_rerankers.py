"""Compare re-ranking setups on retrieval only (no LLM), with the time of each step.

Every arm starts from the production index (VECTOR_STORE) and its top RETRIEVER_TOP_K chunks.
The arms differ in the candidates, their order and the "no sources" gate:

    vec                   vector order
    vec+cos               vector order; no sources when the best cosine is below --cosine-gate
    hyb                   HYBRID_SEARCH: vector and BM25 lists merged by reciprocal rank fusion
    <vec|hyb>+<reranker>  ordered by a CrossEncoder (base, v2m3)
    ... gated             and chunks scoring <= MIN_RELEVANCE dropped; production is "vec+base gated"

A hit: a chunk of the question's document is among the first k chunks (MAX_CHUNKS = 7 is what
the answer model sees). Questions: eval/retrieval_questions.jsonl. A gate check prints the best
cosine and re-ranker score of the eval/questions.jsonl questions by expected outcome.

    python eval/compare_rerankers.py                                     # quality, GPU if present
    python eval/compare_rerankers.py --device cpu --threads 6 --limit 30 # time on CPU, no gate check
Output: eval/results/rerankers_<YYMMDD>_<device>.csv (one row per arm and language)
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import torch
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from sentence_transformers import CrossEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_config  # noqa: E402
from just_os.hybrid import BM25, reciprocal_rank_fusion  # noqa: E402

RERANKERS = {"base": "BAAI/bge-reranker-base", "v2m3": "BAAI/bge-reranker-v2-m3"}


def load_index(path):
    store = json.load(open(f"{path}/docstore.json", encoding="utf-8"))["docstore/data"]
    index_store = json.load(open(f"{path}/index_store.json", encoding="utf-8"))["index_store/data"]
    nodes_dict = json.loads(next(iter(index_store.values()))["__data__"])["nodes_dict"]
    index = faiss.read_index(f"{path}/default__vector_store.json")
    chunks = {i: n["__data__"] for i, n in store.items()}
    return index, {int(row): node_id for row, node_id in nodes_dict.items()}, chunks


def timed(times, step, fn, *args):
    start = time.perf_counter()
    out = fn(*args)
    times[step] = times.get(step, 0.0) + time.perf_counter() - start
    return out


def retrieve(q, ctx):
    """Candidates, scores and the time of each step for one question."""
    times = {}
    vector = timed(times, "embed", ctx["embedder"].get_query_embedding, q)
    vector = np.asarray([vector], dtype=np.float32)
    dist, rows = timed(times, "faiss", ctx["index"].search, vector, ctx["top_k"])
    vec = [ctx["row_to_id"][int(r)] for r in rows[0]]
    # The stored vectors have length 1, so for an L2 index cosine = 1 - distance^2 / 2
    l2 = ctx["index"].metric_type == faiss.METRIC_L2
    cosine = dict(zip(vec, (1 - dist[0] / 2) if l2 else dist[0]))
    keyword = timed(times, "bm25", ctx["bm25"].top, q, ctx["top_k"])
    keyword_ids = [ctx["node_ids"][i] for i in keyword]
    hyb = timed(times, "bm25", reciprocal_rank_fusion, vec, keyword_ids)[: ctx["top_k"]]
    scores = {}
    for name, model in ctx["rerankers"].items():
        for cands_name, cands in (("vec", vec), ("hyb", hyb)):
            pairs = [(q, ctx["text"](c)) for c in cands]
            s = timed(times, f"{name}_{cands_name}", model.predict, pairs)
            scores.setdefault(name, {}).update(zip(cands, map(float, s)))
    return {"vec": vec, "hyb": hyb, "cosine": cosine, "scores": scores, "times": times}


def arms(rerankers):
    out = ["vec", "vec+cos", "hyb"]
    for gate in ("", " gated"):
        out += [f"{c}+{r}{gate}" for r in rerankers for c in ("vec", "hyb")]
    return out


def ranked(r, arm, args, config):
    cands, _, rest = arm.partition("+")
    chunks = r[cands]
    if rest == "cos":
        return chunks if max(r["cosine"].values()) >= args.cosine_gate else []
    if rest:
        model, gated = rest.split(" ")[0], rest.endswith("gated")
        chunks = sorted(chunks, key=lambda c: -r["scores"][model][c])
        if gated:
            chunks = [c for c in chunks if r["scores"][model][c] > config["MIN_RELEVANCE"]]
    return chunks


def arm_seconds(t, arm):
    cands, _, rest = arm.partition("+")
    s = t["embed"] + t["faiss"] + (t["bm25"] if cands == "hyb" else 0)
    if rest and rest != "cos":
        s += t[f"{rest.split(' ')[0]}_{cands}"]
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--threads", type=int, help="CPU threads (production: RERANK_THREADS)")
    parser.add_argument("--limit", type=int, help="every n-th question so that N remain, all languages")
    parser.add_argument("--rerankers", default="base,v2m3")
    parser.add_argument("--cosine-gate", type=float, default=0.55)
    args = parser.parse_args()
    if args.threads:
        torch.set_num_threads(args.threads)
    config = get_config()

    index, row_to_id, chunks = load_index(config["VECTOR_STORE"])
    node_ids = list(chunks)
    doc_of = {i: c["relationships"]["1"]["node_id"] for i, c in chunks.items()}
    titles = {i: c["metadata"].get("title", "Unknown Title") for i, c in chunks.items()}
    t = time.time()
    bm25 = BM25([chunks[i]["text"] for i in node_ids])
    print(f"BM25 index built in {time.time() - t:.1f} s")
    half = {"torch_dtype": torch.float16} if args.device == "cuda" else {}
    ctx = {
        "index": index, "row_to_id": row_to_id, "node_ids": node_ids, "bm25": bm25,
        "top_k": config["RETRIEVER_TOP_K"],
        "embedder": HuggingFaceEmbedding(model_name=config["EMBEDDING_MODEL"], device=args.device),
        "rerankers": {
            name: CrossEncoder(RERANKERS[name], device=args.device, model_kwargs=half)
            for name in args.rerankers.split(",")
        },
        # what production's re-ranker reads (DocumentRetriever.node_to_text)
        "text": lambda c: f"Title: {titles[c]} Text: {' '.join(chunks[c]['text'].split())}",
    }
    for model in ctx["rerankers"].values():  # load the weights before timing
        model.predict([("warm up", "warm up")])
    ctx["embedder"].get_query_embedding("warm up")

    questions = [json.loads(line) for line in open("eval/retrieval_questions.jsonl", encoding="utf-8")]
    if args.limit:
        questions = questions[:: max(1, len(questions) // args.limit)][: args.limit]
    results = []
    for n, q in enumerate(questions):
        results.append({"q": q, **retrieve(q["question"], ctx)})
        if n % 50 == 0:
            print(f"{n}/{len(questions)}", flush=True)

    rows, hits7 = [], {}
    for arm in arms(ctx["rerankers"]):
        firsts = []
        for r in results:
            docs = [doc_of[c] for c in ranked(r, arm, args, config)]
            firsts.append(docs.index(r["q"]["doc_id"]) + 1 if r["q"]["doc_id"] in docs else None)
        hits7[arm] = np.array([f is not None and f <= 7 for f in firsts], dtype=float)
        seconds = np.array([arm_seconds(r["times"], arm) for r in results])
        for lang in ("all", "en", "nl", "de", "es"):
            sel = [i for i, r in enumerate(results) if lang in ("all", r["q"]["lang"])]
            f = [firsts[i] for i in sel]
            rows.append({
                "arm": arm, "lang": lang, "n": len(sel),
                "hit@5": np.mean([x is not None and x <= 5 for x in f]),
                "hit@7": np.mean([x is not None and x <= 7 for x in f]),
                "mrr": np.mean([1 / x if x else 0 for x in f]),
                "no_sources": sum(not ranked(results[i], arm, args, config) for i in sel),
                "ms_mean": 1000 * seconds[sel].mean(), "ms_p95": 1000 * np.percentile(seconds[sel], 95),
                "device": args.device, "threads": torch.get_num_threads(),
            })
    df = pd.DataFrame(rows)
    print(df[df.lang == "all"].drop(columns=["lang", "device", "threads"]).round(3).to_string(index=False))

    rng = np.random.default_rng(0)
    print("\nhit@7 difference against vec, paired bootstrap 95% interval")
    for arm, h in hits7.items():
        d = h - hits7["vec"]
        boot = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
        print(f"{arm:16} {d.mean():+.3f} [{np.percentile(boot, 2.5):+.3f}, {np.percentile(boot, 97.5):+.3f}]")

    out = Path(f"eval/results/rerankers_{datetime.now():%y%m%d}_{args.device}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(out, index=False)
    print(f"wrote {out}")
    if args.limit:  # a timing run: skip the gate check
        return

    print("\ngate check on eval/questions.jsonl: best score per question")
    pipe = [json.loads(line) for line in open("eval/questions.jsonl", encoding="utf-8")]
    scored = [(q, retrieve(q["question"], ctx)) for q in pipe]
    getters = {"cosine": lambda r: max(r["cosine"].values())}
    getters.update({m: (lambda r, m=m: max(r["scores"][m][c] for c in r["vec"])) for m in ctx["rerankers"]})
    for name, get in getters.items():
        for expect in ("answer", "refuse"):
            v = np.array([get(r) for q, r in scored if q["expect"] == expect])
            print(f"{name:7} {expect:6} n={len(v):2} min {v.min():.3f} median {np.median(v):.3f} max {v.max():.3f}")


if __name__ == "__main__":
    main()
