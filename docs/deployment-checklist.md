# Deployment checklist: Just-OS on the University of Münster servers

Status on 25 November 2026, after the answer-model runs of [evaluation.md](evaluation.md) 3.20 and 3.21.

**Priority:** **P0** = blocks deployment, do first. **P1** = do before launch. **P2** = improves answers; can follow the launch.

Order of work: all P0 → P1 → P2. Inside a priority, top to bottom. Decisions taken on 25 November are marked **Decided**.

---

## P0: blockers

### 1. No conversations saved in production; dev keeps saving them

**Decided:** dev saves every chat turn and feedback (for analysis and future testing, also the test-phase chats already in Git, which stay); prod saves nothing. The bot stays embedded on forrt.org like now.

- [x] One switch `PROD_MODE=true`: no chat turn, feedback or arena round saved (file or Redis), no Good/Bad buttons, no debug panel, only the production answer model, a "not saved" notice; `/eval`, `/review`, `/topics`, `/arena`, `/chat/feedback` answer 404. An empty `CHAT_LOG_FILE=` line in `.env` would not have done it (an empty value is ignored and keeps the default path). Test `test_prod_mode_saves_nothing_and_hides_team_pages`.
- [x] Dev and prod side by side from one image: `web` (dev, port 8000, saves chats to `data/chats/`) and `web-prod` (`compose.yaml`, profile `prod`, port 8001, `PROD_MODE=true`, Redis database 1, `data/` read-only). On the server `compose.prod.yaml` names it `just-os-prod` on `proxy-network`. Start: `docker compose --profile prod up -d --build web-prod`.
- [x] Test-phase chats stay in Git (decided).
- [x] `web-prod` started and checked by hand (25 Nov, image built from the Dockerfile's `app` target): `/up` ok; `/eval`, `/review`, `/topics`, `/arena`, `/recommend`, `/chat/feedback` 404; "not saved" notice, no model menu, no nav, no debug panel; `PROD_MODE`, uniGPT, Gemma 4, banded, Redis database 1; `data/` read-only. A question left the dev chat log unchanged and no feedback turn in Redis (only the 1-hour chat memory). Without a uniGPT key the user gets "I'm sorry, I encountered an error…", no stack trace; the placeholder key, not the OpenRouter key, went to uniGPT.
- [ ] Point the reverse proxy (or the Kubernetes ingress, task 3) at it.
- [ ] Privacy notice text checked with the university data-protection officer: the question goes to uniGPT (on university hardware) and, for about two thirds of questions, to OpenRouter's decision model Jev (task 2); the conversation is kept 1 hour in Redis for follow-ups.

### 2. Production answer model and topic check

**Decided (rule):** among the models within ~0.06 of the best score that uniGPT Münster runs, take the cheapest, fastest and best outside English.

From 3.21 (172 questions, today's defaults, bge-m3), only models uniGPT runs **through its API** (GPT-6 Luna is web chat only):

| Model on uniGPT | Score | Gap to best | Mean / p95 s (OpenRouter) | Judge non-English (14 q) | Output tokens / answer | uniGPT API price |
|---|---|---|---|---|---|---|
| Muse Glimmer 30B | **0.755** | 0 | 18.5 / 37.6 | 0.90 | 1461 | flat rate |
| **Gemma 4 31B** | 0.729 | 0.026 | **7.1 / 14.2** | **0.92** | **452** | flat rate |
| DeepSeek V4 Flash | 0.705 | 0.050 | 12.5 / 31.8 | 0.80 | 917 | flat rate |
| Qwen 3.8 27B | 0.687 | 0.068 | 22.2 / 42.2 | 0.83 | 1190 | flat rate |
| Mistral Small 4 | 0.675 | 0.080 | 6.1 / 12.6 | 0.82 | 720 | flat rate |
| gpt-oss-120b (run on Groq) | 0.671 | 0.084 | 3.1 / 5.2 | 0.82 | 1088 | flat rate |

uniGPT's API charges one flat rate for all six (0.5 credits / 1M input, 1 / 1M output), so cost per answer follows the output length. **Gemma 4 31B** wins on every tie-breaker: within 0.03 of the best, 2.6x faster than Muse Glimmer (p95 14 s, inside the 15 s target of #13), the best non-English answers, and the shortest answers (lowest cost). Muse Glimmer's lead (0.026) is inside the noise of one judge on ~160 answers.

**Pair:** banded topic check + Gemma 4 31B. The topic check runs before the answer model, so its accuracy (banded 0.891 vs Jev 0.895, 3.17; tie within the 0.009 run-to-run spread) does not depend on the answer model.

**Pairs rebuilt on 25 Nov** (`eval/pairs.py` → `pairs_261125-1434.csv`: the 3.21 answer runs with the topic checks of `classify_261115-1412`). The /eval table had still shown 15 Nov's pairs from the hybrid + re-ranker runs, and it picked the "best pair" on one number (Correct, then judge), hence "Jev + GPT-6 Luna" and, after the rebuild, "Jev + Muse Glimmer".

**The best pair is now chosen on several factors** (`eval_report.best_pair`; the /eval card, the shortlist under "Topic check × answer model", and `AUTO_DEFAULTS` all use it):

1. **Eligible:** uniGPT's API runs the answer model, its run on today's setting has a score and no errors, and there is a topic check.
2. **Good enough:** Correct within 0.01 of the best eligible pair (a topic check varies by 0.009 between runs), answer score within 0.06 of the best eligible model, and p95 ≤ 15 s (#13). Speed is a requirement, not a race.
3. **Balance:** 2 × quality (score / best) + answers outside English (judge on non-English questions / best) + cost (cheapest uniGPT credits / these); quality counts double, as the citation judge does in the score.
4. **Same answer model, two topic checks:** the cheaper topic check (fewer questions to OpenRouter's decision model, so less text leaves the university).

| Pair | Correct | Score | p95 s | Judge outside English | uniGPT credits / 1k q | Balance |
|---|---|---|---|---|---|---|
| **banded + Gemma 4 31B** | 0.953 | 0.727 | 14.1 | 0.92 | 2.69 | **4.00** (cheaper topic check) |
| Jev + Gemma 4 31B | 0.959 | 0.727 | 14.1 | 0.92 | 2.69 | 4.00 |
| banded / Jev + Mistral Small 4 | 0.953 / 0.959 | 0.673 | 12.6 | 0.82 | 2.99 | 3.64 |
| banded / Jev + gpt-oss-120b | 0.953 / 0.959 | 0.670 | 5.2 | 0.82 | 3.57 | 3.49 |

Left out: Muse Glimmer 30B (1 error, and p95 35 s), DeepSeek V4 Flash and Qwen 3.8 27B (p95 31 s and 42 s), GPT-6 Luna and Qwen 3.7 Flash (not on uniGPT's API), and the topic checks more than 0.01 below the best (cosine, LLM classifier, Clef). Banded and Jev differ by one question (banded refused one in-scope question Jev answered); banded decides a third of the questions without calling OpenRouter. Times are from OpenRouter; the uniGPT run (task 2) checks them.

**How banded works and what it calls:** layer 1 is the bge-m3 cosine of the question to the nearest paper chunk and the nearest FORRT page, with no model call: below both low thresholds → refuse; paper high and page low → answer from the papers. That decides about a third of the questions. Layer 2 (everything else) asks **Jev** (`typesafe/jev-1.14`, `BAND_MIDDLE_ROUTER`), a decision model on OpenRouter's decisions API (calibrated probabilities, ~0.2 s, ~0.014 USD per 1,000 questions). The FORRT pages next to the papers are picked by **Clef** (`cloudflare/clef`), the same API. **uniGPT has no decision models**: it offers chat models (DeepSeek V4 Flash, Qwen 3.8 27B, Qwen 3.5 35B-A3B, Muse Glimmer 30B, Gemma 4 31B, gpt-oss-120b, Mistral Small 4, MedGemma 4B), Qwen3-Embedding-4B, speech and image models; no endpoint returns calibrated choice probabilities, and logprobs are not documented. So Jev and Clef stay on OpenRouter. The alternative without OpenRouter is `BAND_MIDDLE_ROUTER=llm` (the LLM classifier on `GENERAL_MODEL`), which scored 0.810 with Llama 3.1 8B (3.17); with Gemma 4 31B it is untested (P1 task 10).

- [x] `web-prod`: `BASE_URL=https://gpt.uni-muenster.de/v1`, `CITATION_MODEL=GENERAL_MODEL=gemma-4-31B-it`, `ROUTER=banded`, `LLM_API_KEY=${UNIGPT_API_KEY}`, and a separate `DECISION_API_KEY` (the OpenRouter key) for Jev and Clef, so they keep working when the answers go to uniGPT. Without `UNIGPT_API_KEY` the prod key is a placeholder, so the OpenRouter key is never sent to uniGPT.
- [ ] **You:** request a uniGPT API key for the project (research-project keys: the uniGPT team on Mattermost, `mattermost.uni-muenster.de/wwu/channels/unigpt`) with access to `gemma-4-31B-it` and **more than the default 4 parallel requests** (each question makes up to 2 calls: rephrase/classify and answer). Put it in `.env` as `UNIGPT_API_KEY`.
- [ ] With the key: confirm the exact model id (`GET /v1/models`), run the 172 questions once on uniGPT (`eval/run_batches.py` with `--set BASE_URL=... --set LLM_API_KEY=...`) and check score, p95 time and errors against the OpenRouter run.
- [ ] `GENERAL_MODEL` (rephrase, small talk, classifier fallback) was Llama 3.1 8B in every eval; on uniGPT it is Gemma 4 31B, untested in that role: the uniGPT run above covers it.
- [ ] Budget cap / alert on both keys.

### 3. Server: Kubernetes specs and settings

**The embedding model runs inside each web pod, on its CPU; the spec below is sized for it.** Nothing about embedding goes to an API: bge-m3 (568 M parameters) embeds every question locally, and the index and the FORRT page index were embedded with it once, ahead of time. Measured in the dev container (one worker): **4.3 GB RSS** in total:

| Part | Memory | CPU per question |
|---|---|---|
| bge-m3 on CPU (float32) | ~2.3 GB | one forward pass of the question: ~65 ms (eval/compare_embeddings.py, 3.19); up to `OMP_NUM_THREADS` cores |
| Paper index + FORRT glossary (`vs_latest_bge-m3_glossary`): 166,449 vectors of 1,024 dims (~650 MB) + chunk text (~750 MB), with the 26 Nov full texts, abstract cards and web pages | ~1.4 GB | FAISS search over all vectors: ~0.1 s |
| FORRT page index (`vector_data/forrt_pages`) | 1 MB | negligible |
| Python, Flask, gunicorn threads | ~0.5 GB | |

So one pod answers the embedding and search part of a question in about 0.2 s of CPU; at 1 vCPU that is ~5 questions per second, far above the expected traffic, and the answer time is the LLM's on uniGPT (7 s mean, p95 14 s for Gemma 4 31B). No GPU is needed. The re-ranker is off (`RERANK=false`); switching it on would add a second model (~1.1 GB) and 4-15 s of CPU per question, so the limits below would need about 1.5 GB more memory and 4+ dedicated cores.

**Recommended (per environment):**

| Object | Spec | Why |
|---|---|---|
| Deployment `just-os-web` | **2 replicas**, each `requests: cpu 1, memory 5Gi`, `limits: cpu 4, memory 6Gi`; `WEB_CONCURRENCY=1` (one worker; 8 gthreads); `OMP_NUM_THREADS=2` (bge-m3's threads per question) | 4.3 GB measured, bge-m3 included, + headroom; two replicas so a restart or node drain keeps the bot up; one worker per pod, since each worker loads its own copy (~4 GB) |
| Probes | `readinessProbe` and `livenessProbe`: HTTP `GET /up`; `startupProbe` with `failureThreshold × periodSeconds` ≥ 180 s | the models and index load for about a minute; without a startup probe the pod is killed while loading |
| Deployment `redis` | 1 replica, `requests: cpu 100m, memory 256Mi`, no persistence needed | holds 1-hour chat memory and rate-limit counters, shared by both web replicas (that is why it must be one Redis, not one per pod) |
| Volumes | index + FORRT page index: a **ReadOnlyMany PVC** (~2 GB) or baked into the image; Hugging Face cache (bge-m3, ~2.3 GB): baked into the image or a PVC | no download at start; read-only, as in `compose.yaml` |
| Node | ≥ 4 vCPU, ≥ 16 GB RAM for two replicas + Redis (or two nodes with 8 GB); no GPU | |
| Ingress | HTTPS, host for the widget; `PROXY_FIX_X_FOR=1` (one proxy) so the rate limit sees client IPs; `ALLOWED_ORIGINS=https://forrt.org` | the widget is embedded on forrt.org |
| Egress | `gpt.uni-muenster.de` (answers), `openrouter.ai` (Jev, Clef), `forrt.org` (FORRT pages are fetched live per question) | NetworkPolicy, if the cluster restricts egress |
| Secrets | `UNIGPT_API_KEY`, `OPENROUTER_API_KEY` as a Kubernetes Secret, never in the image | |
| Autoscaling | optional HPA on CPU 70%, 2-4 replicas; memory per replica stays fixed | |

- [ ] **You:** ask the university's Kubernetes team whether these fit, and whether they run the ingress and TLS.
- [x] Manifests: [deploy/kubernetes/just-os.yaml](../deploy/kubernetes/just-os.yaml) (ConfigMap, data and model PVCs, web Deployment with probes and the sizes above, Service, Redis, Ingress with streaming, optional HPA; keys from a Secret). Parsed and checked offline; not applied to a cluster yet.
- [x] Build, key, copy and check steps: [deploy/kubernetes/README.md](../deploy/kubernetes/README.md). `data/` is not in the image, so the data volume holds the index and the two files the bot reads from `data/raw` (`pub_years.csv`, `forrt_sheet1_261028.csv`) and, since 26 Nov, `data/curation/forrt_article_list.csv` (cluster boost).
- [ ] **You / cluster team:** registry for the image, host name, storage class; then apply and run the checks in the README.
- [ ] Rotate the keys that were in team bundles (`scripts/make_share_bundle.py`).
- [ ] Unit tests green on the deploy commit. (25 Nov: all green; `test_no_proxy_fix_by_default` no longer reads `PROXY_FIX_X_FOR` from `.env`.)

### 4. Open issues and PRs

Read on 25 November (17 issues, 1 draft PR). **The 6 below were closed on 25 November with notes** (#57, #10, #34, #32, #14, #8); 2 close after a result, 6 wait on you or the team, 4 are open work for later.

**Closed 25 Nov** (the "done when" of each was met):

| # | Why it can close | Note to add |
|---|---|---|
| 57 N6 more embedding models | Run (3.19) and decided (keep bge-m3); prefixes and real-question run checked on 25 Nov (task 8) | link evaluation.md 3.19, 3.21, 3.22 |
| 10 M1 compare answer models | 13 models compared (3.20, 3.21) with quality, errors, time and cost; Gemma 4 31B chosen (task 2) | link 3.20, 3.21 and task 2 |
| 34 M7 FORRT questions without a router | Compared: no router (`none`) 0.035 vs banded 0.891 (3.17); mixed questions get FORRT pages next to the papers (`FORRT_IN_PAPERS`, 3.14) | link 3.14, 3.17 |
| 32 E4 one command per configuration | `eval/scorecard.py` + `eval/configs.json`; six `search-*` configurations and the Voyage runs were made with it (3.17, 3.21) | |
| 14 M5 context methods | Compared on 138 chats (3.16); default `CONTEXT_METHOD=hybrid`. Running summary (M2) and cross-chat memory were not built: not planned | link 3.16 |
| 8 E2 citation judge | `eval/judge.py` exists; checked against people on 20 questions (3.15): means agree (0.64 / 0.63), single-answer ranking does not (Spearman 0.18) | link 3.15; the caveat stays in evaluation.md |

**Close after one result:**

| # | Waiting for |
|---|---|
| 33 N5 adaptive top-k | The 25 Nov eval of the per-paper cap + adaptive top-k (task 6); then close with the decision |
| 13 M4 faster answers (p95 ≤ 15 s) | Re-ranker off (3.18) removed the 14-38 s step; Gemma 4 31B is p95 14.2 s on OpenRouter. Close after the same measure on uniGPT (task 2, needs your key) |

**Wait on you or the team:**

| # | Decision needed |
|---|---|
| 31 Hackathon success criteria | Date passed; most points are decided (eval pipeline, model shortlist, router). You or Lukas: close with a summary, or keep as the record |
| 12 M3 arena votes (≥ 50 from 4 people) | Needs people. Arena is dev-only now: run a rating session, or close as not needed |
| 35 M8 arena protocol | Same: only needed if the arena is used for decisions |
| 36 C5 faster PDF conversion / chunk size | Conversion done: `./run curate` downloads and converts in parallel and resumes (573 rows in 16 min instead of ~15 h). Chunk size: needs a full re-embed (~1 day CPU); close as won't do, or keep for after launch |
| 1 JUST-OS ideas | Keep open as the backlog |
| PR 40 OpenScholar-8B on a RunPod GPU (Lukas) | OpenScholar is not a production candidate (3.12: 0.574). Ask Lukas to close or merge it as a tool for later tests |

**Open work (P2, not blocking):** #61 one question bank (native-speaker checks of 20 translations are pending), #68 answer store format (the hybrid part is moot while search is `vector`), #23 hallucination check (calibrated 26 Nov, evaluation.md 3.26: catches at most a third of unsupported sources and doubles answer time, so it stays off), #18 HTML route for web resources (done 26 Nov: 318 FORRT web pages indexed).

- [x] Closed the 6 with notes (25 Nov). #33 and #13 close after their results.

---

## P1: before launch

### 5. FORRT Cluster publications not in the index

Counted on 25 November against `data/processed/vs_latest_bge-m3`:

| | Count |
|---|---|
| Rows in `Publications.csv` | 1,295 (1 marked "Display exclusion") |
| Unique DOIs | 820 (the rest repeat a paper in another sub-cluster) |
| DOIs in the index | 582 |
| **DOIs not found in the index** | **238** |
| … of which **already in the index by title** (their metadata has no DOI) | **68**: fix the metadata only |
| … of which the **PDF is already on disk** (`data/FORRT Clusters pdfs`, matched in `data/interim/cluster_pdf_metadata.csv`) | **9** (4 already converted to `data/processed/cluster_markdown`) |
| … with **no copy on disk** | **161** (66 with an open-access link; 95 without: books, paywalled papers, 18 websites) |
| Rows **without a DOI** | 161 rows, 130 unique titles: 74 websites, 25 OSF preprints, 22 books, 8 blog posts, 5 policy documents, 4 videos, … (none has an `OA Link`) |

**No full rebuild is needed:** `scripts/add_to_index.py` adds documents to the existing index. **Every one of these rows has an `Abstract` or FORRT `Summary`** in the CSV (161/161 and 161/161), so the fastest complete step is:

- [x] ~~Write the DOI into the metadata of the 68 found by title~~: not needed. They are in the index as the **published version** (journal DOI) while FORRT's list cites the preprint DOI; both are valid, so nothing was overwritten.
- [x] The 9 PDFs on disk are part of the download run below (in `data/curation/forrt_need_pdf.csv`).
- [x] **Abstract cards** for everything still missing (done, see the line below; 161 papers without a copy + 130 rows without a DOI): one document per row with title, FORRT summary, abstract, sub-cluster and link (DOI, or the URL from the APA reference), added with `add_to_index`. Abstracts and FORRT's own summaries can be indexed without full-text rights; the card links to the full work.
- [x] **Downloader** (25 Nov): `./run curate` now looks for an open copy in several places, modelled on FLoRA's `shared/pdf_sources.py` ([ingest/pdf_sources.py](../ingest/pdf_sources.py)): the row's link, arXiv/OSF preprints, Unpaywall (all locations), OpenAlex, Semantic Scholar, Europe PMC, the publisher page's `citation_pdf_url`; only real PDFs are kept and GROBID's title must match the row's (else `wrong_document`, the next copy is tried). Input ready: `data/curation/forrt_cluster_missing.csv` (the 9 on disk + 161 without a copy) and `data/curation/forrt_cluster_doi_fixes.csv` (the 68 to fix).
- [x] **Recommend a study** (25 Nov): page `/recommend` (dev, team page) where anyone pastes DOIs or links with a note; `./run curate --recommendations` processes them like any other list ([curators.md](curators.md)).
- [x] **Downloaded (25–26 Nov):** `./run curate --csv data/curation/forrt_need_pdf.csv --no-index` on the 573 articles and books of the article list's "Need a PDF" sheet: 141 converted, 138 without an open copy, 190 downloads failed, 83 web pages failed or too short, 14 wrong document, 4 already indexed (`data/curation/261125/report.csv`). The 141 were added to `vs_latest_bge-m3_glossary` (26 Nov; the index before: `vs_latest_bge-m3_glossary_before_261125_additions`).
- [x] **Abstract cards** built (25 Nov, `scripts/build_abstract_cards.py`): 908 resources not in the index whose FORRT summary + abstract has ≥100 characters (525 web resources, 314 articles, 69 books) → `data/processed/abstract_cards/`. Added to the index after the downloads, so full texts win: 818 cards added on 26 Nov (the other 90 had a document already). Decided: all of them, quotes hidden unless openly licensed. The other ~940 (mostly ORxD and JUSTOS rows) have only a title and a link: they need their page fetched (#18).
- [x] Websites (#18, 26 Nov): 737 FORRT web resources fetched, 318 with enough running text indexed (`data/curation/261126/`; 316 too short, 88 failed, 102 menu and landing pages dropped by the new 200-word rule). Backup: `vs_latest_bge-m3_glossary_before_261126_web`.
- [x] Retried (26 Nov) every "Need a PDF" row that had no full text, including those with only an abstract card (curate and `add_to_index` used to count a card as indexed): 1 more full text of 428 (QuOCCA, added). The rest: 179 downloads failed, 148 without an open copy, 72 web pages failed, 14 wrong document, 11 web pages too short, 3 not converted (`data/curation/261126_need_pdf_retry/report.csv`).
- [ ] **Someone with library access:** the 427 articles and books still without a full text are in `data/curation/forrt_need_pdf.csv` (and the "Need a PDF" sheet of `forrt_article_list.xlsx`), with the last try and its reason. PDFs they find go through `./run curate --csv` like any other rows.
- [x] Re-run hit@7 (26 Nov, evaluation.md 3.26): 0.694 → 0.648 on the larger index, mostly new documents taking slots from expected DOIs picked on the old index; with the cluster boost (task 12) 0.704. Correct 0.871, judge 0.812.

Other files in `data/FORRT Clusters/`: `Clusters.csv` (13) and `Sub-Clusters.csv` (95) hold the explanation of each cluster and sub-cluster (useful as chunk metadata and topic-map labels; the `annotations` column is editors' notes); `Publications.csv` also has `Focus`, `Specificity`, `Summary`, `Language`, `License`; `Website Source.xlsx` is the same three tables plus a `tags` sheet of allowed values.

### 6. Fewer paragraphs from the same paper; 4-10 citations

**Decided:** per-paper cap + adaptive top-k, evaluated before switching on.

Today 7 chunks come from 4.6 papers on average; only 42 of 542 cached questions get 7 different papers.

- [x] `MAX_CHUNKS_PER_DOC` (per-paper cap) existed. `ADAPTIVE_TOP_K` worked only with the re-ranker; since 25 Nov it also works with `RERANK=false` (vector search): keep chunks whose cosine is at least `ADAPTIVE_TOP_K_RATIO` × the best one's, at least `ADAPTIVE_TOP_K_MIN`, at most `MAX_CHUNKS`, after the cap. Test `test_adaptive_top_k_without_reranker_cuts_on_cosine_after_the_paper_cap`. The eval retrieval cache now keys on the ratio and minimum too.
- [x] Simulated on 542 cached retrievals: cap 2 → 5.5 papers in 7 chunks; cap 2 + ratio 0.95, min 4, max 10 → 7.1 chunks from 5.4 papers on average (4 to 10).
- [x] **Result (evaluation.md 3.23):** cap 2 → 4.6 papers per answer instead of 4.1, at most 1.9 chunks of one paper instead of 2.6, score level (0.727 vs 0.729); cap + adaptive 4-10: score 0.721, rubric lower, no gain.
- [x] Cap switched on (25 Nov): `MAX_CHUNKS_PER_DOC=2` is the default in `config/settings.py` (dev, `web-prod` and Kubernetes); adaptive top-k stays off.
- [x] #33 closed with 3.23 (25 Nov).

### 6b. Questions about one specific paper (reference lookup)

- [x] (25 Nov) `just_os/reference_lookup.py`, on by default (`REFERENCE_LOOKUP`): a question naming a paper of the library by DOI, title, short title ("the false positive psychology paper") or two of its authors' surnames (or one + the year) is answered from that paper's chunks only, without the per-paper cap; the index stores full text, but titles and authors were never searched. Checked live: "Why did Simmons, Nelson and Simonsohn kick off the crisis in psychology?" now answers from their papers; fires on 1 of the 596 eval questions (correctly). Memory: a table of 1,354 papers and their FAISS row numbers, a few MB.
- [x] 13 reference questions in `eval/reference_questions.jsonl` (DOI, title, short title, two authors, author + year, organisation + year): the lookup finds the expected paper for **13 of 13**; on the 596 other eval questions it fires twice, both rightly (Open Science Collaboration 2015; "qualitative research reporting standards" → SRQR). Titles now use function words only as stop words ("A manifesto for reproducible science" had lost its words), and a title match needs all its words or a cue that a work is meant.
- [x] Answered the 13 with the bot (26 Nov, `eval/run.py --questions eval/reference_questions.jsonl`, Llama 3.1 8B as answer model in both runs): with the lookup the named paper is among the sources for **13 of 13** (all answered, judge 1.00); without it **4 of 13**, and "What does Cumming (2013) recommend in The New Statistics?" is refused. Results: `eval/results/reference_lookup_{true,false}.csv`. (`eval/run.py` now also records the lookup's chunks; before, it saw only the search.)

### 6c. Rewriting follow-up questions

- [x] (25 Nov) Follow-ups are rewritten by Gemma 4 31B (`GENERAL_MODEL`) instead of Llama 3.1 8B, which copied the previous answer into the rewrite (so the topic check refused or misrouted the follow-up); an over-long rewrite falls back to the question as typed. On the 138 follow-up chats: 1.86 → **1.91** of 2, 91% → 93% fully answered, routed as labelled 92% → 96% (evaluation.md 3.25). Production already used Gemma 4 for this.

### 7. FORRT Glossary as sources

**Decided:** one document per term per language, all available languages.

- [x] `scripts/build_glossary.py`: reads FORRT's `content/glossary/_glossaries.json` (GitHub) and forrt.org's sitemap; writes `data/processed/glossary_markdown/` (1,298 documents: English 260, German 262, Chinese 262, Arabic 261, Turkish 253). Each document: the title, definition and related terms; title "`<term>` (FORRT Glossary, `<Language>`)", link to the entry's own forrt.org page (1,297 of 1,298 found in the sitemap; Hugo changes some Arabic and Turkish slugs, so the sitemap, not the title, gives the address; the one miss links to the language's glossary), licence CC BY-NC-SA 4.0 (linked, no quote shown), the DOIs of its references in `reference_dois`.
- [x] At most one glossary entry per answer (the best-matching one, usually in the question's language), so the same term in five languages cannot push out the papers: the other slots stay papers, which gives "glossary link + paper" for a definition question. Test `test_one_glossary_entry_per_answer`.
- [x] **Result (evaluation.md 3.23):** added to `data/processed/vs_latest_bge-m3_glossary`; score 0.764 vs 0.729 (rubric 0.80 vs 0.72, on questions written from the glossary, so favourable to it), judge support on the 147 other questions level (0.716 vs 0.701), hit@7 level; a glossary entry in the sources of 50 of 172 answers.
- [x] Checked live on dev (25 Nov): "What is HARKing?" cites the English glossary entry and four papers. Fixed on the way: the kept glossary entry is now the one in the question's language, else English (it had picked the Turkish "HARKing", spelled alike); and `AUTO_DEFAULTS` now also reaches the RAG service that gunicorn preloads (it had answered with `CITATION_MODEL` from `.env`, Llama 3.1 8B, whenever a request named no model, as the forrt.org widget does; production sets the model explicitly and was not affected).
- [x] Glossary index switched on (25 Nov): `VECTOR_STORE=data/processed/vs_latest_bge-m3_glossary` is the default in `config/settings.py`; the Kubernetes README copies that folder. Rebuilding: `scripts/build_glossary.py`, then `add_to_index` onto a fresh copy of the paper index.
- [x] When a kept glossary entry cites papers in the index (`reference_dois`), they come first among the found chunks (26 Nov, `limit_per_document`).

### 8. Embedding model: why bge-m3 (OpenScholar_Retriever and sciembed)

Checked on 25 November:
- **No missing prefix, for any model.** OpenScholar_Retriever (Contriever, continued pre-training on peS2o) and sciembed-full (ModernBERT) document none (sciembed's sentence-transformers config has empty prompts); bge-m3 needs none ("no longer requires adding instructions to the queries"). The others got theirs: e5 `query: `/`passage: `, Qwen3 the instruction, Snowflake `query: `, Voyage `input_type`, voyage-4-nano its prompt, bge-small-en-v1.5 llama-index's BGE instruction (added automatically; llama-index adds none to bge-m3).
- **Loaded correctly:** both use mean pooling as their authors do; only OpenScholar's unused pooler weights are missing.
- **Not truncation:** chunks are ~330 tokens (p90 ~370), within the 512-token limit of both.
- **Why they score low:** both are English-only (the question set is 63% Dutch, German and Spanish; in English alone they are still below bge-m3: hit@5 0.37 and 0.44 against 0.51); OpenScholar_Retriever is a first-stage retriever meant to sit in front of OpenScholar's re-ranker over 237 M passages, and sciembed was trained to match citation sentences to the papers they cite, not questions to passages; and our library is psychology and meta-science, not the CS/biomedicine they mostly saw.
- [x] **Result (evaluation.md 3.22):** with 95% intervals and the prefix per model. OpenScholar_Retriever and sciembed are below bge-m3 in English alone (-0.14, -0.08) and on the 91 real questions (-0.14, -0.12). Voyage's +0.16 on synthetic questions disappears on real ones (-0.01, interval -0.10 to +0.08), as in 3.21. bge-m3 stays.

### 9. /eval page cleanup

- [x] (25 Nov) Answer models: one table on today's setting (bge-m3 · vector search), every row with its **Setting** and a **Why**; other settings (Voyage, paper cap) and runs before 14 Nov (hybrid + re-ranker) folded; the full numbers folded. Tables show 10 rows with "Show all"; column help and the old full-pipeline runs folded. Embeddings: 95% interval, English hit@5 and a Why per model.
- [x] Corrected the note "uniGPT Münster offers no embedding models": it offers Qwen3-Embedding-4B on request (E5).

### 10. Keyword ranking (hybrid search)

**Default since 14 November: plain vector search** (`SEARCH_MODE=vector`, `RERANK=false` in `config/settings.py` and `.env`). **Already evaluated (3.17, 172 questions, three answer models):** plain vector search found an expected paper most often (hit@7 0.63-0.68 against 0.61-0.66 for hybrid and 0.41-0.44 for BM25 alone), with judge support and rubric coverage level within noise, and without the 15-38 s of the re-ranker. Hence `SEARCH_MODE=vector`, `RERANK=false` since 14 November (3.18). This matches the earlier finding that vector search is as good and faster.

- [ ] Not needed for launch. Optional later: a keyword boost only for acronyms and glossary terms (HARKing, QRP, SIPS, HiTOP: #68 lists two names bge-m3 does not know), which the glossary documents of task 7 may already cover.
- [ ] Optional: `BAND_MIDDLE_ROUTER=llm` with Gemma 4 31B (topic check without OpenRouter), if keeping all question text on university hardware becomes a requirement.

### 11. Speed and reliability

- [ ] p95 with Gemma 4 31B on uniGPT (task 2), target ≤ 15 s.
- [x] Behaviour when uniGPT or OpenRouter is down (25 Nov): the user gets a clear error message and **Try again**, no stack trace; Jev falls back to the LLM classifier. Errors no retry can fix (400, 401 wrong key, 403, 404 unknown model) are no longer retried 4 times (`NO_RETRY_STATUS`): the error shows at once; time-outs, 429 and 5xx are still retried.
- [ ] Short load test (10 parallel users) on the server; mind uniGPT's parallel-request limit. Dev (26 Nov, one container, OpenRouter models, the larger index): 10 questions at once all answered, median 12.9 s, slowest 21.9 s, 3.8 GB memory; repeat on the server with uniGPT.

---

## P2: after launch or when time allows

### 12. Topic map

`eval/topic_map/` maps the index by FORRT cluster / sub-cluster with keywords and citation density, and lists wrong files and titles.

- [x] **Data quality** (25 Nov): `config/index_corrections.json`. The 6 documents whose text is another work (e.g. 752 chunks of Canadian Journal of Surgery abstracts) are never returned by the search or the reference lookup (`exclude`); the 7 wrong titles (a licence line, a repository header, "Alfalfa…" for *Building better theories*) are corrected in both indexes' metadata by `scripts/fix_index_titles.py` (384 chunks; backups `docstore.json.bak-261125`). 27 Nov: the 29 file-name titles too (4,541 chunks; evaluation.md 3.29).
- [x] **Coverage gaps:** task 5's abstract cards and web pages are in. Publication Sharing is still thin (2% of chunks, 38 documents; `cluster_balance_261126.md`).
- [x] Cluster boost (26 Nov, evaluation.md 3.26): clusters come from `forrt_article_list.csv` at start, not stored on chunks (`just_os/clusters.py`). On by default: `CLUSTER_BOOST=0.02`, hit@7 0.648 → 0.704, judge 0.802 → 0.812.
- [x] Suggested questions on the chat start page, one per cluster (`SUGGESTED_QUESTIONS`; four at random until the first question).
- [x] Eval balance (`eval/cluster_balance.py`): Replication Crisis, Academic Structures and Replication and Meta-research are under-tested (-6 to -12 points); add questions there next.

### 13. Other

- [x] Hallucination check before sending (#23): calibrated, kept off (evaluation.md 3.26).
- [ ] Human review of a sample of Gemma 4 31B answers on `/review` (dev).
- [x] Re-run the topic check on today's defaults (26 Nov, `classify_261126-1341.csv`): banded 0.89, the same answers as on 15 Nov; no retuning.
- [x] Faster PDF conversion (#36: parallel, resumable `./run curate`), HTML route for web resources (#18: 318 pages indexed).
- [x] Runbook: [runbook.md](runbook.md) (deploy, update the index with glossary and abstract cards, roll back, rotate keys, symptoms).

---

## Questions answered (25 November)

| Question | Answer |
|---|---|
| Dev and prod | Two services from one image; dev saves chats, prod does not |
| Old chats in Git | Keep (dev, analysis) |
| Answer model | Gemma 4 31B on uniGPT (task 2) |
| Where the bot runs | Embedded on forrt.org, as now |
| Server | Kubernetes, specs in task 3 |
| Glossary languages | All five |
