"""Build the expert grading page for the glossary items: one HTML file that works offline.

    python eval/build_grading_page.py GLOSSARY_JSON --items eval/glossary_items_A.jsonl ... \
        --runs eval/results --out DIR

Part 1 rates every item: is the question one a researcher would ask, and for each rubric
item, should a good answer cover it (essential, nice to have, not needed) and is it in the
glossary definition. This is the check ResearchQA ran with PhD annotators.

Part 2 grades answers against a rubric on the 0-4 scale of eval/rubric_judge.py, with the
same instructions the judge gets, so the expert's scores and the judge's compare directly.
Both see the answer as the app shows it; the page also removes the [n] markers, which would
tell the expert which answers had the library.
Each term gets the rubric of one generator, in turn, and the bot's answers to that item's
question with the library and without it (eval/results/glossary_<generator>_<mode>.csv).

The page is blind: items and answers carry random keys, and DIR/grading_key.csv maps each
key to its generator and condition. Progress stays in the browser; the expert exports
two CSVs (and a JSON backup that the page can import again).
"""

import argparse
import csv
import json
import random
import re
from pathlib import Path

MODES = ("library", "noretrieval")
CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


def shown_answer(raw):
    """The answer as the app shows it: only the text between [Response_Start] and
    [Response_End] (ResponseGenerator.post_process_response); the model sometimes echoes
    its source passages after the end marker."""
    if "[Response_Start]" in raw:
        raw = raw.split("[Response_Start]", 1)[1]
    return raw.split("[Response_End]")[0].strip()


def without_citations(text):
    """The answer with its [n] markers removed, so the expert cannot tell a library answer
    from one without sources; the rubric judge ignores the markers as well."""
    return CITATION.sub("", text)


def load_items(paths):
    """{generator: [items in term order]}, English items only."""
    out = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            items = [i for i in map(json.loads, f) if i["lang"] == "en"]
        out[items[0]["generator"]] = items
    return out


def load_answers(runs, generator):
    """{mode: {item id: answer}} for one generator's item file, answered rows only."""
    answers = {}
    for mode in MODES:
        path = Path(runs) / f"glossary_{generator.replace('/', '__')}_{mode}.csv"
        with open(path, encoding="utf-8") as f:
            answers[mode] = {r["id"]: without_citations(shown_answer(r["answer"])) for r in csv.DictReader(f) if r["outcome"] == "answered" and r["answer"]}
    return answers


def build(glossary, items, runs, seed=7):
    rng = random.Random(seed)
    definitions = {t["en_title"]: t["definition"] for t in glossary}
    generators = sorted(items)
    keys, part1, part2 = [], [], []

    for generator in generators:
        for item in items[generator]:
            part1.append({"term": item["term"], "definition": definitions[item["term"]],
                          "question": item["question"], "rubric": item["rubric"],
                          "_key": {"generator": generator, "item": item["id"], "condition": ""}})

    answers = {g: load_answers(runs, g) for g in generators}
    for n, item_id in enumerate(i["id"] for i in items[generators[0]]):
        generator = generators[n % len(generators)]
        item = next(i for i in items[generator] if i["id"] == item_id)
        for mode in MODES:
            answer = answers[generator][mode].get(item_id)
            if answer:
                part2.append({"question": item["question"], "answer": answer, "rubric": item["rubric"],
                              "_key": {"generator": generator, "item": item_id, "condition": mode}})

    for part, prefix in ((part1, "i"), (part2, "a")):
        rng.shuffle(part)
        for n, entry in enumerate(part, 1):
            entry["key"] = f"{prefix}{n:03d}"
            keys.append({"key": entry["key"], "part": 1 if prefix == "i" else 2, **entry.pop("_key")})
    return {"part1": part1, "part2": part2}, keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glossary")
    parser.add_argument("--items", nargs="+", required=True)
    parser.add_argument("--runs", default="eval/results")
    parser.add_argument("--out", required=True, help="folder for grading.html and grading_key.csv")
    args = parser.parse_args()

    with open(args.glossary, encoding="utf-8") as f:
        english = next(block["english"] for block in json.load(f) if "english" in block)
    data, keys = build(english, load_items(args.items), args.runs)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    template = (Path(__file__).parent / "grading_page.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (out / "grading.html").write_text(template.replace("/*DATA*/null", payload), encoding="utf-8")
    with open(out / "grading_key.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["key", "part", "generator", "item", "condition"])
        writer.writeheader()
        writer.writerows(keys)
    print(f"wrote {out / 'grading.html'}: {len(data['part1'])} items, {len(data['part2'])} answers; key in {out / 'grading_key.csv'}")


if __name__ == "__main__":
    main()
