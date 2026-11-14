"""The search step, chosen by SEARCH_MODE: vector, keyword (BM25) or both (issue N1, #19).

Vector search misses exact terms (names, acronyms such as "HARKing" or "CRediT");
BM25 finds them. SEARCH_MODE=hybrid merges the two ranked lists with reciprocal rank
fusion, SEARCH_MODE=bm25 uses the keywords alone. Both build the keyword index from the
docstore at start-up.

A vector hit keeps its FAISS score, the squared L2 distance of unit vectors, from which
vector_cosine gives the cosine; a keyword hit has score None (hybrid) or its BM25 score
(bm25), which is on no fixed scale.
"""

import logging
from typing import Any, List, Optional

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

    def top(self, query: str, k: int, scores=None) -> List[int]:
        """The k best documents with a score above 0; `scores` reuses scores already computed."""
        scores = self.scores(query) if scores is None else scores
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
            found.get(node_id) or NodeWithScore(node=self.by_id[node_id], score=None)
            for node_id in fused[: self.top_k]
        ]


class KeywordRetriever:
    """SEARCH_MODE=bm25: the top_k chunks by BM25 alone, with their BM25 score. Keeps the
    vector retriever for what needs the FAISS index, such as the cosine router."""

    def __init__(self, nodes: List[Any], top_k: int, vector_retriever=None):
        self.vector_retriever = vector_retriever
        self.nodes = nodes
        self.top_k = top_k
        logger.info(f"Building the BM25 keyword index over {len(nodes)} chunks")
        self.bm25 = BM25([node.get_content() for node in nodes])

    def retrieve(self, query: str) -> List[NodeWithScore]:
        scores = self.bm25.scores(query)
        return [NodeWithScore(node=self.nodes[i], score=float(scores[i])) for i in self.bm25.top(query, self.top_k, scores)]


SEARCH_MODES = ("vector", "bm25", "hybrid")


def search_retriever(mode: str, vector_retriever, nodes: List[Any], top_k: int):
    """The retriever for SEARCH_MODE; nodes (the docstore's chunks) are only read for bm25 and hybrid."""
    if mode == "vector":
        return vector_retriever
    if mode == "bm25":
        return KeywordRetriever(nodes, top_k, vector_retriever)
    if mode == "hybrid":
        return HybridRetriever(vector_retriever, nodes, top_k)
    raise ValueError(f"SEARCH_MODE must be one of {', '.join(SEARCH_MODES)}, not {mode!r}")


def vector_cosine(hits: List[NodeWithScore]) -> Optional[float]:
    """Cosine of the best vector hit (FAISS IndexFlatL2 over unit vectors: cosine = 1 - d / 2),
    or None when no hit came from the vector search."""
    distances = [hit.score for hit in hits if hit.score is not None]
    return 1 - min(distances) / 2 if distances else None
