"""The criteria people and LLM judges score answers on (#54), read from config/criteria.json.

`criteria` holds the shared criteria on the shared `scale`; `decisions` the review page's verdict on
answering or refusing. `forms` lists what each page asks while it keeps its own scale: the review page
scores shared criteria, and the arena scores its own three, each mapped to the shared ones it covers.
"""

import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "config" / "criteria.json"
DEFINITIONS = json.loads(PATH.read_text(encoding="utf-8"))


def text(criterion: dict) -> str:
    """'Label: definition', as the pages show it."""
    return f"{criterion['label']}: {criterion['definition']}"


CRITERIA = {key: text(c) for key, c in DEFINITIONS["criteria"].items()}
DECISIONS = dict(DEFINITIONS["decisions"])
REVIEW = {key: CRITERIA[key] for key in DEFINITIONS["forms"]["review"]["criteria"]}
ARENA = {key: text(c) for key, c in DEFINITIONS["forms"]["arena"]["criteria"].items()}
ARENA_MAPS_TO = {key: c["maps_to"] for key, c in DEFINITIONS["forms"]["arena"]["criteria"].items()}
