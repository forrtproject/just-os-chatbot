"""Step 2: how well the index covers each FORRT sub-cluster, and how close each eval question gets.

    python eval/topic_map/taxonomy.py [--work eval/.topic_map/latest] [--pdfs "data/FORRT Clusters pdfs"]

Embeds the 93 sub-cluster names (the folder names under --pdfs) and ranks the papers by their
closest real chunk (reference lists left out). The similarity of the 10th-best paper gives the
status (common.status): a name with few close papers has few papers that really cover it.
The name alone is the probe: a suffix such as "in open science" pulls every name to the same
generic text. Also scores eval/questions.jsonl (closest paper chunk or FORRT page) and gives
each topic its nearest sub-cluster.

Writes to --work: taxonomy_coverage.csv, questions_scored.csv; adds the sub-cluster to topics.csv.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CLUSTERS, WORK, embed, unit  # noqa: E402


def ranked(sims, real, doc, k):
    """Indices of the k most similar chunks, best first, without reference-list chunks."""
    top = np.argpartition(-sims, k)[:k]
    top = top[np.argsort(-sims[top])]
    return top[real[top]]


def sub_clusters(pdf_dir: Path) -> pd.DataFrame:
    rows = []
    for cdir in sorted(p for p in pdf_dir.glob("Cluster *") if p.is_dir()):
        n = int(cdir.name.split()[-1])
        for sdir in sorted(p for p in cdir.iterdir() if p.is_dir()):
            name = re.sub(r"^Sub-Cluster\s*\d*_\s*", "", sdir.name).replace("_", " ").strip(" .")
            pdfs = {re.sub(r"\s*\(\d\)$", "", p.stem) for p in sdir.rglob("*.pdf")}
            rows.append({"cluster_no": n, "cluster": CLUSTERS[n], "sub_cluster": name, "cluster_pdfs": len(pdfs)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK / "latest")
    ap.add_argument("--pdfs", type=Path, default=Path("data/FORRT Clusters pdfs"))
    ap.add_argument("--questions", type=Path, default=Path("eval/questions.jsonl"))
    ap.add_argument("--pages", type=Path, default=Path("vector_data/forrt_pages/vectors.npy"))
    args = ap.parse_args()

    X = np.load(args.work / "vectors.npy")
    C = np.load(args.work / "centroids.npy")
    chunks = pd.read_csv(args.work / "chunks.csv", low_memory=False)
    topics = pd.read_csv(args.work / "topics.csv")
    doc, title = chunks.doc_id.to_numpy(), chunks.title.fillna("").to_numpy()
    real = ~chunks.is_boilerplate.to_numpy()

    # --- eval questions: closest paper chunk and closest FORRT page ---------------------
    qs = [json.loads(line) for line in open(args.questions, encoding="utf-8")]
    qs = [q for q in qs if not q.get("history")]
    qv = embed([q["question"] for q in qs])
    pages = unit(np.load(args.pages))
    rows = []
    for q, v in zip(qs, qv):
        sims = X @ v
        top = ranked(sims, real, doc, 200)
        rows.append({
            "id": q["id"], "question": q["question"], "expect": q.get("expect", ""), "route": q.get("route", ""),
            "lang": q.get("lang", ""), "best_paper_sim": round(float(sims[top[0]]), 3),
            "papers_0.60": len({doc[i] for i in top if sims[i] >= 0.60}),
            "best_forrt_page_sim": round(float((pages @ v).max()), 3), "top_paper": title[top[0]][:90],
        })
    qdf = pd.DataFrame(rows)
    qdf["gate_score"] = qdf[["best_paper_sim", "best_forrt_page_sim"]].max(axis=1)
    qdf.to_csv(args.work / "questions_scored.csv", index=False)

    # --- FORRT sub-clusters -------------------------------------------------------------
    sdf = sub_clusters(args.pdfs)
    sv = embed(sdf.sub_cluster.tolist())
    ranks = []
    for v in sv:
        sims = X @ v
        seen = {}
        for i in ranked(sims, real, doc, 3000):
            seen.setdefault(doc[i], (title[i], float(sims[i])))
        ranks.append(list(seen.values()))
    sdf["best_sim"] = [round(r[0][1], 3) for r in ranks]
    for n in (3, 10, 25):  # how close is the n-th best paper? low = few papers really cover it
        sdf[f"paper{n}_sim"] = [round(r[n - 1][1], 3) if len(r) >= n else 0 for r in ranks]
    for limit in (0.55, 0.60):
        sdf[f"papers_{limit:.2f}"] = [sum(s >= limit for _, s in r) for r in ranks]
    sdf["top_papers"] = [" | ".join(t[:70] for t, _ in r[:3]) for r in ranks]
    sdf.to_csv(args.work / "taxonomy_coverage.csv", index=False)

    # --- each topic's nearest sub-cluster -------------------------------------------------
    tsim = C @ sv.T
    topics["forrt_cluster_no"] = sdf.cluster_no.to_numpy()[tsim.argmax(1)]
    topics["forrt_sub_cluster"] = sdf.sub_cluster.to_numpy()[tsim.argmax(1)]
    topics["forrt_sim"] = tsim.max(1).round(3)
    topics.to_csv(args.work / "topics.csv", index=False)
    print(f"{len(qdf)} questions, {len(sdf)} sub-clusters -> {args.work}")


if __name__ == "__main__":
    main()
