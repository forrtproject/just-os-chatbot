"""Shared helpers for the topic map (eval/topic_map/). No heavy imports, so the tests can load it."""

import os
import re
import time
from pathlib import Path

import numpy as np

WORK = Path("eval/.topic_map")  # intermediate files (vectors, chunks); large, not in Git
API_MODEL = "baai/bge-m3"  # the index model (EMBEDDING_MODEL) on OpenRouter: same vectors, $0.01 per 1M tokens

# The 11 FORRT clusters (folder "Cluster <n>" in data/FORRT Clusters pdfs/)
CLUSTERS = {
    1: "Replication Crisis and Credibility Revolution", 2: "Conceptual and Statistical Knowledge",
    3: "Ways of Working", 4: "Pre-analysis Planning", 5: "Reproducible Analyses",
    6: "FAIR Data and Materials", 7: "Publication Sharing", 8: "Replication and Meta-research",
    9: "Academic Structures and Institutions", 10: "Qualitative Research", 11: "Research Integrity",
}
CLUSTER_PDF_LICENCE = "FORRT cluster PDF (open access)"  # conditions_of_use of the cluster papers

# Coverage of a sub-cluster: similarity of its name to the 10th-closest paper
STATUS_LIMITS = ((0.56, "blind"), (0.59, "thin"), (0.63, "covered"))

# Reference-list chunk: many "(2013)", "2013.", "et al.", "12(3)" or "123-130." per 100 words
CITATION = re.compile(r"\(\d{4}[a-z]?\)|\b(19|20)\d{2}[a-z]?\.|et al\.|\b\d+\(\d+\)|\b\d{1,4}[–-]\d{1,4}\.")
CITATIONS_PER_100_WORDS = 4
MIN_WORDS = 25


def plain(value):
    """10 documents store every metadata value as {doi_hash: value} (data.md, #24)."""
    return next(iter(value.values())) if isinstance(value, dict) and len(value) == 1 else value


def clean(text: str) -> str:
    """Chunk text without marker's HTML anchors, link targets, URLs and DOIs (for keywords)."""
    text = re.sub(r"<[^>]+>", " ", text)  # <span id="page-3-1">, <sup>
    text = re.sub(r"\]\([^)]*\)", "]", text)  # Markdown link targets
    text = re.sub(r"https?://\S+|www\.\S+|doi:\s*\S+|\b10\.\d{4,}/\S+", " ", text)
    return re.sub(r"[*_#|\[\]]", " ", text)


def citation_density(text: str) -> float:
    """Citation patterns per 100 words of cleaned text."""
    return len(CITATION.findall(text)) / max(len(text.split()), 1) * 100


def is_boilerplate(text: str) -> bool:
    """A reference list, author block or near-empty chunk: it does not count as coverage."""
    return citation_density(text) > CITATIONS_PER_100_WORDS or len(text.split()) < MIN_WORDS


def topic_kind(boilerplate_share: float, top_paper_share: float) -> str:
    if boilerplate_share > 0.5:
        return "reference lists"
    return "one paper" if top_paper_share > 0.7 else "topic"


def status(paper10_sim: float) -> str:
    for limit, name in STATUS_LIMITS:
        if paper10_sim < limit:
            return name
    return "strong"


def unit(x) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x / np.linalg.norm(x, axis=-1, keepdims=True)


def embed(texts, batch: int = 64) -> np.ndarray:
    """bge-m3 vectors (normalised) through OpenRouter; needs OPENROUTER_API_KEY."""
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    out = []
    for i in range(0, len(texts), batch):
        for attempt in range(5):
            try:
                r = client.embeddings.create(model=API_MODEL, input=list(texts[i:i + batch]))
                out += [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
                break
            except Exception as e:
                if attempt == 4:
                    raise
                print(f"  embedding API error (try {attempt + 1}): {e}")
                time.sleep(2 ** attempt)
    return unit(out)
