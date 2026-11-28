"""Calibrate the hallucination check (#23, VERIFY_CITATIONS) on a run with whole passages.

    docker compose run --rm -T --no-deps -v ./eval:/app/eval web python eval/citation_check.py eval/results/<run>.csv

The run must keep whole answers and chunks (`eval/run.py` without `--truncate`; numbered from 0 = papers route).
Every (cited sentence, cited chunk) pair, split as DocumentRetriever.unsupported_citations splits it, gets
  - the re-ranker score the app would compute (RERANK_MODEL), and the seconds that took per answer;
  - a label from the citation judge (gpt-oss-20b, config/criteria.json): does the chunk support the sentence?
The app flags a source when its BEST pair score is below VERIFY_MIN_SCORE, so it is measured per (answer, source):
for each threshold, how many sources the judge finds unsupported are flagged (caught), how many flags are right,
and how many answers would show a flag. Writes eval/results/citation_check_<run>.md and a .csv of the pairs.
"""

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402
from just_os import criteria  # noqa: E402
from just_os.qualle import OpenAIClientManager, QueryProcessor  # noqa: E402

THRESHOLDS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
PROMPT = """Does the source support the sentence? Supported means the source states what the sentence claims, or
the claim follows directly from it; a sentence that adds facts, numbers or conclusions the source does not have is
not supported.

Source:
{source}

Sentence:
{sentence}

Return a JSON object with a single boolean entry "supported"."""


def pairs_of(answer, passages):
    """(source number, sentence without citation marks, passage) for every citation, like unsupported_citations."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", answer):
        claim = re.sub(r"\[\d+\]", "", sentence).strip()
        for ref in sorted({int(m) for m in re.findall(r"\[(\d+)\]", sentence)}):
            if claim and ref < len(passages):
                out.append((ref, claim, passages[ref]))
    return out


def table(sources):
    """(unsupported sources, rows per threshold) from sources = [(best score, judge: some citing sentence supported)]."""
    bad = sum(1 for _, ok in sources if not ok)
    rows = []
    for t in THRESHOLDS:
        flagged = [ok for s, ok in sources if s < t]
        right = sum(1 for ok in flagged if not ok)
        rows.append((t, len(flagged), right, right / max(bad, 1), right / max(len(flagged), 1)))
    return bad, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    from sentence_transformers import CrossEncoder

    config = get_config()
    judge_config = {**config, "GENERAL_MODEL": criteria.JUDGES["support"]["model"], "TEMPERATURE_GENERAL": 0.0}
    judge = QueryProcessor(OpenAIClientManager(judge_config), judge_config, chat_manager=None)
    reranker = CrossEncoder(config["RERANK_MODEL"])

    rows = [r for r in csv.DictReader(open(args.run_csv, encoding="utf-8"))
            if r["outcome"] == "answered" and r.get("answered_from") == "papers"][: args.limit]
    records, seconds = [], []
    for row in rows:
        pairs = pairs_of(row["answer"], json.loads(row["passages"] or "[]"))
        if not pairs:
            continue
        start = time.time()
        scores = reranker.predict([(claim, passage) for _, claim, passage in pairs])
        seconds.append(time.time() - start)
        with ThreadPoolExecutor(8) as pool:
            labels = list(pool.map(lambda p: judge._structured_output(
                PROMPT.format(source=p[2], sentence=p[1]), "supported", "boolean"), pairs))
        records += [{"id": row["id"], "source": ref, "score": round(float(s), 4), "supported": label, "sentence": claim}
                    for (ref, claim, _), s, label in zip(pairs, scores, labels)]
        print(f"{row['id']:6} {len(pairs)} pairs, {seconds[-1]:.1f} s", flush=True)

    # per (answer, source): the app keeps the best pair score; the judge's view: any citing sentence supported
    best = {}
    for r in records:
        if r["supported"] is None:
            continue
        score, ok = best.get((r["id"], r["source"]), (-1e9, False))
        best[(r["id"], r["source"])] = (max(score, r["score"]), ok or bool(r["supported"]))
    bad, rows_t = table(list(best.values()))
    stem = Path(args.run_csv).stem
    out = Path("eval/results") / f"citation_check_{stem}"
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "source", "score", "supported", "sentence"])
        writer.writeheader()
        writer.writerows(records)
    seconds.sort()
    median = seconds[len(seconds) // 2] if seconds else 0
    p95 = seconds[int(0.95 * (len(seconds) - 1))] if seconds else 0
    lines = [f"# Citation check calibration: `{stem}`", "",
             f"{len(seconds)} answers, {len(records)} cited sentence-source pairs, {len(best)} cited sources; "
             f"the judge ({criteria.JUDGES['support']['model']}) finds {bad} sources unsupported by every sentence "
             f"citing them. Re-ranker `{config['RERANK_MODEL']}` on CPU: median {median:.1f} s, p95 {p95:.1f} s "
             "per answer.", "",
             "| VERIFY_MIN_SCORE | Sources flagged | Of them unsupported | Unsupported caught | Flags right |",
             "|---|---|---|---|---|"]
    lines += [f"| {t} | {n} | {r} | {c:.0%} | {p:.0%} |" for t, n, r, c, p in rows_t]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
