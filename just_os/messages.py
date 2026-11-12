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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MESSAGES_FILE = Path(__file__).resolve().parent.parent / "config" / "refusals.csv"
MESSAGE_KEYS = (
    "off_topic",  # the question is not about Open Science
    "no_sources",  # no passage passed MIN_RELEVANCE
    "model_unavailable",  # the classifier model could not be reached
    "generation_error",  # the answer model returned nothing
    "unexpected_error",  # any other exception
    "about",  # a greeting or a question about the bot: a short self-introduction
)
DEFAULT_LANGUAGE = "en"
# Languages lingua does not detect, recognised by a script only they use: a question
# where at least half of the letters are in that script is in that language
SCRIPTS = {"kn": re.compile(r"[ಀ-೿]")}


def row_problems(row: Dict[Optional[str], Any]) -> List[str]:
    """What is wrong with one CSV row (an empty list for a good row)."""
    problems = []
    # csv.DictReader puts the fields beyond the header under the key None
    extra = row.get(None)
    if extra:
        problems.append(f"{len(extra)} field{'s' if len(extra) > 1 else ''} too many (an unquoted comma?)")
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

    return LanguageDetectorBuilder.from_all_languages().build()


def detect_language(text: str) -> Optional[str]:
    """ISO 639-1 code of the text's language, or None if it cannot be told."""
    letters = [c for c in text if c.isalpha()]
    for code, script in SCRIPTS.items():
        if letters and sum(bool(script.match(c)) for c in letters) * 2 >= len(letters):
            return code
    # English acronyms and field terms (DNA, HARKing, OSF, CRediT) made lingua read
    # "Was ist DNA Replikation und HARKing" as Swedish: detect on the other words
    words = [w for w in text.split() if sum(c.isupper() for c in w) < 2]
    try:
        language = detector().detect_language_of(" ".join(words) or text)
    except Exception as e:  # a detection failure must not hide the message itself
        logger.error(f"Language detection failed: {e}")
        return None
    return language.iso_code_639_1.name.lower() if language else None


def confident_language(text: str) -> Optional[str]:
    """Like detect_language, but None when the question is too short or unclear to tell.

    Short questions were guessed badly: "what is forrt" as Hungarian, "is it open" as Dutch, "Hallo" as
    Sesotho, "ORCID" as Portuguese. The name FORRT and acronyms are ignored; a language is returned only
    with at least 3 words (or a non-Latin script) and a lingua confidence of at least 0.10, and never Latin
    or Esperanto (English keyword queries such as "neurodiversity in academia" scored as Latin). On 190
    labelled questions in 7 languages plus edge cases this recognised all 35 non-English ones ("Was ist
    Replikation?": German 0.13) and forced no wrong language; on the logged chat questions it only changes
    "Hallo", "ORCID" and "Forrt" (to no language).
    """
    letters = [c for c in text if c.isalpha()]
    for code, script in SCRIPTS.items():
        if letters and sum(bool(script.match(c)) for c in letters) * 2 >= len(letters):
            return code
    words = [w for w in text.split() if sum(c.isupper() for c in w) < 2 and not re.fullmatch(r"\W*forrt\W*", w, re.I)]
    if len(words) < 3 and not re.search(r"[\u0370-\uffff]", text):
        return None
    code = _confident(words or text.split())
    # Names pull an English question to their language: "What is the best pizza in Maastricht?" was Dutch,
    # "Who is Lukas Wallrich at FORRT?" German. When the words without capitalised names (not the first
    # word) read as English, the question is English.
    rest = [w for i, w in enumerate(words) if i == 0 or not w[:1].isupper()]
    if code and code != "en" and 3 <= len(rest) < len(words) and _confident(rest, 0.0) == "en":
        return "en"
    return code


def _confident(words: List[str], minimum: float = 0.10) -> Optional[str]:
    """Lingua's best language for the words if its confidence is at least minimum (never Latin or Esperanto)."""
    try:
        best = detector().compute_language_confidence_values(" ".join(words))[0]
    except Exception as e:  # a detection failure must not hide the message itself
        logger.error(f"Language detection failed: {e}")
        return None
    code = best.language.iso_code_639_1.name.lower()
    return code if best.value >= minimum and code not in ("la", "eo") else None


def message(key: str, question: str = "") -> str:
    """The message `key` in the language of `question` when it is clear, else in English."""
    table = messages()
    language = confident_language(question) if question else None
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
