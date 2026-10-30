"""Build a second index from the chunks of an existing one, with another embedding model.

The chunks and metadata stay the same, so only the embedding model differs.

    python reembed.py data/processed/vs_latest_bge-small-en-v1.5 BAAI/bge-m3
"""

import sys

import faiss
import torch
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore

if __name__ == "__main__":
    source_dir, model_name = sys.argv[1], sys.argv[2]
    output_path = f"data/processed/vs_latest_{model_name.split('/')[-1]}"

    nodes = list(SimpleDocumentStore.from_persist_dir(source_dir).docs.values())
    for node in nodes:
        node.embedding = None  # nodes with an embedding are not embedded again

    # Half precision on a GPU is about 3x faster and uses half the memory
    model_kwargs = {"torch_dtype": torch.float16} if torch.cuda.is_available() else {}
    embed_model = HuggingFaceEmbedding(
        model_name=model_name, embed_batch_size=32, model_kwargs=model_kwargs
    )
    probe = embed_model.get_text_embedding("Why is the sky blue?")
    vector_store = FaissVectorStore(faiss_index=faiss.IndexFlatL2(len(probe)))
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )
    index.storage_context.persist(output_path)
    print(f"{len(nodes)} nodes -> {output_path}")
