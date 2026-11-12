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
| Coverage audit | `python eval/coverage.py` | `eval/results/coverage_<YYMMDD>.{csv,md,svg}` (see [data.md](data.md) 4) |
| Arena (human ratings) | http://localhost:8000/arena with `ARENA_ENABLED=true`: pick models, rate each answer 1-5 on correct / references / clarity | `/arena/leaderboard`, `/arena/ratings` |

Question sets:
- `eval/questions.jsonl`: 54 questions for the full pipeline (32 should answer, 22 should refuse, 13 not English: translations of pr03 (nl), pr01 (de) and pr05 (es), and in tr, it, hi, mr and kn of pr01 and off01, checked by native speakers; 12 with `expected_dois`).
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

All models embed the **same 59,473 chunks** from 513 documents (see [data.md](data.md)), so only the model is different. Since the cluster papers were added (11 Nov 2026), `compare_embeddings.py` reads the frozen copies `vs_261111_*_before_clusters/`, so these results stay reproducible.

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
5. The multilingual re-ranker `BAAI/bge-reranker-v2-m3` is the default since 12 Nov (section 3.5, #21).

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

### 3.4 Index with all cluster papers (12 November 2026, 54 questions, `meta-llama/llama-3.1-8b-instruct`)

| Index (bge-m3, `HYBRID_SEARCH=true`) | Correct | Answered | Refused | Errors | hit@7 | Citations valid | Completion tokens / q |
|---|---|---|---|---|---|---|---|
| 646 documents (11 Nov, `run_261111-1520`) | 0.87 | 26/32 | 21/22 | 0 | 0.17 | 0.90 | 4,373 |
| 1,354 documents (12 Nov, `run_261112-0302`) | 0.91 | 28/32 | 21/22 | 0 | 0.17 | 0.96 | 379 |

Findings:
1. Doubling the index did not lower any score: two more questions are answered, refusals are the same.
2. hit@7 is unchanged, but it still uses only the few questions with expected DOIs (issue E1).
3. The difference is 2 of 54 questions and the answer model is not deterministic, so "not worse" is the safe reading, not "better".
4. **The times of the 12 Nov run cannot be compared** (mean 146 s against 22.5 s). Every question took about 140 s more, also refused ones that never search (0.2 s on 11 Nov). The run was started with `docker run` without the Redis container and logged "Error -2 connecting to redis:6379", so the likely cause is the wait for Redis, not the index. Without that constant an answered question took about 12 s. Run the eval with `docker compose run` to get real times for the larger index.

### 3.5 Multilingual changes (12 November 2026, 54 questions, `meta-llama/llama-3.1-8b-instruct`)

Same index (1,354 documents, bge-m3, `HYBRID_SEARCH=true`). Each row adds changes to the one above. Runs 0734–1034 ran outside Docker on the same laptop CPU, so their times compare with each other but not with 0302.

| Run | Change | Correct | Answered | Refused | Citations valid | Answers without `[n]` | Mean s | p95 s | Longest s | Completion tokens / q |
|---|---|---|---|---|---|---|---|---|---|---|
| `run_261112-0302` | baseline (`bge-reranker-base`) | 0.91 | 28/32 | 21/22 | 0.96 | 5 | (146) | (171) | (262) | 379 |
| `run_261112-0734` | multilingual re-ranker `bge-reranker-v2-m3` + language/glossary rule in the answer prompt | 0.93 | 29/32 | 21/22 | 0.93 | 3 | 12.9 | 37.5 | 346 | 420 |
| `run_261112-0939` | + topic check with `OPEN_SCIENCE_SCOPE`, retry of answers without `[n]` | 0.93 | 30/32 | 20/22 | 0.90 | 2 | 57.6 | 114.0 | 748 | 1,137 |
| **`run_261112-1034`** | **+ `MAX_ANSWER_TOKENS=2000`, retry only after a quick first answer** | **0.93** | **30/32** | 20/22 | **0.96** | 5 | 22.3 | 79.7 | 135 | 457 |

Findings:
1. **The multilingual re-ranker fixes German and Spanish** (#21): ml02 (de) and ml03 (es) were "no sources" with `bge-reranker-base`; now both are answered with 9 and 8 citations. Re-rank of 20 chunks on the server CPU: 14–17 s (`Timing:` log), about the same as before.
2. **The topic check refused short non-English term questions** ("Was ist Replikation?", "Was ist HARKing?", Turkish "Ön kayıt nedir…"): 9 of 45 decisions wrong in a 15-question check (3 tries each), 0 with `OPEN_SCIENCE_SCOPE`. Side effect: the Marathi and Kannada translations of the off-topic question off01 (ml11, ml13) are now answered; the English off01 is still refused. Mixed questions ("Was ist DNA Replikation und HARKing") are still refused; a prompt line for them changed nothing.
3. **Answer length had no cap.** In 0939 Llama 3.1 8B looped in Kannada and Marathi up to 16,384 tokens (ml12, ml13: 9–12 min per question; this also stalled two runs). `MAX_ANSWER_TOKENS=2000` brings the longest question to 135 s and the mean tokens back to 457.
4. **Answers without `[n]`:** in German, 3 of 7 test answers had no citation, so the source list showed every retrieved paper. The prompt now asks for `[n]` in every language and an uncited answer is asked once more, but only if the first came back within `LLM_TIMEOUT`; the 5 uncited answers left in 1034 are slow non-English ones (nl, hi, mr, kn). Since #42 they show no sources instead of all.
5. ml04 (Turkish) now passes the topic check but no chunk reaches `MIN_RELEVANCE` ("no sources").
6. Correct moves within 2 of 54 questions and the model is not deterministic: read 0.91 → 0.93 as "not worse, multilingual better", not as a measured gain.

### 3.6 FORRT page router and decision models (12 November 2026, prototype, `meta-llama/llama-3.1-8b-instruct`)

Measured in a stand-alone prototype of `just_os/forrt_pages.py` (same steps; page vectors from bge-m3 via OpenRouter). **Question set:** 226 simulated visitor questions written by `google/gemma-4-31b-it` from the text of real forrt.org pages: one per menu / project / tool page, news posts and newsletters, 20 open-science questions from glossary and curated-resource pages, 12 off-topic questions and 32 hand-written ones. Styles: natural question, 2–5 word search query, vague "my situation" question, other languages (de, es, nl, pt, zh). **Judge:** `google/gemma-4-31b-it` (not one of the answer models) with the source page and the pages the bot read: correct / complete / helpful 1–5, invented facts, date error, language, pass. Calibrated by hand on 8 answers only: treat differences of a few points as noise.

**Router** (`just_os/decisions.py`, 226 questions). Labels come from each question's source page (off-topic → neither; page in the FORRT scope → forrt; glossary, curated resources, clusters → open_science), so they are noisy: many "misroutes" are right on reading (*"Why is it a problem if studies only use one group of people?"*, written from an Educators' Corner page, is an open-science question). Read the numbers as a comparison between classifiers, not as accuracy.

| Classifier | Exact | FORRT questions sent to "neither" | Mean / p95 s | USD / 1,000 q |
|---|---|---|---|---|
| Llama 3.1 8B with `classify_intent` (current) | 0.51 | 25 / 159 | 1.1 / 2.2 | 0.006 |
| `typesafe/jev-1.14` | 0.59 | 16 | 1.1 / 3.1 | 0.020 |
| `cloudflare/clef` | 0.58 (0.73 counting `both` as right) | 2 | 1.3 / 3.0 | 0.064 |
| `cloudflare/clef-flash` | 0.62 | 2 | 1.3 / 2.6 | 0.007 |
| **`cloudflare/clef-flash`, Llama below p 0.5** (the defaults) | **0.65** | – | – | – |

A hand-labelled question set is needed for real accuracy; real errors seen include *"When is the OSF conference early-bird deadline?"* → forrt (p 0.91).

**Page selector** (32 hand-written questions, the same 12 candidates for each): decision models pick as well as an LLM, 5–15× faster.

| Selector | Right page picked | Top pick right | Mean / p95 s | USD / 1,000 q |
|---|---|---|---|---|
| top search result only | 25/32 | 25/32 | 0 | 0 |
| `cloudflare/clef` | **30/32** | 28/32 | 2.8 / 7.9 | 0.60 |
| `cloudflare/clef-flash` | 29/32 | **29/32** | 0.9 / 1.7 | 0.07 |
| `typesafe/jev-1.14` | 29/32 | 28/32 | 0.7 / 1.9 | 0.09 |
| `openai/gpt-oss-20b` (LLM) | 28/30 | 25/30 | 2.1 / 5.3 | – |
| `meta-llama/llama-3.1-8b-instruct` (LLM) | 27/30 | 25/30 | 8.6 / 15.1 | – |

**End to end, Clef + Llama 3.1 8B**, 171 questions in the new scope (menu pages, announcements, newsletters, project sites):

| | Before: all 1,929 pages, no checks | After: 163 pages + checks in code (`forrt_checks.py`) |
|---|---|---|
| **Answers judged acceptable** | 0.75 | **0.77** |
| Other languages (21 questions) | 0.50 | **0.76** |
| News and events (22) | 0.52 | **0.65** |
| Hand-written (28) | 0.73 | **0.85** |
| Natural questions (59) | **0.89** | 0.79 |
| Answers with `[n]` citations | 0.36 | **1.00** |
| Answers with a link not in the pages read | 0.035 | **0.006** |
| Answers with a broken link (`osf.io/af4nk\_v2` escapes) | 0.135 | **0.006** |
| Past events called upcoming (time questions) | 0.17 | 0.14 |
| Right page among 12 candidates / picked / top pick | 0.87 / 0.85 / 0.58 | **0.94 / 0.90 / 0.69** |
| Off-topic refused | **12/12** | 11/12 |
| Mean / p95 seconds | **10.1 / 20.9** | 12.9 / 23.7 |

Findings:
1. **Narrowing the scope helps search**: with the 1,474 curated-resource pages gone, the right page is a candidate for 94 % of questions (87 %) and the top pick for 69 % (58 %).
2. **The checks in code fix what the prompt alone did not**: every answer cites its pages, invented and broken links are gone, and non-English questions are answered in their language (the one rewrite adds ~3 s on average).
3. **Llama 3.1 8B is now the weak step**: of the remaining failures most are answer-model errors (invented references, "not found" although the page has the answer, irrelevant newsletter items, past events still called upcoming in 14 % of time questions). The drop for natural questions is part judge noise and part these errors. A stronger answer model (`FORRT_ANSWER_MODEL`; deepseek-v4-flash and qwen3.6-27b handled dates correctly in spot checks) is the next test.
4. Of the 55 questions now out of scope (glossary, curated resources, clusters), the FORRT route still answered 48 from FORRT pages; with `DECISION_ROUTER` they go to the papers path instead.
5. Questions and judge come from one model family and the judge was checked on 8 answers: re-run with a reviewed question set before relying on differences under ~5 points.
