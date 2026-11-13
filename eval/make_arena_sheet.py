"""100 test questions for a team arena session (M3, #12), as CSV and Excel.

    python eval/make_arena_sheet.py [--seed 13] [--out eval/arena_test_questions]

A random mix from the eval sets plus written two-part and "both" questions: open science (35, five
of them not in English), FORRT website (20), open science and FORRT together (10), science-related
questions the bot should refuse (20), two-part questions that test the chat memory (10, on the Chat
page: the arena keeps no history) and greetings (5). Every row suggests 3 random answer models for
testers who do not want all 10 answers.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DEFAULT_CONFIG  # noqa: E402

BOTH = ["What does FORRT offer to help me teach preregistration?",
        "What is a replication study, and does FORRT have resources about replication?",
        "What is open peer review, and does FORRT have materials on it?",
        "How can I make my analysis code reproducible, and can FORRT help me learn this?",
        "What are the FAIR principles, and where can I find FORRT's teaching materials about them?"]
TWO_PART = [("What is preregistration?", "How is that different from a registered report?"),
            ("What is open access?", "Which of those models costs me least as an author?"),
            ("What is FORRT?", "How can I join one of its teams?"),
            ("What is p-hacking?", "How can I avoid it in my own analysis?"),
            ("What are the FAIR principles?", "Which repository should I use to follow them for survey data?"),
            ("Has the ego depletion effect been replicated?", "Where can I look up other replications like this one?"),
            ("What is a data management plan?", "Are there tools that help me write one?"),
            ("What is the FORRT glossary?", "Can I contribute a translation to it?"),
            ("What is HARKing?", "Why is it a problem for replicability?"),
            ("What is citizen science?", "Is it a form of open science?")]
GREETINGS = ["Hello", "Who are you?", "What can you do?", "Thanks!", "Hi, how do I use this?"]
EXPECTED = {"open science": "answer from the papers, with sources",
            "FORRT": "answer from forrt.org, with the page links",
            "open science and FORRT": "answer, citing papers and forrt.org pages",
            "should be refused (science-related)": "politely refuse",
            "two-part (context)": "answer; the follow-up must use the first answer",
            "greeting / about the bot": "introduce itself"}


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def build(seed=13):
    rng = random.Random(seed)
    written = {q.lower() for pair in TWO_PART for q in pair} | {q.lower() for q in BOTH + GREETINGS}
    qs = [q for q in load("eval/questions.jsonl") if q["question"].lower() not in written]
    forrt = [q for q in load("eval/forrt_questions.jsonl")
             if not q["id"].startswith("m") and q["question"].lower() not in written]  # English
    refuse = [q for q in qs if q["expect"] == "refuse" and q["lang"] == "en"] + \
             [q for q in load("eval/refusal_questions.jsonl") if q["lang"] == "en" and q["kind"] != "general"]
    os_en = [q for q in qs if q["route"] == "open_science" and q["lang"] == "en"]
    os_other = [q for q in qs if q["route"] == "open_science" and q["lang"] != "en"]
    rows = [("open science", q["id"], q["question"], "") for q in rng.sample(os_en, 30) + rng.sample(os_other, 5)]
    rows += [("FORRT", q["id"], q["question"], "") for q in rng.sample(forrt, 20)]
    both = [q for q in qs if q["route"] == "both"][:6]
    rows += [("open science and FORRT", q["id"], q["question"], "") for q in both] + \
            [("open science and FORRT", f"both{i}", q, "") for i, q in enumerate(BOTH[:10 - len(both)], 1)]
    rows += [("should be refused (science-related)", q["id"], q["question"], "") for q in rng.sample(refuse, 20)]
    rows += [("two-part (context)", f"tp{i:02d}", a, b) for i, (a, b) in enumerate(TWO_PART, 1)]
    rows += [("greeting / about the bot", f"hi{i}", q, "") for i, q in enumerate(GREETINGS, 1)]
    rng.shuffle(rows)
    models = [m.strip() for m in DEFAULT_CONFIG["ARENA_MODELS"].split(",") if m.strip() and m.strip() != "openscholar-8b"]
    return pd.DataFrame([{
        "no": n, "category": c, "id": i, "test_on": "Chat (ask the follow-up next)" if f else "Arena",
        "question": q, "follow_up": f, "the_bot_should": EXPECTED[c],
        "suggested_models": ", ".join(sorted(rng.sample(models, 3))), "tester": "", "notes": ""}
        for n, (c, i, q, f) in enumerate(rows, 1)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--out", default="eval/arena_test_questions")
    args = parser.parse_args()
    df = build(args.seed)
    assert len(df) == 100 and df["question"].is_unique, "100 different questions"
    df.to_csv(f"{args.out}.csv", index=False, encoding="utf-8")
    with pd.ExcelWriter(f"{args.out}.xlsx", engine="openpyxl") as xls:
        df.to_excel(xls, index=False, sheet_name="questions")
        sheet = xls.sheets["questions"]
        for col, width in zip("ABCDEFGHIJ", (5, 30, 9, 26, 70, 50, 40, 70, 18, 40)):
            sheet.column_dimensions[col].width = width
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    print(df["category"].value_counts().to_string())
    print(f"wrote {args.out}.csv and .xlsx")


if __name__ == "__main__":
    main()
