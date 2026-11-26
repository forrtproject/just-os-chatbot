"""Eval balance: eval questions per FORRT cluster against the index's documents and chunks per cluster.

    python eval/cluster_balance.py [index-dir]        # default: VECTOR_STORE

A cluster with many chunks but few questions is under-tested; one with many questions but few chunks is
under-covered (it needs papers or abstract cards). Clusters of a document: just_os/clusters.py (CLUSTERS_FILE).
Writes eval/results/cluster_balance_<YYMMDD>.md.
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings  # noqa: E402
from just_os.clusters import CLUSTERS, clusters_of, document_clusters  # noqa: E402
from just_os.references import document_key, plain_metadata  # noqa: E402


def balance(nodes, table, questions):
    """Rows (cluster, questions, documents, chunks, share of questions, share of chunks), largest gap first."""
    chunks, documents = Counter(), {c: set() for c in CLUSTERS}
    for meta in nodes:
        for c in clusters_of(meta, table):
            chunks[c] += 1
            documents[c].add(document_key(meta))
    asked = Counter(q.get("cluster") for q in questions)
    n_q, n_c = sum(asked[c] for c in CLUSTERS) or 1, sum(chunks.values()) or 1
    rows = [(c, asked[c], len(documents[c]), chunks[c], asked[c] / n_q, chunks[c] / n_c) for c in CLUSTERS]
    return sorted(rows, key=lambda r: r[4] - r[5])


def main(index_dir):
    data = json.loads((Path(index_dir) / "docstore.json").read_text(encoding="utf-8"))["docstore/data"]
    nodes = [plain_metadata(n["__data__"].get("metadata", {})) for n in data.values()]
    questions = [json.loads(line) for line in open("eval/questions.jsonl", encoding="utf-8")]
    rows = balance(nodes, document_clusters(settings.CLUSTERS_FILE), questions)
    lines = [f"# Eval balance per FORRT cluster ({date.today():%d %b %Y}, `{index_dir}`)", "",
             f"{len(nodes):,} chunks in the index; a chunk counts once per cluster of its document. "
             "Gap = share of the eval questions minus share of the cluster chunks: negative = under-tested.", "",
             "| Cluster | Questions | Documents | Chunks | Share of questions | Share of chunks | Gap |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| {c} | {q} | {d:,} | {k:,} | {sq:.0%} | {sk:.0%} | {sq - sk:+.0%} |" for c, q, d, k, sq, sk in rows]
    out = Path(f"eval/results/cluster_balance_{date.today():%y%m%d}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else settings.VECTOR_STORE)
