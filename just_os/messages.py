"""Fixed messages (refusals and errors) in the language of the question.

The texts are in config/refusals.csv, one row per language: an ISO 639-1 code in
the `language` column and one column per message (MESSAGE_KEYS). Adding a row adds
a language; no code changes, as long as lingua detects it or SCRIPTS has its script.
The language is detected with lingua over all its languages, so a language without
a row (for example Spanish) is recognised as itself and gets English, instead of
being taken for the nearest language that has a row.
"""

import csv
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MESSAGES_FILE = Path(__file__).resolve().parent.parent / "config" / "refusals.csv"
MESSAGE_KEYS = (
    "off_topic",  # the question is not about Open Science
    "no_sources",  # no passage passed MIN_RELEVANCE
    "model_unavailable",  # the classifier model could not be reached
    "generation_error",  # the answer model returned nothing
    "unexpected_error",  # any other exception
)
DEFAULT_LANGUAGE = "en"
# Languages lingua does not detect, recognised by a script only they use: a question
# where at least half of the letters are in that script is in that language
SCRIPTS = {"kn": re.compile(r"[ಀ-೿]")}


def row_problems(row: Dict[str, str]) -> List[str]:
    """What is wrong with one CSV row (an empty list for a good row)."""
    problems = []
    code = (row.get("language") or "").strip().lower()
    if code not in SCRIPTS:
        from lingua import IsoCode639_1

        try:
            IsoCode639_1.from_str(code)
        except ValueError:
            problems.append(f"'{code}' is not an ISO 639-1 code that lingua detects")
    for key in MESSAGE_KEYS:
        if not (row.get(key) or "").strip():
            problems.append(f"no text for {key}")
    return problems


def load_messages(path: Path = MESSAGES_FILE) -> Dict[str, Dict[str, str]]:
    """Read the CSV into {language: {message key: text}}; a bad row is logged and skipped."""
    # utf-8-sig: spreadsheet programs may start a UTF-8 CSV with a byte-order mark
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    messages = {}
    for line, row in enumerate(rows, start=2):
        problems = row_problems(row)
        if (row.get("language") or "").strip().lower() in messages:
            problems.append("a second row for this language")
        if problems:
            logger.error(f"{path.name} line {line} skipped: {'; '.join(problems)}")
            continue
        messages[row["language"].strip().lower()] = {k: row[k].strip() for k in MESSAGE_KEYS}
    if DEFAULT_LANGUAGE not in messages:
        raise ValueError(f"{path} needs a valid '{DEFAULT_LANGUAGE}' row")
    return messages


@lru_cache(maxsize=1)
def messages() -> Dict[str, Dict[str, str]]:
    return load_messages()


@lru_cache(maxsize=1)
def detector():
    """All lingua languages, high accuracy, under 1 ms per question.

    Lingua loads a language's model on the first question that needs it: a process grew
    from 28 to 174 MB after questions in 16 languages (lingua 2.2.0).
    """
    from lingua import LanguageDetectorBuilder

    return LanguageDetectorBuilder.from_all_languages().with_preloaded_language_models().build()


def detect_language(text: str) -> Optional[str]:
    """ISO 639-1 code of the text's language, or None if it cannot be told."""
    letters = [c for c in text if c.isalpha()]
    for code, script in SCRIPTS.items():
        if letters and sum(bool(script.match(c)) for c in letters) * 2 >= len(letters):
            return code
    try:
        language = detector().detect_language_of(text)
    except Exception as e:  # a detection failure must not hide the message itself
        logger.error(f"Language detection failed: {e}")
        return None
    return language.iso_code_639_1.name.lower() if language else None


def message(key: str, question: str = "") -> str:
    """The message `key` in the language of `question`, else in English."""
    table = messages()
    language = detect_language(question) if question else None
    return table.get(language, table[DEFAULT_LANGUAGE])[key]


def all_texts(key: str) -> List[str]:
    """The message `key` in every language (eval/run.py recognises refusals by text)."""
    return [texts[key] for texts in messages().values()]


def preload() -> None:
    """Read the CSV and build the detector at start-up, so a bad CSV fails here.

    The language models still load on the first detection, which takes about 0.1 s.
    """
    messages()
    detector()
