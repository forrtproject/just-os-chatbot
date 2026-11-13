"""Step 1: topics of an index, from the vectors it already has (no LLM, no re-embedding).

    python eval/topic_map/build_map.py [--index data/processed/vs_latest_bge-m3] [--work eval/.topic_map/latest]

UMAP (5-d) + HDBSCAN finds the topics (the BERTopic recipe), a 2-d UMAP places every chunk on
the map, and c-TF-IDF over each topic's cleaned text gives its keywords. Reference lists and
near-empty chunks are flagged (common.is_boilerplate) and left out of the keywords.

Writes to --work: chunks.csv (one row per chunk), topics.csv (one row per topic), vectors.npy,
centroids.npy and texts.json. Needs the "analysis" dependency group (umap-learn).
146,899 chunks take about 5 minutes on a laptop CPU.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import umap
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CLUSTER_PDF_LICENCE, WORK, clean, citation_density, is_boilerplate, plain, topic_kind, unit  # noqa: E402

STOP = list(ENGLISH_STOP_WORDS | {
    "et", "al", "doi", "org", "https", "http", "vol", "pp", "journal", "pdf", "www", "com", "figure", "table",
    "fig", "university", "ed", "eds", "page", "span", "sup", "id", "ont", "refhub", "elsevier", "crossref",
    "pubmed", "ncbi", "nlm", "nih", "gov", "pmid", "psychol", "accessed", "retrieved", "available", "press",
    "use", "used",
})


def load_index(index_dir: Path):
    index = faiss.read_index(str(index_dir / "default__vector_store.json"))
    vectors = unit(index.reconstruct_n(0, index.ntotal))
    store = json.load(open(index_dir / "index_store.json", encoding="utf-8"))["index_store/data"]
    nodes = json.loads(next(iter(store.values()))["__data__"])["nodes_dict"]
    docs = json.load(open(index_dir / "docstore.json", encoding="utf-8"))["docstore/data"]
    rows = []
    for i in range(index.ntotal):
        d = docs[nodes[str(i)]]["__data__"]
        m = {k: plain(v) for k, v in d["metadata"].items()}
        rows.append({
            "faiss_id": i,
            "doc_id": d["relationships"]["1"]["node_id"],
            "title": str(m.get("title", ""))[:200],
            "doi": m.get("doi", ""),
            "source": "cluster" if m.get("conditions_of_use") == CLUSTER_PDF_LICENCE else "justos",
            "source_file": m.get("source_file", ""),
            "text": d["text"],
        })
    return pd.DataFrame(rows), vectors


def keywords(chunks: pd.DataFrame, n_topics: int, n: int = 8):
    text = chunks[~chunks.is_boilerplate].groupby("topic").clean.apply(" ".join).reindex(range(n_topics)).fillna("")
    cv = CountVectorizer(stop_words=STOP, ngram_range=(1, 2), min_df=2, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z-]{2,}\b")
    tf = cv.fit_transform(text).astype(np.float64)
    tf = tf.multiply(1 / np.maximum(tf.sum(1), 1)).tocsr()
    idf = np.log(1 + tf.shape[0] / (np.asarray((tf > 0).sum(0)).ravel() + 1))
    ctfidf = tf.multiply(idf).tocsr()
    vocab = np.array(cv.get_feature_names_out())
    return [", ".join(vocab[ctfidf[t].toarray().ravel().argsort()[::-1][:n]]) for t in range(n_topics)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=Path("data/processed/vs_latest_bge-m3"))
    ap.add_argument("--work", type=Path, default=WORK / "latest")
    ap.add_argument("--min-topic", type=int, default=100, help="smallest topic, in chunks (100 for ~150k chunks)")
    args = ap.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    chunks, X = load_index(args.index)
    print(f"{len(chunks)} chunks, {chunks.doc_id.nunique()} documents ({time.time() - t0:.0f}s)")
    chunks["clean"] = chunks.text.map(clean)
    chunks["ref_density"] = chunks.clean.map(citation_density).round(1)
    chunks["is_boilerplate"] = chunks.clean.map(is_boilerplate)
    print(f"reference-list / near-empty chunks: {chunks.is_boilerplate.mean():.0%}")

    z5 = umap.UMAP(n_components=5, n_neighbors=30, min_dist=0.0, metric="cosine", random_state=42).fit_transform(X)
    labels = HDBSCAN(min_cluster_size=args.min_topic, min_samples=15).fit_predict(z5)
    n_topics = labels.max() + 1
    print(f"{n_topics} topics, {np.mean(labels < 0):.0%} noise ({time.time() - t0:.0f}s)")
    # Centroids in the original space; noise chunks join their nearest topic (and stay flagged)
    C = unit(np.stack([X[labels == t].mean(0) for t in range(n_topics)]))
    noise = labels < 0
    labels[noise] = (X[noise] @ C.T).argmax(1)
    chunks["topic"], chunks["noise"] = labels, noise

    z2 = umap.UMAP(n_components=2, n_neighbors=30, min_dist=0.1, metric="cosine", random_state=42).fit_transform(X)
    chunks["x"], chunks["y"] = z2[:, 0], z2[:, 1]
    print(f"2-d map done ({time.time() - t0:.0f}s)")

    kws = keywords(chunks, n_topics)
    topics = []
    for t in range(n_topics):
        sub = chunks[chunks.topic == t]
        per_doc = sub.groupby("title").size().sort_values(ascending=False)
        real = sub[~sub.is_boilerplate]
        row = {
            "topic": t, "keywords": kws[t], "chunks": len(sub), "papers": sub.doc_id.nunique(),
            "papers_3plus": int((real.groupby("doc_id").size() >= 3).sum()),  # papers with 3+ real chunks here
            "top_paper_share": round(per_doc.iloc[0] / len(sub), 2),
            "top_papers": " | ".join(f"{k} ({v})" for k, v in per_doc.head(4).items()),
            "boilerplate_share": round(sub.is_boilerplate.mean(), 2),
            "x": float(sub.x.median()), "y": float(sub.y.median()),
        }
        row["kind"] = topic_kind(row["boilerplate_share"], row["top_paper_share"])
        topics.append(row)
    topics = pd.DataFrame(topics)

    json.dump(chunks.text.tolist(), open(args.work / "texts.json", "w", encoding="utf-8"))
    chunks.drop(columns=["text", "clean"]).to_csv(args.work / "chunks.csv", index=False)
    topics.to_csv(args.work / "topics.csv", index=False)
    np.save(args.work / "vectors.npy", X)
    np.save(args.work / "centroids.npy", C)
    print(topics.kind.value_counts().to_string())
    print(f"done in {time.time() - t0:.0f}s -> {args.work}")


if __name__ == "__main__":
    main()
