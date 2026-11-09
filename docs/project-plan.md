# JUST-OS — Project plan

**Updated:** 9 November 2026. **Repo:** [forrtproject/just-os-chatbot](https://github.com/forrtproject/just-os-chatbot).
This file keeps the purpose, decisions, requirements, bug status, designs and roadmap. The day-by-day preparation plan (23 Oct – 10 Nov) is done and is in the Git history (`Project Plan/JUST-OS_Project_Plan.md`, `Project Plan/PRE_HACKATHON_STATUS.md`).

## 1. Purpose

JUST-OS answers open-science questions with citations to the FORRT resource library and runs as the chat widget on forrt.org. The goal: accurate, well-sourced answers and a bot that can be hosted sustainably.

## 2. Current state (November 2026)

- Flask + Gunicorn + Redis in Docker; LlamaIndex + FAISS; index of 513 open-access documents (59,473 chunks), embedding `BAAI/bge-m3`; local re-ranker `BAAI/bge-reranker-base` with fallback to vector order.
- LLM: any OpenAI-compatible API. Default OpenRouter (`meta-llama/llama-3.1-8b-instruct`). OpenScholar-8B is self-hosted (`OPENSCHOLAR_BASE_URL`); the old RUG gateway still works with the four `.env` lines.
- Tools: eval (`eval/run.py`, `eval/compare.py`), embedding comparison, arena (`/arena`), unit tests in `test/`.
- See [architecture.md](architecture.md), [data.md](data.md), [evaluation.md](evaluation.md).

## 3. Decisions

| Date | Decision |
|---|---|
| 23 Oct | Do not train a new model. Run the re-ranker on the server CPU. Keep the `/chat` API fields. Measure each change with the eval set |
| 28 Oct | LLM provider is **OpenRouter**, not Hugging Face (the old plan said HF) |
| 28 Oct | **`bge-m3` is the default embedding** (multilingual; see evaluation 3.1) |
| 28 Oct | Multilingual answers are in scope (may come after the hackathon) |
| 28 Oct | Test Perplexity Sonar and `typesafe/jev-router` only as **classifiers**, not as answer models |
| 9 Nov | OpenScholar-8B is self-hosted on an OpenAI-compatible server with a Bearer key; only `CITATION_MODEL` goes there, classify/rephrase stay on OpenRouter |
| Proposed | Memory over many chats with an anonymous browser ID, no login, 1 h TTL (see 7.1) |

## 4. Goals and success measures

| Goal | Measure |
|---|---|
| Accurate, well-sourced answers | Retrieval hit@5 ≥ 0.85; citation support ≥ 0.90 (LLM judge) |
| Correct references | Citation number → correct document 100 %; DOIs resolve 100 %; 0 duplicate papers; year = publication year |
| Correct refusals | ≥ 0.95 refusal off-topic; ≤ 0.05 false refusal in scope; API errors shown as errors |
| Sustainable hosting | Model served by ≥ 2 API providers **and** self-hostable on 1 GPU; monthly cost under a cap |
| Coverage | Reason for every non-indexed FORRT row; one new ingestion route for the largest group |
| Easy contribution | Fresh clone → running bot in ≤ 30 min; `pytest` runs without the index |

## 5. Requirements

| ID | Requirement |
|---|---|
| F1 | `/chat` keeps the current request/response contract |
| F2 | Each citation number maps to the passage the model saw |
| F3 | Each answer lists each document one time, with authors, publication year, title and a working link |
| F4 | A source passage shows only when the licence allows (CC BY, CC0, public domain) |
| F5 | Off-topic questions get a refusal; API failures get an error message |
| F6 | Provider and models are set by env vars; no code change to switch |
| F7 | The eval CLI runs any model on the question set and writes a CSV |
| F8 | Ingestion writes a coverage report with a reason for each skipped row |
| F9 | `/up` returns 200 when the app is healthy |
| N1 | p95 answer time ≤ 15 s (now 33–78 s) |
| N2 | Web server runs on CPU only |
| N3 | Fresh-clone setup ≤ 30 min on Windows (WSL2), macOS, Linux |
| N4 | `pytest` runs in ≤ 2 min without network or the big index |
| N5 | No secrets in Git; no chat content kept longer than 1 h |
| N6 | Server in the EU (GDPR) |

## 6. Bug and finding status (audit of 23 Oct, commit `20bb9e0`)

| # | Finding | Status |
|---|---|---|
| 1 | Citation numbers used the pre-rerank node list | **Fixed** (test `test_citations_use_ranked_nodes`) |
| 2 | Re-rank failure → empty answer | **Fixed**: falls back to vector order |
| 3 | Year is the form time stamp | Open → issue R1 |
| 4 | Raw links; DOI regex cuts or keeps bad characters | Open → R2 |
| 5 | One reference per chunk (duplicates) | Open → R3 |
| 6 | Classify API error shown as a refusal | **Fixed** (`CLASSIFY_ERROR_RESPONSE`) |
| 7 | Forced tool calls fail on some models | **Fixed**: JSON fallback |
| 8 | Remote `/rerank` endpoint | **Fixed**: local CrossEncoder |
| 9 | Index not available to contributors | **Partly**: `scripts/get_index.py` + zip ready; upload link missing |
| 10 | Tooltip `innerHTML` → stored XSS | Open → R4 |
| 11 | Model names fixed to RUG names | **Fixed** (`BASE_URL`, `LLM_API_KEY`, `CITATION_MODEL`, `GENERAL_MODEL`, `OPENSCHOLAR_*`) |
| 12 | OpenScholar prompt used for every model | Open → M2 |
| 13 | Rate limit key = proxy IP | Open (Phase 3) |
| 14 | `/up` route missing | **Fixed** |
| 15 | Each worker loads the models lazily | **Fixed**: `post_worker_init` preload, `WEB_CONCURRENCY=1` |
| 16 | `distutils` import in `config/gunicorn.py` | Open (Phase 3) |
| 17 | Unpaywall title search takes the first result | Open (Phase 3) |
| 18 | PDF download saves any response as `.pdf` | Open (Phase 3) |
| 19 | No `uv.lock` | **Fixed** |
| 20 | No tests, no `ruff` | **Fixed** |
| 21 | Index upload only via Google Drive OAuth | Open |
| 22 | FAISS L2 while bge expects cosine | Open |
| 23 | Setup needs a symlink and a manual settings copy | **Fixed** (`COMPOSE_FILE` in `.env`; `settings.py` is in Git) |
| 24 | Unused `session["user_id"]` | Open (Phase 3) |
| — | 10 documents with dict-valued metadata (duplicate `doi_hash`) | Open (new, see [data.md](data.md)) |

## 7. Designs (not built yet)

### 7.1 Context (memory) methods
Now: if a chat has history, one LLM call rewrites the new question ("rephrase"); Redis keeps the history 1 h. Known defect: the history stores the rephrased question, not the user's question.

| ID | Method | Notes |
|---|---|---|
| M0 | Rephrase (now) | Baseline |
| M1 | Full history in the answer prompt, no rephrase | Saves 1 call per turn, more input tokens |
| M2 | Short running summary | Good for long chats |
| M3 | Semantic answer cache (embed the question; reuse a stored answer above a similarity limit) | Saves all calls on a hit |
| M4 | Provider prompt caching | Lower cost only |

Memory over many chats (proposed, no login): the widget makes a random `client_id` in `localStorage` and sends it as an optional field; no cookie (it would be third-party on forrt.org); Redis `client:{id}` with a 1 h TTL reset on each message; a "Forget me / New chat" button. Longer retention needs a privacy notice and FORRT approval.

### 7.2 Two modes: Open Science and FORRT lookup
"Where is X on FORRT?" / "How do I contribute?" needs a link and a short description, not a summary. Proposal: classify into `open_science`, `forrt_lookup`, `off_topic`; lookup searches the metadata of **all** sheet rows plus forrt.org pages; `/chat` stays the same.

### 7.3 Multilingual
97 % of the sources are English. bge-m3 solved retrieval for nl/de/es; the English re-ranker still drops non-English questions → test `BAAI/bge-reranker-v2-m3`. Tell the model to answer in the user's language.

### 7.4 Target ingestion
FORRT sheets → triage: DOI + OA → PDF (check `%PDF`) → marker; web pages → HTML fetch + trafilatura; paywalled DOI → resource card (OpenAlex title + abstract); video/course → resource card from the FORRT description → normalise metadata (`doi`, `pub_year`, authors, licence) → chunk + embed → versioned index + coverage report.

## 8. Rules

1. `main` is protected; work on `feat/<topic>` or `fix/<topic>`; during the hackathon PRs go to `hackathon`.
2. One problem per PR, under ~300 changed lines, link the issue.
3. A bug fix has a test that fails before the fix; `pytest` passes before merge.
4. Changes to prompts, models, retrieval or chunking include the eval table before and after.
5. Do not change `/chat` fields without approval.
6. Keys only in `.env`.
7. Do not commit PDFs, indexes or generated data.
8. `ruff check --select E,F --ignore E501 just_os test eval` passes.
9. Keep the Apache-2.0 header in `openscholar.py` and the GPL-3 notice in `assets/`.
10. **Definition of done:** code + test + updated docs in `docs/` + eval result if relevant.

## 9. Roadmap after the hackathon (from 16 Nov)

| Week | Work | Done when |
|---|---|---|
| 1 | Merge `hackathon` → `main`; close/relabel issues; model decision record (scores, cost, licence, providers, GPU) | `main` green; decision recorded |
| 2 | #13 ProxyFix, #16 distutils, #24, CI (`pytest` + `ruff` on each PR) | Tests green in CI |
| 3–4 | Retrieval: hybrid BM25 + dense, per-paper cap, inner product (#22), multilingual re-ranker | Eval shows a gain, or the change is rejected |
| 5–6 | Coverage: HTML route, resource cards, incremental ingest (#17, #18), versioned index | Coverage report; more resources indexed |
| 7 | Staging deploy (EU VM) | Staging URL works |
| 8 | Production switch to the chosen model with a fallback; privacy notice; operator README | Prod stable 2 weeks |

## 10. Infrastructure

| Component | GPU | Spec |
|---|---|---|
| Web/API server | No | 4 vCPU, 16 GB RAM, 100 GB SSD, EU, Docker |
| Team laptops | No | 16 GB RAM, Docker Desktop (WSL2), ~10 GB free disk |
| marker PDF → Markdown | Recommended | 1 GPU ≥ 16 GB for a few hours per full run |
| Self-hosted LLM (OpenScholar or the chosen model) | Yes | vLLM on 1× 24–48 GB GPU; 80 GB to test larger models |

Cost estimate: one answer ≈ 6k input + 0.7k output tokens; one eval run (44–60 questions) < 0.10 USD for most models; production at 10,000 questions/month: 5–25 USD with a small model.

Secrets: `OPENROUTER_API_KEY`, `OPENSCHOLAR_API_KEY`, `LLM_API_KEY` (RUG, optional), `UNPAYWALL_EMAIL`, Google Drive `credentials.json` (optional).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Provider removes the chosen model | Second model in the decision record; self-hosted fallback |
| Self-hosted OpenScholar server goes down | Keep `CITATION_MODEL` on an OpenRouter model as fallback |
| OpenScholar server uses plain HTTP: the Bearer key and the questions travel unencrypted | Put the server behind HTTPS (reverse proxy) before production |
| Wrong DOIs from the Unpaywall title match | Similarity threshold (#17) |
| Copyright with shown passages | Licence gate (F4, issue R5) |
| Private admin files leak via the data folder | Keep them out of shared bundles (see [data.md](data.md)) |
| Scope creep (solo work after the hackathon) | Work only from labelled issues; eval gate |

## 12. Crucial additions

GDPR privacy notice (1 h TTL, no full IPs in logs); version the index like research data (source list + embedding model); observability (model, latency, tokens, error type per request); transparency page (model, sources, last index date); accessibility check of the widget (WCAG 2.2 AA); a private ops note (who owns server, domain, keys, Drive); publish the eval set and scores (Zenodo/OSF).

## 13. Open questions

1. Budget for OpenRouter credits (hackathon and production)?
2. Who runs the production host, and is the rate limiter behind a proxy (#13)?
3. Long-term GPU server from FORRT/UM/RUG/SURF for the self-hosted model?
4. Preference for fully open models (OLMo) for values, even at some quality cost?
