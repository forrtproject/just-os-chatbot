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
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Settings that change the answer: a cache entry is only reused with the same values
NAMESPACE_KEYS = (
    "CITATION_MODEL",
    "EMBEDDING_MODEL",
    "VECTOR_STORE",
    "PROMPT_STYLE",
    "SEARCH_MODE",
    "RERANK",
    "MIN_VECTOR_SIMILARITY",
    "MAX_CHUNKS",
    "MAX_CHUNKS_PER_DOC",
)


class AnswerCache:
    def __init__(self, redis, embed_model, config: Dict[str, Any]):
        self.redis = redis
        self.embed_model = embed_model
        self.ttl = config["ANSWER_CACHE_TTL"]
        self.min_similarity = config["ANSWER_CACHE_MIN_SIMILARITY"]
        self.max_items = config["ANSWER_CACHE_MAX_ITEMS"]
        self.config = config
        self.key = self.key_for(None)

    def key_for(self, model: Optional[str]) -> str:
        """One cache per setup; a model chosen for one request replaces CITATION_MODEL."""
        values = [self.config.get(k) for k in NAMESPACE_KEYS]
        if model:
            values[NAMESPACE_KEYS.index("CITATION_MODEL")] = model
        return f"answer_cache:{hashlib.md5(json.dumps(values).encode()).hexdigest()[:12]}"

    def _vector(self, query: str) -> np.ndarray:
        vector = np.asarray(self.embed_model.get_query_embedding(query), dtype=np.float32)
        return vector / (np.linalg.norm(vector) or 1.0)

    def lookup(self, query: str, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the stored entry ({"response", "text"}) of the most similar fresh question."""
        try:
            vector = self._vector(query)
            now = time.time()
            best, best_score = None, self.min_similarity
            for raw in self.redis.lrange(self.key_for(model), 0, -1):
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

    def store(self, query: str, response: Dict[str, Any], text: str, model: Optional[str] = None) -> None:
        try:
            entry = {
                "time": time.time(),
                "vector": np.round(self._vector(query), 4).tolist(),
                "response": response,
                "text": text,
            }
            key = self.key_for(model)
            self.redis.lpush(key, json.dumps(entry))
            self.redis.ltrim(key, 0, self.max_items - 1)
            self.redis.expire(key, self.ttl)
        except Exception as e:
            logger.error(f"Answer cache store failed: {e}")
