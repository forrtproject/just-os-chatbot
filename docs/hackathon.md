# JUST-OS hackathon — 11–13 November 2026

JUST-OS answers open-science questions with citations to the FORRT resource library. In three days we make the answers **measurably** better and choose a model that can be hosted sustainably.

## 1. Setup (target: 30 minutes)

Follow [README.md → Installation](../README.md#installation). You get the OpenRouter key and the index link from the project lead (one-to-one, never in chat or issues).

Check that it works:
- `docker compose exec web pytest test/` → all tests pass (no index or network needed).
- http://localhost:8000 → ask "What is preregistration?" → an answer with numbered sources.
- http://localhost:8000/arena → pick models, one answer card per model, rate each 1-5.

Windows: use Docker Desktop with WSL2. If the build fails with `exit code 127`, your Git changed the line ends of `bin/*`: run `git add --renormalize .` or clone again (`.gitattributes` keeps them LF).

## 2. Rules

1. Make your branch from `main` (`feat/<topic>` or `fix/<topic>`) and open the PR to `dev`. The project lead reviews it there and merges `dev` into `main`. Do not push to `main` or `dev` directly.
2. One problem per PR, under ~300 changed lines, link the issue.
3. A bug fix has a test that fails before the fix. `pytest` passes before merge (GitHub Actions runs it on each PR).
4. A change to prompts, models, retrieval or chunking has the eval table in the PR (`eval/run.py` before and after, `eval/compare.py`).
5. Do not change the `/chat` request or response fields: the forrt.org widget uses them.
6. Keys only in `.env`. Never paste keys in issues, chat or screenshots. The hackathon key is switched off on 13 November in the evening.
7. Do not commit PDFs, indexes or generated data (`data/` is git-ignored). `data/NWO JUST-OS/` has private files (grants, e-mails): never put them in Git or in the index.
8. Style: `ruff check --select E,F --ignore E501 just_os test eval` passes.
9. Update `docs/` in the same PR when you change behaviour, settings or files (see [architecture.md](architecture.md)).

## 3. Tracks

Issues with files, approach and "done when": [issues.md](issues.md) (also on GitHub). How the code fits together: [architecture.md](architecture.md).

| Track | Goal by Friday 14:00 | Issues |
|---|---|---|
| **Evaluation** | 40–60 reviewed questions with expected sources (first: the other tracks need them); LLM judge; classifier comparison; one command per configuration | E1–E4 (#7, #8, #9, #32) |
| **Models** | Eval of 4–6 models; arena ratings and protocol; faster answers; memory methods; FORRT lookup mode, with and without a router | M1, M3–M8 (#10, #12–#15, #34, #35) |
| **Retrieval & quality** | Multilingual re-ranker; embedding model for production; adaptive top-k; hallucination check | N3–N5, Q1 (#21, #22, #33, #23) |
| **Coverage** | Metadata for the cluster PDFs; HTML route for web resources; ingestion for curators; optional: faster conversion and chunking | C2–C5 (#17, #18, #25, #36) |

What we must decide by Friday, and which issues feed each decision: [#31](https://github.com/forrtproject/just-os-chatbot/issues/31).

Done before the hackathon (closed): references R1–R5, M2 prompt comparison, C1 coverage audit, N1 hybrid search, N2 source variety, Q2 metadata fix, O2 CI, O4 answer cache. Most open issues already have code; the issue comments on GitHub say what is left.

## 4. Tools you will use

| Tool | Command | Output |
|---|---|---|
| Eval run | `docker compose exec -e OMP_NUM_THREADS=8 web python eval/run.py --model <id> [--limit 5]` | `eval/results/run_<date>_<model>.csv` |
| Eval table | `docker compose exec web python eval/compare.py` | Markdown table of all runs |
| Embedding comparison | `python eval/compare_embeddings.py` (needs a GPU or the API; see the script) | `eval/results/embeddings_<date>.csv` |
| Arena | http://localhost:8000/arena | ratings at `/arena/leaderboard`, raw data at `/arena/ratings` and in `data/arena/ratings.jsonl` (the server commits it at each stand-up) |
| Change a model | `CITATION_MODEL=...` in `.env`, then `docker compose up -d web` | — |
| OpenScholar (self-hosted) | `OPENSCHOLAR_BASE_URL` + `OPENSCHOLAR_API_KEY` in `.env`, then `--model openscholar-8b` | — |

Costs: one eval run of 44 questions costs less than 0.10 USD for most models. Look at the OpenRouter balance each morning.

## 5. Schedule

| | Wednesday 11 | Thursday 12 | Friday 13 |
|---|---|---|---|
| 09:00 | Kick-off: problem, bugs, rules, tracks | Stand-up | Stand-up |
| 09:45 | Setup (this file) | Track work | Finish, tests, docs |
| 11:00 | Track work | | 12:30 feature freeze, merge round 2 |
| 13:00 | Lunch | Lunch | Lunch, final eval |
| 13:45 | Track work | 13:45 merge round 1, full eval | Scorecard, model table, coverage chart |
| 17:30 | Stand-up: one result per track | Stand-up: what is in the demo | 16:30 demo, 17:15 retro |

## 6. Demo (Friday 16:30, local)

1. Eval scorecard before and after (`eval/compare.py`).
2. A live answer with correct citation numbers, years, `https://doi.org/` links, one reference per paper, passage tooltip.
3. Off-topic question → refusal; model outage → an error message, not a refusal.
4. Model comparison table and arena leaderboard (`/arena/leaderboard`).
5. Change `CITATION_MODEL` in `.env`, restart, ask again.
6. Coverage chart.

## 7. Background

- Plan, decisions, bug status: [project-plan.md](project-plan.md).
- Data, indexes, which PDFs are embedded: [data.md](data.md).
- Metrics and results so far: [evaluation.md](evaluation.md).
- Code map and caching: [architecture.md](architecture.md).
