"""Does a cluster boost help? Retrieval only (no answer model), on the eval questions with a cluster label.

    docker compose run --rm -T --no-deps web python eval/cluster_boost.py

Each FORRT cluster gets a centroid: the mean of the unit vectors of its documents' chunks (just_os/clusters.py,
the same code as the app's CLUSTER_BOOST).
A question "clearly belongs" to a cluster when its cosine to that centroid beats the second-best by MARGIN.
Then chunks of that cluster's documents get BONUS added to their cosine among the RETRIEVER_TOP_K candidates,
before the per-paper cap and the cut to MAX_CHUNKS. Measured per (margin, bonus): how often the question's
cluster is detected (and right), hit@7 on the questions with expected_dois, and the share of the 7 chunks in the
question's labelled cluster. Writes eval/results/cluster_boost_<YYMMDD>.md.
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DEFAULT_CONFIG  # noqa: E402
from just_os.clusters import CLUSTERS, boosted, centroids, clusters_of, document_clusters  # noqa: E402
from just_os.references import normalize_doi, plain_metadata  # noqa: E402

MARGINS = [0.0, 0.01, 0.02, 0.03]
BONUSES = [0.0, 0.01, 0.02, 0.04]


def boost_limiter(config, excluded):
    """The app's per-paper cap and chunk limit (DocumentRetriever.limit_per_document) with the config's settings."""
    from just_os.qualle import DocumentRetriever

    limiter = object.__new__(DocumentRetriever)
    limiter.n_context_items, limiter.max_per_doc, limiter.excluded = config["MAX_CHUNKS"], config["MAX_CHUNKS_PER_DOC"], excluded
    limiter.skip_reference_chunks = config.get("SKIP_REFERENCE_CHUNKS", False)
    return limiter


def boost_and_limit(limiter, nodes, cluster, bonus, table):
    """Excluded documents out first, so they get no bonus and no place; then the boost and the limits."""
    nodes = limiter.without_excluded(nodes)
    return limiter.limit_per_document(boosted(nodes, cluster, bonus, table) if cluster else nodes)


def main():
    from just_os.rag_service import create_embedding_model, create_retriever, load_index
    from just_os.qualle import excluded_documents

    config = dict(DEFAULT_CONFIG)
    embed = create_embedding_model(config)
    index = load_index(config, embed)
    table = document_clusters(config["CLUSTERS_FILE"])
    excluded = excluded_documents(config.get("INDEX_CORRECTIONS_FILE"))
    cents = centroids(index, table, excluded=excluded)
    # as the app: excluded documents left out before the cut to RETRIEVER_TOP_K (the boost is for vector search)
    retriever = create_retriever({**config, "SEARCH_MODE": "vector"}, embed, index)
    limiter = boost_limiter(config, excluded)

    questions = [q for q in map(json.loads, open("eval/questions.jsonl", encoding="utf-8")) if q.get("cluster") in CLUSTERS]
    prepared = []
    for q in questions:
        v = np.asarray(embed.get_query_embedding(q["question"]))
        sims = cents @ (v / np.linalg.norm(v))
        order = np.argsort(-sims)
        prepared.append((q, CLUSTERS[order[0]], float(sims[order[0]] - sims[order[1]]), retriever.retrieve(q["question"])))

    lines = [f"# Cluster boost, retrieval only ({date.today():%d %b %Y}, {len(questions)} questions with a cluster, "
             f"{sum(1 for q in questions if q.get('expected_dois'))} with expected DOIs)", "",
             "| Margin | Bonus | Detected | Detected right | hit@7 | Chunks in the question's cluster |", "|---|---|---|---|---|---|"]
    for margin in MARGINS:
        for bonus in BONUSES:
            if bonus == 0 and margin > 0:
                continue  # no bonus: the margin changes nothing
            detected = right = hits = with_dois = in_cluster = total = 0
            for q, best, gap, nodes in prepared:
                cluster = best if gap >= margin and bonus > 0 else None
                detected += cluster is not None
                right += cluster == q["cluster"]
                kept = boost_and_limit(limiter, nodes, cluster, bonus, table)
                expected = {normalize_doi(d) for d in q.get("expected_dois", [])}
                if expected:
                    with_dois += 1
                    hits += any(normalize_doi(plain_metadata(n.node.metadata).get("doi")) in expected for n in kept)
                in_cluster += sum(q["cluster"] in clusters_of(plain_metadata(n.node.metadata), table) for n in kept)
                total += len(kept)
            lines.append(f"| {margin} | {bonus} | {detected} | {right} | {hits / max(with_dois, 1):.3f} | "
                         f"{in_cluster / max(total, 1):.3f} |")
    out = Path(f"eval/results/cluster_boost_{date.today():%y%m%d}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
