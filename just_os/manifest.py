"""manifest.json of an index folder: the embedding model and vector size it was built with, and its counts.

Written by the scripts that build an index (scripts/embed.py, add_to_index.py, reembed.py, build_forrt_pages.py,
build_voyage_index.py) and checked when the app loads one (just_os/rag_service.py, just_os/forrt_pages.py) and before
add_to_index appends to one, so an index built with another model or vector size raises ValueError instead of
returning wrong sources or growing into a mixed index. A folder without manifest.json (every index built before it)
loads as before. No heavy imports.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"


def write_manifest(directory: Union[str, Path], embedding_model: str, dimension: int, chunk_size: Optional[int] = None,
                   document_count: Optional[int] = None, vector_count: Optional[int] = None) -> Path:
    path = Path(directory) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"embedding_model": embedding_model, "dimension": int(dimension), "chunk_size": chunk_size,
                "document_count": document_count, "vector_count": vector_count,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return path


def read_manifest(directory: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """The folder's manifest, or None when it has none (or it is not readable JSON)."""
    path = Path(directory) / MANIFEST
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"{path} is not readable ({e}); loading the index without checking it")
        return None
    return manifest if isinstance(manifest, dict) else None


def check_manifest(manifest: Optional[Dict[str, Any]], embedding_model: str, dimension: int, where: str = "index",
                   embedder_size: Optional[int] = None) -> None:
    """Raise ValueError when the vectors (dimension), the active embedder (embedder_size, when known) or
    EMBEDDING_MODEL differ from the manifest: questions and chunks embedded by different models give wrong sources,
    and chunks added with another model make a mixed index. No manifest: only the embedder size against the vectors."""
    if embedder_size is not None and int(embedder_size) != int(dimension):
        raise ValueError(f"{where}: the embedding model {embedding_model} gives {embedder_size}-dimensional "
                         f"vectors, the index has {dimension}: use the index's model or rebuild the index")
    if not manifest:
        return
    expected = manifest.get("dimension")
    if expected is not None and int(expected) != int(dimension):
        raise ValueError(f"{where}: manifest.json says {expected}-dimensional vectors "
                         f"({manifest.get('embedding_model')}), the vectors have {dimension}: rebuild the index")
    built_with = manifest.get("embedding_model")
    if built_with and built_with != embedding_model:
        raise ValueError(f"{where} was built with {built_with}, but EMBEDDING_MODEL is {embedding_model}: set "
                         "EMBEDDING_MODEL to the index's model or rebuild the index")


def check_index_dir(directory: Union[str, Path], embedding_model: str, dimension: int,
                    embedder_size: Optional[int] = None) -> None:
    check_manifest(read_manifest(directory), embedding_model, dimension, where=str(directory),
                   embedder_size=embedder_size)


def embedder_dimension(embed_model) -> Optional[int]:
    """The vector size of a llama-index embedding model without embedding anything: the sentence-transformers model
    behind HuggingFaceEmbedding knows it; None for API models (Voyage), test doubles and anything else."""
    model = getattr(embed_model, "_model", None)
    # get_embedding_dimension in sentence-transformers 5, get_sentence_embedding_dimension (deprecated) before
    getter = getattr(model, "get_embedding_dimension", None) or getattr(model, "get_sentence_embedding_dimension", None)
    if not callable(getter):
        return None
    try:
        size = getter()
    except Exception:  # noqa: BLE001 - an unknown size skips the check, it never stops the app
        return None
    return int(size) if isinstance(size, int) and size > 0 else None


def index_counts(index) -> Dict[str, int]:
    """document_count (distinct source documents) and vector_count of a llama-index FAISS index."""
    docs = index.docstore.docs
    return {"document_count": len({node.ref_doc_id or node_id for node_id, node in docs.items()}),
            "vector_count": int(index.vector_store._faiss_index.ntotal)}
