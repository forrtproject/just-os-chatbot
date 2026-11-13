# Team test session through the Cloudflare tunnel (#8, #12)

Everyone uses the same bot on the host machine, so every chat turn, arena round, rating and review lands in
the host's `data/` folders and goes into Git from there.

## What is saved where

| What | File on the host | Written when |
|---|---|---|
| Every chat answer (question, answer, sources, outcome, languages, times) | `data/chats/chats.jsonl` | the answer is complete |
| Good/Bad feedback on a chat answer | `data/chats/feedback.jsonl` | the tester presses Good/Bad |
| Every arena question with all model answers | `data/arena/rounds.jsonl` | all answers are complete |
| Arena ratings (1-5 per answer) | `data/arena/ratings.jsonl` (and Redis, for the leaderboard) | the tester submits the ratings |
| Answer reviews (`/review`) | `data/reviews/review_<name>_<time>.csv`, one file per save | the reviewer presses **Save to the team** |

All five are writable mounts in `compose.yaml` and are tracked in Git during the test phase (`.gitignore`).
Writes from parallel requests are serialised, so two answers finishing at once cannot mix their lines.

## Before the session

1. `docker compose up -d` (after a pull: `docker compose up -d --build web`, so the new mounts and pages are active).
2. Check `.env`: `ARENA_ENABLED=true`. OpenScholar: start it with the "OpenScholar server" workflow and set
   `OPENSCHOLAR_BASE_URL` to its URL, or leave the line empty so the arena does not offer it (a stopped server
   gives an error card).
3. **Do not run evals during the session** (`eval/run_batches.py`, `scorecard.py`): they use most of Docker's
   memory, and a worker killed for memory loses the answers it was writing.
4. Start the tunnel and share the link: `cloudflared tunnel --url http://localhost:8000`.
5. Share `eval/arena_test_questions.xlsx` (100 questions, each with 3 suggested models) and, for reviewers, the
   `/review` page.

## During the session

- Testers should wait for an answer to finish before closing the tab: a turn is written when it is complete.
- Two-part questions go to the **Chat** page (the arena keeps no history): ask the question, then the follow-up.

## After the session

```
git add data/chats data/arena data/reviews
git commit -m "Test session <date>: chats, arena rounds and ratings, reviews"
git push
```

The CSVs from `/review` have one row per question: reviewer, item_id, category, expected, bot_did, question,
decision, correctness, citation_support, source_relevance, completeness, clarity (1-5 or n/a; files saved before #54 use 0-5), note, saved_at.
Compare them with the LLM judge by `item_id` (`eval/results/human_review_<date>.csv`, column `judge_support`).
