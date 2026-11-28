"""Add new documents to an existing index, without a full rebuild (issue C4, #25).

    docker compose run --rm -v ./data:/app/data web \\
        python -m scripts.add_to_index <markdown-dir> <metadata.csv> [--index DIR] [--output DIR]

<metadata.csv> has a doi_hash column (the Markdown file name without .md) and the usual
metadata (title, creators, link_to_resource, doi, conditions_of_use, ...). Documents whose
DOI or title is already in the index are skipped. The embedding model is EMBEDDING_MODEL,
so it must be the model of the index (a manifest.json naming another model or vector size stops the run). --output defaults to the index folder itself; give a
new folder to keep the old index. Example: scripts/fetch_web_resources.py output.
"""

import argparse
from pathlib import Path

import pandas as pd
from llama_index.core import Document, Settings, StorageContext, load_index_from_storage
from llama_index.vector_stores.faiss import FaissVectorStore

from config import settings as justos_settings
from just_os.manifest import check_index_dir, embedder_dimension, index_counts, read_manifest, write_manifest
from just_os.references import document_key, plain_metadata
from scripts.build_abstract_cards import CARD_TYPE
from scripts.embed import cleanup_markdown, excluded_keys, unique_metadata


def load_index(index_dir: str, embed_model):
    vector_store = FaissVectorStore.from_persist_dir(index_dir)
    storage = StorageContext.from_defaults(vector_store=vector_store, persist_dir=index_dir)
    return load_index_from_storage(storage_context=storage, embed_model=embed_model)


def indexed_keys(index) -> set:
    """document_key of every document in the index except abstract cards, so a full text can join its card.
    shortcut: the card stays in the index (FAISS here cannot delete vectors; the per-paper cap counts both as one
    paper); drop cards when the index is next built from scratch."""
    return {document_key(meta) for node in index.docstore.docs.values()
            if not str((meta := plain_metadata(node.metadata)).get("material_type", "")).startswith(CARD_TYPE)}


def new_documents(markdown_dir: Path, metadata: pd.DataFrame, known: set) -> list:
    """Documents for the Markdown files with metadata that are not in the index yet."""
    excluded = excluded_keys(metadata)
    documents = []
    for path in sorted(markdown_dir.glob("*.md")):
        if path.stem not in metadata.index:
            continue
        meta = {k: ("" if pd.isna(v) else v) for k, v in metadata.loc[path.stem].to_dict().items()}
        if document_key(meta) in known:
            continue
        known.add(document_key(meta))
        documents.append(Document(
            text=cleanup_markdown(path.read_text(encoding="utf-8")),
            metadata=meta,
            text_template="{content}",
            excluded_llm_metadata_keys=excluded,
            excluded_embed_metadata_keys=excluded,
        ))
    return documents


def check_index(index, index_dir, embedding_model: str, embed_model=None) -> None:
    """ValueError before anything is added when the index's manifest.json names another embedding model or vector
    size, or the embedder's vectors are not the index's size: adding would mix two vector spaces in one index."""
    check_index_dir(index_dir, embedding_model, index.vector_store._faiss_index.d, embedder_dimension(embed_model))


def add_documents(index, documents) -> int:
    for document in documents:
        index.insert(document)
    return len(documents)


def update_manifest(index, output, source, embedding_model: str, chunk_size: int) -> None:
    """manifest.json of the grown index; the source folder's chunk size when it has one (this run chunks with
    CHUNK_SIZE)."""
    old = read_manifest(source) or {}
    write_manifest(output, embedding_model, index.vector_store._faiss_index.d, old.get("chunk_size") or chunk_size,
                   **index_counts(index))


if __name__ == "__main__":
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    parser = argparse.ArgumentParser()
    parser.add_argument("markdown_dir", type=Path)
    parser.add_argument("metadata_csv")
    parser.add_argument("--index", default=justos_settings.VECTOR_STORE)
    parser.add_argument("--output")
    args = parser.parse_args()

    Settings.chunk_size = justos_settings.CHUNK_SIZE
    import torch

    # Half precision on a GPU is about 3x faster and uses half the memory (as in scripts/reembed.py)
    model_kwargs = {"torch_dtype": torch.float16} if torch.cuda.is_available() else {}
    embed_model = HuggingFaceEmbedding(
        model_name=justos_settings.EMBEDDING_MODEL, embed_batch_size=32, model_kwargs=model_kwargs
    )
    index = load_index(args.index, embed_model)
    check_index(index, args.index, justos_settings.EMBEDDING_MODEL, embed_model)  # never a mixed index
    # doi_hash as text: file names such as 0011 are not numbers
    metadata = unique_metadata(pd.read_csv(args.metadata_csv, dtype={"doi_hash": str}).set_index("doi_hash"))
    added = add_documents(index, new_documents(args.markdown_dir, metadata, indexed_keys(index)))
    output = args.output or args.index
    index.storage_context.persist(output)
    update_manifest(index, output, args.index, justos_settings.EMBEDDING_MODEL, justos_settings.CHUNK_SIZE)
    print(f"added {added} documents → {output} (restart the web container to load it)")
