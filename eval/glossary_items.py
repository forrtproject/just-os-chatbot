"""Generate eval items with rubrics from the FORRT glossary (issue E1, a ResearchQA-style pilot).

    docker compose exec web python eval/glossary_items.py GLOSSARY_JSON [--limit 3]

GLOSSARY_JSON is content/glossary/_glossaries.json from github.com/forrtproject/forrt.
For each English term that cites at least one indexed document (docs/indexed_documents.csv),
a model writes a stand-alone question, a reference answer and 3-5 rubric items from the
definition only, and translates the question into German. Citation items are not
generated: the indexed DOIs among the term's references become expected_dois.
Output: eval/glossary_items.jsonl, one line per question and language, with the
fields of eval/questions.jsonl plus term, reference_answer and rubric. The rubric is
the same (same ids, in English) for both languages. Check the items by hand before use.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import get_config  # noqa: E402
from just_os.qualle import OpenAIClientManager  # noqa: E402

DOI = re.compile(r"10\.\d{4,}/[^\s<\"]+")

ITEM_PROMPT = """You write one evaluation item for a chatbot that answers questions about open
science and research methods from a library of papers.

Source: the FORRT glossary entry for "{term}".
Definition: {definition}
Related terms: {related}

Write:
1. "question": a question a researcher or student would ask the chatbot, which this
   definition answers. It must make sense on its own: do not mention a glossary, a
   definition, "this term" or "the text". Prefer a natural question (what is X, why does
   X matter, how does X differ from Y) over a quiz question.
2. "reference_answer": an answer of 80-150 words that uses only what the definition says.
3. "rubric": 3 to 5 items. Each item is one statement a good answer must cover, checkable
   on its own, taken from the definition and not from outside knowledge. Order them by
   importance. Give each a "type": "core" for what the answer cannot leave out, "detail"
   for a further point a complete answer includes.

Return a JSON object: {{"question": str, "reference_answer": str,
"rubric": [{{"type": "core"|"detail", "criterion": str}}, ...]}}"""

TRANSLATE_PROMPT = """Translate this question into German, as a German-speaking researcher would
ask it. Use the German term "{term_de}" for "{term}". Return a JSON object
{{"question": str}}.

Question: {question}"""


def indexed_dois(path="docs/indexed_documents.csv"):
    return {r["doi"].strip().lower() for r in csv.DictReader(open(path, encoding="utf-8")) if r["doi"]}


def select_terms(english, index):
    """(term, indexed DOIs) for every term that cites at least one indexed document."""
    terms = []
    for t in english:
        dois = sorted({d.lower().rstrip(".") for r in t.get("references", []) for d in DOI.findall(r)} & index)
        if dois:
            terms.append((t, dois))
    return terms


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
    return json.loads(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glossary")
    parser.add_argument("--model", default="openai/gpt-4.1-mini", help="generator (OpenRouter id)")
    parser.add_argument("--limit", type=int, help="only the first N terms")
    parser.add_argument("--out", default="eval/glossary_items.jsonl")
    args = parser.parse_args()

    glossary = {lang: terms for block in json.load(open(args.glossary, encoding="utf-8")) for lang, terms in block.items()}
    german = {t["en_title"]: t["title"] for t in glossary["german"]}
    terms = select_terms(glossary["english"], indexed_dois())
    terms = terms[: args.limit] if args.limit else terms

    manager = OpenAIClientManager(get_config())
    cost = [0.0]
    with open(args.out, "w", encoding="utf-8") as f:
        for n, (t, dois) in enumerate(terms, 1):
            item = ask(manager, args.model, ITEM_PROMPT.format(
                term=t["title"], definition=t["definition"], related=", ".join(t.get("related_terms") or [])), cost)
            rubric = [{"id": f"r{i}", **r} for i, r in enumerate(item["rubric"], 1)]
            term_de = german.get(t["en_title"], t["title"])
            question_de = ask(manager, args.model, TRANSLATE_PROMPT.format(
                term=t["title"], term_de=term_de, question=item["question"]), cost)["question"]
            base = {"expect": "answer", "expected_dois": dois, "source": "FORRT glossary",
                    "term": t["en_title"], "reference_answer": item["reference_answer"], "rubric": rubric}
            for lang, question in (("en", item["question"]), ("de", question_de)):
                f.write(json.dumps({"id": f"gl{n:02d}{lang}", "question": question, "lang": lang, **base},
                                   ensure_ascii=False) + "\n")
            print(f"gl{n:02d} {t['en_title']}: {item['question']}")
    print(f"wrote {args.out}, {len(terms)} terms, cost ${cost[0]:.4f}")


if __name__ == "__main__":
    main()
