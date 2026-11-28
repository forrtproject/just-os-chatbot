"""Semantic answer cache (issue O4, #29).

If a recent first-turn question is very similar (cosine of the question embeddings
>= ANSWER_CACHE_MIN_SIMILARITY), the stored answer is sent again: no classify,
retrieval or LLM call. Kept in one Redis list per pipeline setup (models, index,
prompt), newest first, at most ANSWER_CACHE_MAX_ITEMS entries for ANSWER_CACHE_TTL
seconds. Off when ANSWER_CACHE_TTL is 0 (default). The cache is shared by all users,
so it stores the question text: mention it in the privacy notice before turning it on.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from just_os import trace

logger = logging.getLogger(__name__)

# Settings that change the answer: a cache entry is only reused with the same values
NAMESPACE_KEYS = (
    "CITATION_MODEL",
    "EMBEDDING_MODEL",
    "VECTOR_STORE",
    "PROMPT_STYLE",
    "SEARCH_MODE",
    "RERANK",
    "RERANK_MODEL",
    "MIN_RELEVANCE",
    "RETRIEVER_TOP_K",
    "MIN_VECTOR_SIMILARITY",
    "MAX_CHUNKS",
    "MAX_CHUNKS_PER_DOC",
    "ROUTER",
    "CLUSTER_BOOST",
    "CLUSTER_BOOST_MARGIN",
    "SKIP_REFERENCE_CHUNKS",
    "FORRT_IN_PAPERS",
    "ADAPTIVE_TOP_K",
    "ADAPTIVE_TOP_K_RATIO",
    "ADAPTIVE_TOP_K_MIN",
    "REFERENCE_LOOKUP",
    "VERIFY_CITATIONS",
    "TEMPERATURE",
    "MAX_ANSWER_TOKENS",
    "BASE_URL",
)


def file_hash(path: Optional[str]) -> Optional[str]:
    """sha1 of a file's bytes, or None when there is no such file."""
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest() if path else None
    except OSError:
        return None


def index_fingerprint(config: Dict[str, Any]) -> list:
    """What the namespace keys cannot see: an index changed in place (size and mtime of its docstore, as
    scripts/fix_index_titles.py and add_to_index write it), the excluded documents and corrected titles
    (INDEX_CORRECTIONS_FILE) and the cluster list the boost reads (CLUSTERS_FILE)."""
    try:
        stat = (Path(config.get("VECTOR_STORE") or "") / "docstore.json").stat()
        docstore = [stat.st_size, int(stat.st_mtime)]
    except OSError:
        docstore = None
    return [docstore, file_hash(config.get("INDEX_CORRECTIONS_FILE")), file_hash(config.get("CLUSTERS_FILE"))]


class AnswerCache:
    def __init__(self, redis, embed_model, config: Dict[str, Any]):
        self.redis = redis
        self.embed_model = embed_model
        self.ttl = config["ANSWER_CACHE_TTL"]
        self.min_similarity = config["ANSWER_CACHE_MIN_SIMILARITY"]
        self.max_items = config["ANSWER_CACHE_MAX_ITEMS"]
        self.config = config
        self.fingerprint = index_fingerprint(config)  # read once at start, like the index itself
        self.key = self.key_for(None)

    def key_for(self, model: Optional[str], router: Optional[str] = None) -> str:
        """One cache per setup (NAMESPACE_KEYS and the index fingerprint); a model or router chosen for one request
        (the chat and arena dropdowns) replaces CITATION_MODEL or ROUTER, so the key names the effective router."""
        values = [self.config.get(k) for k in NAMESPACE_KEYS]
        if model:
            values[NAMESPACE_KEYS.index("CITATION_MODEL")] = model
        if router:
            values[NAMESPACE_KEYS.index("ROUTER")] = router
        raw = json.dumps(values + [self.fingerprint], default=str)
        return f"answer_cache:{hashlib.md5(raw.encode()).hexdigest()[:12]}"

    def _vector(self, query: str, query_vector: Optional[np.ndarray] = None) -> np.ndarray:
        """The unit question vector; query_vector is the turn's embedding when Qualle already has it."""
        if query_vector is None:
            query_vector = self.embed_model.get_query_embedding(query)
        vector = np.asarray(query_vector, dtype=np.float32)
        return vector / (np.linalg.norm(vector) or 1.0)

    @trace.step("answer cache", lambda result, *a, **k: {"hit": bool(result)})
    def lookup(self, query: str, model: Optional[str] = None,
               query_vector: Optional[np.ndarray] = None, router: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the stored entry ({"response", "text"}) of the most similar fresh question."""
        try:
            vector = self._vector(query, query_vector)
            now = time.time()
            best, best_score = None, self.min_similarity
            for raw in self.redis.lrange(self.key_for(model, router), 0, -1):
                entry = json.loads(raw)
                if now - entry["time"] > self.ttl:
                    continue
                score = float(np.dot(vector, np.asarray(entry["vector"], dtype=np.float32)))
                if score >= best_score:
                    best, best_score = entry, score
            if best:
                logger.info(f"Answer cache hit (similarity {best_score:.3f})")
            return best
        except Exception as e:
            # The cache must never break an answer
            logger.error(f"Answer cache lookup failed: {e}")
            return None

    def store(self, query: str, response: Dict[str, Any], text: str, model: Optional[str] = None,
              query_vector: Optional[np.ndarray] = None, router: Optional[str] = None) -> None:
        try:
            entry = {
                "time": time.time(),
                "vector": np.round(self._vector(query, query_vector), 4).tolist(),
                "response": response,
                "text": text,
            }
            key = self.key_for(model, router)
            self.redis.lpush(key, json.dumps(entry))
            self.redis.ltrim(key, 0, self.max_items - 1)
            self.redis.expire(key, self.ttl)
        except Exception as e:
            logger.error(f"Answer cache store failed: {e}")
