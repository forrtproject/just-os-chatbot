"""The /architecture team page: how a question is answered and how the index is built, for people who do not read
the code. Nothing on the page is copied from the code: values come from config/settings.py (code default), the
running app's config (this server: .env and AUTO_DEFAULTS applied) and deploy/kubernetes/just-os.yaml (prod); the
prompts are captured by calling the pipeline's own prompt builders with a client that records the call and answers
nothing; the worked example runs the loaded search on a fixed question (no LLM call).
test/test_app.py fails when a setting the page names is gone or a ROUTER / SEARCH_MODE option has no text here.
"""

import ast
import json
import logging
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import yaml

from just_os.decisions import DecisionClient, ROUTERS, ROUTES

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "config" / "settings.py"
KUBERNETES_FILE = ROOT / "deploy" / "kubernetes" / "just-os.yaml"

# One line per ROUTER option (keys must be decisions.ROUTERS; test_app checks it)
ROUTER_TEXT = {
    "": "Default: the decision model DECISION_ROUTER_MODEL when DECISION_ROUTER is on and it is at least "
        "DECISION_ROUTER_MIN_CONFIDENCE sure; otherwise the LLM classifier below.",
    "clef-flash": "Asks the decision model Cloudflare Clef-flash which of the four routes fits. If the call fails, the "
                  "LLM classifier decides.",
    "clef": "The same with Cloudflare Clef.",
    "jev": "The same with TypeSafe Jev (also the middle band of 'banded').",
    "llm": "Asks GENERAL_MODEL with the classification prompt below (open_science / forrt_lookup / off_topic); no "
           "decision model.",
    "cosine": "No model call: the question's similarity to the nearest paper chunk and to the nearest FORRT page "
              "description, against COSINE_PAPER_MIN and COSINE_PAGE_MIN.",
    "banded": "Similarity first, a model only when unsure: clearly far from everything is refused, clearly close to "
              "the papers (and not to a FORRT page) goes to the papers, everything in between goes to "
              "BAND_MIDDLE_ROUTER.",
    "none": "No check: every question is treated as 'both' (papers plus FORRT page links); only the similarity floor "
            "can still say 'no sources'.",
}

# One line per SEARCH_MODE (keys must be hybrid.SEARCH_MODES)
SEARCH_MODE_TEXT = {
    "vector": "Meaning search: the question becomes a vector and FAISS returns the RETRIEVER_TOP_K nearest chunk "
              "vectors. Finds paraphrases, can miss exact names and acronyms.",
    "bm25": "Keyword search (BM25) over all chunk texts: finds exact words such as 'HARKing' or 'CRediT', not "
            "synonyms. Its scores have no fixed scale, so the similarity floor does not apply.",
    "hybrid": "Both lists merged by reciprocal rank fusion (a chunk high in either list ranks high). The cluster "
              "boost only works in vector mode.",
}

EXAMPLE_QUESTION = "What is preregistration?"
EXAMPLE_HISTORY = [
    {"role": "user", "content": "What is a registered report?"},
    {"role": "assistant", "content": "A registered report is a journal article whose methods are peer reviewed before "
                                     "the data are collected [1]."},
]
EXAMPLE_FOLLOW_UP = "Which journals offer them?"
SECRET = "(secret, not shown)"


def code_defaults(path: Path = SETTINGS_FILE) -> Dict[str, Any]:
    """DEFAULT_CONFIG as written in config/settings.py, before any environment variable (the imported dict already has
    the environment applied). A value that is not a literal (os.getenv(...)) is "from the environment"."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "DEFAULT_CONFIG":
            out = {}
            for key, value in zip(node.value.keys, node.value.values):
                try:
                    out[ast.literal_eval(key)] = ast.literal_eval(value)
                except ValueError:
                    out[ast.literal_eval(key)] = "(from the environment)"
            return out
    raise ValueError(f"No DEFAULT_CONFIG in {path}")


def prod_overrides(path: Path = KUBERNETES_FILE) -> Dict[str, Any]:
    """What the public deployment sets: the ConfigMap's data and the names of the secrets it passes in."""
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as e:
        logger.warning(f"Could not read {path}: {e}")
        return {}
    out: Dict[str, Any] = {}
    for doc in docs:
        if not doc:
            continue
        if doc.get("kind") == "ConfigMap":
            out.update(doc.get("data") or {})
        for container in (((doc.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers", []):
            out.update({e["name"]: SECRET for e in container.get("env", []) if "valueFrom" in e})
    return out


def shown(name: str, value: Any) -> str:
    if "KEY" in name or value == SECRET:
        return SECRET if value else "(not set)"
    if value in ("", None):
        return "(empty)"
    return str(value)


class Settings:
    """The settings the page names. Unknown names raise, so a renamed setting breaks the page (and its test)."""

    def __init__(self, running: Dict[str, Any]):
        self.code = code_defaults()
        self.prod_set = prod_overrides()
        self.running = running

    def check(self, name: str) -> None:
        if name not in self.code:
            raise KeyError(f"/architecture names {name}, which config/settings.py no longer has")

    def value(self, name: str) -> str:
        """The value on this server, for the text."""
        self.check(name)
        return shown(name, self.running.get(name, self.code[name]))

    def row(self, name: str) -> Dict[str, Any]:
        self.check(name)
        here = self.running.get(name, self.code[name])
        prod = self.prod_set.get(name, self.code[name])
        return {"name": name, "code": shown(name, self.code[name]), "here": shown(name, here),
                "prod": shown(name, prod), "prod_set": name in self.prod_set,
                "differs": "KEY" not in name and str(here).lower() != str(prod).lower()}


class Capture:
    """Stands in for the LLM client, the decision client and the chat memory: records what the code would send
    and answers nothing, so every caller takes its "no answer" path."""

    def __init__(self, history: Optional[List[Dict[str, str]]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.history = history or []

    def create_chat_completion(self, **kwargs):
        """A forced tool call answered with a sample value of the asked type (so nothing logs an error)."""
        self.calls.append(kwargs)
        schema = kwargs["tools"][0]["function"]["parameters"]
        key = schema["required"][0]
        value = True if schema["properties"][key]["type"] == "boolean" else "open_science"
        call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps({key: value})))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])

    def decide(self, model, state, questions):
        self.calls.append({"model": model, "state": state, "questions": questions})
        return None, {}

    def get_history(self, chat_id):
        return self.history


def prompts(config: Dict[str, Any], rag=None) -> Dict[str, Any]:
    """The prompts as the pipeline builds them, for the example questions."""
    from just_os import forrt_pages
    from just_os.qualle import QueryProcessor, ResponseGenerator

    def llm(call: Capture) -> Dict[str, Any]:
        first = call.calls[0]
        return {"model": first["model"], "prompt": first["messages"][0]["content"],
                "temperature": first["temperature"], "key": first["tools"][0]["function"]["parameters"]["required"][0]}

    out: Dict[str, Any] = {}
    c = Capture(EXAMPLE_HISTORY)
    QueryProcessor(c, config, c).rephrase_query(EXAMPLE_FOLLOW_UP, "example")
    out["rephrase"] = llm(c)
    c = Capture()
    QueryProcessor(c, config, c).classify_query(EXAMPLE_QUESTION)
    out["classify"] = llm(c)
    c = Capture()
    QueryProcessor(c, config, c).classify_intent(EXAMPLE_QUESTION)
    out["intent"] = llm(c)
    c = Capture()
    DecisionClient.route(c, config.get("DECISION_ROUTER_MODEL"), EXAMPLE_QUESTION)
    out["decision"] = c.calls[0]
    example = worked_example(rag)
    candidates = (example or {}).get("page_candidates") or [
        {"rec": {"title": "<page title>", "url": "https://forrt.org/<page>/", "summary": "<summary>",
                 "use_when": "<use when>"}, "score": 0.0}]
    c = Capture()
    forrt_pages.ForrtPages.select(SimpleNamespace(config=config, decisions=c, listing_urls=[]), EXAMPLE_QUESTION,
                                  candidates)
    out["select"] = c.calls[0]
    generator = ResponseGenerator(None, config, None)
    out["answer_system"] = generator.system_prompt
    out["answer_template"] = generator.prompt_template
    out["marks_response"] = generator.marks_response
    today = date.today().isoformat()
    out["forrt_system"] = forrt_pages.ANSWER_SYSTEM.format(today=today, language="English")
    out["forrt_user"] = forrt_pages.ANSWER_USER.format(
        context="[1] <page title>\nURL: https://forrt.org/<page>/\n<the parts of the page that best match the question>",
        question=EXAMPLE_QUESTION, language="English", today=today)
    out["forrt_rewrite"] = forrt_pages.REWRITE_USER
    return out


_examples: Dict[int, Dict[str, Any]] = {}  # per loaded service: its index and settings stay until a restart


def worked_example(rag) -> Optional[Dict[str, Any]]:
    """The loaded search on EXAMPLE_QUESTION: similarities, the hits, what is kept, the exact answer messages.
    None while the RAG service is not loaded in this process (or is a test double). Kept per service: four
    question embeddings on CPU took ~5 s per page view."""
    if not hasattr(rag, "document_retriever"):
        return None
    if id(rag) in _examples:
        return _examples[id(rag)]
    example = _search_example(rag)
    if "error" not in example:  # a failed search is tried again on the next view
        _examples[id(rag)] = example
    return example


def _search_example(rag) -> Dict[str, Any]:
    from just_os.references import plain_metadata

    try:
        index = getattr(rag._retriever, "vector_retriever", rag._retriever)._index
        paper, page = rag.similarities(EXAMPLE_QUESTION)
        kept, found = rag.document_retriever.retrieve_and_rerank(EXAMPLE_QUESTION, {})
        sent = {id(getattr(n, "node", n)): i for i, n in enumerate(kept)}
        hits = []
        for n in found:
            meta = plain_metadata(n.node.metadata)
            hits.append({"title": meta.get("title") or "?", "type": meta.get("material_type") or "",
                         "language": meta.get("language") or "",
                         "cosine": None if n.score is None else round(1 - n.score / 2, 3),
                         "sent": sent.get(id(n.node))})
        context = rag.document_retriever.context_from_nodes(kept)
        top = found[0].node if found else None
        pages = getattr(rag, "forrt_pages", None)
        return {
            "page_candidates": pages.retrieve(EXAMPLE_QUESTION)[:2] if pages is not None else [],
            "paper": round(paper, 3), "page": round(page, 3), "hits": hits, "context": context,
            "messages": rag.response_generator._messages(EXAMPLE_QUESTION, context, None),
            "chunks": len(index.docstore.docs), "dimension": index.vector_store._faiss_index.d,
            "faiss": type(index.vector_store._faiss_index).__name__,
            "chunk": None if top is None else {
                "id": top.node_id, "text": top.text, "metadata": plain_metadata(top.metadata),
                "embedded": sorted(set(top.metadata) - set(top.excluded_embed_metadata_keys)),
                "template": top.text_template},
        }
    except Exception as e:  # the page must still show the rest
        logger.warning(f"/architecture worked example failed: {e}")
        return {"error": f"{e.__class__.__name__}: {e}"}


def constants(config: Dict[str, Any]) -> SimpleNamespace:
    """Fixed numbers and lists that live in the code, not in the settings."""
    from llama_index.core.node_parser import SentenceSplitter

    from just_os import answer_cache, hybrid, messages, qualle, reference_lookup, references

    return SimpleNamespace(
        rephrase_answer_chars=qualle.REPHRASE_ANSWER_CHARS, rewrite_max_added_words=qualle.REWRITE_MAX_ADDED_WORDS,
        history_turns=qualle.HISTORY_TURNS, intents=qualle.INTENTS, glossary_languages=qualle.GLOSSARY_LANGUAGES,
        local_word_rule=qualle.LOCAL_WORD_RULE, citations_per_100_words=references.CITATIONS_PER_100_WORDS,
        min_words=references.MIN_WORDS, glossary_type=references.GLOSSARY_TYPE, rrf_k=hybrid.RRF_K,
        title_coverage=reference_lookup.TITLE_COVERAGE, min_title_words=reference_lookup.MIN_TITLE_WORDS,
        max_matches=reference_lookup.MAX_MATCHES, cache_keys=answer_cache.NAMESPACE_KEYS,
        message_keys=messages.MESSAGE_KEYS, message_languages=sorted(messages.messages()),
        chunk_overlap=SentenceSplitter(chunk_size=config["CHUNK_SIZE"]).chunk_overlap)


def page(config: Dict[str, Any], rag=None) -> Dict[str, Any]:
    """Everything templates/architecture.html shows."""
    return {"s": Settings(config), "c": constants(config), "routers": ROUTERS, "router_text": ROUTER_TEXT,
            "routes": ROUTES, "search_modes": SEARCH_MODE_TEXT, "prompts": prompts(config, rag),
            "example": worked_example(rag), "question": EXAMPLE_QUESTION, "follow_up": EXAMPLE_FOLLOW_UP,
            "history": EXAMPLE_HISTORY}
