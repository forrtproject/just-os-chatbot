"""Excel copy of eval/questions.jsonl for the reviewers (Meltem, Mohit).

One row per question: the expected DOIs/URLs (with titles from the index), the DOIs the
bot retrieved and cited in an eval run, which of them match, and empty columns to judge.

    python eval/export_questions.py [eval/results/run_....csv]
Default run: the newest eval/results/run_*.csv. Output: eval/questions.xlsx
Needs pandas + openpyxl (run on the host; openpyxl is not in the Docker image).
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.settings import get_config  # noqa: E402
from just_os.references import plain_metadata  # noqa: E402

OUTPUT = ROOT / "eval/questions.xlsx"
REVIEW = ["expected_ok (yes/partly/no)", "bot_ok (yes/partly/no)", "dois_to_add", "comments"]


def titles():
    """DOI -> title of every document in the production index."""
    store = ROOT / get_config()["VECTOR_STORE"] / "docstore.json"
    out = {}
    for node in json.load(open(store, encoding="utf-8"))["docstore/data"].values():
        meta = plain_metadata(node["__data__"]["metadata"])
        if meta.get("doi"):
            out[meta["doi"].lower()] = meta.get("title") or ""
    return out


def bot_dois(row):
    """(retrieved, cited): cited = the sources the answer points to with [n]."""
    retrieved = str(row["retrieved_dois"]) if pd.notna(row["retrieved_dois"]) else ""
    ranked = retrieved.split(" ")  # one slot per source; "" = source without a DOI
    refs = {int(n) for n in re.findall(r"\[(\d+)\]", str(row["answer"]))}
    cited = [ranked[n] for n in sorted(refs) if n < len(ranked) and ranked[n]]
    return list(dict.fromkeys(d for d in ranked if d)), list(dict.fromkeys(cited))


def main():
    runs = sorted((ROOT / "eval/results").glob("run_*.csv"))
    run_path = Path(sys.argv[1]) if len(sys.argv) > 1 else runs[-1]
    run = pd.read_csv(run_path).set_index("id")
    title = titles()
    link = lambda d: f"https://doi.org/{d} — {title.get(d, 'NOT IN INDEX')}"  # noqa: E731

    rows = []
    for line in open(ROOT / "eval/questions.jsonl", encoding="utf-8"):
        q = json.loads(line)
        expected = [d.lower() for d in q["expected_dois"]]
        retrieved, cited = bot_dois(run.loc[q["id"]]) if q["id"] in run.index else ([], [])
        rows.append({
            "id": q["id"], "cluster": q["cluster"], "type": q["type"], "lang": q["lang"],
            "route": q["route"], "expect": q["expect"], "question": q["question"],
            # one DOI/URL per cell so each is a one-click link
            **{f"expected_{i + 1}": link(d) for i, d in enumerate(expected)},
            **{f"expected_url_{i + 1}": u for i, u in enumerate(q["expected_urls"])},
            "bot_outcome": run.loc[q["id"], "outcome"] if q["id"] in run.index else "not in run",
            **{f"cited_{i + 1}": link(d) for i, d in enumerate(cited)},
            "bot_retrieved_dois": "\n".join(link(d) for d in retrieved),
            "cited_match": "\n".join(f"https://doi.org/{d}" for d in cited if d in expected),
            "retrieved_match": "\n".join(f"https://doi.org/{d}" for d in retrieved if d in expected),
            **{c: "" for c in REVIEW},
        })
    df = pd.DataFrame(rows)
    # pandas orders columns by first appearance; put the numbered ones in their blocks
    block = lambda p: sorted((c for c in df.columns if re.fullmatch(p + r"\d+", c)), key=lambda c: int(c.rsplit("_", 1)[1]))  # noqa: E731
    head = ["id", "cluster", "type", "lang", "route", "expect", "question"]
    df = df[head + block("expected_") + block("expected_url_") + ["bot_outcome"] + block("cited_")
            + ["bot_retrieved_dois", "cited_match", "retrieved_match"] + REVIEW]
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="questions", index=False)
        sheet = xl.sheets["questions"]
        sheet.freeze_panes = "H2"
        sheet.auto_filter.ref = sheet.dimensions
        widths = {"question": 50, "bot_retrieved_dois": 60}
        for i, col in enumerate(df.columns):
            letter = sheet.cell(row=1, column=i + 1).column_letter
            sheet.column_dimensions[letter].width = widths.get(col, 45 if col[-1].isdigit() else 18)
            if col[-1].isdigit():
                for cell in sheet[letter][1:]:
                    if isinstance(cell.value, str) and cell.value.startswith("https://"):
                        cell.hyperlink, cell.style = cell.value.split(" — ")[0], "Hyperlink"
        pd.DataFrame({"note": [
            f"Bot DOIs from {run_path.name}. Questions not in that run show 'not in run'.",
            "expected_N: picked from the production index; expected_url_N: FORRT page index. Click a cell to open it.",
            "cited_N: sources the answer cites with [n]. *_match: bot DOIs that are also expected.",
            "Judge in the last four columns.",
        ]}).to_excel(xl, sheet_name="readme", index=False)
    print(f"{len(df)} questions -> {OUTPUT} (bot DOIs from {run_path.name})")


if __name__ == "__main__":
    main()
