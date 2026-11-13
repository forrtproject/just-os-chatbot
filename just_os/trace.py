"""Debug trace of one chat turn, for the debug panel on the chat page (`?debug=1`).

Only collected when the page asks for it (`"debug": true` in POST /chat); otherwise every function
here returns at once. One Trace per turn records:
  - steps: the pipeline steps that ran (rephrase, topic check, sources, answer, ...) with their start
    and duration, and a few facts per step (the rewritten question, the chosen route, ...)
  - calls: every model call (LLM or decision model) with tokens, cost (as the provider reports it)
    and the step it belongs to
  - info: scores the panel shows (router probabilities and thresholds, source scores and cut-offs)

The trace lives in a ContextVar, so code deep in the pipeline records into it without passing it
around. A thread pool only sees it when the job is submitted with contextvars.copy_context().run.
"""

import functools
import inspect
import logging
import threading
import time
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_active: ContextVar[Optional["Trace"]] = ContextVar("debug_trace", default=None)
_step: ContextVar[Optional[str]] = ContextVar("debug_trace_step", default=None)


class Trace:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.steps: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self.info: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def ms_since_start(self, t: float) -> int:
        return round((t - self.t0) * 1000)

    def export(self, timings: Dict[str, float]) -> Dict[str, Any]:
        calls = list(self.calls)
        costs = [c["cost"] for c in calls if c.get("cost") is not None]
        return {
            "steps": sorted(self.steps, key=lambda s: s["start_ms"]),
            "calls": calls,
            "info": self.info,
            "timings": timings,
            "totals": {
                "ms": round(timings.get("total_s", 0) * 1000) or self.ms_since_start(time.perf_counter()),
                # None when no call reported a cost (self-hosted models, or a provider without it)
                "cost": round(sum(costs), 6) if costs else None,
                "cost_missing": sum(1 for c in calls if c.get("cost") is None and not c.get("error")),
                "tokens_in": sum(c.get("tokens_in") or 0 for c in calls),
                "tokens_out": sum(c.get("tokens_out") or 0 for c in calls),
                "tokens_cached": sum(c.get("tokens_cached") or 0 for c in calls),
                "calls": len(calls),
            },
        }


def begin() -> Any:
    """Start a trace for this turn; returns the token for end()."""
    return _active.set(Trace())


def end(token: Any) -> None:
    try:
        _active.reset(token)
    except ValueError:  # a closed generator can end in another context
        _active.set(None)


def active() -> Optional[Trace]:
    return _active.get()


def note(**values: Any) -> None:
    """Add values to the trace's info (no-op without a trace)."""
    t = _active.get()
    if t is not None:
        with t.lock:
            t.info.update(values)


def step(name: str, summary: Optional[Callable[..., Dict[str, Any]]] = None):
    """Decorator: record a call of the function as step `name`. summary(result, *args, **kwargs)
    returns facts to keep with the step. A function that calls itself (Qualle.route) is one step.
    Generator functions are timed from the first value to the last."""

    def record(t: Trace, start: float, parent: Optional[str], result: Any, args, kwargs, error: Optional[str]) -> None:
        entry = {"name": name, "start_ms": t.ms_since_start(start), "ms": round((time.perf_counter() - start) * 1000)}
        if parent:  # a step inside another one (page search inside FORRT pages)
            entry["parent"] = parent
        if error:
            entry["error"] = error
        if summary is not None and not error:
            try:
                entry.update(summary(result, *args, **kwargs) or {})
            except Exception as exc:  # the panel must never break an answer
                logger.debug(f"trace summary for {name} failed: {exc}")
        with t.lock:
            t.steps.append(entry)

    def decorator(fn):
        if inspect.isgeneratorfunction(fn):
            @functools.wraps(fn)
            def gen_wrapper(*args, **kwargs):
                t = _active.get()
                if t is None or _step.get() == name:
                    yield from fn(*args, **kwargs)
                    return
                parent = _step.get()
                token, start, error = _step.set(name), time.perf_counter(), None
                try:
                    yield from fn(*args, **kwargs)
                except Exception as exc:
                    error = f"{exc.__class__.__name__}: {exc}"[:200]
                    raise
                finally:
                    _reset_step(token)
                    record(t, start, parent, None, args, kwargs, error)
            return gen_wrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t = _active.get()
            if t is None or _step.get() == name:
                return fn(*args, **kwargs)
            parent = _step.get()
            token, start = _step.set(name), time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                _reset_step(token)
                record(t, start, parent, None, args, kwargs, f"{exc.__class__.__name__}: {exc}"[:200])
                raise
            _reset_step(token)
            record(t, start, parent, result, args, kwargs, None)
            return result
        return wrapper

    return decorator


def _reset_step(token: Any) -> None:
    try:
        _step.reset(token)
    except ValueError:
        _step.set(None)


def _usage_number(usage: Any, *path: str) -> Optional[float]:
    value = usage
    for key in path:
        if value is None:
            return None
        value = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
    return value if isinstance(value, (int, float)) else None


def llm_call(model: str, start: float, usage: Any = None, error: Optional[str] = None,
             attempts: int = 1, stream: bool = False) -> None:
    """One LLM call (with its retries). usage: the OpenAI-style usage object or dict; OpenRouter adds `cost`."""
    t = _active.get()
    if t is None:
        return
    cost = _usage_number(usage, "cost")
    if cost is None and getattr(usage, "model_extra", None):
        cost = _usage_number(usage.model_extra, "cost")
    entry = {
        "kind": "llm",
        "step": _step.get() or "other",
        "model": model,
        "start_ms": t.ms_since_start(start),
        "ms": round((time.perf_counter() - start) * 1000),
        "tokens_in": _usage_number(usage, "prompt_tokens"),
        "tokens_out": _usage_number(usage, "completion_tokens"),
        "tokens_cached": _usage_number(usage, "prompt_tokens_details", "cached_tokens"),
        "cost": cost,
    }
    if attempts > 1:
        entry["attempts"] = attempts
    if stream:
        entry["stream"] = True
    if error:
        entry["error"] = error[:200]
    with t.lock:
        t.calls.append(entry)


def decision_call(model: str, start: float, info: Dict[str, Any], questions: Dict[str, Any],
                  answers: Optional[Dict[str, Any]]) -> None:
    """One decision-model call: its cost and, per question, the probabilities it gave."""
    t = _active.get()
    if t is None:
        return
    results = {}
    for qid, q in (questions or {}).items():
        a = (answers or {}).get(qid)
        if not isinstance(a, dict):
            a = {"noul": a} if isinstance(a, (int, float)) else {}
        label = q.get("instructions", "")
        if "Page: " in label:  # FORRT page selection: the page title
            label = label.split("Page: ", 1)[1].split(" (", 1)[0]
        results[qid] = {"type": q.get("type"), "label": label[:160],
                        "choice": a.get("choice"), "probabilities": a.get("probabilities"), "yes": a.get("noul")}
    entry = {
        "kind": "decision",
        "step": _step.get() or "other",
        "model": model,
        "start_ms": t.ms_since_start(start),
        "ms": info.get("ms"),
        "tokens_in": None, "tokens_out": None, "tokens_cached": None,
        "cost": info.get("cost"),
        "questions": results,
    }
    if info.get("error"):
        entry["error"] = info["error"]
    with t.lock:
        t.calls.append(entry)
