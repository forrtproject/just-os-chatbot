"""Compare embedding models on retrieval only (no LLM).

All models use the same chunks (the production index). For models with an index
folder, the chunk vectors come from that index. For the others, the chunk vectors are
computed once and cached in data/processed/emb_cache/.

    python eval/compare_embeddings.py            # all models
    python eval/compare_embeddings.py E2 E4      # some models
    python eval/compare_embeddings.py --real     # the bot's questions with an expected DOI instead
Output: eval/results/embeddings_<YYMMDD>.csv (one row per model and language, with the query prefix used,
95% bootstrap intervals of hit@5 and the paired difference to E3 bge-m3) and embeddings-ranks_<YYMMDD>.csv
(the rank of the expected document per model and question); --real writes embeddings-real_*.csv instead
"""

import argparse
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import torch
from dotenv import load_dotenv
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from openai import OpenAI

# Frozen copies from before the cluster PDFs (#17): the emb_cache vectors are for these 59,473 chunks
SOURCE_INDEX = "data/processed/vs_261111_bge-small-en-v1.5_before_clusters"
QUESTIONS = "eval/retrieval_questions.jsonl"
REAL_QUESTIONS = "eval/questions.jsonl"
CACHE = Path("data/processed/emb_cache")
QWEN_QUERY = "Instruct: Given a question, retrieve passages that answer the question\nQuery: "
TOP_K = 20

# query/text: prefixes the model needs. None = the llama-index default (what the bot uses now).
MODELS = {
    "E1": {"name": "BAAI/bge-small-en-v1.5", "index": SOURCE_INDEX},
    "E2": {"name": "intfloat/multilingual-e5-small", "query": "query: ", "text": "passage: "},
    "E3": {"name": "BAAI/bge-m3", "index": "data/processed/vs_261111_bge-m3_before_clusters"},
    "E4": {"name": "Qwen/Qwen3-Embedding-0.6B", "query": QWEN_QUERY},
    "E5": {"name": "qwen/qwen3-embedding-4b", "api": True, "query": QWEN_QUERY},
    "E6": {"name": "qwen/qwen3-embedding-8b", "api": True, "query": QWEN_QUERY},
    # 13 Nov: OpenScholar's own retriever (Contriever, mean pooling, no prefixes), a scientific ModernBERT
    # model, and Snowflake's multilingual arctic-embed (custom code, "query: " on questions, CLS pooling)
    "E7": {"name": "OpenSciLM/OpenScholar_Retriever"},
    "E8": {"name": "J0nasW/sciembed-full"},
    "E9": {"name": "Snowflake/snowflake-arctic-embed-m-v2.0", "query": "query: ", "trust_remote_code": True,
           # its code asks for xformers (a GPU attention library) unless these config values are off
           "config_kwargs": {"use_memory_efficient_attention": False}},
    # Voyage 4 (#57): one embedding space for the series, so the library can be embedded once with the large
    # API model and each question with the small local one. OpenRouter returns 1024 dimensions for -large;
    # voyage-4-nano (Matryoshka) gives 2048, cut to the first 1024. "voyage": send input_type document/query
    "E10": {"name": "mongodb/voyage-4-large", "api": True, "voyage": True, "query": ""},
    "E11": {"name": "mongodb/voyage-4-large", "api": True, "voyage": True, "query": "",
            "query_model": {"name": "MongoDB/voyage-4-nano", "trust_remote_code": True,
                            "query": "Represent the query for retrieving supporting documents: "}},
}


def load_chunks():
    nodes = json.load(open(f"{SOURCE_INDEX}/docstore.json", encoding="utf-8"))["docstore/data"]
    ids = list(nodes)
    texts = [nodes[i]["__data__"]["text"] for i in ids]
    docs = {i: nodes[i]["__data__"]["relationships"]["1"]["node_id"] for i in ids}
    return ids, texts, docs


def normalize(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def local_model(spec, device):
    if "config_kwargs" in spec:
        return SentenceTransformerModel(spec, device)
    kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
    return HuggingFaceEmbedding(
        model_name=spec["name"], query_instruction=spec.get("query"),
        text_instruction=spec.get("text"), embed_batch_size=32, device=device,
        model_kwargs=kwargs, trust_remote_code=spec.get("trust_remote_code", False),
    )


class SentenceTransformerModel:
    """For a model that needs config values changed at load (E9); the llama-index wrapper has no such option."""

    def __init__(self, spec, device):
        from sentence_transformers import SentenceTransformer

        self.spec = spec
        self.model = SentenceTransformer(spec["name"], device=device, trust_remote_code=spec.get("trust_remote_code", False),
                                         config_kwargs=spec["config_kwargs"])

    def get_text_embedding_batch(self, texts, show_progress=False):
        return self.model.encode([self.spec.get("text", "") + t for t in texts], batch_size=32,
                                 show_progress_bar=show_progress).tolist()

    def get_query_embedding(self, query):
        return self.model.encode([self.spec.get("query", "") + query])[0].tolist()


class ApiModel:
    def __init__(self, spec):
        self.spec = spec
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
        self.cost = 0.0

    def _embed(self, texts, input_type="document"):
        extra = {"extra_body": {"input_type": input_type}} if self.spec.get("voyage") else {}
        for attempt in range(6):
            try:
                r = self.client.embeddings.create(model=self.spec["name"], input=texts, **extra)
                self.cost += getattr(r.usage, "cost", 0) or 0
                return [d.embedding for d in r.data]
            except Exception as e:
                print(f"  API error (try {attempt + 1}): {e}")
                time.sleep(2**attempt)
        raise RuntimeError("API failed 6 times")

    def get_text_embedding_batch(self, texts, show_progress=False):
        batches = [texts[i : i + 64] for i in range(0, len(texts), 64)]
        out = []
        with ThreadPoolExecutor(8) as pool:
            for n, vectors in enumerate(pool.map(self._embed, batches)):
                out += vectors
                if show_progress and n % 50 == 0:
                    print(f"  {len(out)}/{len(texts)} chunks, cost so far {self.cost:.3f} USD")
        return out

    def get_query_embedding(self, query):
        return self._embed([self.spec["query"] + query], "query")[0]


def chunk_vectors(key, spec, ids, texts):
    if "index" in spec:
        index = faiss.read_index(f"{spec['index']}/default__vector_store.json")
        store = json.load(open(f"{spec['index']}/index_store.json", encoding="utf-8"))
        nodes_dict = json.loads(next(iter(store["index_store/data"].values()))["__data__"])["nodes_dict"]
        order = {node_id: int(row) for row, node_id in nodes_dict.items()}
        vectors = index.reconstruct_n(0, index.ntotal)
        return normalize(vectors[[order[i] for i in ids]])
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{spec['name'].replace('/', '__')}.npy"
    if path.exists():
        return normalize(np.load(path))
    model = ApiModel(spec) if spec.get("api") else local_model(spec, "cuda" if torch.cuda.is_available() else "cpu")
    t = time.time()
    vectors = normalize(model.get_text_embedding_batch(texts, show_progress=True))
    print(f"  embedded {len(texts)} chunks in {(time.time() - t) / 60:.1f} min"
          + (f", cost {model.cost:.3f} USD" if spec.get("api") else ""))
    np.save(path, vectors.astype(np.float16))
    return vectors


def query_model(spec):
    # The web server has no GPU: measure question time on the CPU
    if "query_model" in spec:  # questions embedded by another model of the same vector space (E11)
        return local_model(spec["query_model"], "cpu")
    return ApiModel(spec) if spec.get("api") else local_model(spec, "cpu")


def real_questions(docstore_path=f"{SOURCE_INDEX}/docstore.json", path=REAL_QUESTIONS):
    """The bot's eval questions with an expected DOI that is in SOURCE_INDEX; a hit is any document with that DOI.
    Caveat: expected_dois were picked partly from bge-m3 search results, which can favour bge-m3."""
    from just_os.references import normalize_doi

    by_doi = defaultdict(set)
    for node in json.load(open(docstore_path, encoding="utf-8"))["docstore/data"].values():
        doi = node["__data__"]["metadata"].get("doi")
        if isinstance(doi, dict):  # a few documents store it as a one-item dict
            doi = next(iter(doi.values()), None)
        if doi := normalize_doi(doi):
            by_doi[doi].add(node["__data__"]["relationships"]["1"]["node_id"])
    out = []
    for line in open(path, encoding="utf-8"):
        q = json.loads(line)
        targets = set().union(*(by_doi.get(normalize_doi(d), set()) for d in q.get("expected_dois") or []))
        if targets:
            out.append({"id": q["id"], "lang": q.get("lang", "en"), "question": q["question"], "targets": targets})
    return out


def query_prefix(spec):
    """The prefix the question really got (llama-index adds its own BGE instruction when none is given)."""
    if "query_model" in spec:
        return spec["query_model"].get("query", "")
    if spec.get("voyage"):
        return "input_type=query"
    if spec.get("api") or "config_kwargs" in spec or "query" in spec:
        return spec.get("query") or ""
    from llama_index.embeddings.huggingface.utils import get_query_instruct_for_model_name
    return get_query_instruct_for_model_name(spec["name"])


def bootstrap(hits, base=None, n=2000, seed=0):
    """95% interval of the mean of 0/1 hits, and of the paired difference to base (same questions)."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(hits), (n, len(hits)))
    lo, hi = np.percentile(hits[idx].mean(1), [2.5, 97.5])
    if base is None:
        return lo, hi, None, None, None
    diff = hits - base
    dlo, dhi = np.percentile(diff[idx].mean(1), [2.5, 97.5])
    return lo, hi, diff.mean(), dlo, dhi


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("keys", nargs="*", help=f"models: {', '.join(MODELS)} (default all)")
    parser.add_argument("--real", action="store_true",
                        help="the bot's eval questions with an expected DOI (eval/questions.jsonl) instead of "
                             "eval/retrieval_questions.jsonl; results go to embeddings-real_<date>.csv")
    args = parser.parse_args()
    keys = args.keys or list(MODELS)
    if args.real:
        questions = real_questions()
    else:
        questions = [json.loads(line) for line in open(QUESTIONS, encoding="utf-8")]
        for q in questions:
            q["targets"] = {q["doc_id"]}
    ids, texts, docs = load_chunks()
    rows, ranks_out = [], []
    for key in keys:
        spec = MODELS[key]
        print(f"{key} {spec['name']}")
        C = chunk_vectors(key, spec, ids, texts)
        model = query_model(spec)
        t = time.time()
        Q = np.asarray([model.get_query_embedding(q["question"]) for q in questions], dtype=np.float32)
        Q = normalize(Q[:, : C.shape[1]])  # a Matryoshka question model can give more dimensions than the chunks
        ms_per_query = (time.time() - t) / len(questions) * 1000
        top = np.argsort(-(Q @ C.T), axis=1)[:, :200]
        by_lang = defaultdict(list)
        for q, row in zip(questions, top):
            ranked = list(dict.fromkeys(docs[ids[i]] for i in row))[:TOP_K]  # document level
            rank = next((n + 1 for n, d in enumerate(ranked) if d in q["targets"]), None)
            by_lang[q["lang"]].append(rank)
            by_lang["all"].append(rank)
            if q["lang"] != "en":
                by_lang["non-en"].append(rank)
            ranks_out.append({"model": key, "id": q["id"], "lang": q["lang"], "rank": rank})
        for lang, ranks in by_lang.items():
            rows.append({
                "model": key, "name": spec["name"], "lang": lang, "n": len(ranks),
                "hit@1": np.mean([r is not None and r <= 1 for r in ranks]),
                "hit@5": np.mean([r is not None and r <= 5 for r in ranks]),
                "hit@20": np.mean([r is not None for r in ranks]),
                "mrr@20": np.mean([1 / r if r else 0 for r in ranks]),
                "ms_per_query": ms_per_query, "dim": C.shape[1], "query_prefix": query_prefix(spec),
            })
        print(pd.DataFrame([r for r in rows if r["model"] == key]).round(3).to_string(index=False))

    stem = "embeddings-real" if args.real else "embeddings"  # /eval reads only embeddings_*.csv
    out = Path(f"eval/results/{stem}_{datetime.now():%y%m%d}.csv")
    ranks_file = out.with_name(f"{stem}-ranks_{datetime.now():%y%m%d}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    ranks = pd.DataFrame(ranks_out)
    if ranks_file.exists():
        old = pd.read_csv(ranks_file)
        ranks = pd.concat([old[~old.model.isin(keys)], ranks])
    ranks.to_csv(ranks_file, index=False)
    df = pd.DataFrame(rows)
    if out.exists():  # keep results of models not run this time
        old = pd.read_csv(out)
        df = pd.concat([old[~old.model.isin(keys)], df])
    # 95% bootstrap intervals for hit@5, and the paired difference to bge-m3 (E3) on the same questions
    hit5 = {m: g.set_index("id")["rank"].le(5).astype(float) for m, g in ranks.groupby("model")}
    for i, r in df.iterrows():
        if r["model"] not in hit5:
            continue
        h = hit5[r["model"]]
        sel = h.index if r["lang"] == "all" else ranks[(ranks.model == r["model"]) & (
            (ranks.lang != "en") if r["lang"] == "non-en" else (ranks.lang == r["lang"]))]["id"]
        base = hit5["E3"].reindex(sel).to_numpy() if "E3" in hit5 and r["model"] != "E3" else None
        lo, hi, diff, dlo, dhi = bootstrap(h.reindex(sel).to_numpy(), base)
        df.loc[i, ["hit@5_lo", "hit@5_hi", "hit@5_vs_E3", "vs_E3_lo", "vs_E3_hi"]] = [lo, hi, diff, dlo, dhi]
    df.sort_values(["lang", "model"]).round(4).to_csv(out, index=False)
    print(f"wrote {out} and {ranks_file}")
