"""Step 3: papers whose text does not match their title (a wrong PDF behind a DOI, or a wrong title).

    python eval/topic_map/title_check.py [--work eval/.topic_map/latest]

Compares each paper's title vector with the mean of its real chunks. The lowest similarities
are worth a look by hand; the confirmed cases go into wrong_files.json (the text is another
paper) or wrong_titles.json (the text is right, the title is not). Writes title_check.csv.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import WORK, embed, unit  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK / "latest")
    args = ap.parse_args()

    chunks = pd.read_csv(args.work / "chunks.csv", low_memory=False)
    X = np.load(args.work / "vectors.npy")
    real = ~chunks.is_boilerplate.to_numpy()
    docs = chunks.groupby("doc_id").agg(title=("title", "first"), doi=("doi", "first"),
                                        chunks=("title", "size")).reset_index()
    centroids = []
    for d in docs.doc_id:
        mine = (chunks.doc_id == d).to_numpy()
        centroids.append(X[mine & real].mean(0) if (mine & real).any() else X[mine].mean(0))
    docs["title_content_sim"] = (embed(docs.title.fillna("").tolist()) * unit(centroids)).sum(1).round(3)
    docs = docs.sort_values("title_content_sim")
    docs.to_csv(args.work / "title_check.csv", index=False)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 80)
    print(docs.head(20)[["title_content_sim", "chunks", "doi", "title"]].to_string(index=False))


if __name__ == "__main__":
    main()
