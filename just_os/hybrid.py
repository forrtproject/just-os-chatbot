"""Hybrid retrieval: keyword search (BM25) next to vector search (issue N1, #19).

Vector search misses exact terms (names, acronyms such as "HARKing" or "CRediT");
BM25 finds them. The two ranked lists are merged with reciprocal rank fusion.
On with HYBRID_SEARCH=true. Builds the keyword index from the docstore at start-up.
"""

import logging
from typing import Any, List

import numpy as np
from llama_index.core.schema import NodeWithScore
from sklearn.feature_extraction.text import CountVectorizer

logger = logging.getLogger(__name__)

RRF_K = 60  # standard constant of reciprocal rank fusion


class BM25:
    """Okapi BM25 over a sparse term matrix (scikit-learn is already a dependency)."""

    def __init__(self, texts: List[str], k1: float = 1.5, b: float = 0.75):
        self.vectorizer = CountVectorizer(lowercase=True, token_pattern=r"(?u)\b\w\w+\b")
        tf = self.vectorizer.fit_transform(texts).tocsc().astype(np.float32)
        n_docs = tf.shape[0]
        df = np.diff(tf.indptr)  # documents per term
        self.idf = np.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        lengths = np.asarray(tf.sum(axis=1)).ravel()
        self.norm = k1 * (1 - b + b * lengths / max(lengths.mean(), 1.0))
        self.tf, self.k1, self.n_docs = tf, k1, n_docs
        self.analyzer = self.vectorizer.build_analyzer()

    def scores(self, query: str) -> np.ndarray:
        scores = np.zeros(self.n_docs, dtype=np.float32)
        vocab = self.vectorizer.vocabulary_
        for term in {t for t in self.analyzer(query) if t in vocab}:
            j = vocab[term]
            rows = self.tf.indices[self.tf.indptr[j] : self.tf.indptr[j + 1]]
            freq = self.tf.data[self.tf.indptr[j] : self.tf.indptr[j + 1]]
            scores[rows] += self.idf[j] * freq * (self.k1 + 1) / (freq + self.norm[rows])
        return scores

    def top(self, query: str, k: int) -> List[int]:
        scores = self.scores(query)
        best = np.argsort(-scores)[:k]
        return [int(i) for i in best if scores[i] > 0]


def reciprocal_rank_fusion(*rankings: List[str]) -> List[str]:
    """Merge ranked id lists: score = sum of 1 / (RRF_K + rank)."""
    fused = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking):
            fused[node_id] = fused.get(node_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(fused, key=fused.get, reverse=True)


class HybridRetriever:
    """Same interface as a llama-index retriever: retrieve(query) -> [NodeWithScore]."""

    def __init__(self, vector_retriever, nodes: List[Any], top_k: int):
        self.vector_retriever = vector_retriever
        self.nodes = nodes
        self.by_id = {node.node_id: node for node in nodes}
        self.top_k = top_k
        logger.info(f"Building the BM25 keyword index over {len(nodes)} chunks")
        self.bm25 = BM25([node.get_content() for node in nodes])

    def retrieve(self, query: str) -> List[NodeWithScore]:
        vector_hits = self.vector_retriever.retrieve(query)
        found = {hit.node.node_id: hit for hit in vector_hits}
        keyword_ids = [self.nodes[i].node_id for i in self.bm25.top(query, self.top_k)]
        fused = reciprocal_rank_fusion([hit.node.node_id for hit in vector_hits], keyword_ids)
        return [
            found.get(node_id) or NodeWithScore(node=self.by_id[node_id], score=0.0)
            for node_id in fused[: self.top_k]
        ]
