import os
import warnings
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
    # Models that reason by default and must not (their reasoning used up MAX_ANSWER_TOKENS, so the
    # answer came back empty): OpenRouter's reasoning is switched off for these only
    "NO_REASONING_MODELS": "qwen/qwen3.7-flash",
    # A failed model call (provider error, time-out or an empty answer) is tried this many more times,
    # with a short pause, before the user sees an error and its Try again button. Not for OpenScholar,
    # whose answers take minutes. Worst case (1 + retries) x LLM_TIMEOUT must stay under WEB_TIMEOUT
    "LLM_RETRIES": 3,
    # Seconds before an LLM call gives up (the answer then shows an error, not a hang)
    "LLM_TIMEOUT": 60,
    # Longest answer in tokens. Without a cap Llama 3.1 8B looped in Kannada and Marathi up to
    # 16k tokens (12 min, eval 12 Nov); English answers stay under ~1k. 0 = no cap
    "MAX_ANSWER_TOKENS": 2000,
    # Self-hosted OpenScholar (OpenAI-compatible). When OPENSCHOLAR_BASE_URL is set,
    # calls for OPENSCHOLAR_MODEL go to that server; all other models stay on BASE_URL.
    "OPENSCHOLAR_BASE_URL": "",
    "OPENSCHOLAR_API_KEY": os.getenv("OPENSCHOLAR_API_KEY"),
    "OPENSCHOLAR_MODEL": "openscholar-8b",
    # Seconds for one OpenScholar answer (the self-hosted CPU server needs minutes)
    "OPENSCHOLAR_TIMEOUT": 600,
    # Multilingual; must match VECTOR_STORE. English-only option: BAAI/bge-small-en-v1.5
    # with data/processed/vs_latest_bge-small-en-v1.5
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    # Local CrossEncoder on CPU; multilingual (bge-reranker-base is English-focused and
    # dropped German/Spanish questions as "no sources", eval 5 Nov)
    "RERANK_MODEL": "BAAI/bge-reranker-v2-m3",
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
    # Decision-model router: one call to a decision model (TypeSafe Jev, Cloudflare Clef or
    # Clef-flash via OpenRouter's decisions API) classifies the question as open_science /
    # forrt / both / neither. Below DECISION_ROUTER_MIN_CONFIDENCE, or when the call fails,
    # the LLM classifier above decides. Models: typesafe/jev-1.14, cloudflare/clef, cloudflare/clef-flash
    "DECISION_ROUTER": True,
    # Default topic check for every question (empty = DECISION_ROUTER as below); one of the keys
    # of ROUTERS in just_os/decisions.py. The chat and arena pages can choose another per question.
    "ROUTER": "",
    # Cosine router: nearest paper chunk / nearest FORRT page description (bge-m3 cosine);
    # calibrated on eval/questions.jsonl + eval/forrt_questions.jsonl, docs/evaluation.md 3.7
    "COSINE_PAPER_MIN": 0.62,
    "COSINE_PAGE_MIN": 0.51,
    # Banded router (ROUTER=banded): below both LOW → refuse; paper at or above BAND_PAPER_HIGH and
    # page below BAND_PAGE_HIGH → papers; both with no model call. Anything else, including every
    # question close to a FORRT page, → BAND_MIDDLE_ROUTER (a ROUTERS key). Set on held-out questions
    # by eval/tune_bands.py, strictly: an answered off-topic question is the worse error
    # eval/results/bands_261112.csv, docs/evaluation.md 3.11
    "BAND_PAPER_LOW": 0.586,
    "BAND_PAPER_HIGH": 0.701,
    "BAND_PAGE_LOW": 0.461,
    "BAND_PAGE_HIGH": 0.606,
    "BAND_MIDDLE_ROUTER": "jev",
    "DECISION_ROUTER_MODEL": "cloudflare/clef-flash",  # best of Jev/Clef/Clef-flash in docs/evaluation.md 3.6
    "DECISION_ROUTER_MIN_CONFIDENCE": 0.5,
    "DECISION_URL": "https://openrouter.ai/api/alpha/decisions",
    "DECISION_TIMEOUT": 8,  # seconds; on timeout or error the LLM classifier decides
    # FORRT page router (just_os/forrt_pages.py): "forrt" questions are answered from forrt.org's
    # own pages; "both" questions get the paper answer plus links to FORRT pages. Needs the page
    # index from scripts/build_forrt_pages.py in FORRT_PAGES_DIR.
    "FORRT_PAGES": True,
    "FORRT_PAGES_DIR": "vector_data/forrt_pages",  # in Git (~1 MB); rebuild with scripts/build_forrt_pages.py
    "FORRT_SELECT_MODEL": "cloudflare/clef",  # decision model that picks the pages
    "FORRT_ANSWER_MODEL": "",  # empty = CITATION_MODEL
    "FORRT_DESCRIBE_MODEL": "openai/gpt-oss-20b",  # writes the page descriptions (build script)
    "FORRT_TOP_K": 12,  # candidate pages from the search
    "FORRT_MAX_PAGES": 4,  # pages read for one answer
    # Papers answers also read forrt.org pages (follow-up of #53): the page index is searched while the
    # papers are; pages with a search score >= FORRT_IN_PAPERS_MIN_SCORE that the decision model clearly
    # picks (FORRT_DECISION_THRESHOLD, no fallback) join the paper chunks as sources. The `both` route
    # skips the score floor. Measured in docs/evaluation.md 3.14.
    "FORRT_IN_PAPERS": True,
    "FORRT_IN_PAPERS_MIN_SCORE": 0.6,
    "FORRT_IN_PAPERS_MAX_PAGES": 2,
    "FORRT_IN_PAPERS_MAX_CHARS": 3000,  # per page, the parts that best match the question
    "FORRT_IN_PAPERS_TIMEOUT": 10,  # seconds to wait after the paper search; then the papers alone
    "FORRT_DECISION_THRESHOLD": 0.7,  # keep pages with p >= this ...
    "FORRT_DECISION_FLOOR": 0.2,  # ... or, if none, the plausible ones above this; below = not found
    "FORRT_FETCH_TIMEOUT": 6,
    "FORRT_CACHE_TTL": 3600,  # pages are always read live; seconds an answer may reuse a fetched page
    "FORRT_FETCH_DOMAINS": "forrt.org",
    "FORRT_MAX_CHARS_PER_PAGE": 12000,  # a typical long page whole (/about/us/ ~8,400); longer pages are trimmed
    "FORRT_MAX_ANSWER_TOKENS": 1500,
    "FORRT_LISTING_URLS": "https://forrt.org/post/",  # read first for news/event questions
    "FORRT_LEXICAL_WEIGHT": 0.1,
    "FORRT_RECENCY_WEIGHT": 0.1,
    "FORRT_RECENCY_HALF_LIFE": 90,
    "FORRT_EXTRA_URLS_FILE": "config/forrt_extra_urls.txt",  # FORRT project sites missing from the sitemap
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
    # Adaptive top-k (N5, #33): keep the re-ranked chunks that score at least ADAPTIVE_TOP_K_RATIO
    # of the best chunk's score, but at least ADAPTIVE_TOP_K_MIN; MAX_CHUNKS stays the maximum
    # and MIN_RELEVANCE / MAX_CHUNKS_PER_DOC still apply. Off: always up to MAX_CHUNKS
    "ADAPTIVE_TOP_K": False,
    "ADAPTIVE_TOP_K_RATIO": 0.5,
    "ADAPTIVE_TOP_K_MIN": 3,
    # At most this many chunks of one paper in the context (0 = no limit), for variety
    "MAX_CHUNKS_PER_DOC": 0,
    # Search: "vector" (FAISS), "bm25" (keywords) or "hybrid" (both, merged by reciprocal
    # rank fusion); just_os/hybrid.py. Replaces HYBRID_SEARCH=true, now SEARCH_MODE=hybrid
    "SEARCH_MODE": "vector",
    # Re-rank the found chunks with RERANK_MODEL and drop those at or below MIN_RELEVANCE;
    # false keeps the search order and does not load the re-ranker (unless VERIFY_CITATIONS)
    "RERANK": True,
    # With RERANK=false: "no sources" when the best vector match of the question has a lower
    # cosine (vector and hybrid search; 0 = no check). 0.55 from docs/evaluation.md 3.4 (#21)
    "MIN_VECTOR_SIMILARITY": 0.55,
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
    # true: hide the model names until the answers are rated (blind rating)
    "ARENA_BLIND": False,
    # Each rating is also appended here (JSON lines, in Git for the team); empty = Redis only
    "ARENA_RATINGS_FILE": "data/arena/ratings.jsonl",
    # Every arena question with all answers, rated or not (JSON lines); empty = not saved
    "ARENA_ROUNDS_FILE": "data/arena/rounds.jsonl",
    # true: at start-up the answer model (CITATION_MODEL) and the topic check (ROUTER) of chat and arena
    # are the eval winners in EVAL_RESULTS_DIR (eval_report.best_defaults, the /eval summary cards);
    # the settings above stay the fallback when the results cannot decide. A restart picks up new results
    "AUTO_DEFAULTS": False,
    # Page /review (#8): the questions, answers and sources people score (eval/build_review.py); scores
    # are saved as one CSV per reviewer and save in REVIEW_DIR (in Git during the test phase, like the chats)
    "REVIEW_ITEMS_FILE": "eval/human_review_items.json",
    "REVIEW_DIR": "data/reviews",
    # Page /eval reads the result CSVs of eval/run.py, eval/classify.py and eval/compare_embeddings.py here
    "EVAL_RESULTS_DIR": "eval/results",
    # Chat page: every answered turn (question, answer, outcome: answered/off_topic/
    # no_sources/error/forrt_lookup/forrt/both) and every Good/Bad feedback are appended here as JSON
    # lines. Empty = not saved. These and the arena files are in Git during the test phase
    # only: remove them from Git (and .gitignore) before the bot goes live.
    "CHAT_LOG_FILE": "data/chats/chats.jsonl",
    "CHAT_FEEDBACK_FILE": "data/chats/feedback.jsonl",
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

if os.environ.get("HYBRID_SEARCH"):
    warnings.warn("HYBRID_SEARCH is no longer read; set SEARCH_MODE=hybrid instead", stacklevel=1)

# Export all configuration values to module level for backward compatibility
for key, value in DEFAULT_CONFIG.items():
    globals()[key] = value


def get_config() -> Dict[str, Any]:
    """Return the current configuration as a dictionary."""
    return {k: v for k, v in DEFAULT_CONFIG.items()}
