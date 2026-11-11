# Evaluation

How we measure the bot, the results so far, and what each number means.
Rule: a change to prompts, models, retrieval or chunking needs an eval table before and after (see [hackathon.md](hackathon.md)).

## 1. Tools

| Tool | Command | Output |
|---|---|---|
| Full pipeline eval | `docker compose exec -e OMP_NUM_THREADS=8 web python eval/run.py --model <id> [--general-model <id>] [--limit 5]` | `eval/results/run_<YYMMDD-HHMM>_<model>.csv` |
| Table of runs | `docker compose exec web python eval/compare.py [csv ...]` | Markdown table (with "Judge support" once judged) |
| LLM judge (#8) | `docker compose exec web python eval/judge.py eval/results/run_X.csv [--model ...]` | adds `judge_support` (0-1) to the run CSV; needs runs made after 10 Nov (they save the passages) |
| Classifier comparison (#9) | `docker compose exec web python eval/classify.py --models a,b [--intent]` | Markdown table: accuracy, false refusals, false answers, errors, time, cost |
| Retrieval question set | `python eval/make_retrieval_set.py` | `eval/retrieval_questions.jsonl` |
| Embedding comparison | `python eval/compare_embeddings.py [E2 E4 ...]` (GPU or API) | `eval/results/embeddings_<YYMMDD>.csv` |
| Re-ranker comparison | `python eval/compare_rerankers.py` (quality, GPU); `python eval/compare_rerankers.py --device cpu --threads 6 --limit 20` (time on CPU) | `eval/results/rerankers_<YYMMDD>_<device>.csv`; prints paired differences and a gate check |
| Coverage audit | `python eval/coverage.py` | `eval/results/coverage_<YYMMDD>.{csv,md,svg}` (see [data.md](data.md) 4) |
| Arena (human ratings) | http://localhost:8000/arena with `ARENA_ENABLED=true`: pick models, rate each answer 1-5 on correct / references / clarity | `/arena/leaderboard`, `/arena/ratings` |

Question sets:
- `eval/questions.jsonl`: 44 questions for the full pipeline (24 should answer, 17 should refuse, 3 not English; 5 with `expected_dois`).
- `eval/retrieval_questions.jsonl`: 474 questions for retrieval only (24 from `data/interim/questions_and_text.csv`, 150 synthetic, 300 translations to nl/de/es).

## 2. What the numbers mean

### Embedding comparison (`eval/compare_embeddings.py`)

This test checks **only the search step**: no re-ranker and no LLM. Each question has one "right" document (the document the question was written from). The script embeds the question, finds the 20 nearest chunks, turns the chunks into a ranked list of documents, and looks for the right document.

| Column | Meaning | Good value |
|---|---|---|
| **ID (E1–E6)** | Short name of the candidate model | — |
| **Model** | Embedding model (Hugging Face id or OpenRouter id) | — |
| **Format** | How the chunk vectors are stored. **FAISS index**: a complete llama-index folder (`data/processed/vs_latest_<model>/`) that the app can load (`VECTOR_STORE`). **`.npy`**: only a matrix of chunk vectors in `data/processed/emb_cache/`, made for this comparison; the app cannot use it until `scripts/reembed.py` builds a full index | — |
| **Dims** (`dim`) | Length of one vector. More dimensions can hold more meaning, but need more RAM and disk (59,473 chunks × dims × 2–4 bytes) and a slower search | Smaller is cheaper |
| **n** | Number of questions in the score | — |
| **lang** | Question language: `all`, `en`, `nl`, `de`, `es` | — |
| **hit@1 / hit@5 / hit@20** | Share of questions where the right document is in the first 1 / 5 / 20 documents. hit@5 = 0.50 means half the questions find their document in the top 5. The bot re-ranks the top 20 and gives the best 7 to the LLM, so **hit@20 is the upper limit** for the re-ranker, and **hit@5** is close to what the LLM sees | Higher |
| **MRR@20** (`mrr@20`) | Mean reciprocal rank: for each question 1/rank of the right document (rank 1 → 1.0, rank 2 → 0.5, rank 4 → 0.25, not in the top 20 → 0), then the mean. One number for "how high is the right document" | Higher |
| **Time per query** (`ms_per_query`) | Time to embed one question, in milliseconds. Local models: on the CPU of the laptop. API models (E5, E6): includes the network round trip. The vector search itself takes a few ms for all models | Lower; the server adds this to every answer |
| **Index build** | Time (and cost for API models) to embed all 59,473 chunks one time | Lower |

Why the scores look low: many documents are on the same subject (for example, many papers on preregistration), so a "wrong" document can still answer the question. Use the numbers to **compare** models, not as absolute quality. With 474 questions the uncertainty is about ±0.05 (±0.07 per language).

### Full pipeline eval (`eval/run.py`, `eval/compare.py`)

| Column | Meaning |
|---|---|
| **outcome** | `answered`, `refused` (classifier said "not open science", or no sources), `error` (API failure) |
| **expect** | Gold label in `questions.jsonl`: `answer` or `refuse` |
| **Correct** | Share of questions where the outcome matches `expect` |
| **Answered / Refused** | Counts against the gold label (22/27 = 22 of the 27 "answer" questions got an answer) |
| **hit@7** | For questions with `expected_dois`: one of them is in the 7 sources that the LLM saw |
| **Citations valid** | Share of answers where every `[n]` in the text points to a source in the list |
| **Mean s / p95 s** | Mean and 95th-percentile answer time in seconds (target p95 ≤ 15 s) |
| **USD / 1k q** | OpenRouter cost for 1,000 questions (from the token counts) |

## 3. Results

### 3.1 Embedding models (28 October 2026, `eval/results/embeddings_261028.csv`)

All models embed the **same 59,473 chunks** from 513 documents (see [data.md](data.md)), so only the model is different.

| ID | Model | Format | Dims | hit@5 all | hit@5 en | hit@5 nl | hit@5 de | hit@5 es | hit@20 | MRR@20 | Time per query | Index build |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | `BAAI/bge-small-en-v1.5` (old production) | FAISS index | 384 | 0.27 | 0.46 | 0.16 | 0.11 | 0.19 | 0.42 | 0.21 | 41 ms (CPU) | done |
| E2 | `intfloat/multilingual-e5-small` | `.npy` | 384 | 0.33 | 0.45 | 0.29 | 0.20 | 0.30 | 0.53 | 0.24 | 32 ms (CPU) | 5 min (GPU) |
| **E3** | **`BAAI/bge-m3` (default now)** | **FAISS index** | 1024 | **0.50** | 0.51 | **0.51** | **0.50** | **0.49** | 0.70 | 0.40 | 268 ms (CPU) | 20 min (GPU) |
| E4 | `Qwen/Qwen3-Embedding-0.6B` | `.npy` | 1024 | 0.35 | 0.46 | 0.28 | 0.28 | 0.32 | 0.58 | 0.26 | 3,319 ms (CPU) | 35 min (GPU) |
| E5 | `qwen/qwen3-embedding-4b` (API) | `.npy` | 2560 | 0.48 | 0.54 | 0.45 | 0.42 | 0.48 | 0.68 | 0.36 | 577 ms (API) | 6 min, 0.38 USD |
| E6 | `qwen/qwen3-embedding-8b` (API) | `.npy` | 4096 | **0.53** | **0.58** | 0.50 | 0.50 | 0.48 | 0.71 | **0.43** | 780 ms (API) | 18 min, 0.21 USD |

Findings:
1. E1 is bad for questions that are not in English (hit@5 0.11–0.19 against 0.46 in English).
2. **E3 `bge-m3` is the default** (decided 28 Oct). It is almost equal to E6, has the same score in all four languages, is free, runs on the server CPU and sends no question to a provider.
3. E6 is a little better in English, but the difference is inside the uncertainty. It needs the API for each question and sends each user question to a provider.
4. E4 is low for its size and very slow on CPU; the configuration (pooling or prompt) can be wrong.
5. Next: test the multilingual re-ranker `BAAI/bge-reranker-v2-m3`; `bge-reranker-base` is English-focused.

Limits: synthetic questions come from one chunk and some are vague; the translations are from an LLM.

### 3.2 Answer models (5 November 2026, 44 questions, index bge-m3, classifier Llama 3.1 8B)

| Answer model | Correct | Answered | Refused | Errors | hit@7 | Citations valid | Mean s | p95 s | USD / 1k q |
|---|---|---|---|---|---|---|---|---|---|
| `meta-llama/llama-3.1-8b-instruct` | 0.86 | 22/27 | 16/17 | 0 | 0.29 | 0.95 | 30.4 | 78.0 | 0.15 |
| `openai/gpt-oss-20b` | 0.86 | 22/27 | 16/17 | 0 | 0.29 | 1.00 | 15.9 | 32.6 | 0.14 |

Files: `eval/results/run_261105-*.csv`. Findings:
1. The English re-ranker blocks non-English questions (de, es got "no sources": scores under `MIN_RELEVANCE`).
2. Two English questions also got "no sources" for the same reason.
3. hit@7 uses only 7 questions with expected DOIs; the eval set must grow (issue E1).
4. gpt-oss-20b is 2× faster at the same cost. Text quality is not measured yet (issue E2, LLM judge).

Speed (5 Nov, warm server): classify 0.4 s, retrieval + re-rank 31 s (re-ranker 21 s for 20 chunks on 1 CPU thread), answer 15 s.

### 3.3 Answer model candidates (OpenRouter prices 28 Oct 2026, USD per 1 M tokens in / out)

| Model | In / Out | Tools | Reasoning | Open weights | Notes |
|---|---|---|---|---|---|
| `openscholar-8b` (self-hosted, `OPENSCHOLAR_BASE_URL`) | own server | — | no | yes | Baseline. Fine-tuned Llama 3.1 8B |
| `meta-llama/llama-3.1-8b-instruct` | 0.02 / 0.04 | yes | no | yes | Default; same base as OpenScholar |
| `openai/gpt-oss-20b` | 0.018 / 0.09 | yes | yes | yes | Cheapest reasoning model |
| `qwen/qwen3-14b` | 0.12 / 0.24 | yes | yes | yes | |
| `qwen/qwen3.7-flash` | 0.03 / 0.13 | yes | yes | no | Cheap |
| `google/gemma-3-12b-it` | 0.05 / 0.15 | yes | no | yes | Cheap |
| `mistralai/mistral-small-3.2-24b-instruct` | 0.075 / 0.20 | yes | no | yes | |
| `openai/gpt-6-luna` | 0.10 / 0.50 | yes | yes | no | |
| `deepseek/deepseek-v4-flash` | 0.091 / 0.182 | yes | yes | too large | |
| `perplexity/sonar` | 1.00 / 1.00 | no | no | no | Searches the web itself: not a fair comparison |

Free (`:free`) and router models can change or log prompts: do not use them in production.

### 3.4 Re-ranking and the "no sources" gate (11 November 2026, `eval/compare_rerankers.py`)

Retrieval only, on the 474 questions of `eval/retrieval_questions.jsonl` and the bge-m3 index. Every arm starts from the FAISS top 20. hit@7: a chunk of the question's document is among the first 7 chunks, what the answer model sees (chunk positions, so not comparable with the document-level hit@5 of 3.1). Gate: chunks with a re-ranker score ≤ `MIN_RELEVANCE` (0.1) are dropped, and none left means "no sources". Time: CPU of the laptop, 6 threads (`RERANK_THREADS`), 20 questions, query embedding included.

| Arm | hit@7 all | en | nl | de | es | No sources | hit@7 vs vector [95% CI] | CPU ms mean / p95 |
|---|---|---|---|---|---|---|---|---|
| Vector order | 0.49 | 0.51 | 0.48 | 0.48 | 0.49 | 0 | — | 93 / 124 |
| Hybrid (BM25 + RRF) | 0.46 | 0.52 | 0.43 | 0.43 | 0.43 | 0 | −0.027 [−0.051, −0.006] | 96 / 125 |
| Vector + `bge-reranker-base` | 0.52 | 0.53 | 0.54 | 0.47 | 0.52 | 0 | +0.023 [−0.002, +0.049] | 4,391 / 5,093 |
| Vector + `bge-reranker-v2-m3` | 0.54 | 0.54 | 0.57 | 0.53 | 0.50 | 0 | +0.044 [+0.017, +0.072] | 14,576 / 18,126 |
| **Vector + base + gate (production)** | **0.25** | 0.44 | 0.19 | 0.11 | 0.12 | **226** | −0.241 [−0.283, −0.198] | 4,391 / 5,093 |
| Vector + v2-m3 + gate | 0.50 | 0.52 | 0.52 | 0.48 | 0.46 | 41 | +0.008 [−0.023, +0.040] | 14,576 / 18,126 |

Files: `eval/results/rerankers_261111_cuda.csv` (quality, all arms including hybrid + re-ranker), `eval/results/rerankers_261111_cpu.csv` (times; its hit numbers come from 20 questions only). Findings:
1. The gate, not the order, causes most misses: production answers "no sources" for 226 of 474 questions, most of them not English. Without the gate the same re-ranker reaches 0.52.
2. Re-ranking adds little over vector order: +0.044 for v2-m3, +0.023 (inside the noise) for base, at 4–15 s per question on CPU.
3. Hybrid search is a little worse than vector order, worse in nl/de/es (BM25 over English text gets nothing from those questions) and equal in English. This set has no exact-term questions (acronyms, names), the case hybrid is for.
4. A cosine gate on the best vector match separates on-topic from general-knowledge questions: at 0.55 it keeps all 474 retrieval questions (lowest 0.561) and all 27 "answer" questions of `eval/questions.jsonl` (lowest 0.598), and drops 10 of 11 general-knowledge off-topic questions. Off-topic questions close to academia (grants, careers) score 0.57–0.72, so refusing them stays with the classifier.
5. v2-m3 lets ml02 (de) and ml03 (es) pass the gate (best scores 0.95 and 0.83, base 0.07); whether they then cite the expected papers needs `eval/run.py`.

Limits: the questions were written by an LLM from one chunk each and the translations are an LLM's; no question here needs an exact term. Not yet measured: the full pipeline (`eval/run.py`) with the re-ranker off and a cosine gate, which needs a code change.
