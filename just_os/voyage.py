"""Voyage 4 embeddings through OpenRouter (EMBEDDING_MODEL=mongodb/voyage-4-large, docs/evaluation.md 3.21).

Voyage embeds questions and passages differently (input_type "query" / "document"). The vectors are
normalized, like the bge-m3 vectors of the FAISS index (squared L2 of unit vectors = 2 - 2 cosine).
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import numpy as np
from openai import OpenAI


def is_voyage(model: str) -> bool:
    return model.startswith("mongodb/voyage-")


class Voyage:
    def __init__(self, model: str, api_key: str = ""):
        self.model = model
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key or os.environ["OPENROUTER_API_KEY"])
        self.cost = 0.0

    def embed(self, texts: List[str], input_type: str) -> np.ndarray:
        """One request; retried with backoff, since a lost batch would stop an index build."""
        for attempt in range(6):
            try:
                r = self.client.embeddings.create(model=self.model, input=texts, extra_body={"input_type": input_type})
                self.cost += getattr(r.usage, "cost", 0) or 0
                v = np.asarray([d.embedding for d in r.data], dtype=np.float32)
                return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None)
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(2**attempt)

    def documents(self, texts: List[str], batch: int = 64, threads: int = 8) -> np.ndarray:
        parts = [texts[i: i + batch] for i in range(0, len(texts), batch)]
        with ThreadPoolExecutor(threads) as pool:
            return np.concatenate(list(pool.map(lambda p: self.embed(p, "document"), parts)))

    def query(self, text: str) -> List[float]:
        return self.embed([text], "query")[0].tolist()
