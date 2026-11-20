"""Thresholds for another embedding model that cut at the same share of questions as today's (3.21).

MIN_VECTOR_SIMILARITY is compared with the cosine of the best paper chunk, FORRT_IN_PAPERS_MIN_SCORE
with a FORRT page's search score; both are on the scale of one embedding model. For each, this prints
the value of the other model at the same quantile over the questions, so both models send the same
share of questions to "no sources" and the comparison is about which passages they find.

    docker compose run --rm -T web python eval/calibrate_embedding.py EMBEDDING_MODEL=mongodb/voyage-4-large \
        VECTOR_STORE=data/processed/vs_latest_voyage-4-large FORRT_PAGES_DIR=vector_data/forrt_pages_voyage-4-large
"""

import json
import sys
from pathlib import Path

import faiss
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402
from just_os.forrt_pages import ForrtPages  # noqa: E402
from just_os.rag_service import create_embedding_model  # noqa: E402

QUESTIONS = ["eval/questions.jsonl", "eval/forrt_questions.jsonl"]


def scores(config, questions):
    """Per question: cosine of the best paper chunk and the best FORRT page search score."""
    embed = create_embedding_model(config)
    index = faiss.read_index(f"{config['VECTOR_STORE']}/default__vector_store.json")
    pages = ForrtPages(config, embed, None)
    paper, page = [], []
    for q in questions:
        v = np.asarray([embed.get_query_embedding(q)], dtype=np.float32)
        distance, _ = index.search(v / np.linalg.norm(v), 1)
        paper.append(1 - float(distance[0][0]) / 2)  # squared L2 of unit vectors -> cosine
        page.append(max(c["score"] for c in pages.retrieve(q)))
    return np.array(paper), np.array(page)


def matched(threshold, old, new):
    share = float(np.mean(old < threshold))
    return share, float(np.quantile(new, share))


def main():
    questions = [json.loads(line)["question"] for f in QUESTIONS for line in open(f, encoding="utf-8") if line.strip()]
    base = get_config()
    other = {**base, **dict(kv.split("=", 1) for kv in sys.argv[1:])}
    old, new = scores(base, questions), scores(other, questions)
    for name, i in (("MIN_VECTOR_SIMILARITY", 0), ("FORRT_IN_PAPERS_MIN_SCORE", 1)):
        share, value = matched(base[name], old[i], new[i])
        print(f"{name}: {base[name]} for {base['EMBEDDING_MODEL']} cuts {share:.1%} of {len(questions)} questions; "
              f"same share for {other['EMBEDDING_MODEL']}: {value:.3f}")


if __name__ == "__main__":
    main()
