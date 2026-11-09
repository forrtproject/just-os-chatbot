"""Add new documents to an existing index, without a full rebuild (issue C4, #25).

    docker compose run --rm -v ./data:/app/data web \\
        python -m scripts.add_to_index <markdown-dir> <metadata.csv> [--index DIR] [--output DIR]

<metadata.csv> has a doi_hash column (the Markdown file name without .md) and the usual
metadata (title, creators, link_to_resource, doi, conditions_of_use, ...). Documents whose
DOI or title is already in the index are skipped. The embedding model is EMBEDDING_MODEL,
so it must be the model of the index. --output defaults to the index folder itself; give a
new folder to keep the old index. Example: scripts/fetch_web_resources.py output.
"""

import argparse
from pathlib import Path

import pandas as pd
from llama_index.core import Document, Settings, StorageContext, load_index_from_storage
from llama_index.vector_stores.faiss import FaissVectorStore

from config import settings as justos_settings
from just_os.references import document_key, plain_metadata
from scripts.embed import cleanup_markdown, unique_metadata


def load_index(index_dir: str, embed_model):
    vector_store = FaissVectorStore.from_persist_dir(index_dir)
    storage = StorageContext.from_defaults(vector_store=vector_store, persist_dir=index_dir)
    return load_index_from_storage(storage_context=storage, embed_model=embed_model)


def indexed_keys(index) -> set:
    return {document_key(plain_metadata(node.metadata)) for node in index.docstore.docs.values()}


def new_documents(markdown_dir: Path, metadata: pd.DataFrame, known: set) -> list:
    """Documents for the Markdown files with metadata that are not in the index yet."""
    excluded = set(metadata.columns).difference(("title",))
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
            excluded_llm_metadata_keys=list(excluded),
            excluded_embed_metadata_keys=list(excluded),
        ))
    return documents


def add_documents(index, documents) -> int:
    for document in documents:
        index.insert(document)
    return len(documents)


if __name__ == "__main__":
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    parser = argparse.ArgumentParser()
    parser.add_argument("markdown_dir", type=Path)
    parser.add_argument("metadata_csv")
    parser.add_argument("--index", default=justos_settings.VECTOR_STORE)
    parser.add_argument("--output")
    args = parser.parse_args()

    Settings.chunk_size = justos_settings.CHUNK_SIZE
    embed_model = HuggingFaceEmbedding(model_name=justos_settings.EMBEDDING_MODEL)
    index = load_index(args.index, embed_model)
    metadata = unique_metadata(pd.read_csv(args.metadata_csv).set_index("doi_hash"))
    added = add_documents(index, new_documents(args.markdown_dir, metadata, indexed_keys(index)))
    output = args.output or args.index
    index.storage_context.persist(output)
    print(f"added {added} documents → {output} (restart the web container to load it)")
