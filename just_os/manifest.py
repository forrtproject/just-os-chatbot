"""manifest.json of an index folder: the embedding model and vector size it was built with, and its counts.

Written by the scripts that build an index (scripts/embed.py, add_to_index.py, reembed.py, build_forrt_pages.py,
build_voyage_index.py) and checked when the app loads one (just_os/rag_service.py, just_os/forrt_pages.py), so an
index built with another model fails loudly instead of returning wrong sources. A folder without manifest.json
(every index built before it) loads as before. No heavy imports.
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


def check_manifest(manifest: Optional[Dict[str, Any]], embedding_model: str, dimension: int, where: str = "index") -> None:
    """A vector size other than the manifest's raises ValueError (the search would fail or be meaningless); another
    embedding model is logged as an error (a renamed copy of the same model still works). No manifest: no check."""
    if not manifest:
        return
    expected = manifest.get("dimension")
    if expected is not None and int(expected) != int(dimension):
        raise ValueError(f"{where}: manifest.json says {expected}-dimensional vectors "
                         f"({manifest.get('embedding_model')}), the vectors have {dimension}: rebuild the index")
    built_with = manifest.get("embedding_model")
    if built_with and built_with != embedding_model:
        logger.error(f"{where} was built with {built_with}, but EMBEDDING_MODEL is {embedding_model}: "
                     "questions and chunks are embedded with different models, so the sources will be wrong")


def check_index_dir(directory: Union[str, Path], embedding_model: str, dimension: int) -> None:
    check_manifest(read_manifest(directory), embedding_model, dimension, where=str(directory))


def index_counts(index) -> Dict[str, int]:
    """document_count (distinct source documents) and vector_count of a llama-index FAISS index."""
    docs = index.docstore.docs
    return {"document_count": len({node.ref_doc_id or node_id for node_id, node in docs.items()}),
            "vector_count": int(index.vector_store._faiss_index.ntotal)}
