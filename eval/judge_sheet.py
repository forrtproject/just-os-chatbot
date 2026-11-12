"""A judged eval run as a Markdown sheet for checking the LLM judge by hand (E2, #8).

    python eval/judge_sheet.py eval/results/run_X.csv [--out docs/judge-check.md]

For every answer that eval/judge.py scored: the question, the answer, each passage the answer
cites (numbered from 0, as the answer model saw them) and the judge's judge_support. The checker
writes their own share of supported cited sentences next to it; the table at the top collects them.
"""

import argparse
import csv
import json
import re
from pathlib import Path

HEAD = """# LLM judge: hand check (E2, #8)

Run: `{run}` ({n} judged answers; judge `eval/judge.py`, default `openai/gpt-oss-20b`).

**What the judge did.** For each answer it read the passages the answer model saw and returned the share of the
answer's cited sentences (those with `[n]`) that their passage supports, from 0 to 1.

**How to check.** For each answer below: read every sentence with a citation, open the cited passage under it and
decide whether the passage supports the sentence. Write the share you find (supported / cited sentences) in
**Your score**, and a note when you disagree. Then copy your scores into the table. About 20 answers are enough to
tell whether the judge can be trusted; start at the top, where the judge gave the lowest scores.

| id | Judge | Your score | Note |
|---|---|---|---|
{table}
"""


def cited(answer: str) -> list:
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})


def section(row: dict) -> str:
    passages = json.loads(row.get("passages") or "[]")
    lines = [f"## {row['id']}", "", f"**Question:** {' '.join(row['question'].split())}", "",  # heading = anchor of the table link
             f"**Judge:** {row['judge_support']} &nbsp; **Your score:** ____ &nbsp; **Note:**", "",
             "**Answer**", "", "\n".join(f"> {line}" if line else ">" for line in row["answer"].strip().splitlines()), ""]
    for n in cited(row["answer"]):
        text = passages[n] if n < len(passages) else "(no passage with this number: the citation is invalid)"
        lines += [f"<details><summary>Passage [{n}]</summary>", "", " ".join(text.split()), "", "</details>", ""]
    return "\n".join(lines)


def sheet(run_csv: Path) -> str:
    rows = [r for r in csv.DictReader(open(run_csv, encoding="utf-8")) if r.get("judge_support") not in (None, "")]
    rows.sort(key=lambda r: float(r["judge_support"]))  # the doubtful ones first
    table = "\n".join(f"| [{r['id']}](#{r['id'].lower()}) | {r['judge_support']} | | |" for r in rows)
    return HEAD.format(run=run_csv.as_posix(), n=len(rows), table=table) + "\n" + "\n\n".join(section(r) for r in rows) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv", type=Path)
    parser.add_argument("--out", type=Path, default=Path("docs/judge-check.md"))
    args = parser.parse_args()
    args.out.write_text(sheet(args.run_csv), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
