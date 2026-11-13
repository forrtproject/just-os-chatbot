"""An eval run as a Markdown sheet for checking the LLM judge by hand (E2, #8).

    python eval/judge_sheet.py eval/results/human_review_X.csv [--questions eval/human_review_questions.jsonl]
        [--out docs/judge-check.md]

Every question of the run: what was asked, what the bot should have done and did, the answer, and each
source the answer cites (title, DOI or URL, the passage the answer model read), with the judge's
judge_support where eval/judge.py scored it. Refusals and "no sources" have no answer to judge: the
checker only decides whether that was the right call. The table at the top collects the checker's scores.
"""

import argparse
import csv
import json
import re
from pathlib import Path

HEAD = """# LLM judge: hand check (E2, #8)

Run: `{run}`: {n} questions, {judged} answers scored by the LLM judge (`eval/judge.py`, default `openai/gpt-oss-20b`).
The same questions can be scored without the judge's numbers on the review page (`/review`, see `docs/evaluation.md`).

**What the judge did.** For each answer it read the passages or forrt.org pages the answer model saw and returned
the share of the answer's cited sentences (those with `[n]`) that their source supports, from 0 to 1.

**How to check.** For each question below: was answering (or refusing) the right call? Then read every sentence with
a citation, open the cited source under it and decide whether it supports the sentence. Write the share you find
(supported / cited sentences) in **Your score**, and a note when you disagree with the judge.

| id | Category | Bot did | Judge | Your score | Note |
|---|---|---|---|---|---|
{table}
"""


def cited(answer: str) -> list:
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})


def source_items(row: dict) -> list:
    """The sources of one run row, numbered as the answer cites them: {n, title, doi, url, passage, cited}.
    FORRT-page answers number their pages from 1, paper answers their passages from 0."""
    passages = json.loads(row.get("passages") or "[]")
    sources = json.loads(row.get("sources") or "[]") or [{"n": i} for i in range(len(passages))]
    start = 1 if row.get("answered_from") == "forrt pages" else 0
    used = set(cited(row.get("answer") or ""))
    return [{"n": s["n"], "title": s.get("title", ""), "doi": s.get("doi", ""), "url": s.get("url", ""),
             "passage": passages[s["n"] - start] if 0 <= s["n"] - start < len(passages) else "",
             "cited": s["n"] in used} for s in sources]


def bot_did(row: dict) -> str:
    return {"answered": f"answered from the {row.get('answered_from') or 'papers'}", "refused": "refused",
            "no_sources": "said it found no sources", "error": "error", "small_talk": "introduced itself"}.get(
        row["outcome"], row["outcome"])


def section(row: dict, category: str) -> str:
    lines = [f"## {row['id']}", "",  # the heading is the anchor of the table link
             f"**Question:** {' '.join(row['question'].split())}", "",
             f"**Category:** {category} &nbsp; **The bot should:** {row['expect']} &nbsp; **The bot:** {bot_did(row)}", "",
             f"**Judge:** {row.get('judge_support') or '–'} &nbsp; **Your score:** ____ &nbsp; **Note:**", ""]
    answer = (row.get("answer") or "").strip()
    lines += ["**Answer**", "", "\n".join(f"> {line}" if line else ">" for line in answer.splitlines()) or "> (no answer)", ""]
    items = source_items(row)
    for s in items:
        if s["cited"]:
            where = f"https://doi.org/{s['doi']}" if s["doi"] else s["url"]
            lines += [f"<details><summary>Source [{s['n']}]: {s['title'] or 'untitled'} ({where or 'no link'})</summary>", "",
                      " ".join(s["passage"].split()) or "(no passage saved)", "", "</details>", ""]
    for n in sorted(set(cited(answer)) - {s["n"] for s in items}):
        lines += [f"Source [{n}]: no source with this number (the citation is invalid)", ""]
    return "\n".join(lines)


def sheet(run_csv: Path, categories: dict = None) -> str:
    categories = categories or {}
    rows = list(csv.DictReader(open(run_csv, encoding="utf-8")))
    # judged answers first, lowest score first (the doubtful ones), then the rest in run order
    rows.sort(key=lambda r: (r.get("judge_support") in (None, ""), float(r.get("judge_support") or 0)))
    table = "\n".join(f"| [{r['id']}](#{r['id'].lower()}) | {categories.get(r['id'], r.get('route') or '')} | {bot_did(r)} "
                      f"| {r.get('judge_support') or '–'} | | |" for r in rows)
    judged = sum(r.get("judge_support") not in (None, "") for r in rows)
    return (HEAD.format(run=run_csv.as_posix(), n=len(rows), judged=judged, table=table) + "\n"
            + "\n\n".join(section(r, categories.get(r["id"], r.get("route") or "")) for r in rows) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_csv", type=Path)
    parser.add_argument("--questions", help="question file with a category per id (eval/human_review_questions.jsonl)")
    parser.add_argument("--out", type=Path, default=Path("docs/judge-check.md"))
    args = parser.parse_args()
    categories = {}
    if args.questions:
        categories = {q["id"]: q.get("category", "") for q in map(json.loads, open(args.questions, encoding="utf-8"))}
    args.out.write_text(sheet(args.run_csv, categories), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
