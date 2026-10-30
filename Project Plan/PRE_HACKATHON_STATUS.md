# JUST-OS — Pre-hackathon status

**Date:** 28 October 2026  **Deadline:** 10 November 2026 (hackathon 11–13 November)
**Language:** ASD-STE100 Simplified Technical English.
**Change to the plan:** Use **OpenRouter**, not Hugging Face. Where the plan says "HF" or "Hugging Face", read "OpenRouter".

Status keys: **DONE** = complete. **YOU** = needs your action. **OPEN** = work to do.

---

## 1. Summary table

| # | Task | Status |
|---|---|---|
| 1 | Move the code to the repository root | DONE |
| 2 | Keep data and old index out of Git | DONE |
| 3 | Use OpenRouter as the LLM provider (plan P5) | DONE (tested live, 28 Oct) |
| 3a | Bot runs locally in Docker (plan P3) | DONE (see 2.8) |
| 4 | Local re-ranker with fallback (plan P7, bugs #2 and #8) | DONE |
| 5 | Save the FORRT CSV files | DONE |
| 6 | Paste the OpenRouter key | DONE |
| 7 | Get the RUG key for OpenScholar | YOU |
| 8 | Get the current vector index (`vs_latest_bge-small-en-v1.5`) | DONE (found in `NWO JUST-OS/BOT`) |
| 8a | Second index with `BAAI/bge-m3` (multilingual), now the default | DONE (see 2.7) |
| 8c | Share the bge-m3 index with the team | YOU (see 2.7) |
| 8b | Data inventory of the two new folders | DONE (see 2.6) |
| 9 | Compare many OpenRouter models | OPEN (list ready) |
| 10 | Compare context (memory) methods | OPEN (design ready) |
| 11 | Two modes: Open Science and FORRT lookup | OPEN |
| 12 | Cheapest and reasoning models | OPEN (list ready) |
| 13 | Multilingual check | DONE for retrieval (see 4.6b). Full pipeline test OPEN |
| 13a | Embedding model comparison (6 models) | DONE (see 4.6b) |
| 14 | Other plan tasks P6, P8–P22 | OPEN |

---

## 2. Done

### 2.1 Repository layout
- The code is now at the root of `just-os-chatbot`. The folder `just-os/` does not exist now.
- The old upstream Git history (2.3 GB) is now in `D:\Uni\UM\just-os-upstream.git`. Git does not use it. Delete it when you do not need it. Its remotes are `forrtproject/just-os` and `JUST-Open-Science/JUST-OS`.
- `.gitattributes` (Git LFS rules for `data/`) is deleted. We do not use LFS.
- Nothing is committed.

### 2.2 Data out of Git
- `.gitignore` now ignores `data/**` and `archive/`. The files stay on your disk.
- Git tracks only these seed files: `data/raw/*.csv` and `data/interim/questions_and_text.csv`.

### 2.3 OpenRouter
- `config/settings.py` and `config/settings.py.example`: `BASE_URL` is `https://openrouter.ai/api/v1`. The embedding model is `BAAI/bge-m3` (see 2.7). The key comes from `OPENROUTER_API_KEY`. The default model is `meta-llama/llama-3.1-8b-instruct`.
- To change the model, set `CITATION_MODEL` and `GENERAL_MODEL` in `.env`. Then restart. You do not change code.
- To use OpenScholar, set the four RUG lines in `.env` (see `.env.example`).
- `RUGLLM_API_KEY` is not used now. Use `LLM_API_KEY` for the RUG key.

### 2.4 Local re-ranker
- The old code sent the re-rank request to `{BASE_URL}/rerank`. OpenRouter does not have this endpoint. Thus, every answer was empty.
- Now the server runs `BAAI/bge-reranker-base` on the CPU (`sentence_transformers.CrossEncoder`).
- If the re-ranker fails, the code uses the vector order. The answer is not empty.
- Test: `test/test_rerank.py` (2 tests).

### 2.5 FORRT CSV files
You do not need to download them. The ingest code (`ingest/helpers.py`, `URL_FORRT`) reads the same two URLs live.
For a fixed copy, I saved them here:

| File | Rows | Content |
|---|---|---|
| `data/raw/forrt_sheet1_261028.csv` | 1,504 | Main FORRT resource sheet (title, URL/DOI, abstract, language, clusters, APA reference) |
| `data/raw/forrt_sheet2_261028.csv` | 285 | Reference list (reference, clusters, DOI, title, authors, url, material type) |

**Note:** The total is 1,789 rows. The plan says "~2,800". Update the plan (B2.4).
To get a new copy, download again and use the date in the name (`YYMMDD`).

### 2.6 Data inventory (`data/NWO JUST-OS`, `data/FORRT Clusters pdfs`)
Both folders are git-ignored. **Some files are private** (grants, MOU, e-mails, meeting notes). Do not put them in Git, in the index or in a public place.

**Use:**
| Item | Content | Use for |
|---|---|---|
| `NWO JUST-OS/Content/` | 657 PDFs, named by JUST-OS ID (`0001.pdf`). IDs 950–1299 are in sub-folders and IDs below 1000 there have no leading zero (`950.pdf`) | Source PDFs. They match the 657 rows with "Downloaded? = x" in `data/raw/forrt_db_250627.csv` (100 %) |
| `NWO JUST-OS/BOT/vs_latest_bge-small-en-v1.5/` | Production index: 59,473 chunks, 384 dimensions, FAISS `IndexFlatL2` | Index 1 (copied to `data/processed/`) |
| `NWO JUST-OS/BOT/markdown/markdown/` | 546 Markdown files (`0001.md`), the PDFs after marker | Rebuild without marker. All 546 IDs have a PDF in `Content/` |
| `NWO JUST-OS/BOT/just-os_db_latest.csv` | 575 rows, 538 unique `doi_hash`, the metadata for the index | Metadata for `embed.py` (use it in place of the Google Drive URL) |
| `NWO JUST-OS/BOT/Questions.docx` | Preregistration questions with expected sources | Eval set (P13) |
| `NWO JUST-OS/BOT/Qualification open science.docx` | Questions with a label: "Is this open science? Should the bot answer?" | Classifier eval (gold labels) |
| `NWO JUST-OS/BOT/Possible conversations.docx` | Example multi-turn dialogue | Context-method eval (4.2) |
| `NWO JUST-OS/BOT/Feedback JUST-OS Bot.docx` | Bad answers from users | Regression questions for the eval |
| `NWO JUST-OS/BOT/Inclusion_Exclusion Articles.docx` | Rules: which sources go in | Coverage work (T4) |
| `NWO JUST-OS/BOT/questions_and_text.csv` | Same as `data/interim/questions_and_text.csv` | Eval seed (already in repo) |
| `FORRT Clusters pdfs/Cluster 1–11/` | 1,061 PDFs + 930 `.docx` (898 are a copy of a PDF with the same name). Name: `C01_SC01_<topic>_<author>_<year>.pdf` | **New** documents for the index (coverage). They are not in the production index |
| `FORRT Clusters pdfs/*.xlsx` | 2 working lists (121 + 45 references with DOI and file name), list of inaccessible sources per cluster | Metadata for the cluster PDFs |

**Ignore for the bot:** `AERN/`, `Application NWO/`, `Grants/`, `Logo_s and designs/`, `Meeting Agendas-Notes/`, `Memorandum of understanding (MOU)_/`, `merch FORRT booth/`, `Studentassistents/` (except `Evaluating JUST-OS/Brainstorm JUST-OS Testing _ Evaluation.docx`, ideas for the eval, and `FORRT Resource Lists/`, lists of new resources for coverage), `SURF/`, `Website/`, `Writing/`, `BOT/vs_*.zip` (old index versions), `BOT/Main articles/` (27 PDFs, same as `data/raw/main_articles`), `BOT/test.txt`.
**Can delete:** the two `.zip` files in `data/` (the Google Drive downloads of the same folders, about 3 GB).

**Cluster PDFs: not ready for the index.** The bot needs title, authors, year and link for each citation. The sheet column `PDF name` is empty. A match by first author + year finds only 352 of 963 files in sheet 2 and 204 in sheet 1. 98 file names have a different form (`_b` suffix, spaces). Thus, the next step is a metadata table for the cluster PDFs (working lists + sheet 2 + Crossref by DOI). This is a good hackathon task (track T4).

### 2.7 Two indexes (multilingual)
- Index 1: `data/processed/vs_latest_bge-small-en-v1.5` (production, English only).
- Index 2: `data/processed/vs_latest_bge-m3` (multilingual). `reembed.py` makes it from the **same chunks** as index 1. Thus, only the embedding model is different, and the eval comparison is fair.
- **Decided (28 Oct): index 2 (`bge-m3`) is the default** in `config/settings.py` and `config/settings.py.example`.
- To use index 1 (for example, to measure the production baseline), set these two lines in `.env` and restart:
  ```
  EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
  VECTOR_STORE=data/processed/vs_latest_bge-small-en-v1.5
  ```
  The two values must agree. Index 2 with the bge-small model (or the opposite) gives wrong results.
- **The team does not have index 2.** It is only on your disk (`data/processed/vs_latest_bge-m3`, 550 MB). Share it with the team before the hackathon (plan P11), or each person builds it with `reembed.py` (about 20 min on a GPU, many hours on a CPU).
- `bge-m3` is larger (568 M parameters, 1,024 dimensions). Each question takes more CPU time and the server needs about 2.5 GB more RAM.
- **Live test (28 Oct):** the bot uses index 2. The bot answers English and Dutch questions. "Hoe kan ik kwalitatief onderzoek preregistreren?" gives an answer in Dutch with the correct paper (Haven & Van Grootel, "Preregistering qualitative research"). With index 1, the same question gives one source about secondary data analysis, which is not correct.
- Times: first question after start 76 s (the server loads the model and index). Other questions 28–56 s (server time). This is more than the target (N1: p95 ≤ 15 s). A possible cause: `compose.yaml` sets `OMP_NUM_THREADS: 1`, so the re-ranker uses 1 CPU core. Measure each step before you change it.

### 2.8 Local run (28 October 2026)
The bot answers in Docker with OpenRouter (`meta-llama/llama-3.1-8b-instruct`), the production index and the local re-ranker.

| Test | Result |
|---|---|
| "What is preregistration and why is it important?" | Answer with citations and a source list. First request: 113 s (loads the index). |
| "What is the capital of France?" | Refusal, 5 s |

Problems that I repaired to make it run:
1. `bin/*`, `run`, `marker.sh` had Windows line ends (CRLF), so the Docker build failed. I changed them to LF and added `.gitattributes` (`bin/*`, `run`, `*.sh` stay LF on Windows).
2. `pyproject.cpu.toml` and `pyproject.gpu.toml` did not list `beautifulsoup4` and `python-dotenv`, so the server failed to start. I added them, and `openai` and `sentence-transformers` too (the code imports them directly).
3. The embedding and re-ranker models were lost each time Docker made the container again, and llama-index kept the embedding model in its own folder (`~/.cache/llama_index`). Thus, the first question downloaded the model (2.3 GB for bge-m3) and went past the Gunicorn time limit (120 s). Repair: `compose.yaml` now keeps the models in the volume `hf-cache`, and `LLAMA_INDEX_CACHE_DIR` points llama-index to the same folder. `Dockerfile` makes this folder for the `python` user. Do this one time on a new computer (download before the first question):
   ```
   docker compose exec web python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-base')"
   ```

Bugs that the live answer shows (from the plan, still open):
- **#1** The text cites "Kavanagh & Kapitány", but the linked source is a different paper.
- **#3** Year shows the form time stamp ("12/18/2023 17:12:02"), not the publication year.
- **#5** "Open Science Manual" is in the source list two times.
- **#14** `/up` gives 404, so the Docker health check fails.

---

## 3. Your action

### 3.1 OpenRouter key
1. Open `.env` (root of the repository).
2. Write the key after `OPENROUTER_API_KEY=`.
3. Set a credit limit for the key on openrouter.ai (for example 20 USD). Make a second key with a low limit for the hackathon team.

### 3.2 RUG key for OpenScholar (important)
- OpenScholar-8B is **not** on OpenRouter. I checked all 464 OpenRouter models on 28 October 2026. It is also not on Hugging Face Inference Providers (plan B3.2).
- Thus, the only API for OpenScholar is the **RUG LLM gateway** (`https://llm.hpc.rug.nl/`). You need the RUG key.
- Your `.env` has the placeholder `your_rug_llm_key`. Get the key and paste it in `.env` (plan P1).
- Without the key, you cannot run the OpenScholar baseline. Other models do not need it.
- Other option (cost): a dedicated GPU endpoint for the comparison runs only.

### 3.3 Vector index (solved)
- The production index was in `data/NWO JUST-OS/BOT/vs_latest_bge-small-en-v1.5` (26 August 2025). I copied it to `data/processed/vs_latest_bge-small-en-v1.5`. The default config uses this path.
- `data/processed/storage_m3` (old, 723 MB) uses a different storage format (`multi_embed_store.pkl`, not FAISS). The current code cannot load it. Do not use it.
- Use the steps below only for **new** documents (plan track T4).

**How to build an index from PDFs:**
| Step | Script | Input | Output |
|---|---|---|---|
| 1 | `bootstrap_local_database.py` | `data/raw/forrt_db_250627.csv` + PDFs in `data/pdfs/by-justos-id/NNNN.pdf` | Open-access PDFs copied to `data/pdfs/by-doi/<doi_hash>.pdf` + `data/processed/just-os_db.csv` |
| 2 | `marker.sh` | `data/pdfs/by-doi/` | Markdown in `data/processed/markdown/` (slow on CPU; a GPU is better) |
| 3 | `embed.py` | Markdown + metadata CSV | `data/processed/vs_latest_<embedding model>/` |

Limits of the current scripts:
- Step 1 does not download PDFs. It only checks open access and copies the files. It reads the June-2025 snapshot, not the live sheets. The live sheets have no "JUST-OS internal identifier" column.
- Step 3 reads the metadata from Google Drive (`URL_JUST_OS_DB`), not from the local CSV made by step 1.
- Steps 1 and 3 upload to Google Drive at the end. Without `credentials.json`, this upload fails after the files are written.
- Only open-access PDFs with a DOI go in (about 588 documents).

### 3.4 Decisions
1. **Decided (28 Oct):** Multilingual answers are in scope. They can come after the hackathon, but they will be done. (see 4.5)
2. **Proposed (28 Oct):** Memory over many chats uses an anonymous browser ID, with no login. Redis deletes the data 1 hour after the last message. (see 4.2)
3. **Decided (28 Oct):** Test Perplexity Sonar and `typesafe/jev-router` as **classifiers** (Open Science, FORRT or off-topic). Do not test them as answer models. (see 4.1)

---

## 4. Open tasks

### 4.1 Model comparison (OpenRouter)
Prices: USD per 1 million tokens, input / output, from the OpenRouter API on 28 October 2026. "Tools" = supports tool calls (our classify and rephrase steps use tool calls).

| Model (OpenRouter id) | In / Out | Tools | Reasoning | Open weights (self-host) | Notes |
|---|---|---|---|---|---|
| `openscholar` (RUG gateway) | free | yes (RUG) | no | yes | Baseline. RUG key needed |
| `meta-llama/llama-3.1-8b-instruct` | 0.02 / 0.04 | yes | no | yes | Default. Same base as OpenScholar |
| `qwen/qwen3-14b` | 0.12 / 0.24 | yes | yes | yes | |
| `qwen/qwen3.7-flash` | 0.03 / 0.13 | yes | yes | no | Cheap |
| `google/gemma-3-12b-it` | 0.05 / 0.15 | yes | no | yes | Cheap |
| `mistralai/mistral-small-3.2-24b-instruct` | 0.075 / 0.20 | yes | no | yes | |
| `openai/gpt-oss-20b` | 0.018 / 0.09 | yes | yes | yes | Cheapest reasoning model |
| `openai/gpt-6-luna` | 0.10 / 0.50 | yes | yes | no | "GPT-6 Luna" |
| `deepseek/deepseek-v4-flash` | 0.091 / 0.182 | yes | yes | (too large) | |
| `perplexity/sonar` | 1.00 / 1.00 | **no** | no | no | Searches the web itself. Answers are not only from our sources |
| `typesafe/jev-router` | variable | yes | yes | no | A router. The API shows no fixed price. Results may change between runs |

**Classifier comparison:** `GENERAL_MODEL` (classify and rephrase) is a separate setting from `CITATION_MODEL` (answer), so you can change the classifier by itself. Make a set of labelled queries (Open Science, FORRT lookup, off-topic and some non-English ones). Measure accuracy, time and cost for each classifier:
- Small LLMs: `openai/gpt-oss-20b`, `meta-llama/llama-3.1-8b-instruct`, `qwen/qwen3.7-flash`.
- `typesafe/jev-router`: the price is not fixed and the router can choose a different model on each call.
- `perplexity/sonar`: it does a web search on each call (0.005 USD for each request, which is 5 USD for each 1,000 questions). It has no tool calls, so it needs P6 first. It is a bad fit for a classifier that runs on each message.
- No LLM: use the bge embedding model, which is already loaded, and compare the query with example queries. This costs nothing and takes milliseconds. Use it as a baseline.

**Before the comparison:**
1. **P6 (MUST):** JSON fallback for classify and rephrase. Without it, a model with no tool support (Perplexity) refuses every question.
2. Reasoning models make more output tokens. Measure tokens and time per answer in the eval.
3. Run cost: 60 questions ≈ 0.4 M tokens. For each model above (not Perplexity) this is less than 0.10 USD.

### 4.2 Context (memory) methods
The current method: if a chat has history, one LLM call rewrites the new question as a full question ("rephrase"). Redis keeps the history for 1 hour.

Methods to compare with the eval:

| ID | Method | LLM calls saved | Notes |
|---|---|---|---|
| M0 | Rephrase (current) | 0 | Baseline |
| M1 | Full history in the answer prompt, no rephrase | 1 per turn | More input tokens |
| M2 | Short summary of the chat, updated each turn | 0 | Good for long chats |
| M3 | **Semantic answer cache:** embed the question (bge model is already loaded); if a past question is very similar, send the stored answer | All calls on a hit | Meets "use the cache, not the LLM". Needs a similarity limit and a cache-expiry time |
| M4 | Provider prompt caching (OpenRouter, some models) | 0 (lower cost only) | No code for the pipeline |

- **Memory over many chats (proposed design, no login):**
  1. The widget makes a random `client_id` (UUID) one time and keeps it in `localStorage` on forrt.org. Each request sends it as an optional field. Old clients send no `client_id` and continue to operate.
  2. Do not use a cookie. The widget is on forrt.org and the API is on just-os.org, so the cookie is third-party. Safari and Firefox block third-party cookies, and Chrome partitions them.
  3. Redis keeps `client:{client_id}` (short summaries of past chats) with a 1 h TTL. Each new message resets the TTL to 1 h. Thus, the memory stays while the user is active and Redis deletes it 1 h after the last message.
  4. Add a "Forget me" or "New chat" button that deletes the key.
  5. Data kept longer than 1 h is a privacy change. It needs a privacy notice and possibly consent. Ask FORRT before you increase the TTL.
- Known defect: the history stores the rephrased question, not the user's question.
- The eval needs multi-turn questions (follow-ups) to compare M0–M2.

### 4.3 Two modes: Open Science and FORRT lookup
- **Open Science (summary):** the current pipeline. Answer with citations from indexed documents.
- **FORRT lookup:** "Where is X on FORRT?", "How do I contribute to Y?". The answer is a link and a short description, not a summary.
- Proposal:
  1. Change classify to 3 classes: `open_science`, `forrt_lookup`, `off_topic`.
  2. For lookup, search the metadata of **all** sheet rows (title, abstract, clusters, URL). This includes the rows that are not in the index (videos, courses, web pages).
  3. Add forrt.org pages (contribute, clusters, projects) as a second lookup source. The source of these pages is not verified yet.
  4. Keep the `/chat` API the same (plan rule B6.5).
- Add lookup questions to the eval set.

### 4.4 Cheapest and reasoning models
- Cheapest (paid): `openai/gpt-oss-20b`, `meta-llama/llama-3.1-8b-instruct`, `qwen/qwen3.7-flash`, `google/gemma-3-12b-it`.
- Free: `google/gemma-4-26b-a4b-it:free`. Free models have low rate limits. Some free providers can log prompts. Do not use them in production.
- Reasoning: `openai/gpt-oss-20b`, `qwen/qwen3.7-flash`, `deepseek/deepseek-v4-flash`, `openai/gpt-6-luna`, `deepseek/deepseek-r1-0528` (0.50 / 2.15).
- Use the same eval set. Compare quality, time, tokens and cost.

### 4.5 Multilingual
Facts:
- 97 % of the sources are in English (sheet 1: 1,466 of 1,504 rows are "English" only).
- The embedding model `bge-small-en-v1.5` is **English only**. A question in Dutch or Spanish will find bad sources. This is the main problem, not the LLM.
- Qwen, Gemma, DeepSeek and GPT-6 Luna are multilingual. Llama 3.1 supports 8 languages. OpenScholar is trained for English.

Options:
1. Translate the question to English in the rephrase step (no new LLM call). Tell the model to answer in the user's language. Cheapest.
2. Change the embedding to `BAAI/bge-m3` (multilingual) and build the index again.

Add 5–10 non-English questions to the eval set. Then choose.
**Decision:** Multilingual is in scope (3.4). When you build the index again (3.3), also build a `bge-m3` index. Then you can compare both indexes and do not need to build again later.

### 4.6a Embedding model comparison (plan)
The embedding model changes text into vectors. It is used two times: to build the index (all chunks, one time) and for each question (at the server). The two must be the same model. Now: `BAAI/bge-small-en-v1.5` (setting `EMBEDDING_MODEL`).

All candidates use the same 59,473 chunks (`reembed.py`). Only the embedding model is different.

| # | Model | Size | Languages | Build | Notes |
|---|---|---|---|---|---|
| E1 | `BAAI/bge-small-en-v1.5` | 33 M | English | done (production) | Baseline. Cheapest |
| E2 | `intfloat/multilingual-e5-small` | 118 M | many | local GPU, minutes | Small and cheap multilingual model |
| E3 | `BAAI/bge-m3` | 568 M | many | local GPU, about 20 min (fp16) | Done (2.7) |
| E4 | `Qwen/Qwen3-Embedding-0.6B` | 596 M | many | local GPU | Strong new model, Apache-2.0 |
| E5 | `Qwen/Qwen3-Embedding-4B` | 4,022 M | many | **OpenRouter API** (`qwen/qwen3-embedding-4b`, 0.02 USD / M tokens, about 0.40 USD for the index) | The weights (8 GB in fp16) do not fit in the 8 GB laptop GPU. The web server has no GPU, so each question also uses the API |
| E6 | `qwen/qwen3-embedding-8b` (OpenRouter) | 7,567 M | many | OpenRouter API (0.01 USD / M tokens, about 0.20 USD) | Largest. API only |

Rules:
- Measure retrieval only (no LLM): hit@5, hit@20, MRR, time for each question. Use the questions from `questions_and_text.csv` (each question has the source text) and the same questions translated to Dutch, German and Spanish.
- Large models (E5, E6) on the API send each user question to the provider. Record this for the privacy notice.
- Do not use `jinaai/jina-embeddings-v3` (non-commercial licence) or `google/embeddinggemma-300m` (gated, Gemma terms) unless you accept the licence.

### 4.6b Embedding comparison: results (28 October 2026)
Tools: `eval/make_retrieval_set.py` (makes the question set), `eval/compare_embeddings.py` (scores the models). Results: `eval/results/embeddings_261028.csv`.

**Question set** (`eval/retrieval_questions.jsonl`, 474 items): 24 questions from `questions_and_text.csv` (only 8 documents matched the current index) + 150 synthetic questions (one for each of 150 random documents, written by `google/gemma-3-27b-it` from one chunk) + 300 translations (100 each in Dutch, German and Spanish).
**Measure:** the document that answers the question is in the first k documents (hit@k), and the mean reciprocal rank (MRR@20). Only retrieval: no re-ranker and no LLM.

| Model | hit@5 all | hit@5 en | hit@5 nl | hit@5 de | hit@5 es | MRR@20 all | Time per question | Index build |
|---|---|---|---|---|---|---|---|---|
| E1 `bge-small-en-v1.5` (now) | 0.27 | 0.46 | 0.16 | 0.11 | 0.19 | 0.21 | 41 ms (CPU) | done |
| E2 `multilingual-e5-small` | 0.33 | 0.45 | 0.29 | 0.20 | 0.30 | 0.24 | 32 ms (CPU) | 5 min (GPU) |
| **E3 `bge-m3`** | **0.50** | 0.51 | **0.51** | **0.50** | **0.49** | 0.40 | 268 ms (CPU) | 20 min (GPU) |
| E4 `Qwen3-Embedding-0.6B` | 0.35 | 0.46 | 0.28 | 0.28 | 0.32 | 0.26 | 3,319 ms (CPU) | 35 min (GPU) |
| E5 `qwen3-embedding-4b` (API) | 0.48 | 0.54 | 0.45 | 0.42 | 0.48 | 0.36 | 577 ms (API) | 6 min, 0.38 USD |
| E6 `qwen3-embedding-8b` (API) | **0.53** | **0.58** | 0.50 | 0.50 | 0.48 | **0.43** | 780 ms (API) | 18 min, 0.21 USD |

**Results:**
1. The current model (E1) is bad for questions that are not in English: hit@5 is 0.11–0.19, against 0.46 in English. This confirms 4.5.
2. **E3 `bge-m3` is the best choice now.** It is almost equal to the best model (E6). Its score is the same in all four languages. It is free, runs on the server CPU (268 ms for each question) and sends no question to a provider.
3. E6 is a little better in English, but the difference with E3 is in the range of chance for this set size (about ±0.07). E6 needs the API for each question, is slower, and sends each user question to a provider.
4. E4 is lower than expected for its size and is very slow on the CPU. The configuration can be wrong (pooling or prompt). Do not use it until somebody checks it.
5. The absolute scores are low because many documents are about the same subjects (for example, many on preregistration). Use the numbers to compare models, not as the final quality.

**Limits:** Synthetic questions come from one chunk, and some are vague (for example, from a reference list). The translations are from an LLM. The set has 474 questions; repeat with the hackathon eval set (P13).

**Decision:** E3 `bge-m3` is now the default (see 2.7). Then test the full pipeline (re-ranker + LLM) with E1 and E3. Note: `bge-reranker-base` is also English-focused; test `BAAI/bge-reranker-v2-m3` (multilingual) at the same time.

### 4.6 Other plan tasks (Phase 1, B7)
| ID | Task | Status |
|---|---|---|
| P1 | Get index, RUG key, team size, budget | YOU |
| P2 | OpenRouter key + credit limit (was HF) | YOU (key ready, paste it) |
| P3 | Run the stack locally | DONE (see 2.8) |
| P4 | 10 baseline Q&As, reproduce bugs | OPEN |
| P5 | Provider config | DONE |
| P6 | JSON fallback for classify/rephrase | OPEN (MUST before Perplexity) |
| P7 | Local re-ranker + fallback | DONE |
| P8 | Test scaffold, `ruff`/`pytest` dev deps, `uv.lock` | OPEN (first test exists) |
| P9 | Citation mapping fix (#1) | OPEN |
| P10 | Error is not a refusal (#6), `/up` route (#14) | OPEN |
| P11 | Index download script | OPEN (index is on your disk; the team needs a download link) |
| P12 | Write bugs #3, #4, #5, #10 as hackathon issues | OPEN |
| P13–P17 | Eval set, `eval/run.py`, baselines, model list, compare table | OPEN (model list in 4.1) |
| P18 | Setup simplification | PARTLY DONE (`COMPOSE_FILE` already in your `.env`) |
| P19–P22 | `HACKATHON.md`, issues, dry run, team key | OPEN |

---

## 5. Risks found
1. `config/gunicorn.py` imports `distutils` (bug #16). In the current image the server starts, but this can stop when a dependency changes. Fix it in Phase 3.
2. Free and router models (`:free`, `jev-router`) can change. Do not use them as the production model.
3. Perplexity uses web search. Its citations are not from FORRT sources. Its score is not a fair comparison.
