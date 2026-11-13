# Evaluation

How we measure the bot, the results so far, and what each number means.
Rule: a change to prompts, models, retrieval or chunking needs an eval table before and after (see [hackathon.md](hackathon.md)).

The bot first checks the topic of a question (open science, FORRT, both or neither), then answers it from the papers or from the FORRT pages, or refuses it. Two evaluations follow these two steps:

- **Topic check** (`eval/classify.py`): runs only the check, on each question of `eval/questions.jsonl`, and compares the label it gives with the question's gold label. No answer is written, so it is fast and cheap (section 2, Topic check).
- **Answering** (`eval/run.py`): runs the whole bot, topic check included, and scores what comes out against `expect` (answer or refuse), the expected sources and, where a question has one, its rubric; `eval/judge.py` scores whether the cited passages support the answer (section 2, Full pipeline eval).

A wrong refusal or a missing source in the answering eval can come from either step: the topic check turning a question away or sending a paper question to the FORRT pages, or the search finding nothing above the relevance threshold ("no sources"). Read a drop in the answering eval's Correct together with a topic check run on the same questions.

## 1. Tools

| Tool | Command | Output |
|---|---|---|
| Full pipeline eval | `docker compose exec -e OMP_NUM_THREADS=8 web python eval/run.py --model <id> [--general-model <id>] [--limit 5]`; `--no-retrieval` answers without the library (a baseline), `--skip-classifier` treats every question as open science, `--full-answers` keeps the whole answer, `--out` names the file; `--questions eval/forrt_questions.jsonl` runs the 32 FORRT website questions (every one should be answered; hit = an expected forrt.org URL among the pages used) | `eval/results/run_<YYMMDD-HHMM>_<model>.csv` |
| Several models, resumable | `python eval/run_batches.py --since <YYMMDD-HHMM> <model> [<model> ...]` (host) | per model one `run_*.csv`: batches of 30 questions in fresh processes (one long process runs out of the Docker VM's 7.6 GB after ~47 questions); after a stop, the next start skips the questions already in the model's run files since `--since` and merges them when complete |
| Named configuration, one command (E4, #32) | `python eval/scorecard.py <name> [<name> ...] [--limit N] [--since YYMMDD-HHMM] [--no-judge]` (host); `--table` only prints the table | A configuration is a name in `eval/configs.json` with the settings that differ from `.env` (for example `{"ROUTER": "jev", "CITATION_MODEL": "openai/gpt-oss-20b"}`: a topic check + answer model pair). Runs it like `run_batches.py` into `run_<YYMMDD-HHMM>_cfg-<name>.csv`, judges it with `judge.py`, and prints the table of the newest run of each configuration |
| Every topic check x answer model pair (#9, #10) | 1. per answer model `python eval/run_batches.py --since <YYMMDD-HHMM> --questions eval/questions.jsonl,eval/forrt_questions.jsonl --route open_science <model>` and the same with `--route forrt`; 2. `eval/judge.py` on the papers run; 3. `eval/classify.py --routers jev,clef-flash,clef,llm,cosine,banded,none --questions <same files>`; 4. `python eval/pairs.py` | `eval/results/pairs_<YYMMDD-HHMM>.csv`: per pair Correct, answered, refused, hit, citations, judge, seconds, cost. The topic check only picks where a question goes, so each model answers every question once from the papers and once from the FORRT pages, and each topic check's decision per question picks the answer the pair gives: 2 runs per model instead of one per pair. `--route` runs reuse the ranked chunks (`--cache-retrieval`, `eval/.retrieval_cache/`), so the re-ranker runs once per question for all models and their seconds are answer time only |
| Human review of 20 answers (#8) | 1. `docker compose run --rm -T web python eval/run.py --questions eval/human_review_questions.jsonl --full-answers --out eval/results/human_review_<YYMMDD>.csv` (20 English questions: 8 open science, 5 FORRT, 2 both, 5 science-related that should be refused); 2. `eval/judge.py` on it (FORRT-page answers are judged too, against the page text); 3. `python eval/judge_sheet.py <csv> --questions eval/human_review_questions.jsonl` → `docs/judge-check.md` (with the judge's scores); 4. `python eval/build_review.py <csv> --questions ...` → `eval/human_review_items.json` | Reviewers open `/review` (also through the tunnel), write their name, score each question (decision + five 1-5 scores, the arena's scale, + note) and press **Save to the team**: one CSV per save in `data/reviews/`, which is in Git during the test phase. Commit and push that folder afterwards. Compare their scores with `judge_support` by `item_id` |
| Answer store (#54) | `python eval/answers.py [eval/results/run_X.csv ...] [--rounds data/arena/rounds.jsonl] [--chats data/chats/chats.jsonl]` (host; standard library only) | `data/answers/answers_<source>.jsonl`: one record per answer from a run, the arena or the chat, with `answer_id` (`<run>#<question>`, `arena:<battle>:<model>`, `chat:<turn>`), the question, what produced it (`config`), outcome and `answered_from` in the run's terms, the answer, its sources with passages, time and cost; `complete` is false when the run cut answers and passages (no `--full-answers`). `eval/scores.py` scores these same `answer_id`s |
| Score rows and people against judges (#54) | `python eval/scores.py eval/results/human_review_<YYMMDD>.csv [--reviews data/reviews] [--arena data/arena/ratings.jsonl]` (host; standard library only) | `data/scores/scores_<run>.jsonl`: one row per answer, criterion and scorer (person, LLM judge or gold metric) with the raw score and its scale, from the run's columns, the last review of each reviewer per question and the arena ratings; prints people against each judge or metric (Spearman, means on 0-1) and reviewer against reviewer (quadratic weighted kappa, exact, within 1) |
| Criteria judge (#54) | `docker compose run --rm -T -v "$PWD/data/scores:/app/data/scores" web python eval/criteria_judge.py data/answers/answers_X.jsonl [--model ...]` | score rows in `data/scores/scores_criteria-judge_<store>.jsonl`: per answered record of the answer store, correctness, completeness, source relevance and clarity on the shared scale, with the definitions of `/review` (`judges.criteria` in `config/criteria.json`); `eval/scores.py` then compares them with people |
| 100 questions for a team arena session (#12) | `python eval/make_arena_sheet.py` | `eval/arena_test_questions.csv` / `.xlsx`: category, where to test (Arena, or Chat for the 10 two-part questions), the question and follow-up, what the bot should do, 3 suggested models, columns for tester and notes |
| Table of runs | `docker compose exec web python eval/compare.py [csv ...]` | Markdown table (with "Judge support" once judged) |
| LLM judge (#8) | `docker compose exec web python eval/judge.py eval/results/run_X.csv [--model ...]` | adds `judge_support` (0-1) to the run CSV; needs runs made after 10 Nov (they save the passages) |
| Rubric judge (E1, #7) | `docker compose exec web python eval/rubric_judge.py eval/results/run_X.csv [--items FILE] [--model ...] [--controls]` | adds `rubric_coverage`, `rubric_core`, `rubric_scores` and `doi_recall` to the run CSV for the questions with a rubric; default judge `google/gemini-3.8-flash`; `--controls` also scores reference answers |
| Glossary items | `docker compose exec web python eval/glossary_items.py GLOSSARY_JSON --terms eval/glossary_terms.txt --model <id> [--no-reasoning]` | `eval/glossary_items_<model>.jsonl`: per term a question, a reference answer and 3-5 rubric items from the FORRT glossary definition |
| Glossary items answered and judged | `docker compose exec web sh eval/answer_items.sh <generator>` | `eval/results/glossary_<generator>_{library,noretrieval}.csv` |
| Expert grading page | `python eval/build_grading_page.py GLOSSARY_JSON --items eval/glossary_items_*.jsonl --out DIR` | `DIR/grading.html` (blind, works offline) and `DIR/grading_key.csv`, which the grader must not see |
| Expert against generators and judge | `python eval/grading_report.py --key KEY --part1 P1 --part2 P2` | per generator: questions accepted, rubric items needed; per rubric item: expert score against judge score |
| Topic check comparison (#9) | `docker compose exec web python eval/classify.py --routers jev,banded,... [--questions a.jsonl,b.jsonl]` (the whole check) or `--models a,b [--intent]` (the LLM classifier alone) | Markdown table: accuracy, false refusals, false answers, errors, time, cost; also `eval/results/classify_<YYMMDD-HHMM>.csv` |
| Retrieval question set | `python eval/make_retrieval_set.py` | `eval/retrieval_questions.jsonl` |
| Embedding comparison | `python eval/compare_embeddings.py [E2 E4 ...]` (GPU or API) | `eval/results/embeddings_<YYMMDD>.csv` |
| Reviewer sheet | `python eval/export_questions.py [eval/results/run_X.csv]` (host: needs openpyxl) | `eval/questions.xlsx`: each question with its expected DOIs/URLs and the DOIs the bot cited in the newest run, one per cell as a clickable `https://doi.org/…` link with the title; the retrieved DOIs, the matches, and empty columns to judge them |
| Thresholds of the banded topic check | `docker compose exec web python eval/tune_bands.py [--margin 0.01] [--max-refused 0.02]` | the four `BAND_*` settings and the share of each question set in each band; `eval/results/bands_<YYMMDD>.csv` (similarities per question) |
| Coverage audit | `python eval/coverage.py` | `eval/results/coverage_<YYMMDD>.{csv,md,svg}` (see [data.md](data.md) 4) |
| Topic map (section 3.13) | `uv sync --group analysis`, then `python eval/topic_map/build_map.py` (about 5 min on a laptop CPU), `taxonomy.py`, `title_check.py`, `page.py [--before eval/.topic_map/<older run>]` (host; `--index`, `--work` and `--pdfs` change the defaults; the last three call OpenRouter bge-m3 for a few cents) | `eval/results/topic_map_<YYMMDD>.{html,md,csv}`: the interactive map of every chunk, coverage of the 93 FORRT sub-clusters, the eval questions by similarity, papers with a wrong text or title. Working files in `eval/.topic_map/` (not in Git) |
| Arena (human ratings) | http://localhost:8000/arena with `ARENA_ENABLED=true`: pick models, rate each answer 1-5 on correct / references / clarity | `/arena/leaderboard`, `/arena/ratings` |

Question sets:
- `eval/questions.jsonl`: 140 questions for the full pipeline (112 should answer, 28 should refuse; 14 not English, 13 of them checked by native speakers; 108 with `expected_dois`, 8 with `expected_urls`; 25 with a rubric). The first 54 are the earlier set (unchanged); 47 come from the question bank of Meltem and Mohit (`data/raw/questions_bank_261112.csv`, 12 Nov; its 37 other rows were already in the set) and 16 (`new51`-`new66`) from its revised version (`data/raw/questions_bank_261112b.csv`; the earlier rows are unchanged); 23 (`gl01`-`gl25`) are FORRT glossary items by gpt-4.1-mini (section 3.9), whose rubric the other two of its items (HARKing, Preregistration) add to `new60` and `pr01`, which ask the same. The glossary-derived text is under CC BY-NC-SA 4.0 (section 3.9). Fields, in this order:

  | Field | Values |
  |---|---|
  | `id` | `pr01`, `off07`, `ml04`, … (earlier set); `old17`, `new13`, … (bank ID; a multi-turn row has the ID of its first turn) |
  | `cluster` | one of the 11 FORRT clusters (`data/raw/questions_bank_classes_261112.csv`), `FORRT Lookup` (about FORRT itself: its tools, glossary, pages), or empty (out of scope) |
  | `type` | one of the 10 question types of the bank: Conceptual Questions, Teaching, Resource, How-to, Comparative, False premise, Replication fact, Out of scope, Adversarial, Multilingual |
  | `lang`, `format` | ISO 639-1 code; `Single question`, `Multi-turn` or `Two questions in one turn` |
  | `question` | the turn that is scored; `history` (multi-turn only) lists the earlier turns, which `eval/run.py` sends first in the same chat |
  | `expect` | `answer` or `refuse` (what the bot should do) |
  | `route` | gold label for the router (#43): `open_science`, `forrt`, `both` or `neither` (`neither` exactly when `expect` is `refuse`) |
  | `expected_dois`, `expected_urls` | the reference answer: papers and pages a good answer cites |
  | `source`, `note` | where the question comes from; free text |
  | `term`, `reference_answer`, `rubric` | only on the 25 questions with a rubric: the glossary term, an answer written from its definition, and 3-5 items `{id, type: core or detail, criterion}` that `eval/rubric_judge.py` scores |

  **`expected_dois` and `expected_urls` are drafts too** (12 Nov): the 12 DOIs from `BOT/Questions.docx` were kept; the rest were picked by hand from the bge-m3 search results and a title/full-text search of the production index (`VECTOR_STORE`), so every DOI is an indexed paper; URLs are pages of the FORRT page index (`vector_data/forrt_pages`), only for `forrt`/`both` questions. Translations (`source: translation of …`) share the picks of their English question. The labels of `new51`-`new66` are drafted the same way (`new51` is borderline: `off05`, also on impact factors, is a refusal). Without DOIs: refusals, `qa03` (about the bot itself), `new10` (no indexed paper on assigning a DOI to an article), `new33` (false premise: no such FORRT tool) and `new58` (no indexed paper on no-code data cleaning tools). Meltem and Mohit review them in `eval/questions.xlsx`; the `hit` column of `eval/run.py` uses them.

  **`cluster`, `type` and `route` are drafts** (12 Nov, from the definitions in the bank's Classes sheet): two people should review them, as for E1. Few questions test FORRT routing (3 `forrt`, 6 `both`); `eval/forrt_questions.jsonl` (#43) covers that. No question yet for cluster 5 (computation and analysis) and only one for cluster 9. `test/test_questions.py` checks the structure.
- `eval/refusal_questions.jsonl`: 60 questions the topic check should refuse (`route` `neither`), in the fields of `eval/questions.jsonl` plus `kind`, so that `eval/classify.py --routers` is scored on a set with more refusals. 40 English questions written by `google/gemma-4-31b-it` with `eval/make_refusal_questions.py`, 4 kinds: `general` (6, general knowledge), `academic` (12, academic life outside open science), `decline_task` (12, an open-science topic but a task the bot should not do, such as writing or reviewing the user's text or ruling on the user's case) and `near_miss` (10, logistics forrt.org does not cover, such as a journal's fees or a conference's dates). 20 of them are translated into de, nl, es, it, tr, pt, zh and hi (`source: translation of …`); the translations are not yet checked by native speakers. Questions close to one already in the eval sets were dropped. Some are borderline on purpose, such as `rf28` (whether to collect more data, near optional stopping).
- `eval/retrieval_questions.jsonl`: 474 questions for retrieval only (24 from `data/interim/questions_and_text.csv`, 150 synthetic, 300 translations to nl/de/es).

All result files in `eval/results/` are shown on the page **`/eval`** (answer models, classifiers, embedding models, arena ratings), newest first.

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
| **outcome** | `answered` (from the papers or the FORRT pages), `refused` (the topic check said neither open science nor FORRT), `no_sources` (no passage passed the relevance threshold), `error` (API failure) |
| **expect** | Gold label in `questions.jsonl`: `answer` or `refuse` |
| **Correct** | Share of questions where the outcome matches `expect` |
| **Answered / Refused** | Counts against the gold label (22/27 = 22 of the 27 "answer" questions got an answer) |
| **hit@7** | For questions with `expected_dois`: one of them is in the 7 sources that the LLM saw; for questions with `expected_urls` (all of `eval/forrt_questions.jsonl`): one of them is among the forrt.org pages a FORRT-page answer used |
| **Judge support** | After `eval/judge.py`: mean share of cited sentences that their source passage supports (0-1); "–" when the run was not judged |
| **Citations valid** | Share of answers where every `[n]` in the text points to a source in the list |
| **Rubric coverage** | For questions with a rubric, after `eval/rubric_judge.py`: mean score of the rubric items, 1 (not covered) to 5 (fully), minus 1, divided by 4 (the 1-5 scale of every score, #54; the same value as ResearchQA's 0-4 divided by 4) |
| **Mean s / p95 s** | Mean and 95th-percentile answer time in seconds (target p95 ≤ 15 s) |
| **USD / 1k q** | OpenRouter cost for 1,000 questions (from the token counts) |

### Changing the criteria, the scale or a judge (#54)

Everything people and judges score lives in `config/criteria.json`, read by `just_os/criteria.py`; no code changes for these:

| To change | Edit | Takes effect in |
|---|---|---|
| A criterion's name or definition | `criteria.<key>.label` / `definition` | `/review`, the criteria judge's prompt, reports |
| Which criteria `/review` asks | `forms.review.criteria` (keys of `criteria`) | `/review`, saved review CSVs, `eval/scores.py` |
| The arena's criteria and what they cover | `forms.arena.criteria.<key>` (`label`, `definition`, `maps_to`) | `/arena`, its leaderboard, `eval/scores.py` (`arena_<key>`) |
| The scale and its labels | `scale.min`, `scale.max`, `scale.labels` | `/review`, `/arena`, every judge, `eval/scores.py` |
| A judge's default model | `judges.support.model`, `judges.rubric.model`, `judges.criteria.model` (`--model` overrides one run) | `eval/judge.py`, `eval/rubric_judge.py`, `eval/criteria_judge.py` |
| The rubric levels | `judges.rubric.levels` (one per point of the scale) | `eval/rubric_judge.py`, the expert grading page |
| What the criteria judge scores, and how it asks | `judges.criteria.criteria`, and the prompt file `judges.criteria.prompt` (`config/prompts/criteria_judge.txt`; placeholders `{low}`, `{high}`, `{labels}`, `{criteria}`, `{question}`, `{answer}`, `{sources}`, `{keys}`) | `eval/criteria_judge.py` |
| The review decisions | `decisions` | `/review` |

`test/test_criteria.py` checks that the forms use only defined criteria and that pages and judges follow the file. Scores saved on an earlier scale are not converted by changing the file (see the commits of #56 for how the 0-5 reviews were moved).

### Topic check (`eval/classify.py`)

Two modes, both writing `eval/results/classify_<YYMMDD-HHMM>.csv` (one row per strategy or model and question), shown on `/eval`:

| Mode | What runs | Gold label |
|---|---|---|
| `--routers jev,banded,clef-flash,clef,llm,cosine,none` | the whole topic check (`Qualle.route`), one strategy at a time, as the "Topic check" dropdown offers them | `route`: `open_science`, `forrt`, `both` or `neither`; a question file without `route` (`eval/forrt_questions.jsonl`) counts as `forrt` |
| `--models a,b` | only the LLM classifier (`GENERAL_MODEL`), with each model | from `expect`: `answer` → open science, `refuse` → off topic; with `--intent`, the optional `intent` field (open_science, forrt_lookup, off_topic) |

`--questions` takes several files, comma separated (default `eval/questions.jsonl`).

| Column | Meaning |
|---|---|
| **Accuracy** | Share of questions whose predicted label equals the gold label |
| **False refusals** | In-scope questions (open science, FORRT or both) that the check turned away |
| **False answers** | Off-topic questions that the check let through |
| **Errors** | No label at all (the call failed and nothing could fall back) |
| **Mean s, USD / 1k q** | Time and cost of the topic check alone per question |

A strategy tuned on these questions, such as the thresholds of `cosine`, scores too high on them; check it on questions it was not tuned on (section 3.7).

**Question sets for the topic check.** A strategy with thresholds (`cosine`, `banded`) is tuned on one group of files and reported on the other, and no question is in both:

| File | Questions | How it was built | Gold label | Checked by people | Used for |
|---|---|---|---|---|---|
| `eval/questions.jsonl` | 140 (28 to refuse) | the question bank of Meltem and Mohit, `BOT/Questions.docx`, `BOT/Qualification open science.docx` (off-topic), 13 translations and 25 FORRT glossary items by gpt-4.1-mini | `route`, drafted from the bank's class definitions | 13 of 14 translations; `route` labels not yet | reporting |
| `eval/forrt_questions.jsonl` | 32 | written by hand for the FORRT page router (#43): the organisation, its projects, events, glossary, 2 not in English | none; counted as `forrt` | no (`reviewed: false`) | reporting |
| `eval/forrt_handbook_questions.jsonl` | 10 | written by hand for the Replication Handbook chapters: 1 asks for a FORRT guide, 9 are general how-to questions that the handbook answers (choosing a study, preregistering a replication, email templates…) | none; most route to the papers | no (`reviewed: false`) | reporting (`--route forrt`: right chapter 0/10 before the chapters were indexed, 10/10 after) |
| `eval/refusal_questions.jsonl` | 60, all to refuse | generated by `google/gemma-4-31b-it` with `eval/make_refusal_questions.py` in four kinds, `general`, `academic`, `decline_task` and `near_miss` (section 1), 20 translated | `neither` | no | tuning (`banded`); reporting in 3.8 |
| `eval/forrt_sim_questions.jsonl` | 226: 194 generated, 32 by hand | `google/gemma-4-31b-it` writing from forrt.org pages: one question per menu, project or tool page and news post, 20 open-science questions from glossary and resource pages, 11 off-topic ones; the 32 hand-written ones are those of `eval/forrt_questions.jsonl` and are left out of tuning | from the source page: `forrt`, `open_science_general` or `should_refuse` (11) | no; the labels are noisy (3.6) | tuning (`banded`, `cosine` check in 3.7) |
| `eval/retrieval_questions.jsonl` | 474 | 24 from `data/interim/questions_and_text.csv`, 150 generated from one paper chunk each, 300 translations into nl, de and es | in scope, papers | no | tuning (`banded`) |

A generated question is close to the one page or chunk it was written from, so the tuning files separate papers from FORRT pages much more cleanly than real questions do (3.11).

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

### 3.7 Topic check strategies (12 November 2026, 133 questions, `eval/results/classify_261112-1315.csv`)

`python eval/classify.py --routers clef-flash,clef,jev,llm,cosine,none --questions eval/questions.jsonl,eval/forrt_questions.jsonl`: each strategy of `Qualle.route` alone, scored on the four `route` labels (101 questions of `eval/questions.jsonl` with drafted labels + 32 FORRT questions, which count as `forrt`). Same strategies as the "Topic check" dropdown.

| Topic check | Accuracy | False refusals | False answers | Errors | Mean s | USD / 1k q |
|---|---|---|---|---|---|---|
| **Jev** (`typesafe/jev-1.14`) | **0.85** | 0 | 8 | 0 | 0.4 | 0.02 |
| Cosine (bge-m3, no model call) | 0.82* | 6 | 9 | 0 | **0.1** | **0** |
| LLM classifier (Llama 3.1 8B) | 0.76 | 6 | 12 | 0 | 0.4 | 0.09 |
| Clef-flash (default of `DECISION_ROUTER`) | 0.73 | 1 | 17 | 0 | 0.6 | 0.01 |
| Clef | 0.71 | 0 | 16 | 0 | 0.7 | 0.06 |
| No check (always papers + FORRT pages) | 0.05 | 0 | 28 | 0 | 0 | 0 |

\* The cosine thresholds (`COSINE_PAPER_MIN` 0.62, `COSINE_PAGE_MIN` 0.51) were tuned on these same questions, so 0.82 is optimistic: on the 194 simulated questions of `eval/forrt_sim_questions.jsonl` (not used for tuning) the same thresholds reach 0.53. It never predicts `both`.

Findings:
1. **Jev is the most accurate here** and refuses no in-scope question; the decision models mostly err by letting off-topic questions through (false answers), the LLM classifier and cosine by refusing in-scope ones.
2. Clef-flash, the current default, is the weakest decision model on this set (17 off-topic questions answered). PR #43 found the opposite on its simulated questions (0.65, with the LLM fallback); the labels here are hand-drafted and the sets differ, so test Jev as default with a real eval run before switching.
3. "No check" is not a classifier: it sends everything to the papers and FORRT pages, so it only "fails" on off-topic questions, which then depend on `MIN_RELEVANCE` ("no sources") instead of a refusal.
4. Each answer now also records its step times (topic check, search, re-rank, LLM answer): `timings` in the chat log and arena logs, and columns in `eval/run.py` results, shown per model on `/eval`.

### 3.8 Topic check strategies with more refusals (12 November 2026, 209 questions, `eval/results/classify_261112-1332.csv`)

`python eval/classify.py --routers jev,clef-flash,clef,llm,cosine --questions eval/questions.jsonl,eval/forrt_questions.jsonl,eval/refusal_questions.jsonl`: the strategies of 3.7 on 117 + 32 questions plus the 60 generated refusals of `eval/refusal_questions.jsonl`, so 88 of 209 should be refused (28 of 133 in 3.7). Cosine thresholds unchanged (`COSINE_PAPER_MIN` 0.62, `COSINE_PAGE_MIN` 0.51).

| Topic check | Accuracy | False refusals | False answers | Earlier questions only (149) | Mean s | USD / 1k q |
|---|---|---|---|---|---|---|
| **Jev** | **0.82** | 0 | 25 | 0.87 | 0.2 | 0.02 |
| Cosine | 0.72 | 6 | 44 | 0.84 | **0.1** | **0** |
| LLM classifier (Llama 3.1 8B) | 0.71 | 6 | 41 | 0.78 | 0.4 | 0.08 |
| Clef-flash (default) | 0.67 | 1 | 48 | 0.74 | 0.5 | 0.01 |
| Clef | 0.63 | 1 | 51 | 0.71 | 0.4 | 0.06 |

Generated refusals let through, by kind (translations included):

| Topic check | general (8) | academic (18) | decline_task (18) | near_miss (16) |
|---|---|---|---|---|
| Jev | 0 | 0 | 14 | 4 |
| Cosine | 0 | 16 | 13 | 6 |
| LLM classifier | 0 | 6 | 13 | 9 |
| Clef-flash | 0 | 13 | 9 | 9 |
| Clef | 0 | 9 | 14 | 11 |

Findings:
1. **Jev stays the most accurate** and the only strategy that refuses every academic question outside open science; what it lets through is almost all `decline_task`.
2. **`decline_task` questions pass every strategy**: their topic is open science, and the task (write my preregistration, rule on my consent form) is not what a topic check judges. They need the answer prompt to decline the task, or a check of its own.
3. **Cosine lets academic questions through** (16 of 18): career, teaching and writing questions sit close to the papers about academic life in the index, above `COSINE_PAPER_MIN`. Its thresholds are still the in-sample ones of 3.7.
4. Clef-flash, the current default of `DECISION_ROUTER`, is behind Jev on both sets.

### 3.9 Glossary items with rubrics (12 November 2026, 25 terms, `meta-llama/llama-3.1-8b-instruct`)

**Licence of the glossary items:** the items in `eval/glossary_items_*.jsonl` and the questions with a rubric in `eval/questions.jsonl` (their question, `reference_answer` and `rubric`) are adapted from the [FORRT glossary](https://forrt.org/glossary/english/) ([data](https://github.com/forrtproject/forrt/tree/master/content/glossary)), licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). They were written by language models from the glossary definitions and are shared under the same licence, while the rest of this repository is under Apache 2.0.

A question set that measures whether answers are complete, built the way ResearchQA mines survey sections: from each of 25 FORRT glossary terms (`eval/glossary_terms.txt`), a model writes a question, a reference answer and 3-5 rubric items from the definition only; the indexed DOIs the term cites become `expected_dois`. Three generators wrote items for the same terms; each set was answered with the library and without it (`--no-retrieval`), with the classifier skipped, and judged by `google/gemini-3.8-flash`, a family that generated none of the items, on the answer as the app shows it.

| Generator | Cost | Rubric items | Coverage with library | Coverage without | doi_recall | Judge on own reference answer |
|---|---|---|---|---|---|---|
| **`openai/gpt-4.1-mini`** (in `questions.jsonl`) | $0.017 | 110 | 0.677 | 0.433 | 0.29 | 1.000 |
| `anthropic/claude-sonnet-5.5` | $0.15 | 116 | 0.667 | 0.476 | 0.26 | 0.998 |
| `qwen/qwen3.7-plus`, reasoning off | $0.015 | 110 | 0.686 | 0.426 | 0.35 | 0.996 |

Files: `eval/glossary_items_<generator>.jsonl`, `eval/results/glossary_<generator>_{library,noretrieval}.csv`. On another item's reference answer the judge gives 0.000 for all three sets.

Expert check (`eval/results/grading_*_261112.csv`, one expert, `expert1`): 8 of 75 items and 5 of 50 answers graded so far. The judge gives the expert's score on 20 of 21 rubric items, and answer coverage correlates at 0.71. The expert accepted the questions of gpt-4.1-mini 3/3, Claude Sonnet 5.5 1/2 and Qwen 3.7 Plus 1/3, and marked 29% of Qwen's rubric items as not needed against none for the other two.

Findings:
1. **The library raises rubric coverage by 0.19 to 0.26** (0.43-0.48 → 0.67-0.69), with the items of each of the three generators.
2. gpt-4.1-mini's items went into `questions.jsonl`: all of its graded questions were accepted, it cost least and its coverage matches the other two. Two or three graded items per generator cannot rank the generators.
3. **The classifier refuses many glossary questions.** In the pilot (46 items, 11 Nov), Llama 3.1 8B as classifier refused 18 to 26 of them as not open science across nine runs (`eval/results/glossary_pilot_classify_repeats_261111.csv`), among them researcher degrees of freedom, NHST and statistical power; a full eval run now counts these refusals against Correct.
4. The rubrics and their labels are drafts until more of them are graded; the expert's comments (for example overlapping rubric items) are not applied yet.

### 3.10 Topic check: replication look-ups go to FORRT (12 November 2026, 232 questions, `eval/results/classify_261112-1703.csv`)

"Can you tell me if 10.1177/0956797610383437 has been replicated?" went to the papers with both Jev and Clef-flash, which then said that "it has not been replicated", from papers about replication rates. FORRT's replication database FLoRA and its tools (Replication Atlas, Zotero replication checker) answer such questions, and their pages are in the FORRT page index. The description of the `forrt` route in `just_os/decisions.py` (`ROUTES`) now names "whether a specific study, paper or DOI has been replicated or reproduced". Concept questions ("What is a replication crisis?", "How do I conduct a replication study?") stay `open_science`.

`python eval/classify.py --routers jev,clef-flash --questions eval/questions.jsonl,eval/forrt_questions.jsonl,eval/refusal_questions.jsonl` (now 140 + 32 + 60 questions):

| Topic check | Accuracy (232) | False refusals | False answers | Same 209 questions as 3.8: before → after |
|---|---|---|---|---|
| **Jev** | **0.84** | 0 | 25 | 0.823 → 0.828 |
| Clef-flash (default) | 0.71 | 1 | 47 | 0.670 → 0.675 |

Changes on the 209 questions: Jev now routes `new18`, `new22` (FORRT tool questions) correctly and `new09` (open science) to FORRT; Clef-flash gains 7 and loses 5, mostly between `both` and `forrt`. Not changed: greetings and questions about the bot ("Hello", "Who are you?") no longer reach the topic check (`qualle.small_talk`), so they are not in these numbers.

The decision models cannot be fine-tuned (they are served by OpenRouter's decisions API); what can be tuned is the route descriptions, as here. A classifier trained on our own labelled questions (bge-m3 vectors + logistic regression) would need more labelled questions than the 232 here to be measured fairly, since they are also the test set.

### 3.11 Banded topic check (12 November 2026, 172 questions, `eval/results/classify_261112-1733.csv`)

**Idea:** answer only questions grounded in the library and refuse clear off-topic ones with no model call, and ask a decision model only about the rest. `ROUTER=banded` (`Qualle.banded_route`) takes the bge-m3 cosine of the question to the nearest paper chunk and to the nearest FORRT page description:

| Band | Rule | Decision |
|---|---|---|
| Low | paper below `BAND_PAPER_LOW` (0.586) and page below `BAND_PAGE_LOW` (0.461) | refuse, no model call |
| High | paper at or above `BAND_PAPER_HIGH` (0.701) and page below `BAND_PAGE_HIGH` (0.606) | answer from the papers, no model call |
| Middle | everything else, including every question close to a FORRT page | `BAND_MIDDLE_ROUTER` (Jev) decides |

**Thresholds** (`eval/tune_bands.py`, `eval/results/bands_261112.csv`), set on the tuning files of the table in section 2 (494 paper questions, 163 FORRT page questions, 71 off-topic questions) on the FORRT page index of 3.10, by a strict rule, since answering an off-topic question is the worse error: each high threshold sits 0.01 above the closest off-topic tuning question, and each low threshold refuses at most 2% of the in-scope tuning questions of its source. On the tuning questions, the low band holds 20% of the off-topic ones and the high band none of them.

**Report:** `eval/classify.py --routers banded,jev,cosine,clef-flash --questions eval/questions.jsonl,eval/forrt_questions.jsonl`, 172 questions (28 to refuse), none used for tuning:

| Topic check | Accuracy | False refusals | False answers | Decided with no model call | Mean s | USD / 1k q |
|---|---|---|---|---|---|---|
| **Banded** | **0.90** | 1 | 7 | 33% | 0.2 | 0.01 |
| Jev | **0.90** | 0 | 7 | 0% | 0.2 | 0.02 |
| Cosine | 0.87 | 6 | 9 | 100% | 0.1 | 0 |
| Clef-flash (default of `DECISION_ROUTER`) | 0.78 | 1 | 17 | 0% | 0.4 | 0.01 |

A first rule, `eval/results/classify_261112-1711.csv` (measured on the FORRT page index before 3.10, with `BAND_PAGE_HIGH` 0.575), also answered with no model call when only the page similarity was high, sending the question to the FORRT pages: 0.84, the same 7 false answers, 62% decided with no model call. 9 open-science questions close to a FORRT page (open access, teaching about replication, DOIs for data) went to the FORRT pages, for example "What is open access and what are advantages and disadvantages?", paper 0.682 (below its high threshold of 0.701) and page 0.607 (above 0.575). Page descriptions are short and score lower than paper chunks, so the two similarities are on different scales and a high page similarity does not mean the question is about FORRT. The rule above sends these questions to Jev instead. This change was made after seeing the first report, so the report is no longer fully held out.

Findings:
1. **Banded matches Jev** (154 of 172 right each) within run-to-run variation: they differ on 2 questions, `new45` (an instruction to state a falsehood, refused in the low band) and `new09`, in the middle band, where Jev itself answered differently in the two calls. Both let the same 7 off-topic questions through, 5 in the middle band and 2 (`off05` on journal impact factors, `old33` on ethics approval) in the high band, where they sit as close to the papers as open-science questions do.
2. It decides 33% of questions with no model call (12 in the low band, 44 in the high band), and costs about a third less than Jev alone.
3. **The tuning files cannot calibrate papers against FORRT pages:** each generated question was written from one chunk or page and is very close to it, while real questions are close to both. On the tuning questions, routing by similarity looked right for 83 to 91% of the high band.
4. The strict policy gained nothing over Jev yet: the 5 off-topic questions in the middle band are Jev's. A stricter middle band (refuse unless Jev is confident) is the next step.

Limits: the report has only 28 questions to refuse, since the 60 of `eval/refusal_questions.jsonl` were used for tuning; the `route` labels are drafts; the default topic check is unchanged (`ROUTER` empty, `DECISION_ROUTER_MODEL` clef-flash).

### 3.12 How the default answer model and topic check are chosen (13 November 2026)

With `AUTO_DEFAULTS=true` the bot takes its defaults for chat and arena from the results at every start (`just_os/eval_report.best_defaults`); the `/eval` page explains each section and marks the defaults.

- **Answer model:** Score = (2 × Judge + Rubric coverage) / 3, among the papers runs (every question answered from the same passages) that cover the whole question set without errors. The citation judge counts double: a cited sentence its source does not support misleads more than a missing point, and the judge covers ~160 answers per model where the rubric covers the 25 glossary questions. Until a run has a rubric score, the judge alone decides.
- **Topic check:** the most accurate strategy in the newest topic-check run that compared several on the same questions; a tie goes to the cheaper one (fewer model calls), then the faster one. Banded and Jev tie at 154 of 172 (`classify_261112-1733`); banded makes no model call for a third of the questions.

| Answer model | Judge | Rubric | Score |
|---|---|---|---|
| **google/gemma-3-12b-it** (default) | 0.75 | 0.688 | 0.729 |
| google/gemma-3-27b-it | 0.74 | 0.683 | 0.721 |
| mistralai/mistral-small-3.2-24b-instruct | 0.71 | 0.717 | 0.712 |
| qwen/qwen3-14b | 0.66 | 0.722 | 0.681 |
| openai/gpt-oss-20b | 0.60 | 0.754 | 0.651 |
| openscholar-8b | 0.55 | 0.623 | 0.574 |
| meta-llama/llama-3.1-8b-instruct | 0.51 | 0.594 | 0.538 |

The weighting is to be checked against the human review (`/review`, #8): if people's citation-support scores agree with the judge better than their completeness scores agree with the rubric judge, 2:1 stands.

### 3.13 Topic map of the index (13 November 2026, `eval/results/topic_map_261113.{html,md,csv}`)

**What it is:** a map of every chunk in `vs_latest_bge-m3` (1,354 papers, 146,899 chunks), built from the index vectors with no LLM (`eval/topic_map/`): UMAP + HDBSCAN find 292 topics, c-TF-IDF names them. Each of the 93 FORRT sub-cluster names (the folders of the cluster PDFs) is then compared with the papers: the similarity of its 10th-closest paper gives a status, blind < 0.56, thin < 0.59, covered < 0.63, strong otherwise. The name alone is the probe, so a short name such as "Equity" can score low although papers cover it in other words: the status says where to look, not what is missing. Compared with the 513-paper index before the cluster PDFs.

Findings:
1. **Blind spots went from 14 to 7** of 93 sub-clusters, strong ones from 24 to 49. Still blind: Equity, Public and Private Partnerships, Religion and culture, Sexuality, Feminist Thought, Inclusion (all but one in cluster 9) and Rights retention strategies.
2. **16% of chunks are reference lists or near-empty** (22,860): 22% of the JUST-OS chunks, 8% of the cluster chunks (GROBID drops reference lists, marker does not). On the 66 answerable questions of the earlier eval set they took 0.9 of the top 20 search results on average, so they rarely reach an answer.
3. **6 JUST-OS papers hold another work's text** (1,741 chunks), for example "Course on Open Science 101" holds spine-surgery abstracts: the DOI in the FORRT sheet points to another work. 7 cluster papers have a wrong title (a licence line or page header) and 29 show their file name as title. Lists: `eval/topic_map/wrong_files.json`, `wrong_titles.json`.
4. **One document can fill a topic:** 61 topics come mostly from one paper; Haklay 2018 (2,096 chunks), the SAGE Handbook of Qualitative Research and Reproducible Research with R and RStudio are the largest.
5. **Similarity separates trivia, not near-topic questions** (133 single-turn questions of `eval/questions.jsonl`): at 0.55 on the closest paper chunk or FORRT page, every answerable question stays and 36% of the 28 to refuse fall below; career, grant and SPSS questions score 0.56 to 0.73, like open-science ones. This agrees with the banded topic check (3.11).

Limits: the statuses rest on one probe per sub-cluster and thresholds set by eye on this index; the wrong files and titles were confirmed by hand from the lowest title-to-text similarities only.

### 3.14 FORRT pages next to the papers (13 November 2026, 242 questions, `meta-llama/llama-3.1-8b-instruct`)

**Problem:** the topic check sends general questions to the papers, so a forrt.org page that answers them is never read: 9 of the 10 Replication Handbook questions (`eval/forrt_handbook_questions.jsonl`, #53) and the 6 questions labelled `both` (clef-flash never picks `both`; 4 are "has effect X been replicated?", which FLoRA answers) went to the papers only. Section 3.11 found that similarity alone cannot decide papers vs FORRT pages, so `FORRT_IN_PAPERS` does not decide: a papers answer can also read the pages that clearly match (architecture.md, `forrt_pages.py`).

**Threshold** (`FORRT_IN_PAPERS_MIN_SCORE` 0.60), set on the tuning files only (the 194 generated questions of `eval/forrt_sim_questions.jsonl` and the 474 of `eval/retrieval_questions.jsonl`): at 0.60 the strict selector adds a page to 74-85% of the FORRT questions and to 7% of the paper questions; at 0.55 to 23% of the paper questions; above 0.62 it loses FORRT questions with little gain.

**Report:** `eval/run.py` on the four report sets with `FORRT_IN_PAPERS` false and true, run at the same time (default topic check clef-flash, Llama 3.1 8B on Groq; this run without the re-ranker and with bge-m3 through OpenRouter, the same for both). Added pages judged by `openai/gpt-oss-120b`: does the page help answer the question (yes / partly / no)?

| Set | Measure | Off | On |
|---|---|---|---|
| `forrt_handbook_questions` (10) | expected chapter among the answer's sources | 1/10 | **9/10** |
| `forrt_questions` (32) | expected page among the answer's sources | 23/32 | 25/32 |
| `questions` (140) | correct (answered / refused as expected) | 0.89 | 0.87 |
| | citation support (`eval/judge.py`) | 0.60 | 0.61 |
| | rubric coverage (`eval/rubric_judge.py`, 25) | 0.68 | 0.68 |
| | answers with a page added | 0 | 23 |
| | mean s | 3.1 | 3.2 |
| `refusal_questions` (60) | refused | 0.53 | 0.53 |
| all | added pages judged yes / partly / no | – | 32 / 24 / 1 (57 pages, 41 cited) |

Findings:
1. **The handbook and FORRT pages reach general questions** (1/10 → 9/10) and the answers on the 140 questions keep their quality on average; refusals do not change (the topic check decides them before this step).
2. **On the 23 answers that got a page, citation support fell from 0.59 to 0.53:** few answers and a noisy judge, but plausibly pages rated "partly" (24 of 57) cited for claims they only partly back. On by default for the handbook and FLoRA gains; worth a hand check of these answers, and `FORRT_IN_PAPERS_MIN_SCORE` can be raised if it holds.
3. Time: +0.1 s on the 140 questions (most add no page and make no decision call); +3 s on the handbook questions (long chapters read live). In production the page search runs while the re-ranker does, which hides part of it. 2 of 242 questions hit `FORRT_IN_PAPERS_TIMEOUT` (10 s) and were answered from the papers alone.

### 3.15 People against the judges (13 November 2026, 20 questions, `data/scores/scores_human_review_261113.jsonl`)

First comparison of people and automated scorers on the same answers (#54): the run `eval/results/human_review_261113.csv` (20 English questions, `eval/human_review_questions.jsonl`) and the reviews of Meltem Aksoy and Mohit Garg on `/review` during the team test, all on 1-5. `python eval/scores.py eval/results/human_review_261113.csv`.

| Criterion | People against | n answers | Agreement | People mean (0-1) | Scorer mean (0-1) |
|---|---|---|---|---|---|
| decision | gold (outcome against `expect`) | 20 | 0.90 same decision | – | – |
| citation support | support judge | 18 | 0.18 Spearman | 0.63 | 0.64 |
| citation support | citations valid | 13 | – (always 1) | 0.65 | 1.00 |
| source relevance | hit@7 | 15 | 0.46 Spearman | 0.70 | 0.87 |
| correctness | criteria judge (gemini-3.8-flash) | 18 | 0.61 Spearman | 0.69 | 0.72 |
| completeness | criteria judge | 18 | 0.29 Spearman | 0.65 | 0.78 |
| source relevance | criteria judge | 18 | 0.20 Spearman | 0.61 | 0.74 |
| clarity | criteria judge | 18 | 0.17 Spearman | 0.66 | 0.81 |

| Criterion | Weighted kappa, Meltem / Mohit (14 answers) | Exact | Within 1 |
|---|---|---|---|
| correctness | 0.35 | 0.64 | 0.79 |
| citation support | 0.48 | 0.50 | 0.93 |
| source relevance | 0.37 | 0.36 | 0.64 |
| completeness | 0.45 | 0.43 | 0.86 |
| clarity | 0.09 | 0.14 | 0.79 |

Findings, on few answers:
1. **People and the gold labels agree on answering or refusing** in 90% of answers.
2. **The support judge's mean matches people's (0.64 and 0.63), but it ranks answers differently** (Spearman 0.18): the judge is not yet a reliable stand-in for people on single answers.
3. **The two reviewers agree only moderately** (kappa 0.35-0.48) and barely on clarity (0.09), and source relevance is within 1 point on only 9 of 14 answers: the criteria need sharper definitions or examples before people's scores can check the judges.
4. **The criteria judge (`eval/criteria_judge.py`, USD 0.07 for the 18 answers) follows people on correctness** (Spearman 0.61) but hardly on completeness, source relevance and clarity (0.17-0.29), where it also scores higher than people (by 0.13-0.15 on 0-1). Its ranking on those three is no better than the reviewers agree with each other, so the definitions are the first thing to sharpen. The run was not rubric-judged (3 of the 20 questions have a rubric).

