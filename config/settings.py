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
    # Seconds before an LLM call gives up (the answer then shows an error, not a hang)
    "LLM_TIMEOUT": 120,
    # Self-hosted OpenScholar (OpenAI-compatible). When OPENSCHOLAR_BASE_URL is set,
    # calls for OPENSCHOLAR_MODEL go to that server; all other models stay on BASE_URL.
    "OPENSCHOLAR_BASE_URL": "",
    "OPENSCHOLAR_API_KEY": os.getenv("OPENSCHOLAR_API_KEY"),
    "OPENSCHOLAR_MODEL": "openscholar-8b",
    # Multilingual; must match VECTOR_STORE. English-only option: BAAI/bge-small-en-v1.5
    # with data/processed/vs_latest_bge-small-en-v1.5
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    # Local CrossEncoder on CPU
    "RERANK_MODEL": "BAAI/bge-reranker-base",
    # CPU threads for the re-ranker and embedding (20 chunks: ~25 s with 1 thread, ~13 s with 6)
    "RERANK_THREADS": 6,
    # Follow-up questions: "rephrase" (one LLM call makes a stand-alone question) or
    # "history" (no rephrase; the earlier turns go into the answer prompt)
    "CONTEXT_METHOD": "rephrase",
    # Check each cited sentence against its source with the re-ranker; mark weak ones
    "VERIFY_CITATIONS": False,
    "VERIFY_MIN_SCORE": 0.1,
    # FORRT lookup mode: route "where/how on FORRT" questions to a search of the FORRT sheet
    "FORRT_LOOKUP": False,
    "FORRT_SHEET_FILE": "data/raw/forrt_sheet1_261028.csv",
    "FORRT_LOOKUP_TOP_K": 5,
    # Answer prompt: "openscholar" (long, made for OpenScholar) or "short" (model-neutral)
    "PROMPT_STYLE": "openscholar",
    # Semantic answer cache: seconds to keep answers (0 = off); reuse if cosine >= limit
    "ANSWER_CACHE_TTL": 0,
    "ANSWER_CACHE_MIN_SIMILARITY": 0.95,
    "ANSWER_CACHE_MAX_ITEMS": 500,
    # Temperature settings
    "TEMPERATURE": 0.3,
    "TEMPERATURE_GENERAL": 0.15,
    # Vector store settings
    "VECTOR_STORE": "data/processed/vs_latest_bge-m3",
    "RETRIEVER_TOP_K": 20,
    # RANKING SETTINGS
    "MIN_RELEVANCE": 0.1,
    "MAX_CHUNKS": 7,
    # At most this many chunks of one paper in the context (0 = no limit), for variety
    "MAX_CHUNKS_PER_DOC": 0,
    # Keyword (BM25) + vector search, merged by reciprocal rank fusion (just_os/hybrid.py)
    "HYBRID_SEARCH": False,
    # doi,year table for the reference year (scripts/get_pub_years.py); missing → "n.d."
    "PUB_YEARS_FILE": "data/raw/pub_years.csv",
    # Redis settings
    "REDIS_HOST": "redis",
    "REDIS_PORT": 6379,
    "REDIS_DB": 0,
    # see https://flask-limiter.readthedocs.io/en/stable/configuration.html#ratelimit-string
    "RATE_LIMIT": "100/minute;500/hour;2000/day",
    # Number of trusted reverse proxies in front of the app (0 = none). Set to 1 behind
    # one proxy, so the rate limit uses the client IP, not the proxy IP. Never set it
    # without a proxy: clients could then fake their IP.
    "PROXY_FIX_X_FOR": 0,
    # CORS settings
    "ALLOWED_ORIGINS": ["https://forrt.org"],
    # Input validation
    "MAX_MESSAGE_LENGTH": 2000,
    "MIN_MESSAGE_LENGTH": 3,
    # Chat settings
    "MESSAGE_TTL": 3600,  # 1 hour in seconds
    # Arena (page /arena): the user picks models, each answers the same question from the
    # same sources, and the user rates each answer 1-5. Off by default: one LLM call per model.
    # The candidates of docs/evaluation.md 3.3 (all on OpenRouter) + the self-hosted
    # OpenScholar, which is hidden while OPENSCHOLAR_BASE_URL is not set.
    "ARENA_ENABLED": False,
    "ARENA_MODELS": "meta-llama/llama-3.1-8b-instruct,openai/gpt-oss-20b,qwen/qwen3-14b,"
    "qwen/qwen3.7-flash,google/gemma-3-12b-it,google/gemma-3-27b-it,"
    "mistralai/mistral-small-3.2-24b-instruct,openai/gpt-6-luna,deepseek/deepseek-v4-flash,"
    "openscholar-8b",
    # Most models one question may go to (cost and time)
    "ARENA_MAX_MODELS": 10,
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
        # bool before int: bool is a subclass of int
        if isinstance(default_value, bool):
            DEFAULT_CONFIG[key] = os.environ.get(key).lower() in ("true", "yes", "1")
        elif isinstance(default_value, int):
            DEFAULT_CONFIG[key] = int(os.environ.get(key))
        elif isinstance(default_value, float):
            DEFAULT_CONFIG[key] = float(os.environ.get(key))
        else:
            DEFAULT_CONFIG[key] = os.environ.get(key)

# Export all configuration values to module level for backward compatibility
for key, value in DEFAULT_CONFIG.items():
    globals()[key] = value


def get_config() -> Dict[str, Any]:
    """Return the current configuration as a dictionary."""
    return {k: v for k, v in DEFAULT_CONFIG.items()}
