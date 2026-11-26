# Citation check calibration: `run_261126_full_gemma4`

130 answers, 2042 cited sentence-source pairs, 759 cited sources; the judge (openai/gpt-oss-20b) finds 74 sources unsupported by every sentence citing them. Re-ranker `BAAI/bge-reranker-v2-m3` on CPU: median 9.2 s, p95 15.3 s per answer.

| VERIFY_MIN_SCORE | Sources flagged | Of them unsupported | Unsupported caught | Flags right |
|---|---|---|---|---|
| 0.01 | 13 | 7 | 9% | 54% |
| 0.02 | 19 | 10 | 14% | 53% |
| 0.05 | 32 | 12 | 16% | 38% |
| 0.1 | 41 | 13 | 18% | 32% |
| 0.2 | 56 | 19 | 26% | 34% |
| 0.3 | 74 | 20 | 27% | 27% |
| 0.5 | 99 | 28 | 38% | 28% |
