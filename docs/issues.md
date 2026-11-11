# Issues

Source text of the GitHub issues. When an issue changes on GitHub, GitHub is the reference; keep this file for the overview.

Copy each block into a GitHub issue. Labels: `track:refs`, `track:eval`, `track:models`, `track:coverage`, and `good first issue` where marked.
Rules for every issue: [project-plan.md](project-plan.md) section 8 (small PR, a test that fails before the fix, eval CSV in the PR when prompts/models/retrieval change).

---

## track:refs — correct references

### R1. Show the publication year, not the form time stamp (bug #3) — `good first issue`
- **Now:** the year is the Google-Form `timestamp` (for example "12/18/2023 17:12:02").
- **Files:** `just_os/qualle.py` (`TIMESTAMP_KEY`, lines ~515, ~569, ~577).
- **Approach:** get `pub_year` from OpenAlex/Crossref by DOI (at ingestion, or a lookup table made once from `data/NWO JUST-OS/BOT/just-os_db_latest.csv`). Fall back to "n.d.".
- **Done when:** a unit test shows the year for a node with a DOI and "n.d." without one; no answer in the live UI shows a time stamp.

### R2. One `normalize_doi()` and `https://doi.org/` links (bug #4) — `good first issue`
- **Now:** the link is the raw spreadsheet value; the DOI regex `10\.\d{4,}/[\w/.-]+` keeps trailing dots and cuts DOIs with `()`, `;`, `:`.
- **Files:** `ingest/helpers.py:28`, `just_os/qualle.py` (`URL_DOI_KEY`).
- **Done when:** unit tests with messy inputs (trailing ".", `doi:` prefix, `https://dx.doi.org/`, DOIs with parentheses) pass; reference links use `https://doi.org/<doi>` when a DOI exists.

### R3. One reference per paper, not per chunk (bug #5)
- **Now:** two chunks of the same paper get two numbers ("Open Science Manual" twice).
- **Files:** `ReferenceProcessor.process_markdown_with_references` and `references_from_nodes` in `just_os/qualle.py`.
- **Done when:** a test with two chunks of one paper gives one source number; both chunk passages stay available for the tooltip.

### R4. Escape the source tooltip (bug #10, security) — `good first issue`
- **Now:** `assets/js/references.js:19` puts `title`, `authors` and `url` into `innerHTML`. The metadata comes from a public Google Form, so this allows stored XSS; `url` can be `javascript:`.
- **Done when:** the tooltip uses `textContent`; links are shown only for `http(s)` URLs; a manual test with a title `<img src=x onerror=alert(1)>` shows the text, not an alert.

### R5. Show the source passage only when the licence allows (F4)
- **Files:** tooltip (`references.js`), `conditions_of_use` metadata.
- **Done when:** the passage shows for CC-BY, CC0 and public domain; other sources show title + link only.

---

## track:eval — evaluation

### E1. Grow `eval/questions.jsonl` to 40–60 reviewed questions
- **Now:** 44 seed questions (24 answer, 17 refuse, 3 non-English), only 5 with `expected_dois`.
- **Add:** `expected_dois` for most answer questions (search `data/processed/vs_latest_bge-m3/docstore.json` or the FORRT sheets); ~5 questions with no answer in the sources; follow-up (multi-turn) questions for the context-method work (M5).
- **Done when:** two people reviewed each item; `python eval/run.py --limit 5` still runs.

### E2. LLM judge: does the cited passage support the sentence?
- **Files:** new `eval/judge.py`, reads the `answer` and `retrieved_dois` columns of a run CSV (add the passage text to the CSV if needed).
- **Done when:** the judge score is a column in `eval/compare.py`; 20 judge results checked by hand.

### E3. Classifier comparison (Open Science / FORRT / off-topic)
- **Use:** `eval/run.py --general-model <model>`; the `expect` field gives the gold label.
- **Candidates:** `openai/gpt-oss-20b`, `meta-llama/llama-3.1-8b-instruct`, `qwen/qwen3.7-flash`, `typesafe/jev-router`, `perplexity/sonar` (no tool calls: uses the new JSON fallback; 0.005 USD per request for web search), and a no-LLM baseline with the bge embedding.
- **Done when:** a table with accuracy, false refusals, time and cost per 1,000 questions.

### E4. One command that runs a named configuration and adds a scorecard row (#32)
- **Why:** #31 section 1. Comparing configurations now means editing `.env`, restarting, then running `eval/run.py`, `eval/judge.py` and `eval/compare.py` by hand.
- **Approach:** a named configuration (answer model, embedding model, re-ranker, top-k rule, routing on/off, verification on/off) in a config file or as flags; one command runs the eval and the judge for it and the row appears in the `eval/compare.py` table with the configuration name.
- **Done when:** five configurations have scorecard rows from the same question set (E1), each made with one command.

---

## track:models — models and speed

### M1. Compare 4–6 answer models
- **Use:** `docker compose exec -e OMP_NUM_THREADS=8 web python eval/run.py --model <id>` for each model, then `python eval/compare.py`.
- **Candidates:** see [evaluation.md](evaluation.md) 3.3. OpenScholar: set `OPENSCHOLAR_BASE_URL` + `OPENSCHOLAR_API_KEY` in `.env` and use `--model openscholar-8b`.
- **Done when:** one table with quality, refusals, errors, time and cost; the decision record lists licence, providers and self-hosting.

### M2. Short generic prompt vs the OpenScholar prompt (#12)
- **Files:** `just_os/openscholar.py:63`, `just_os/qualle.py` (`ResponseGenerator`, `prompt_template`).
- **Done when:** a setting chooses the prompt; eval CSVs for both prompts on 2 models.

### M3. Collect arena ratings and read them
- **Use:** `/arena` (on with `ARENA_ENABLED=true`): pick models, rate each answer 1-5 on correct / references / clarity; leaderboard at `/arena/leaderboard`, raw data at `/arena/ratings`.
- **Done when:** ≥ 50 rated questions from at least 4 people; a short note on which models win and why. Whether to serve several answers to real users is a decision for after the hackathon.

### M4. Make answers faster (target p95 ≤ 15 s, plan N1)
- **Measured (5 Nov):** classify 0.4 s, retrieval + re-ranking 31 s, two answers in parallel 15 s. The re-ranker takes 21 s for 20 chunks on 1 CPU thread (`compose.yaml`: `OMP_NUM_THREADS: 1`).
- **Try one at a time, with timings:** more threads; re-rank fewer chunks (`RETRIEVER_TOP_K`); the multilingual `BAAI/bge-reranker-v2-m3` (also needed for non-English questions).
- **Also:** the baseline (5 Nov) shows that `bge-reranker-base` drops German and Spanish questions ("no sources"), so test `BAAI/bge-reranker-v2-m3` for quality too, not only speed.
- **Done when:** a table of time per step before and after; eval quality not lower.

### M5. Context (memory) methods
- See [project-plan.md](project-plan.md) 7.1 (M0–M4, `client_id` design). Needs the multi-turn questions from E1.
- **Done when:** eval numbers for M0 (rephrase, now) and at least one other method.

### M6. FORRT lookup mode
- See [project-plan.md](project-plan.md) 7.2: three classes (`open_science`, `forrt_lookup`, `off_topic`); lookup over all FORRT sheet rows; `/chat` API stays the same.
- **Done when:** 10 lookup questions in the eval set answer with the correct FORRT link.

### M7. FORRT questions without a router: FORRT pages in the index, and mixed questions (#34)
- **Why:** #31 section 4. The router (M6) is one option; the simpler one is to put forrt.org pages and FORRT resource rows in the same index and let retrieval find them.
- **Approach:** add forrt.org pages (`scripts/fetch_web_resources.py`, C3) and FORRT sheet rows to a copy of the index (`scripts/add_to_index.py --output ...`); run the FORRT lookup questions from E1 with `FORRT_LOOKUP` off and compare with M6. Example questions are in the #15 comments.
- **Also decide:** mixed questions such as "how can I learn more about [cluster topic]?", which may need both literature and FORRT links.
- **Done when:** a decision record compares router vs no router on the same 10+ FORRT questions (correct FORRT link, false refusals) and picks one; `/chat` fields unchanged.

### M8. Arena rating protocol and first results (#35)
- **Why:** #31 section 6. M3 collects the ratings; this says how, so they can be compared.
- **Approach:** a short protocol in `docs/`: which questions raters ask (a fixed list and their own), which configurations are compared, whether model names are hidden (`ARENA_BLIND=true`), and how ratings are summarised.
- **Done when:** the protocol is in `docs/`; first results are summarised in #31: which configurations win (each linked to its scorecard row), how far ratings agree with the LLM judge (E2), and what raters noticed that the judge missed.

---

## track:coverage — what is in the index

### C1. Coverage audit of the live FORRT sheets
- **Data:** `data/raw/forrt_sheet1_261028.csv` (1,504 rows), `data/raw/forrt_sheet2_261028.csv` (285 rows), production metadata `data/NWO JUST-OS/BOT/just-os_db_latest.csv`.
- **Done when:** a reason for each row that is not in the index (no DOI, paywall, web page, video, …) and a bar chart of the reasons.

### C2. Metadata for the FORRT cluster PDFs
- **Data:** `data/FORRT Clusters pdfs/` (1,061 PDFs, names `C01_SC01_<topic>_<author>_<year>.pdf`), working lists `01.FORRT_Clusters_Working_Document_v1.xlsx` and `FORRT Cluster_s.xlsx`, sheet 2.
- **Done when:** a CSV with title, authors, year, DOI and licence for each cluster PDF (match rate reported); these PDFs can then go through `scripts/marker.sh` and `scripts/embed.py`.

### C3. HTML route for web resources
- **Approach:** fetch + `trafilatura` for OSF/Carpentries/GitHub pages; a sample of 50 rows.
- **Done when:** the sample gives Markdown files with metadata, ready for `scripts/embed.py`.

---

## track:retrieval — search quality (new)

### N1. Hybrid retrieval: keyword (BM25) + vector search
- **Why:** pure vector search misses exact terms (names, acronyms such as "HARKing", "CRediT"). Question 3 of the FORRT brief asks for keyword search.
- **Files:** `just_os/rag_service.py` (`create_retriever`), `just_os/qualle.py` (`DocumentRetriever`). llama-index has `BM25Retriever` and `QueryFusionRetriever`.
- **Done when:** a setting turns hybrid search on; `eval/compare_embeddings.py`-style hit@5 and the full eval are reported before and after.

### N2. More variety in the sources (per-paper cap or MMR)
- **Now:** one paper can fill all 7 context slots with its own chunks.
- **Approach:** cap chunks per document (for example 2) before the re-ranker picks `MAX_CHUNKS`, or use MMR.
- **Done when:** a test shows that 7 chunks from one paper become ≤ 2; eval hit@7 and answer quality not lower.

### N3. Multilingual re-ranker
- **Now:** `BAAI/bge-reranker-base` gives German/Spanish questions scores under `MIN_RELEVANCE` → "no sources" (eval 5 Nov).
- **Approach:** test `BAAI/bge-reranker-v2-m3` (quality and speed on CPU); see M4.
- **Done when:** ml02/ml03 in `eval/questions.jsonl` get an answer; p95 time reported.

### N4. Choose the embedding model for production
- **Data:** [evaluation.md](evaluation.md) 3.1: bge-m3 (local, 0.50 hit@5) vs qwen3-embedding-8b (API, 0.53).
- **Done when:** a decision record (quality, speed, privacy, cost); unused index folders removed from the shared bundle.

### N5. Adaptive top-k: relative score cutoff with a minimum and maximum (#33)
- **Why:** #31 section 3 and #1. A fixed number of passages gives targeted questions junk and broad questions too little.
- **Approach:** over-retrieve, re-rank, keep passages within X% of the top re-ranker score, bounded by a minimum and maximum k. Keep the per-paper cap and `MIN_RELEVANCE`. Behind a setting, off by default.
- **Done when:** an eval row shows it is not worse than the fixed `RETRIEVER_TOP_K` default; the rule is written into the source-selection decision record (with N3, N4, M4).

## track:quality — answer quality (new)

### Q1. Hallucination check before the answer is sent
- **Why:** question 2 of the FORRT brief; E2 only judges answers offline.
- **Approach:** a cheap check per sentence: does the cited passage support it (small LLM or the CrossEncoder as an entailment proxy)? Flag or drop sentences that fail.
- **Done when:** a setting turns it on; added time ≤ 3 s; on 20 hand-checked answers it catches the known bad citations.

### Q2. Fix dict-valued metadata of 10 documents
- **Now:** `just-os_db_latest.csv` has duplicate `doi_hash` rows; `scripts/embed.py` calls `metadata.loc[hash].to_dict()`, so 10 documents store every field as `{"<hash>": value}` and show wrong titles/years.
- **Files:** `scripts/embed.py`; data list in `docs/indexed_documents.csv`.
- **Done when:** `embed.py` drops duplicate hashes (keep the first) and a unit test covers it; a re-built index has no dict values.

## track:coverage (new)

### C4. Easy ingestion for non-technical curators
- **Why:** question 3 of the FORRT brief: add resources without the current technical skill.
- **Approach:** one command (or a GitHub Action) that reads new FORRT sheet rows, fetches OA PDFs / web pages, converts them, and **adds** them to the existing index (no full rebuild).
- **Done when:** a new sheet row with an OA DOI is in the index after one command; a coverage report lists skipped rows with a reason.

### C5. Faster PDF conversion and chunking: GROBID vs marker, chunk size (#36)
- **Why:** #31 "Other tracks" (optional extra). marker is slow without a GPU, and chunks are a fixed 350 tokens. See [data.md](data.md).
- **Approach:** convert a sample of PDFs with GROBID and with marker; compare time and body-text fidelity. Separately, try another chunk size or splitting rule on a re-embedded copy of the index.
- **Done when:** a table of time per PDF and text quality for both converters; any chunking change has an eval row against the current index.

## track:ops — setup and hygiene (new)

### O1. Publish the index for the team
- `scripts/get_index.py` exists, but there is no download link. Upload `data/processed/vs_latest_bge-m3.zip` (173 MB) to SURFdrive or a Hugging Face dataset and put the link in the README.

### O2. CI: tests and lint on each PR
- No `.github/workflows/` yet. Run `pytest test/` and `ruff check --select E,F --ignore E501 just_os test eval` on each PR (CPU image, no index needed).

### O3. Self-hosted OpenScholar behind HTTPS
- The server at `OPENSCHOLAR_BASE_URL` uses plain HTTP, so the Bearer key and the user questions travel unencrypted. Add TLS (reverse proxy) and then switch the URL to `https://`.

### O4. Semantic answer cache (M3 in the plan)
- Embed the question; if a recent question is very similar, return the stored answer. Saves all LLM calls on a hit. Needs a similarity limit, a TTL and a test.

## After the hackathon (Phase 3, not for the team)
#13 ProxyFix for the rate limit, #16 `distutils` in `config/gunicorn.py`, #17 Unpaywall title match, #18 `%PDF` check, #21 index upload without Drive OAuth, #22 inner-product FAISS, #24 unused `session["user_id"]`.
