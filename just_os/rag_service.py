import logging
from typing import Dict, Any, List, Optional

from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore

from config.settings import get_config
from just_os.reference_lookup import ReferenceLookup
from just_os.chat_manager import ChatManager
from just_os.manifest import check_index_dir, embedder_dimension
from just_os.hybrid import excluded_node_ids, search_retriever
from just_os.qualle import Qualle, excluded_documents
from just_os.voyage import Voyage, is_voyage, voyage_dimension

logger = logging.getLogger(__name__)


class VoyageEmbedding(BaseEmbedding):
    """llama-index wrapper of just_os.voyage: questions as "query", passages as "document"."""

    _voyage: Voyage = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._voyage = Voyage(self.model_name)

    @property
    def embedding_dimension(self) -> Optional[int]:
        return voyage_dimension(self.model_name)

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._voyage.query(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._voyage.embed([text], "document")[0].tolist()

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)


# Singleton instance for the RAG service
_rag_service_instance: Optional[Qualle] = None


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
    # manifest.json (new indexes): the vectors are the size and model it names (ValueError otherwise); an older folder
    # is only checked against the embedder's vector size, when known
    dimension = getattr(getattr(vector_store, "_faiss_index", None), "d", None)
    if dimension is not None:
        check_index_dir(persist_dir, config.get("EMBEDDING_MODEL", ""), dimension, embedder_dimension(embed_model))
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
        top_k = config["RETRIEVER_TOP_K"]
        # chunks of excluded documents (config/index_corrections.json) are fetched in addition and dropped before the
        # cut to top_k, so they never take a valid chunk's place
        excluded = excluded_documents(config.get("INDEX_CORRECTIONS_FILE"))
        excluded_ids = excluded_node_ids(index.docstore.docs.values(), excluded) if excluded else frozenset()
        retriever = index.as_retriever(similarity_top_k=top_k + len(excluded_ids))
        mode = config.get("SEARCH_MODE", "vector")
        nodes = list(index.docstore.docs.values()) if mode != "vector" else []
        return search_retriever(mode, retriever, nodes, top_k, excluded_ids)
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
    global _rag_service_instance

    # Return existing instance if available
    if _rag_service_instance is not None:
        return _rag_service_instance

    logger.debug("Initializing RAG components")

    # Use default config if not provided
    if config is None:  # the gunicorn preload (config/gunicorn.py): the same AUTO_DEFAULTS as the app
        from just_os import eval_report
        from just_os.decisions import ROUTERS

        config = get_config()
        eval_report.apply_auto_defaults(config, ROUTERS)

    # Create chat manager if not provided
    if chat_manager is None:
        chat_manager = ChatManager()

    try:
        # Initialize embedding model
        embed_model = create_embedding_model(config)

        # Initialize retriever
        index = load_index(config, embed_model)
        retriever = create_retriever(config, embed_model, index)
        # Questions about one specific paper (by DOI, title or authors) are answered from it alone
        references = (ReferenceLookup.from_index(index, embed_model, config.get("PUB_YEARS_FILE"),
                                                 excluded_documents(config.get("INDEX_CORRECTIONS_FILE")))
                      if config.get("REFERENCE_LOOKUP", True) else None)

        # Create and store the Qualle instance
        _rag_service_instance = Qualle(config, chat_manager, embed_model, retriever, references)
        logger.debug("Created new Qualle instance")

        return _rag_service_instance
    except Exception as e:
        logger.error(f"Failed to create RAG service: {str(e)}")
        raise
