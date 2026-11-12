"""Generate eval items with rubrics from the FORRT glossary (issue E1, in the way ResearchQA mines survey sections).

    docker compose exec web python eval/glossary_items.py GLOSSARY_JSON \
        --terms eval/glossary_terms.txt --model openai/gpt-4.1-mini [--german]

GLOSSARY_JSON is content/glossary/_glossaries.json from github.com/forrtproject/forrt.
The terms are the English titles listed in --terms, one per line, or else every term
that cites at least one indexed document. For each term a model writes a stand-alone
question, a reference answer and 3-5 rubric items from the definition only. Citation
items are not generated: the indexed DOIs among the term's references become
expected_dois, read from the index's docstore (--index), which also holds the cluster
papers that docs/indexed_documents.csv leaves out.

Output: one line per question, with the fields of eval/questions.jsonl plus term,
generator, reference_answer and rubric. Item ids follow the order of --terms, so the
files of different generators share them. --german adds each question in German, with
the same rubric. Check the items by hand before use.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_config  # noqa: E402
from just_os.qualle import OpenAIClientManager  # noqa: E402

DOI = re.compile(r"10\.\d{4,}/[^\s<\"]+")

# The related terms are left out: given them, the model wrote rubric items the
# definition does not support (7 of 105 in the pilot).
ITEM_PROMPT = """You write one evaluation item for a chatbot that answers questions about open
science and research methods from a library of papers.

Source: the FORRT glossary entry for "{term}".
Definition: {definition}

Write:
1. "question": a question a researcher or student would ask the chatbot, which this
   definition answers. It must make sense on its own: do not mention a glossary, a
   definition, "this term" or "the text". Prefer a natural question (what is X, why does
   X matter, how does X differ from Y) over a quiz question.
2. "reference_answer": an answer of 80-150 words that uses only what the definition says.
3. "rubric": 3 to 5 items. Each item is one statement a good answer must cover, checkable
   on its own and stated in the definition; use no outside knowledge. An item must not
   restate something the question already says, since every answer would meet it. A
   specific example is never "core", since a good answer may give another one. Order the
   items by importance. Give each a "type": "core" for what the answer cannot leave out,
   "detail" for a further point a complete answer includes.

Return a JSON object: {{"question": str, "reference_answer": str,
"rubric": [{{"type": "core"|"detail", "criterion": str}}, ...]}}"""

TRANSLATE_PROMPT = """Translate this question into German, as a German-speaking researcher would
ask it. Use the German term "{term_de}" for "{term}". Return a JSON object
{{"question": str}}.

Question: {question}"""


def normalize(doi):
    return str(doi).strip().lower().removeprefix("https://doi.org/").rstrip(".")


def index_dois(index_dir="data/processed/vs_latest_bge-m3"):
    """Every DOI in the index's docstore; the 10 documents from #24 keep theirs in a dict."""
    data = json.load(open(Path(index_dir) / "docstore.json", encoding="utf-8"))["docstore/data"]
    dois = set()
    for node in data.values():
        doi = node["__data__"].get("metadata", {}).get("doi")
        if isinstance(doi, dict):
            doi = next(iter(doi.values()), "")
        if doi:
            dois.add(normalize(doi))
    return dois


def cited_dois(term):
    return {normalize(d) for r in term.get("references", []) for d in DOI.findall(r)}


def select_terms(english, index, titles=None):
    """(term, indexed DOIs) for the listed titles in their order, or for every term citing an indexed DOI."""
    if titles is None:
        return [(t, sorted(cited_dois(t) & index)) for t in english if cited_dois(t) & index]
    by_title = {t["en_title"]: t for t in english}
    missing = [title for title in titles if title not in by_title]
    if missing:
        raise SystemExit(f"not in the glossary: {missing}")
    return [(by_title[title], sorted(cited_dois(by_title[title]) & index)) for title in titles]


def parse_json(text):
    """The JSON object in a reply, also when a model wraps it in a code fence."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def ask(manager, model, prompt, cost):
    """One JSON-mode call; adds its cost (USD, from OpenRouter usage) to cost[0]."""
    response = manager.client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        extra_body={"usage": {"include": True}},
    )
    cost[0] += getattr(response.usage, "cost", 0) or 0
    return parse_json(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glossary")
    parser.add_argument("--model", default="openai/gpt-4.1-mini", help="generator (OpenRouter id)")
    parser.add_argument("--terms", help="file of English term titles, one per line")
    parser.add_argument("--index", default="data/processed/vs_latest_bge-m3", help="index folder")
    parser.add_argument("--german", action="store_true", help="also write each question in German")
    parser.add_argument("--out", help="default eval/glossary_items_<model>.jsonl")
    args = parser.parse_args()
    out = args.out or f"eval/glossary_items_{args.model.replace('/', '__')}.jsonl"

    glossary = {lang: terms for block in json.load(open(args.glossary, encoding="utf-8")) for lang, terms in block.items()}
    german = {t["en_title"]: t["title"] for t in glossary["german"]}
    titles = [line.strip() for line in open(args.terms, encoding="utf-8") if line.strip()] if args.terms else None
    terms = select_terms(glossary["english"], index_dois(args.index), titles)

    manager = OpenAIClientManager(get_config())
    cost = [0.0]
    with open(out, "w", encoding="utf-8") as f:
        for n, (t, dois) in enumerate(terms, 1):
            item = ask(manager, args.model, ITEM_PROMPT.format(term=t["title"], definition=t["definition"]), cost)
            rubric = [{"id": f"r{i}", "type": r["type"], "criterion": r["criterion"]} for i, r in enumerate(item["rubric"], 1)]
            base = {"expect": "answer", "expected_dois": dois, "source": "FORRT glossary", "term": t["en_title"],
                    "generator": args.model, "reference_answer": item["reference_answer"], "rubric": rubric}
            questions = [("en", item["question"])]
            if args.german:
                term_de = german.get(t["en_title"], t["title"])
                questions.append(("de", ask(manager, args.model, TRANSLATE_PROMPT.format(
                    term=t["title"], term_de=term_de, question=item["question"]), cost)["question"]))
            for lang, question in questions:
                f.write(json.dumps({"id": f"gl{n:02d}{lang}", "question": question, "lang": lang, **base},
                                   ensure_ascii=False) + "\n")
            print(f"gl{n:02d} {t['en_title']}: {item['question']}")
    print(f"wrote {out}, {len(terms)} terms, cost ${cost[0]:.4f}")


if __name__ == "__main__":
    main()
