"""Voyage-4-large copies of the paper index and of the FORRT page vectors (docs/evaluation.md 3.21).

Same chunks and pages as the bge-m3 ones, only the vectors change, so a run on them differs from a
bge-m3 run in the embedding alone. Chunk vectors already in data/processed/emb_cache/ (made by
eval/compare_embeddings.py for the same chunk texts) are reused; the rest are embedded through
OpenRouter (about 0.12 USD per 1M tokens). The bot embeds the chunk text only (text template
"{content}"), so the text is all that is sent.

    python -m scripts.build_voyage_index
Output: data/processed/vs_latest_voyage-4-large/ and vector_data/forrt_pages_voyage-4-large/
"""

import json
import shutil
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv

from just_os.voyage import Voyage
from scripts.build_forrt_pages import embed_text

MODEL = "mongodb/voyage-4-large"
SRC, DST = Path("data/processed/vs_latest_bge-m3"), Path("data/processed/vs_latest_voyage-4-large")
CACHE_INDEX = Path("data/processed/vs_261111_bge-small-en-v1.5_before_clusters")  # the emb_cache chunk order
CACHE = Path("data/processed/emb_cache/mongodb__voyage-4-large.npy")
PAGES_SRC, PAGES_DST = Path("vector_data/forrt_pages"), Path("vector_data/forrt_pages_voyage-4-large")


def docstore_texts(folder: Path) -> dict:
    nodes = json.loads((folder / "docstore.json").read_text(encoding="utf-8"))["docstore/data"]
    return {k: v["__data__"]["text"] for k, v in nodes.items()}


def main():
    load_dotenv()
    voyage = Voyage(MODEL)

    # Paper chunks, in the row order of the bge-m3 FAISS index (index_store maps row -> node id)
    store = json.loads((SRC / "index_store.json").read_text(encoding="utf-8"))
    rows = json.loads(next(iter(store["index_store/data"].values()))["__data__"])["nodes_dict"]
    texts_by_id = docstore_texts(SRC)
    texts = [texts_by_id[rows[str(r)]] for r in range(len(rows))]
    cached = dict(zip(docstore_texts(CACHE_INDEX).values(), np.load(CACHE).astype(np.float32)))
    todo = sorted({t for t in texts if t not in cached})
    print(f"{len(texts)} chunks: {sum(t in cached for t in texts)} from the cache, embedding {len(todo)}", flush=True)
    cached.update(zip(todo, voyage.documents(todo)))
    vectors = np.stack([cached[t] for t in texts])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    assert vectors.shape == (len(texts), 1024)

    DST.mkdir(parents=True, exist_ok=True)
    for name in ("docstore.json", "index_store.json", "graph_store.json"):
        shutil.copy2(SRC / name, DST / name)
    index = faiss.IndexFlatL2(vectors.shape[1])  # same type as the bge-m3 index
    index.add(vectors)
    faiss.write_index(index, str(DST / "default__vector_store.json"))
    print(f"wrote {DST} ({index.ntotal} vectors)", flush=True)

    # FORRT page descriptions, the text scripts/build_forrt_pages.py embeds
    records = json.loads((PAGES_SRC / "index.json").read_text(encoding="utf-8"))
    PAGES_DST.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PAGES_SRC / "index.json", PAGES_DST / "index.json")
    np.save(PAGES_DST / "vectors.npy", voyage.documents([embed_text(r) for r in records]))
    print(f"wrote {PAGES_DST} ({len(records)} pages); cost {voyage.cost:.2f} USD", flush=True)


if __name__ == "__main__":
    main()
