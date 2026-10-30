"""Compare embedding models on retrieval only (no LLM).

All models use the same chunks (the production index). For models with an index
folder, the chunk vectors come from that index. For the others, the chunk vectors are
computed once and cached in data/processed/emb_cache/.

    python eval/compare_embeddings.py            # all models
    python eval/compare_embeddings.py E2 E4      # some models
Output: eval/results/embeddings_<YYMMDD>.csv (one row per model and language)
"""

import json
import os
import sys
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

SOURCE_INDEX = "data/processed/vs_latest_bge-small-en-v1.5"
QUESTIONS = "eval/retrieval_questions.jsonl"
CACHE = Path("data/processed/emb_cache")
QWEN_QUERY = "Instruct: Given a question, retrieve passages that answer the question\nQuery: "
TOP_K = 20

# query/text: prefixes the model needs. None = the llama-index default (what the bot uses now).
MODELS = {
    "E1": {"name": "BAAI/bge-small-en-v1.5", "index": SOURCE_INDEX},
    "E2": {"name": "intfloat/multilingual-e5-small", "query": "query: ", "text": "passage: "},
    "E3": {"name": "BAAI/bge-m3", "index": "data/processed/vs_latest_bge-m3"},
    "E4": {"name": "Qwen/Qwen3-Embedding-0.6B", "query": QWEN_QUERY},
    "E5": {"name": "qwen/qwen3-embedding-4b", "api": True, "query": QWEN_QUERY},
    "E6": {"name": "qwen/qwen3-embedding-8b", "api": True, "query": QWEN_QUERY},
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
    kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
    return HuggingFaceEmbedding(
        model_name=spec["name"], query_instruction=spec.get("query"),
        text_instruction=spec.get("text"), embed_batch_size=32, device=device,
        model_kwargs=kwargs,
    )


class ApiModel:
    def __init__(self, spec):
        self.spec = spec
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
        self.cost = 0.0

    def _embed(self, texts):
        for attempt in range(6):
            try:
                r = self.client.embeddings.create(model=self.spec["name"], input=texts)
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
        return self._embed([self.spec["query"] + query])[0]


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
    return ApiModel(spec) if spec.get("api") else local_model(spec, "cpu")


if __name__ == "__main__":
    load_dotenv()
    keys = sys.argv[1:] or list(MODELS)
    questions = [json.loads(line) for line in open(QUESTIONS, encoding="utf-8")]
    ids, texts, docs = load_chunks()
    rows = []
    for key in keys:
        spec = MODELS[key]
        print(f"{key} {spec['name']}")
        C = chunk_vectors(key, spec, ids, texts)
        model = query_model(spec)
        t = time.time()
        Q = normalize([model.get_query_embedding(q["question"]) for q in questions])
        ms_per_query = (time.time() - t) / len(questions) * 1000
        top = np.argsort(-(Q @ C.T), axis=1)[:, :200]
        by_lang = defaultdict(list)
        for q, row in zip(questions, top):
            ranked = list(dict.fromkeys(docs[ids[i]] for i in row))[:TOP_K]  # document level
            rank = ranked.index(q["doc_id"]) + 1 if q["doc_id"] in ranked else None
            by_lang[q["lang"]].append(rank)
            by_lang["all"].append(rank)
        for lang, ranks in by_lang.items():
            rows.append({
                "model": key, "name": spec["name"], "lang": lang, "n": len(ranks),
                "hit@1": np.mean([r is not None and r <= 1 for r in ranks]),
                "hit@5": np.mean([r is not None and r <= 5 for r in ranks]),
                "hit@20": np.mean([r is not None for r in ranks]),
                "mrr@20": np.mean([1 / r if r else 0 for r in ranks]),
                "ms_per_query": ms_per_query, "dim": C.shape[1],
            })
        print(pd.DataFrame([r for r in rows if r["model"] == key]).round(3).to_string(index=False))

    out = Path(f"eval/results/embeddings_{datetime.now():%y%m%d}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if out.exists():  # keep results of models not run this time
        old = pd.read_csv(out)
        df = pd.concat([old[~old.model.isin(keys)], df])
    df.sort_values(["lang", "model"]).round(4).to_csv(out, index=False)
    print(f"wrote {out}")
