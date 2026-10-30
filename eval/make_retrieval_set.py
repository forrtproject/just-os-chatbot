"""Make the retrieval eval set: questions with the document that answers them.

Sources:
1. data/interim/questions_and_text.csv (question + the text it was generated from).
   Each text is matched to a document of the index. These cover only a few documents.
2. Synthetic questions: an OpenRouter model writes one question from one chunk of
   N_SYNTHETIC random documents, so the set covers the whole index.
A subset is translated (nl, de, es) to test multilingual retrieval.

    python eval/make_retrieval_set.py
Output: eval/retrieval_questions.jsonl
"""

import bisect
import json
import os
import random
import re
from collections import Counter, defaultdict

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

DOCSTORE = "data/processed/vs_latest_bge-small-en-v1.5/docstore.json"
OUTPUT = "eval/retrieval_questions.jsonl"
MAX_PER_DOC = 3  # so a few long documents do not dominate the set
N_SYNTHETIC = 150
N_TRANSLATED = 100
LANGUAGES = {"nl": "Dutch", "de": "German", "es": "Spanish"}
LLM_MODEL = "google/gemma-3-27b-it"


def squash(text):
    # Letters and digits only: old PDF text breaks words ("rega rded"), new Markdown does not
    return re.sub(r"[^a-z0-9]", "", text.lower())


def load_documents():
    nodes = json.load(open(DOCSTORE, encoding="utf-8"))["docstore/data"]
    texts, titles = defaultdict(list), {}
    for value in nodes.values():
        node = value["__data__"]
        doc_id = node["relationships"]["1"]["node_id"]
        texts[doc_id].append(node["text"])
        titles[doc_id] = node["metadata"].get("title", "")
    return texts, titles


def match_document(text, corpus, starts, doc_ids):
    s = squash(text)
    votes = Counter()
    for pos in (0.25, 0.5, 0.75):
        snippet = s[int(len(s) * pos) : int(len(s) * pos) + 60]
        if len(snippet) < 60:
            continue
        hit = corpus.find(snippet)
        if hit >= 0:
            votes[doc_ids[bisect.bisect_right(starts, hit) - 1]] += 1
    if votes and votes.most_common(1)[0][1] >= 2:
        return votes.most_common(1)[0][0]
    return None


def ask_json(client, prompt):
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content
    return json.loads(content[content.index("{") : content.rindex("}") + 1])


def write_question(client, passage):
    prompt = (
        "Write one question that a researcher could ask and that this passage answers. "
        "Use your own words: do not copy phrases from the passage and do not name the paper. "
        'Return only JSON: {"question": "..."}\n\n' + passage
    )
    return ask_json(client, prompt)["question"]


def translate(client, question):
    prompt = (
        "Translate this question into Dutch, German and Spanish. Keep technical terms correct. "
        'Return only JSON: {"nl": "...", "de": "...", "es": "..."}\n\n' + question
    )
    return ask_json(client, prompt)


if __name__ == "__main__":
    load_dotenv()
    chunks, titles = load_documents()
    docs = {doc_id: squash(" ".join(parts)) for doc_id, parts in chunks.items()}
    doc_ids = list(docs)
    starts, offset = [], 0
    for doc_id in doc_ids:
        starts.append(offset)
        offset += len(docs[doc_id]) + 1
    corpus = "|".join(docs[d] for d in doc_ids)

    questions = pd.read_csv("data/interim/questions_and_text.csv")
    questions["doc_id"] = [match_document(t, corpus, starts, doc_ids) for t in questions.text]
    print(f"matched {questions.doc_id.notna().sum()} of {len(questions)} questions")

    matched = questions.dropna(subset=["doc_id"]).groupby("doc_id").head(MAX_PER_DOC)
    items = [
        {"id": f"q{i:04d}", "lang": "en", "question": row.question, "doc_id": row.doc_id,
         "title": titles[row.doc_id]}
        for i, row in enumerate(matched.itertuples())
    ]
    print(f"kept {len(items)} questions over {matched.doc_id.nunique()} documents")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    rng = random.Random(0)
    for doc_id in rng.sample(sorted(set(doc_ids) - set(matched.doc_id)), N_SYNTHETIC):
        long_chunks = [c for c in chunks[doc_id] if len(c) > 800] or chunks[doc_id]
        try:
            question = write_question(client, rng.choice(long_chunks))
        except Exception as e:
            print(f"question failed for {doc_id}: {e}")
            continue
        items.append({"id": f"s{len(items):04d}", "lang": "en", "question": question,
                      "doc_id": doc_id, "title": titles[doc_id]})
    print(f"{len(items)} English questions after synthetic ones")

    for item in rng.sample(items, min(N_TRANSLATED, len(items))):
        try:
            translations = translate(client, item["question"])
        except Exception as e:
            print(f"translation failed for {item['id']}: {e}")
            continue
        items += [
            {**item, "id": f"{item['id']}-{lang}", "lang": lang, "question": translations[lang]}
            for lang in LANGUAGES
            if translations.get(lang)
        ]

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(items)} items to {OUTPUT}: {Counter(i['lang'] for i in items)}")
