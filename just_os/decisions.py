"""Decision models (TypeSafe Jev, Cloudflare Clef / Clef-flash) through OpenRouter's decisions API.

A decision model reads a `state` and typed `questions` and returns calibrated probabilities instead
of text: a `choice` question picks one of the given options, a `noul` question gives the probability
of yes. It cannot invent an option, takes about 0.3-2 s and costs under 0.001 USD per call.
JUST-OS uses it twice (see docs/architecture.md):
  - classify a question: open_science / forrt / both / neither   (DECISION_ROUTER_MODEL)
  - pick the FORRT pages worth reading                           (FORRT_SELECT_MODEL)
The endpoint is in alpha: every caller falls back when a call fails.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

ROUTES = {
    "open_science": "a question about open science, research practice, methods or scholarly communication "
                    "that needs an explained answer from the literature",
    "forrt": "a question about FORRT itself: the organisation, its teams, projects, tools, events, news, "
             "newsletters, how to get involved or contribute, contacts, or where something is on forrt.org",
    "both": "a question that needs both: an explanation from the literature and FORRT's own pages, "
            "for example how to learn more about an open-science topic with FORRT",
    "neither": "anything else: not about open science, research practice or FORRT",
}


class DecisionClient:
    def __init__(self, config: Dict[str, Any]):
        self.url = config.get("DECISION_URL", "https://openrouter.ai/api/alpha/decisions")
        self.api_key = config.get("LLM_API_KEY", "")
        self.timeout = config.get("DECISION_TIMEOUT", 8)

    def decide(self, model: str, state: str, questions: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """(answers by question id, info with ms/cost/error); answers is None when the call fails."""
        start = time.perf_counter()
        info: Dict[str, Any] = {"model": model}
        try:
            resp = httpx.post(self.url, timeout=self.timeout,
                              headers={"Authorization": f"Bearer {self.api_key}"},
                              json={"model": model, "state": state, "questions": questions})
            resp.raise_for_status()
            out = resp.json()
        except Exception as exc:
            info.update(ms=round((time.perf_counter() - start) * 1000), error=f"{exc.__class__.__name__}: {str(exc)[:200]}")
            logger.error(f"Decision model {model} failed: {info['error']}")
            return None, info
        usage = out.get("usage") or {}
        info.update(ms=round((time.perf_counter() - start) * 1000), cost=usage.get("cost"))
        return out.get("answers", out), info

    def route(self, model: str, question: str) -> Tuple[Optional[str], float, Dict[str, Any]]:
        """(route, probability of that route, info). Route is None when the call fails."""
        answers, info = self.decide(model, f"Question typed into the chat assistant on forrt.org: {question}",
                                    {"route": {"type": "choice",
                                               "instructions": "Which kind of question is this?",
                                               "criteria": ROUTES}})
        best = (answers or {}).get("route") or {}
        route = best.get("choice") if isinstance(best, dict) else None
        if route not in ROUTES:
            info.setdefault("error", f"no valid choice in {str(best)[:120]}")
            return None, 0.0, info
        probs = best.get("probabilities") or {}
        info["probabilities"] = probs
        return route, float(probs.get(route, best.get("confidence", 0.0)) or 0.0), info
