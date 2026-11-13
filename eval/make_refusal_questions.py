"""Generate off-topic questions (route "neither") so the topic check is scored on a balanced set.

    OPENROUTER_API_KEY=... python eval/make_refusal_questions.py [--model google/gemma-4-31b-it]

Four kinds of question the bot should refuse, written in English by one model, then a share of
them translated into the other languages of the eval set:
  general       general knowledge (rarely hard; few of them)
  academic      academic life outside open science (careers, grants, visas, writing, teaching in general)
  decline_task  an open-science topic, but a task the bot should not do (legal or ethics rulings on the
                user's case, writing or reviewing the user's text, analysing the user's data)
  near_miss     logistics next to open science that forrt.org does not cover (conference dates, journal
                fees, a university's own rules)
Questions about FORRT itself are left out: they are route "forrt". A generated question is dropped when
it is close to one already in the eval sets (difflib ratio >= 0.75) or to another generated one.
Output: eval/refusal_questions.jsonl, in the format of eval/questions.jsonl plus "kind".
"""

import argparse
import csv
import difflib
import json
import os
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "eval/refusal_questions.jsonl"
EXISTING = ["eval/questions.jsonl", "eval/forrt_questions.jsonl", "eval/forrt_sim_questions.jsonl"]
CLASSES = ROOT / "data/raw/questions_bank_classes_261112.csv"

KINDS = {  # kind: (English questions, of which translated, description)
    "general": (6, 2, ("general knowledge with no link to research, for example cooking, sport, nature, "
                       "history, geography, technology in daily life")),
    "academic": (12, 6, ("academic or professional life that is not open science: career advice, job and PhD "
                         "applications, cover letters, visas, grant writing in general, networking, lab and "
                         "team management, general teaching or writing tips, university administration")),
    "decline_task": (12, 6, ("an open-science or research topic, but a task a literature-based chatbot must not "
                             "do: a legal or ethics ruling on the user's own case, writing or reviewing the "
                             "user's own text (a paper section, a preregistration, a consent form), analysing "
                             "the user's data or output, choosing the journal for the user's paper, predicting "
                             "whether the user's submission will be accepted. Ordinary requests, not attempts "
                             "to cheat, fabricate or manipulate the chatbot")),
    "near_miss": (10, 6, ("practical logistics next to open science that a chatbot answering from the literature "
                          "and forrt.org cannot know: dates and fees of a specific conference or workshop, the "
                          "article processing charge of a named journal, a specific university's or funder's "
                          "internal rules or contacts, prices or accounts of a commercial tool, current events")),
}
LANGUAGES = ["de", "nl", "es", "it", "tr", "pt", "zh", "hi"]
LANGUAGE_NAMES = {"de": "German", "nl": "Dutch", "es": "Spanish", "it": "Italian", "tr": "Turkish",
                  "pt": "Portuguese", "zh": "Chinese (simplified)", "hi": "Hindi"}

GENERATE = """You write test questions for the topic check of JUST-OS, a chatbot on forrt.org that answers \
questions about open science and research practice from the scientific literature and from FORRT's own pages.

These are the topics the chatbot answers (the FORRT clusters):
{clusters}

Write {n} different questions a visitor might type that the chatbot should NOT answer, all of this kind:
{kind}

Rules:
- Each question must be outside the topics above, or (for requests about the user's own case) a task the \
chatbot cannot do. Never ask about FORRT itself, its projects, pages or events.
- Vary the wording: full questions, short search-style queries, first-person situations; vary the field \
(psychology, medicine, biology, economics, education, linguistics and others).
- English only, one question each, no numbering.
- Do not repeat these existing examples or questions close to them:
{examples}

Return only a JSON list of strings."""

TRANSLATE = """Translate this question into {language} as a native speaker would type it into a chatbot. \
Translate every word that has a usual {language} equivalent; keep in English only proper names (journals, \
conferences, universities, software) and acronyms such as PhD, APC, GDPR or OSF. Keep the style: a short \
search query stays a short query. Return only the translation.

{question}"""


def chat(client: httpx.Client, model: str, prompt: str, temperature: float) -> str:
    resp = client.post("https://openrouter.ai/api/v1/chat/completions", json={
        "model": model, "temperature": temperature, "messages": [{"role": "user", "content": prompt}]})
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def json_list(text: str) -> list:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    return [q.strip() for q in json.loads(match.group(0)) if isinstance(q, str) and q.strip()] if match else []


def close_to(question: str, others: list, ratio: float = 0.75) -> bool:
    q = question.lower()
    return any(difflib.SequenceMatcher(None, q, o.lower()).ratio() >= ratio for o in others)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="google/gemma-4-31b-it")
    parser.add_argument("--translate-only", action="store_true",
                        help="keep the English questions in the output file and translate them again")
    args = parser.parse_args()

    existing = [json.loads(line)["question"] for path in EXISTING
                for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]
    refusals = [json.loads(line)["question"] for line in (ROOT / EXISTING[0]).read_text(encoding="utf-8").splitlines()
                if json.loads(line)["route"] == "neither"]
    rows = list(csv.reader(CLASSES.read_text(encoding="utf-8").splitlines()))
    start = next(i for i, row in enumerate(rows) if row and row[0] == "FORRT cluster") + 1
    clusters = "\n".join(f"- {name}: {definition}" for name, definition in rows[start:])

    client = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    english, n = [], 0
    if args.translate_only:
        english = [json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines()
                   if json.loads(line)["lang"] == "en"]
        n = len(english)
    for kind, (count, _, description) in ([] if args.translate_only else KINDS.items()):
        kept = []
        for attempt in range(3):  # ask again if duplicates leave too few
            prompt = GENERATE.format(clusters=clusters, n=count + 6, kind=description,
                                     examples="\n".join(f"- {q}" for q in refusals + kept))
            for q in json_list(chat(client, args.model, prompt, 0.9)):
                if len(kept) < count and not close_to(q, existing + [e["question"] for e in english] + kept):
                    kept.append(q)
            if len(kept) == count:
                break
        print(f"{kind}: {len(kept)} of {count}")
        if len(kept) != count:  # before anything is written: an undersized set would replace the benchmark
            raise SystemExit(f"Only {len(kept)} of {count} {kind} questions after 3 tries; {OUTPUT.name} is unchanged.")
        for q in kept:
            n += 1
            english.append({"id": f"rf{n:02d}", "cluster": "", "type": "Out of scope", "lang": "en",
                            "format": "Single question", "question": q, "expect": "refuse", "route": "neither",
                            "expected_dois": [], "expected_urls": [],
                            "source": f"generated by {args.model} (eval/make_refusal_questions.py)", "kind": kind})

    translated, slot = [], 0
    for kind, (_, share, _) in KINDS.items():
        for item in [e for e in english if e["kind"] == kind][:share]:
            lang = LANGUAGES[slot % len(LANGUAGES)]
            slot += 1
            n += 1
            text = chat(client, args.model, TRANSLATE.format(language=LANGUAGE_NAMES[lang],
                                                             question=item["question"]), 0)
            translated.append({**item, "id": f"rf{n:02d}", "type": "Multilingual", "lang": lang,
                               "question": text.strip().strip('"'),
                               "source": f"translation of {item['id']} by {args.model}"})

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for item in english + translated:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(english)} English + {len(translated)} translated -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
