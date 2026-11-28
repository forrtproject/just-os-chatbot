"""The 11 FORRT clusters: which documents of the index belong to which cluster.

The cluster of a document comes from the consolidated FORRT article list (CLUSTERS_FILE, made by
scripts/forrt_article_list.py from all cluster and resource lists), matched by DOI, else by title; the index
itself stores no cluster. A resource can be in several clusters. Used by eval/cluster_balance.py and the
cluster boost of the search (CLUSTER_BOOST, ClusterBoost below).
"""

import csv
import logging
import re
import time
from typing import Dict, Iterable, List, Optional

import numpy as np

from just_os.references import GLOSSARY_TYPE, document_key, plain_metadata

logger = logging.getLogger(__name__)

# The cluster names of the FORRT website (and of the `cluster` field of eval/questions.jsonl)
CLUSTERS = [
    "Replication Crisis and Credibility Revolution",
    "Conceptual and Statistical Knowledge",
    "Replication and Meta-research",
    "Pre-analysis Planning",
    "Transparency and Reproducibility in Computation and Analysis",
    "FAIR Data and Materials",
    "Publication Sharing",
    "Research Integrity",
    "Academic Structures and Institutions",
    "Qualitative Research",
    "Ways of Working",
]
_CANONICAL = {c.casefold(): c for c in CLUSTERS}


def canonical(name: str) -> Optional[str]:
    """'FAIR data and materials' -> 'FAIR Data and Materials'; sub-clusters and ORxD categories -> None."""
    return _CANONICAL.get(name.strip().casefold())


def document_clusters(path: Optional[str]) -> Dict[str, List[str]]:
    """document_key (DOI, and title too, so a document indexed without DOI is found) -> its clusters."""
    out: Dict[str, List[str]] = {}
    if not path:
        return out
    try:
        with open(path, encoding="utf-8-sig") as f:  # Excel writes a BOM before "title"
            rows = list(csv.DictReader(f))
    except OSError:
        return out
    for row in rows:
        clusters = [c for c in dict.fromkeys(canonical(x) for x in row.get("clusters", "").split(";")) if c]
        if not clusters:
            continue
        keys = {document_key({"doi": row.get("doi", ""), "link_to_resource": row.get("url", "")}),
                re.sub(r"[^a-z0-9]", "", row.get("title", "").lower())} - {""}
        for key in keys:
            out[key] = list(dict.fromkeys(out.get(key, []) + clusters))
    return out


def clusters_of(metadata: Dict, table: Dict[str, List[str]]) -> List[str]:
    """The clusters of a chunk's document: by its DOI, else by its title."""
    return table.get(document_key(metadata)) or table.get(re.sub(r"[^a-z0-9]", "", str(metadata.get("title", "")).lower()), [])


def centroids(index, table: Dict[str, List[str]], block: int = 10000, excluded: Iterable[str] = ()) -> np.ndarray:
    """len(CLUSTERS) x dim unit centroids: the mean unit vector of each cluster's chunks (no glossary entries, no
    excluded documents: config/index_corrections.json), read from the FAISS index a block of rows at a time."""
    excluded = set(excluded)
    faiss_index = index.vector_store._faiss_index
    node_of = {int(row): node_id for row, node_id in index.index_struct.nodes_dict.items()}
    docs = index.docstore.docs
    sums, counts = np.zeros((len(CLUSTERS), faiss_index.d)), np.zeros(len(CLUSTERS))
    for start in range(0, faiss_index.ntotal, block):
        vectors = faiss_index.reconstruct_n(start, min(block, faiss_index.ntotal - start))
        for i, v in enumerate(vectors):
            node = docs.get(node_of.get(start + i))
            if node is None:
                continue
            meta = plain_metadata(node.metadata)
            if meta.get("material_type") == GLOSSARY_TYPE or (excluded and document_key(meta) in excluded):
                continue
            for c in clusters_of(meta, table):
                k = CLUSTERS.index(c)
                sums[k] += v / (np.linalg.norm(v) or 1)
                counts[k] += 1
    means = sums / np.maximum(counts, 1)[:, None]
    return means / np.maximum(np.linalg.norm(means, axis=1, keepdims=True), 1e-9)


def question_cluster(cents: np.ndarray, vector, margin: float) -> Optional[str]:
    """The cluster whose centroid is closest to the question, if it beats the second-best by margin."""
    v = np.asarray(vector, dtype=float)
    sims = cents @ (v / (np.linalg.norm(v) or 1))
    second, first = np.argsort(sims)[-2:]
    return CLUSTERS[int(first)] if sims[first] - sims[second] >= margin else None


def boosted(nodes, cluster: str, bonus: float, table: Dict[str, List[str]]):
    """Vector-search candidates re-ordered by cosine (1 - L2 distance / 2) + bonus for chunks of the cluster."""
    def score(n):
        cosine = 1 - (n.score if n.score is not None else 2) / 2
        return cosine + (bonus if cluster in clusters_of(plain_metadata(n.node.metadata), table) else 0)
    return sorted(nodes, key=score, reverse=True)


class ClusterBoost:
    """CLUSTER_BOOST: when a question clearly belongs to one FORRT cluster (CLUSTER_BOOST_MARGIN), that cluster's
    chunks get CLUSTER_BOOST added to their cosine among the found candidates (docs/evaluation.md 3.26)."""

    def __init__(self, index, embed_model, table: Dict[str, List[str]], bonus: float, margin: float,
                 excluded: Iterable[str] = ()):
        start = time.time()
        self.embed_model, self.table, self.bonus, self.margin = embed_model, table, bonus, margin
        self.centroids = centroids(index, table, excluded=excluded)
        logger.info(f"Cluster boost: centroids of {len(CLUSTERS)} clusters in {time.time() - start:.1f} s")

    def apply(self, query: str, nodes) -> List:
        cluster = question_cluster(self.centroids, self.embed_model.get_query_embedding(query), self.margin)
        return boosted(nodes, cluster, self.bonus, self.table) if cluster else nodes


# One question per cluster for the chat start page (four at random are shown; templates/index.html)
SUGGESTED_QUESTIONS = {
    "Replication Crisis and Credibility Revolution": "What started the replication crisis in psychology?",
    "Conceptual and Statistical Knowledge": "Why do small samples lead to false-positive findings?",
    "Replication and Meta-research": "What is the difference between a direct and a conceptual replication?",
    "Pre-analysis Planning": "What should a preregistration include?",
    "Transparency and Reproducibility in Computation and Analysis": "How can I make my analysis code reproducible?",
    "FAIR Data and Materials": "How do I share data from human participants without risking their privacy?",
    "Publication Sharing": "What are preprints, and should I post one?",
    "Research Integrity": "What counts as a questionable research practice?",
    "Academic Structures and Institutions": "How do academic incentives work against open science?",
    "Qualitative Research": "Can qualitative research be open and transparent?",
    "Ways of Working": "How does team science change who gets credit for research?",
}
