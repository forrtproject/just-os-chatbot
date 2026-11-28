import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore

from config.settings import get_config
from just_os.reference_lookup import ReferenceLookup
from just_os.chat_manager import ChatManager
from just_os.hybrid import search_retriever
from just_os.qualle import Qualle, excluded_documents
from just_os.voyage import Voyage, is_voyage

logger = logging.getLogger(__name__)


class VoyageEmbedding(BaseEmbedding):
    """llama-index wrapper of just_os.voyage: questions as "query", passages as "document"."""

    _voyage: Voyage = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._voyage = Voyage(self.model_name)

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._voyage.query(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._voyage.embed([text], "document")[0].tolist()

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)


# Singleton instance for the RAG service. One lock: requests that arrive while the models load wait for that
# load instead of starting their own (each load holds ~4 GB, so parallel loads ran the pod out of memory).
_rag_service_instance: Optional[Qualle] = None
_rag_lock = threading.Lock()
# The last failed load: callers within INIT_RETRY_SECONDS get this error at once instead of loading again,
# so a broken index or a missing model cannot turn every request into a new ~1 min load. After that one
# caller tries again (Docker Compose restarts nothing; on Kubernetes the startup probe on /ready restarts the pod).
_rag_init_error: Optional[str] = None
_rag_init_failed_at = 0.0
INIT_RETRY_SECONDS = 60


def rag_status() -> Tuple[bool, Optional[str]]:
    """(loaded, last load error) without loading or waiting for the lock (for /ready)."""
    return _rag_service_instance is not None, _rag_init_error


def create_embedding_model(config: Dict[str, Any]):
    """
    Create and initialize the embedding model.

    Args:
        config: Configuration dictionary

    Returns:
        The initialized embedding model
    """
    try:
        if is_voyage(config["EMBEDDING_MODEL"]):
            return VoyageEmbedding(model_name=config["EMBEDDING_MODEL"])
        return HuggingFaceEmbedding(model_name=config["EMBEDDING_MODEL"])
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {str(e)}")
        raise


def load_index(config: Dict[str, Any], embed_model):
    persist_dir = config["VECTOR_STORE"]
    vector_store = FaissVectorStore.from_persist_dir(persist_dir)
    storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir=persist_dir)
    return load_index_from_storage(storage_context=storage_context, embed_model=embed_model)


def create_retriever(config: Dict[str, Any], embed_model, index=None):
    """
    Create and initialize the retriever component.

    Args:
        config: Configuration dictionary
        embed_model: The embedding model to use

    Returns:
        The initialized retriever
    """
    try:
        index = index if index is not None else load_index(config, embed_model)
        retriever = index.as_retriever(similarity_top_k=config["RETRIEVER_TOP_K"])
        mode = config.get("SEARCH_MODE", "vector")
        nodes = list(index.docstore.docs.values()) if mode != "vector" else []
        return search_retriever(mode, retriever, nodes, config["RETRIEVER_TOP_K"])
    except Exception as e:
        logger.error(f"Failed to initialize retriever: {str(e)}")
        raise


def create_rag_service(
    config: Optional[Dict[str, Any]] = None, chat_manager: Optional[ChatManager] = None
) -> Qualle:
    """
    Create a RAG service (Qualle) instance with the necessary components.
    Uses a singleton pattern to avoid creating multiple instances.

    Args:
        config: Configuration dictionary. If None, uses the default config.
        chat_manager: Chat manager instance. If None, creates a new instance.

    Returns:
        Qualle: The initialized RAG service instance
    """
    global _rag_service_instance, _rag_init_error, _rag_init_failed_at

    # Return existing instance if available
    if _rag_service_instance is not None:
        return _rag_service_instance

    with _rag_lock:
        # a caller that waited for the lock finds the service another one just loaded, or its fresh error
        if _rag_service_instance is not None:
            return _rag_service_instance
        if _rag_init_error is not None and time.monotonic() - _rag_init_failed_at < INIT_RETRY_SECONDS:
            raise RuntimeError(f"RAG service failed to load (retry within {INIT_RETRY_SECONDS} s): {_rag_init_error}")
        try:
            _rag_service_instance = _build_rag_service(config, chat_manager)
        except Exception as e:
            _rag_init_error, _rag_init_failed_at = f"{e.__class__.__name__}: {e}", time.monotonic()
            logger.error(f"Failed to create RAG service: {str(e)}")
            raise
        _rag_init_error = None
        logger.debug("Created new Qualle instance")
        return _rag_service_instance


def _build_rag_service(config: Optional[Dict[str, Any]], chat_manager: Optional[ChatManager]) -> Qualle:
    logger.debug("Initializing RAG components")

    # Use default config if not provided
    if config is None:  # without the app (eval scripts): the same AUTO_DEFAULTS as the app
        from just_os import eval_report
        from just_os.decisions import ROUTERS

        config = get_config()
        eval_report.apply_auto_defaults(config, ROUTERS)

    # Create chat manager if not provided
    if chat_manager is None:
        chat_manager = ChatManager()

    # Initialize embedding model
    embed_model = create_embedding_model(config)

    # Initialize retriever
    index = load_index(config, embed_model)
    retriever = create_retriever(config, embed_model, index)
    # Questions about one specific paper (by DOI, title or authors) are answered from it alone
    references = (ReferenceLookup.from_index(index, embed_model, config.get("PUB_YEARS_FILE"),
                                             excluded_documents(config.get("INDEX_CORRECTIONS_FILE")))
                  if config.get("REFERENCE_LOOKUP", True) else None)

    return Qualle(config, chat_manager, embed_model, retriever, references)
