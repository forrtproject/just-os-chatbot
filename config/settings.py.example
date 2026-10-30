import os
from typing import Dict, Any

# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    # Chunking settings
    "CHUNK_SIZE": 350,
    # LLM settings: any OpenAI-compatible API. Default is OpenRouter.
    # OpenScholar runs only on the RUG gateway: set BASE_URL=https://llm.hpc.rug.nl/,
    # LLM_API_KEY=<RUG key>, CITATION_MODEL=openscholar, GENERAL_MODEL=default-chat
    "BASE_URL": "https://openrouter.ai/api/v1",
    "LLM_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    "CITATION_MODEL": "meta-llama/llama-3.1-8b-instruct",
    "GENERAL_MODEL": "meta-llama/llama-3.1-8b-instruct",
    # Multilingual; must match VECTOR_STORE. English-only option: BAAI/bge-small-en-v1.5
    # with data/processed/vs_latest_bge-small-en-v1.5
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    # Local CrossEncoder on CPU
    "RERANK_MODEL": "BAAI/bge-reranker-base",
    # Temperature settings
    "TEMPERATURE": 0.3,
    "TEMPERATURE_GENERAL": 0.15,
    # Vector store settings
    "VECTOR_STORE": "data/processed/vs_latest_bge-m3",
    "RETRIEVER_TOP_K": 20,
    # RANKING SETTINGS
    "MIN_RELEVANCE": 0.1,
    "MAX_CHUNKS": 7,
    # Redis settings
    "REDIS_HOST": "redis",
    "REDIS_PORT": 6379,
    "REDIS_DB": 0,
    # see https://flask-limiter.readthedocs.io/en/stable/configuration.html#ratelimit-string
    "RATE_LIMIT": "100/minute;500/hour;2000/day",
    # CORS settings
    "ALLOWED_ORIGINS": ["https://forrt.org"],
    # Input validation
    "MAX_MESSAGE_LENGTH": 2000,
    "MIN_MESSAGE_LENGTH": 3,
    # Chat settings
    "MESSAGE_TTL": 3600,  # 1 hour in seconds
    # Google Drive settings
    "CREDENTIALS_FILE": "credentials.json",
    "GDRIVE_FOLDER_ID": "1EqOxpkb-ksYjRmvSHl1XjULlcPxZINdD",
    "URL_JUST_OS_DB": "https://drive.google.com/uc?id=1eMiimpcwcnVJT6k4PQ9xfz3Udvsejo6V",
    "GDRIVE_AUTHENTICATION_SERVER_PORT": 41813,
}

# Override defaults with environment variables
for key in DEFAULT_CONFIG:
    if os.environ.get(key):
        # Convert to appropriate type based on default value
        default_value = DEFAULT_CONFIG[key]
        if isinstance(default_value, int):
            DEFAULT_CONFIG[key] = int(os.environ.get(key))
        elif isinstance(default_value, float):
            DEFAULT_CONFIG[key] = float(os.environ.get(key))
        elif isinstance(default_value, bool):
            DEFAULT_CONFIG[key] = os.environ.get(key).lower() in ("true", "yes", "1")
        else:
            DEFAULT_CONFIG[key] = os.environ.get(key)

# Export all configuration values to module level for backward compatibility
for key, value in DEFAULT_CONFIG.items():
    globals()[key] = value


def get_config() -> Dict[str, Any]:
    """Return the current configuration as a dictionary."""
    return {k: v for k, v in DEFAULT_CONFIG.items()}
