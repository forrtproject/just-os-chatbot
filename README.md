# JUST-OS

[JUST-OS](https://www.just-os.org/) answers questions about open and reproducible research with cited sources from the [FORRT](https://forrt.org/) resource library. It runs as the chat widget on forrt.org.

It is a retrieval-augmented generation (RAG) app: Flask + Redis, LlamaIndex + FAISS over 513 open-access documents (embedding `BAAI/bge-m3`), a local re-ranker, and any OpenAI-compatible LLM (OpenRouter by default, or a self-hosted OpenScholar-8B).

## Documentation

All documentation is in [`docs/`](docs/README.md):
[architecture](docs/architecture.md) (code map, request flow, caching) ·
[data](docs/data.md) (indexes, which PDFs are embedded, ingestion) ·
[evaluation](docs/evaluation.md) (metrics and results) ·
[project plan](docs/project-plan.md) ·
[hackathon](docs/hackathon.md) ·
[issues](docs/issues.md)


## Installation

You need Docker (Docker Desktop with WSL2 on Windows), Git and Python 3. About 8 GB free disk.

1. Clone without the old large data files:
   ```bash
   GIT_LFS_SKIP_SMUDGE=1 git clone <repository-url>
   ```
2. Copy the environment file and add your OpenRouter key (`OPENROUTER_API_KEY`) to `.env`:
   ```bash
   cp .env.example .env
   ```
   All settings are in `config/settings.py`; any of them can be overridden with a line in `.env`.
   `.env.example` already selects the development setup (`COMPOSE_FILE=compose.yaml:compose.dev.yaml`): code changes restart the server. For production use `compose.yaml:compose.prod.yaml`.
3. Get the vector index (ask the project lead for the link):
   ```bash
   python scripts/get_index.py <index-zip-url>
   ```
4. Start the containers. The first build takes 10–20 minutes:
   ```bash
   docker compose up -d --build
   ```
5. One time on a new computer, download the embedding and re-ranker models (about 3.5 GB, kept in the `hf-cache` volume):
   ```bash
   docker compose exec web python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-base')"
   docker compose restart web
   ```
6. Open http://localhost:8000 (chat) or http://localhost:8000/arena (two models side by side, with `ARENA_ENABLED=true`). The server loads the models for about one minute after each start.

### Models

The LLM provider is any OpenAI-compatible API, by default [OpenRouter](https://openrouter.ai). Change models in `.env` and run `docker compose up -d web`:

| Setting | Use |
|---|---|
| `CITATION_MODEL` | writes the answer |
| `GENERAL_MODEL` | classifies and rephrases the question |
| `EMBEDDING_MODEL` + `VECTOR_STORE` | search; the two must match (default `BAAI/bge-m3`) |
| `ARENA_MODELS` | models for `/arena`, comma separated |
| `PROMPT_STYLE` | `openscholar` (default) or `short` (model-neutral answer prompt) |
| `ANSWER_CACHE_TTL` | seconds to reuse answers to near-identical first questions; `0` = off (default) |
| `PROXY_FIX_X_FOR` | number of trusted reverse proxies (prod: `1`), so the rate limit uses the client IP; `0` = none (default) |
| `HYBRID_SEARCH` | `true`: keyword (BM25) + vector search (default `false`) |
| `MAX_CHUNKS_PER_DOC` | at most this many chunks of one paper in the context; `0` = no limit (default) |

| `OPENSCHOLAR_BASE_URL` + `OPENSCHOLAR_API_KEY` | self-hosted OpenScholar server; calls for `OPENSCHOLAR_MODEL` (`openscholar-8b`) go there, all other models stay on OpenRouter |

To answer with OpenScholar, set `OPENSCHOLAR_BASE_URL`, `OPENSCHOLAR_API_KEY` and `CITATION_MODEL=openscholar-8b` in `.env` (see `.env.example`).

### Tests and evaluation

```bash
docker compose exec web pytest test/                       # offline, no index needed
docker compose exec web ruff check --select E,F --ignore E501 just_os test eval
docker compose exec -e OMP_NUM_THREADS=8 web python eval/run.py --model openai/gpt-oss-20b
docker compose exec web python eval/compare.py             # table of all runs in eval/results/
```

Before you open a PR: tests pass, and `docs/` is updated for any changed file, setting, route or cache.

## Ingestion pipeline

The ingestion creates the vector index in `data/processed/`. Run the steps in order from the repository root (details and limits: [docs/data.md](docs/data.md#5-build-an-index-ingestion)):

1. **Filter resources on open-access status (Unpaywall):**
   ```bash
   uv run python -m scripts.bootstrap_local_database
   ```
2. **Convert PDFs to Markdown:**
   ```bash
   ./scripts/marker.sh
   ```
3. **Generate embeddings:**
   ```bash
   uv run python -m scripts.embed
   ```

## API Integration

JUST-OS provides an API that can be integrated into external websites. The API is currently configured to allow access from `https://forrt.org`.

### Endpoint

**POST `/chat`**

Send a message and receive a streaming response.

### Request

```json
{
  "message": "What is open science?",
  "chat_id": "unique-conversation-id"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `message` | Yes | The user's question (3-2000 characters) |
| `chat_id` | Yes | UUID for conversation continuity (generate with `crypto.randomUUID()`) |

### Response

The endpoint returns a Server-Sent Events stream with JSON objects:

```json
{"status": "processing", "message": "Searching knowledge base..."}
{"status": "complete", "message": "<formatted HTML response>"}
```


### Example JavaScript Implementation

```javascript

let chatId = crypto.randomUUID();

async function sendMessage(userMessage) {
  const response = await fetch('https://www.just-os.org/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userMessage,
      chat_id: chatId,
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    const lines = text.split('\n').filter(line => line.trim());
    
    for (const line of lines) {
      const data = JSON.parse(line);
      if (data.status === 'complete') {
        // Display the final response
        console.log(data.message);
      } else {
        // Show processing status
        console.log('Status:', data.message);
      }
    }
  }
}
```

## Acknowledgements
The development of the application benefitted greatly from the following open source software and public resources:
- Allen Institute for AI's [OpenScholar model](https://huggingface.co/OpenSciLM/Llama-3.1_OpenScholar-8B) and [associated software](https://github.com/AkariAsai/OpenScholar)
- Sebastian Mathot's [Sigmund repository](https://github.com/open-cogsci/sigmund-ai) (The front-end portion of JUST-OS was developed with substantial reference to Sigmund and is hence shared under GPL3)
- The [Unpaywall API](https://unpaywall.org/products/api)
- [This](https://github.com/nickjj/docker-flask-example) example Docker + Flask web app
