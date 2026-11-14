import contextvars
import html
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Generator, Iterator, Tuple

import markdown
import numpy as np
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion
import torch
from sentence_transformers import CrossEncoder

from config.settings import DEFAULT_CONFIG
from just_os.answer_cache import AnswerCache
from just_os import trace
from just_os.chat_manager import ChatManager
from just_os.decisions import DECISION_ROUTERS, DecisionClient
from just_os.forrt_lookup import ForrtLookup
from just_os import forrt_checks as checks
from just_os.forrt_pages import ForrtPages
from just_os.hybrid import vector_cosine
from just_os import messages as msg
from just_os.openscholar import generation_instance_prompts_w_references, system_prompt
from llama_index.core.schema import TextNode

from just_os.references import (
    best_snippet,
    document_key,
    paper_key,
    load_publication_years,
    passage_allowed,
    plain_metadata,
    publication_year,
    short_authors,
    reference_url,
)

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Constants for metadata keys
CREATOR_KEY = "creators"
TITLE_KEY = "title"
LICENCE_KEY = "conditions_of_use"

# Follow-up questions: the rewrite into a stand-alone question (CONTEXT_METHOD rephrase and hybrid).
# Measured on eval/context_questions.jsonl (docs/evaluation.md 3.16): the earlier prompt lost the user's details,
# returned off-topic-looking follow-ups unchanged ("something similar for neurodiversity?" was then refused)
# and only looked at the last turn.
REPHRASE_ANSWER_CHARS = 300
REPHRASE_PROMPT = """Conversation so far (oldest first):
{conversation}

New message from the user: {question}

Rewrite the new message as one question that can be understood without the conversation.
- Replace every word that points back (it, that, this, they, there, "the first thing", "the same", "something similar")
  with what it refers to. It may refer to any earlier turn, not only the last one.
- Keep everything else the user wrote: every condition, field, number, name and detail, in the user's own terms.
  Do not add details, do not answer, do not make the question broader or narrower.
- If the new message does not point back to the conversation, return it unchanged.
- Write in the language of the new message.
Example: after "What is a data paper?", "where can I publish one in ecology?" becomes
"Where can I publish a data paper in ecology?"
"""

# CONTEXT_METHOD=history: number of earlier messages passed to the answer model
HISTORY_TURNS = 4
INTENTS = ("open_science", "forrt_lookup", "off_topic")

# Greetings, thanks and questions about the bot itself get a short self-introduction (the "about"
# message) instead of a refusal or a search: "Hello" was refused, "Who are you?" answered from FORRT pages
_GREETING = (r"hi|hello|hey|hiya|howdy|greetings|good (?:morning|afternoon|evening|day)|hallo|hoi|moin|servus|"
             r"bonjour|salut|hola|ciao|namaste|merhaba|thanks|thank you(?: so much| very much)?|many thanks|cheers|"
             r"danke(?: schön)?|bedankt|merci|gracias|grazie|there|bot|chatbot|just-os")
_ABOUT = (r"(?:who|what) are you|what can you do(?: for me)?|what do you do|how can you help(?: me)?|"
          r"how (?:do|can) i use (?:this|you)|introduce yourself|what(?:'s| is) your name|who (?:made|built|created) you|"
          r"help|wer bist du|was kannst du|wie ben je|wie ben jij|wat kun je|qui es-tu|qui êtes-vous|quién eres|chi sei")
SMALL_TALK = re.compile(rf"(?:\W*\b(?:{_GREETING})\b)*\W*(?:(?:{_ABOUT})\b\W*)?", re.I)


def small_talk(text: str) -> bool:
    """True for a greeting, thanks or a question about the bot ("Hi!", "Who are you?", "Hello, what can you do?")."""
    return bool(re.search(r"\w", text)) and SMALL_TALK.fullmatch(text.strip()) is not None


def page_references(pages: List[Dict[str, Any]], start: int = 1) -> List[Dict[str, Any]]:
    """forrt.org pages ({title, url}) as entries of metadata.references, for the Sources box."""
    return [{"number": n, "authors": "", "authors_short": "", "year": "", "title": p["title"], "url": p["url"],
             "unverified": False, "snippet": ""} for n, p in enumerate(pages, start=start)]


def page_nodes(pages: List[Dict[str, Any]]) -> List[TextNode]:
    """forrt.org pages read next to the papers (FORRT_IN_PAPERS) as source nodes after the paper chunks,
    so they get [n] citations and a Sources entry like a paper. No licence: no quote under the source."""
    return [TextNode(text=p["text"], metadata={TITLE_KEY: p["title"], CREATOR_KEY: "FORRT", "link_to_resource": p["url"],
                                               "pub_year": (p.get("date") or "")[:4] or None}) for p in pages]


def page_source_lines(refs: List[Dict[str, Any]]) -> str:
    """The same entries as text lines (metadata.sources, read by the forrt.org widget)."""
    return "\n".join(f"[{r['number']}] {r['title']}. {r['url']}" for r in refs)


def visible_answer(raw: str, marked: bool) -> str:
    """The part of a streamed answer that can be shown yet (#41): with the OpenScholar
    prompt (marked) nothing before [Response_Start]; nothing after [Response_End]; and not
    a trailing "[..." that is still being written (a marker or a citation number)."""
    if marked:
        if "[Response_Start]" not in raw:
            return ""
        raw = raw.split("[Response_Start]", 1)[1]
    raw = raw.split("[Response_End]")[0]
    cut = raw.rfind("[")
    return raw[:cut] if cut != -1 and "]" not in raw[cut:] else raw

# PROMPT_STYLE=short: a short, model-neutral prompt instead of the OpenScholar prompt
# (~1.5k tokens with a worked example, made for the fine-tuned OpenScholar model)
SHORT_SYSTEM_PROMPT = (
    "You are JUST-OS, an assistant for questions about open and reproducible research. "
    "Answer only with information from the numbered sources. Cite every claim with the "
    "number of its source in square brackets, for example [0] or [2]. If the sources do "
    "not answer the question, say so."
)

# What the topic check counts as open science. Without it, Llama 3.1 8B refused short
# non-English term questions ("Was ist Replikation?", "Was ist HARKing?"): 9 of 45 wrong, 0 with it
OPEN_SCIENCE_SCOPE = """Open Science here is broad: open access, open data and materials, preregistration,
registered reports, replication and reproducibility of research findings, questionable
research practices (p-hacking, HARKing), research integrity, metascience, research
methods and statistics, scholarly publishing and peer review, and open research training.
The query can be in any language, and a short question that only asks what one of these
terms means (for example "Was ist Replikation?") is about Open Science.
Not about Open Science: everyday topics, and the same words in another field
(for example DNA replication in biology)."""

# Added to the system prompt of both PROMPT_STYLEs: the answer follows the question's
# language, but these field terms stay in English (a translated term no longer matches
# the literature, FORRT resources or what users search for).
GLOSSARY_TERMS = (
    "Open Science", "open access", "open data", "open materials", "open source",
    "preregistration", "registered report", "replication", "replicability",
    "reproducibility", "p-hacking", "HARKing", "questionable research practices",
    "publication bias", "FAIR data", "preprint", "meta-analysis", "power analysis",
    "CRediT", "FORRT",
)
# Answers are Markdown rendered with these extensions (the chat page draft uses marked, which
# also renders tables). Without "tables" a model's table came out as one line of | cells.
MARKDOWN_EXTENSIONS = ["tables"]
# Also added to both system prompts: what the page can show, and speak to the person asking
# (12 Nov: of six arena models only one answered "How should I decide which study to
# replicate?" as advice to the asker; the others wrote a general overview).
ANSWER_STYLE = (
    "Speak to the person who asked: answer their question directly as advice to them, "
    "using \"you\", not as a general overview or literature review. "
    "Your answer is shown as Markdown: use short paragraphs, bullet or numbered lists and "
    "**bold**; use a table only to compare several items, as a standard Markdown table with a "
    "header row and one row per line. Do not use HTML or headings."
)

LANGUAGE_RULE = (
    "Always answer in the language of the question, even though the sources are in English. "
    "In every language, cite only with the source number in square brackets, for example [0], "
    "never with author names and years. "
    "Keep these terms in English in every language: " + ", ".join(GLOSSARY_TERMS) + ". "
    "In a non-English answer, add the usual local word in brackets after the first use of "
    "such a term, if the language has one."
)
SHORT_PROMPT_TEMPLATE = (
    "Sources:\n{context_items}\n\nQuestion: {query}\n\n"
    "Write a clear answer of one to three short paragraphs with citations."
)


class QueryProcessor:
    """
    Handles query processing operations including classification and rephrasing.
    """

    def __init__(
        self, client_manager, config: Dict[str, Any], chat_manager: ChatManager
    ):
        """
        Initialize the query processor.

        Args:
            client_manager: OpenAI client manager
            config: Configuration dictionary
            chat_manager: Chat manager instance
        """
        self.client_manager = client_manager
        self.config = config
        self.chat_manager = chat_manager
        self.general_model = config["GENERAL_MODEL"]

    def _structured_output(self, prompt: str, key: str, value_type: str) -> Any:
        """
        Ask the general model for one JSON value.

        Tries a forced tool call first. Not every model or provider supports
        tool calls, so it then asks for plain JSON in the message content.

        Args:
            prompt: Prompt for the model
            key: Name of the value to return
            value_type: JSON schema type of the value ("boolean", "string")

        Returns:
            The value, or None if both attempts fail (for example, an API error)
        """
        messages = [{"role": "user", "content": prompt}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "structure_output",
                    "description": "Send structured output back to the user",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {key: {"type": value_type}},
                        "required": [key],
                        "additionalProperties": False,
                    },
                    "additionalProperties": False,
                },
            }
        ]
        tool_choice = {"type": "function", "function": {"name": "structure_output"}}
        temperature = self.config.get("TEMPERATURE_GENERAL", 0.3)

        response = self.client_manager.create_chat_completion(
            model=self.general_model,
            messages=messages,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
        )
        try:
            return json.loads(
                response.choices[0].message.tool_calls[0].function.arguments
            )[key]
        except (AttributeError, TypeError, KeyError, IndexError, json.JSONDecodeError):
            logger.info(f"No tool call from {self.general_model}, asking for plain JSON")

        response = self.client_manager.create_chat_completion(
            model=self.general_model,
            messages=[
                {
                    "role": "user",
                    "content": f'{prompt}\nReply with only a JSON object with the key "{key}".',
                }
            ],
            temperature=temperature,
        )
        try:
            content = response.choices[0].message.content
            return json.loads(content[content.index("{") : content.rindex("}") + 1])[key]
        except (AttributeError, TypeError, KeyError, IndexError, ValueError) as e:
            logger.error(f"Structured output failed for '{key}': {str(e)}")
            return None

    def classify_query(self, query: str) -> Optional[bool]:
        """
        Classify whether a query is about Open Science.

        Args:
            query: User query

        Returns:
            True or False, or None if the model could not be reached or parsed
            (an error, which must not look like a refusal)
        """
        prompt = f"""You are an Open Science expert.
Classify whether the following query is about Open Science.
{OPEN_SCIENCE_SCOPE}
Query: "{query}"
Return your answer as a valid JSON object with a single boolean entry "concerns_open_science"
"""
        result = self._structured_output(prompt, "concerns_open_science", "boolean")
        if not isinstance(result, bool):
            logger.error(f"Failed to classify query, got: {result!r}")
            return None
        return result

    def classify_intent(self, query: str) -> Optional[str]:
        """
        Route a query (FORRT_LOOKUP=true): "open_science" (explained answer with sources),
        "forrt_lookup" (find a FORRT resource or a way to take part) or "off_topic".

        Returns:
            One of INTENTS, or None if the model could not be reached or parsed
        """
        prompt = f"""You route questions for JUST-OS, the chatbot of FORRT (Framework for Open and Reproducible Research Training).
Classify the query into one category:
- "open_science": a question about open science or research practice that needs an explained answer
- "forrt_lookup": the user wants to find a FORRT resource, course, reading or page, or asks how to get involved with FORRT
- "off_topic": anything else
{OPEN_SCIENCE_SCOPE}
Query: "{query}"
Return your answer as a valid JSON object with a single string entry "category"
"""
        result = self._structured_output(prompt, "category", "string")
        result = result.strip().lower() if isinstance(result, str) else None
        if result not in INTENTS:
            logger.error(f"Failed to classify intent, got: {result!r}")
            return None
        return result

    @trace.step("rephrase", lambda result, self, query, chat_id: {"from": query, "to": result})
    def rephrase_query(self, query: str, chat_id: str) -> str:
        """
        Rephrase a query based on conversation history.

        Args:
            query: User query
            chat_id: Chat session ID

        Returns:
            Rephrased query, or the original query if rephrasing fails
        """
        # Get conversation history
        conversation_history = self.chat_manager.get_history(chat_id)

        # Build prompt. Answers are cut short: the rewrite must take its words from the user, not from
        # an answer ("single-blind" became "double-blind" from a list of review types, docs/evaluation.md)
        lines = []
        for message in conversation_history:
            text = " ".join(str(message["content"]).split())
            if message["role"] != "user" and len(text) > REPHRASE_ANSWER_CHARS:
                text = text[:REPHRASE_ANSWER_CHARS] + " ..."
            lines.append(f"{'User' if message['role'] == 'user' else 'Assistant'}: {text}")
        prompt = REPHRASE_PROMPT.format(conversation="\n".join(lines), question=query)

        result = self._structured_output(prompt, "reformulated_query", "string")
        if not isinstance(result, str) or not result.strip():
            logger.warning("Failed to rephrase query, using original")
            return query
        return result


class DocumentRetriever:
    """
    Handles document retrieval and reranking operations.
    """

    def __init__(self, config: Dict[str, Any], retriever):
        """
        Initialize the document retriever.

        Args:
            config: Configuration dictionary
            retriever: Retriever component
        """
        self.config = config
        self._retriever = retriever
        # The container sets OMP_NUM_THREADS=1; the re-ranker is ~2x faster with 6 threads
        torch.set_num_threads(config.get("RERANK_THREADS", 6))
        self.rerank = config.get("RERANK", True)
        self.search_mode = config.get("SEARCH_MODE", "vector")
        self.min_vector_similarity = config.get("MIN_VECTOR_SIMILARITY", DEFAULT_CONFIG["MIN_VECTOR_SIMILARITY"])
        # VERIFY_CITATIONS also scores with the re-ranker model
        needed = self.rerank or config.get("VERIFY_CITATIONS")
        self.reranker = CrossEncoder(config["RERANK_MODEL"]) if needed else None
        self.verify_min_score = config.get("VERIFY_MIN_SCORE", 0.1)
        self.n_context_items = config["MAX_CHUNKS"]
        self.min_relevance = config["MIN_RELEVANCE"]
        self.max_per_doc = config.get("MAX_CHUNKS_PER_DOC", 0)
        self.adaptive_top_k = config.get("ADAPTIVE_TOP_K", False)
        self.adaptive_ratio = config.get("ADAPTIVE_TOP_K_RATIO", 0.5)
        self.adaptive_min = config.get("ADAPTIVE_TOP_K_MIN", 3)

    @trace.step("citation check", lambda result, *a, **k: {"unverified": sorted(result)})
    def unsupported_citations(self, text: str, nodes: List[Any]) -> set:
        """
        VERIFY_CITATIONS: score each (cited sentence, cited chunk) pair with the re-ranker.
        A source number whose best score is below VERIFY_MIN_SCORE is "not verified".

        Returns:
            Indices of the cited nodes that no citing sentence is supported by
        """
        pairs, refs = [], []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            claim = re.sub(r"\[\d+\]", "", sentence).strip()
            for ref in {int(m) for m in re.findall(r"\[(\d+)\]", sentence)}:
                if claim and ref < len(nodes):
                    pairs.append((claim, self.node_to_text(nodes[ref])))
                    refs.append(ref)
        if not pairs or self.reranker is None:
            return set()
        try:
            scores = self.reranker.predict(pairs)
        except Exception as e:
            logger.error(f"Citation check failed, showing all citations: {e}")
            return set()
        best: Dict[int, float] = {}
        for ref, score in zip(refs, scores):
            best[ref] = max(best.get(ref, 0.0), float(score))
        return {ref for ref, score in best.items() if score < self.verify_min_score}

    def limit_per_document(self, nodes: List[Any]) -> List[Any]:
        """Keep at most MAX_CHUNKS_PER_DOC chunks of one paper (0 = no limit), then MAX_CHUNKS."""
        if self.max_per_doc > 0:
            counts: Dict[str, int] = {}
            kept = []
            for node in nodes:
                key = document_key(node.metadata)
                counts[key] = counts.get(key, 0) + 1
                if counts[key] <= self.max_per_doc:
                    kept.append(node)
            nodes = kept
        return nodes[: self.n_context_items]

    def search_order(self, query: str, nodes: List[Any]) -> List[Any]:
        """RERANK=false: the chunks in search order, or none ("no sources") when the best vector
        match is below MIN_VECTOR_SIMILARITY. BM25 scores have no fixed scale, so bm25 search
        has no such check."""
        if self.search_mode != "bm25" and self.min_vector_similarity > 0:
            cosine = vector_cosine(nodes)
            if cosine is not None and cosine < self.min_vector_similarity:
                logger.info(f"No sources: best vector match {cosine:.3f} < MIN_VECTOR_SIMILARITY for {query[:60]!r}")
                return []
        return self.limit_per_document(nodes)

    def node_to_text(self, node) -> str:
        """
        Convert a node to a text representation.

        Args:
            node: Node to convert

        Returns:
            Text representation of the node
        """
        return f"Title: {plain_metadata(node.metadata).get(TITLE_KEY, 'Unknown Title')} Text: {' '.join(node.text.split())}"

    def context_from_nodes(self, nodes: List[Any]) -> str:
        """
        Format context from retrieved nodes.

        Args:
            nodes: List of retrieved nodes

        Returns:
            Formatted context string
        """
        try:
            return "\n".join(
                f"[{idx}] {self.node_to_text(node)} " for idx, node in enumerate(nodes)
            )
        except Exception as e:
            logger.error(f"Error formatting context: {str(e)}")
            return ""

    @trace.step("sources", lambda result, *a, **k: {"retrieved": len(result[1]), "kept": len(result[0])})
    def retrieve_and_rerank(
        self, query: str, timings: Optional[Dict[str, float]] = None
    ) -> Tuple[List[Any], List[Any]]:
        """
        Retrieve and rerank documents for a query.

        Args:
            query: User query
            timings: filled with search_s (vector/BM25 search) and rerank_s (re-ranker)

        Returns:
            Tuple of (ranked nodes, all retrieved nodes)
        """
        timings = {} if timings is None else timings
        # Retrieve relevant nodes
        start = time.time()
        nodes = self._retriever.retrieve(query)
        retrieved = time.time()
        timings["search_s"] = retrieved - start

        if not nodes:
            return [], []

        if not self.rerank:
            ordered = self.search_order(query, nodes)
            if trace.active():
                # vector search scores are FAISS L2 distances of unit vectors: as cosine (vector_cosine), higher = closer
                cosine = self.search_mode == "vector"
                self.trace_sources([((1 - n.score / 2) if cosine and n.score is not None else n.score, n) for n in nodes],
                                   ordered, None, "cosine" if cosine else "search")
            return ordered, nodes

        try:
            scores = self.reranker.predict(
                [(query, self.node_to_text(node)) for node in nodes]
            )
            timings["rerank_s"] = time.time() - retrieved
            logger.info(
                f"Timing: retrieval {retrieved - start:.1f}s, re-rank {timings['rerank_s']:.1f}s "
                f"({len(nodes)} chunks)"
            )
        except Exception as e:
            # Fall back to vector order so a reranker failure never empties the answer
            logger.error(f"Reranking failed, using vector order: {str(e)}")
            return self.limit_per_document(nodes), nodes

        ranked = sorted(zip(scores, nodes), key=lambda pair: pair[0], reverse=True)

        kept = [(score, node) for score, node in ranked if score > self.min_relevance]
        cutoff = None
        if self.adaptive_top_k and kept:
            # a targeted question keeps only its few strong chunks, a broad one up to MAX_CHUNKS
            cutoff = float(kept[0][0]) * self.adaptive_ratio
            kept = [pair for i, pair in enumerate(kept) if i < self.adaptive_min or pair[0] >= cutoff]
        ranked_nodes = self.limit_per_document([node for _, node in kept])
        if trace.active():
            self.trace_sources(ranked, ranked_nodes, cutoff, "rerank")

        return ranked_nodes, nodes

    def trace_sources(self, scored: List[Tuple[Any, Any]], sent: List[Any], cutoff: Optional[float], kind: str) -> None:
        """Debug panel: every retrieved chunk with its score, and why it was not sent to the model."""
        sent_ids = {id(node): i for i, node in enumerate(sent)}
        rows = []
        for rank, (score, node) in enumerate(scored):
            meta = plain_metadata(node.metadata)
            score = None if score is None else float(score)
            if id(node) in sent_ids:
                why = None
            elif kind == "rerank" and score is not None and score <= self.min_relevance:
                why = "below minimum relevance"
            elif kind == "cosine" and not sent and self.min_vector_similarity > 0:
                why = "best match below minimum similarity"
            elif cutoff is not None and score is not None and score < cutoff and rank >= self.adaptive_min:
                why = "below adaptive cut-off"
            else:
                why = "paper or chunk limit"
            rows.append({"title": meta.get(TITLE_KEY) or "Unknown title", "url": meta.get("link_to_resource") or meta.get("doi") or "",
                         "score": None if score is None else round(score, 4), "sent": id(node) in sent_ids,
                         "n": sent_ids.get(id(node)), "why": why, "text": " ".join(node.text.split())[:400]})
        floor = {"rerank": self.min_relevance, "cosine": self.min_vector_similarity or None}.get(kind)
        trace.note(sources={"kind": kind, "min_relevance": floor,
                            "cutoff": cutoff, "max_chunks": self.n_context_items, "max_per_doc": self.max_per_doc,
                            "chunks": rows})


class ResponseGenerator:
    """
    Handles response generation and processing.
    """

    def __init__(
        self,
        client_manager: "OpenAIClientManager",
        config: Dict[str, Any],
        reference_processor: "ReferenceProcessor",
    ):
        """
        Initialize the response generator.

        Args:
            client_manager: OpenAI client manager
            config: Configuration dictionary
            reference_processor: Reference processor instance
        """
        self.client_manager = client_manager
        self.config = config
        self.reference_processor = reference_processor
        self.citation_model = config["CITATION_MODEL"]
        if config.get("PROMPT_STYLE", "openscholar") == "short":
            self.system_prompt = SHORT_SYSTEM_PROMPT + " " + LANGUAGE_RULE + " " + ANSWER_STYLE
            self.prompt_template = SHORT_PROMPT_TEMPLATE
        else:
            self.system_prompt = system_prompt + " " + LANGUAGE_RULE + " " + ANSWER_STYLE
            self.prompt_template = generation_instance_prompts_w_references
        # The OpenScholar prompt asks for [Response_Start] ... [Response_End]
        self.marks_response = config.get("PROMPT_STYLE", "openscholar") != "short"

    def _messages(self, query: str, context: str, history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        prompt = self.prompt_template.format(context_items=context, query=query)
        return [
            {"role": "system", "content": self.system_prompt},
            # CONTEXT_METHOD=history: the earlier turns of the chat
            *[{"role": m["role"], "content": m["content"]} for m in history or []],
            {"role": "user", "content": prompt},
        ]

    @trace.step("answer")
    def stream_response(
        self,
        query: str,
        context: str,
        model: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Iterator[str]:
        """The raw answer in pieces while the model writes it (#41)."""
        yield from self.client_manager.stream_chat_completion(
            model=model or self.citation_model,
            messages=self._messages(query, context, history),
            temperature=self.config.get("TEMPERATURE", 0.3),
            max_tokens=self.config.get("MAX_ANSWER_TOKENS"),
        )

    @trace.step("answer")
    def generate_response(
        self,
        query: str,
        context: str,
        model: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        """
        Generate a response using the LLM.

        Args:
            query: User query
            context: Context for the query
            model: Model to use instead of CITATION_MODEL (used by the arena)

        Returns:
            Generated response or None if generation fails
        """
        response = self.client_manager.create_chat_completion(
            model=model or self.citation_model,
            messages=self._messages(query, context, history),
            temperature=self.config.get("TEMPERATURE", 0.3),
            max_tokens=self.config.get("MAX_ANSWER_TOKENS"),
        )

        if not response or not response.choices:
            logger.error("Failed to generate response")
            return None

        return response.choices[0].message.content

    def post_process_response(self, raw_response: str) -> str:
        """
        Extract the actual response from the raw LLM output.

        Args:
            raw_response: Raw response from the LLM

        Returns:
            Processed response
        """
        try:
            response = raw_response
            if "[Response_Start]" in response:
                response = response.split("[Response_Start]", 1)[1]
            if "[Response_End]" in response:
                response = response.split("[Response_End]")[0]
            return checks.autolink(response)
        except Exception as e:
            logger.error(f"Error post-processing response: {str(e)}")
            return raw_response

    def process_with_references(
        self, processed_message: str, nodes: List[Any], unverified: frozenset = frozenset()
    ) -> Tuple[str, List[int]]:
        """
        Process a response with references.

        Args:
            processed_message: Processed response message
            nodes: List of reference nodes

        Returns:
            Tuple of (HTML message with references, list of used reference indices)
        """
        return self.reference_processor.process_markdown_with_references(
            processed_message, nodes, unverified
        )


class OpenAIClientManager:
    """
    Manages OpenAI client creation and API calls.
    Provides error handling and retry logic.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI client manager.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.api_key = config["LLM_API_KEY"]
        if not self.api_key:
            logger.warning("LLM_API_KEY / OPENROUTER_API_KEY environment variable not set")

        self.client = self._create_client(self.api_key, config["BASE_URL"])
        # The self-hosted OpenScholar server has its own URL and key
        self.openscholar_client = (
            self._create_client(
                config.get("OPENSCHOLAR_API_KEY"),
                config["OPENSCHOLAR_BASE_URL"],
                # self-hosted on CPU: minutes for a long prompt; a retry would only double that
                timeout=config.get("OPENSCHOLAR_TIMEOUT", 600),
                retries=0,
            )
            if config.get("OPENSCHOLAR_BASE_URL")
            else None
        )

    def _client_for(self, model: str) -> Optional[OpenAI]:
        if self.openscholar_client and model == self.config.get("OPENSCHOLAR_MODEL"):
            return self.openscholar_client
        return self.client

    def _create_client(
        self, api_key: Optional[str], base_url: str, timeout: Optional[float] = None, retries: int = 0
    ) -> Optional[OpenAI]:
        """
        Create an OpenAI client instance.

        Returns:
            OpenAI client or None if initialization fails
        """
        try:
            # A hard time limit: one slow model must not hold up a whole answer or arena round
            return OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout or self.config.get("LLM_TIMEOUT", 60),
                max_retries=retries,  # 0: create_chat_completion retries (LLM_RETRIES), so they do not multiply
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            return None

    def no_reasoning(self, model: str) -> Dict[str, Any]:
        """NO_REASONING_MODELS reason by default and spent the whole answer cap on it: Qwen 3.7 Flash gave
        172 empty answers of 2,000 tokens (eval 13 Nov). Only these get the field; others may refuse it."""
        listed = {m.strip() for m in self.config.get("NO_REASONING_MODELS", "").split(",") if m.strip()}
        return {"extra_body": {"reasoning": {"enabled": False}}} if model in listed else {}

    def create_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[ChatCompletion]:
        """
        Create a chat completion with error handling.

        Args:
            model: Model name to use
            messages: List of message dictionaries
            temperature: Sampling temperature
            tools: Optional list of tools
            tool_choice: Optional tool choice

        Returns:
            ChatCompletion or None if the request fails
        """
        client = self._client_for(model)
        if not client:
            logger.error("OpenAI client not initialized")
            return None

        kwargs = {"model": model, "messages": messages, "temperature": temperature, **self.no_reasoning(model)}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        traced = trace.active() is not None
        if traced:
            if self.usage_request(client):
                kwargs["extra_body"] = {**kwargs.get("extra_body", {}), **self.usage_request(client)}
            started, attempts = time.perf_counter(), 0

        # The first try plus LLM_RETRIES more on a provider error, a time-out or an empty answer; only
        # then does the user see an error (and Try again). OpenScholar is not retried: it takes minutes
        retries = 0 if model == self.config.get("OPENSCHOLAR_MODEL") else self.config.get("LLM_RETRIES", 3)
        response = None
        for attempt in range(retries + 1):
            if attempt:
                time.sleep(min(2 ** (attempt - 1), 4))
            if traced:
                attempts = attempt + 1
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as e:
                logger.error(f"OpenAI API error ({model}, try {attempt + 1} of {retries + 1}): {str(e)}")
                response = None
                continue
            choice = response.choices[0] if response and response.choices else None
            if tools or (choice and (choice.message.content or "").strip()):
                if traced:
                    trace.llm_call(model, started, getattr(response, "usage", None), attempts=attempts)
                return response
            logger.warning(f"Empty answer from {model} (try {attempt + 1} of {retries + 1})")
            if choice and choice.finish_reason == "length" and "reasoning" not in kwargs.get("extra_body", {}):
                # a reasoning model (gpt-oss) used the whole token cap on reasoning and wrote no answer
                # (19 of 172 FORRT-page answers, eval 13 Nov): the next tries reason less
                kwargs["extra_body"] = {**kwargs.get("extra_body", {}), "reasoning": {"effort": "low"}}
        if traced:
            trace.llm_call(model, started, getattr(response, "usage", None), attempts=attempts,
                           error=None if response else "no answer after all tries")
        return response

    def usage_request(self, client: OpenAI) -> Dict[str, Any]:
        """Debug trace: ask OpenRouter to report the cost of the call (other servers do not know the field)."""
        return {"usage": {"include": True}} if "openrouter.ai" in str(client.base_url) else {}

    def stream_chat_completion(
        self, model: str, messages: List[Dict[str, str]], temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """The answer text in pieces as the model writes it. An error ends the stream; the
        caller treats an empty answer like a failed call.
        shortcut: LLM_TIMEOUT limits each wait for a piece, not the whole answer; add a
        deadline if a model ever trickles text for minutes (PR #40 has one)."""
        client = self._client_for(model)
        if not client:
            logger.error("OpenAI client not initialized")
            return
        options = {**({"max_tokens": max_tokens} if max_tokens else {}), **self.no_reasoning(model)}
        traced = trace.active() is not None
        if traced:  # debug trace: the last chunk then carries the token counts (and the cost on OpenRouter)
            body = {**options.get("extra_body", {}), **self.usage_request(client)}
            options.update(stream_options={"include_usage": True}, **({"extra_body": body} if body else {}))
        started, usage, error = time.perf_counter(), None, None
        try:
            for chunk in client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, stream=True, **options,
            ):
                usage = getattr(chunk, "usage", None) or usage
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield choice.delta.content
        except Exception as e:
            logger.error(f"OpenAI API error (stream): {str(e)}")
            error = str(e)
        finally:
            if traced:
                trace.llm_call(model, started, usage, error=error, stream=True)


class ReferenceProcessor:
    """
    Turns [n] citations into clickable references and a source list.

    One number per document (chunks of the same paper share it), the publication
    year (not the form time stamp), https://doi.org/ links, and the passage only
    when the licence allows it.
    """

    def __init__(self, pub_years: Optional[Dict[str, str]] = None):
        self.pub_years = pub_years or {}

    def reference_data(self, node, unverified: bool = False) -> Dict[str, Any]:
        """Tooltip data for one cited chunk. The front end inserts it as text, not HTML."""
        meta = plain_metadata(node.metadata)
        return {
            "unverified": unverified,
            "title": meta.get(TITLE_KEY, "Unknown Title"),
            "authors": meta.get(CREATOR_KEY, "Unknown Author"),
            "year": publication_year(meta, self.pub_years),
            "url": reference_url(meta),
            "text": node.text if passage_allowed(meta.get(LICENCE_KEY)) else "",
        }

    def process_markdown_with_references(
        self, markdown_text: str, references_nodes: List[Any], unverified: frozenset = frozenset()
    ) -> Tuple[str, List[int]]:
        """
        Convert markdown to HTML and add clickable references with tooltips.

        Args:
            markdown_text: Markdown text with references
            references_nodes: List of reference nodes

        Returns:
            Tuple of (HTML text with clickable references, list of node indices:
            the first cited chunk of each document, in order of appearance)
        """
        try:
            html_text = markdown.markdown(markdown_text, extensions=MARKDOWN_EXTENSIONS)
            soup = BeautifulSoup(html_text, "html.parser")
            reference_pattern = r"\[(\d+)\]"
            text_nodes = soup.find_all(string=True)

            used_refs_ordered = []  # first node index of each cited document
            doc_numbers = {}  # document key -> new number
            ref_mapping = {}  # old node index -> new number

            # First pass - number documents in order of appearance
            for text in text_nodes:
                for match in re.finditer(reference_pattern, text):
                    ref_idx = int(match.group(1))
                    if ref_idx >= len(references_nodes) or ref_idx in ref_mapping:
                        continue
                    key = paper_key(plain_metadata(references_nodes[ref_idx].metadata))
                    if key not in doc_numbers:
                        doc_numbers[key] = len(doc_numbers) + 1
                        used_refs_ordered.append(ref_idx)
                    ref_mapping[ref_idx] = doc_numbers[key]

            logger.debug(f"Used refs: {used_refs_ordered}, mapping: {ref_mapping}")

            # Second pass - replace references with new numbers
            for text in text_nodes:
                matches = list(re.finditer(reference_pattern, text))
                if not matches:
                    continue
                new_text = text
                # Right to left, so earlier positions stay valid
                for i in reversed(range(len(matches))):
                    match = matches[i]
                    old_ref_num = int(match.group(1))
                    if old_ref_num not in ref_mapping:
                        continue
                    start, end = match.span()
                    nxt = matches[i + 1] if i + 1 < len(matches) else None
                    # "[0][2]" with both chunks from one paper would show "[1][1]": keep one
                    if nxt and nxt.start() == end and ref_mapping.get(int(nxt.group(1))) == ref_mapping[old_ref_num]:
                        new_text = new_text[:start] + new_text[end:]
                        continue
                    # Each citation keeps the passage of the chunk it cites
                    data_string = json.dumps(
                        self.reference_data(
                            references_nodes[old_ref_num], old_ref_num in unverified
                        ),
                        ensure_ascii=True,
                        separators=(",", ":"),
                    )
                    reference_html = (
                        f'<a href="#" class="reference-link" '
                        f'data-reference="{html.escape(data_string, quote=True)}">'
                        f"[{ref_mapping[old_ref_num]}]"
                        f"</a>"
                    )
                    new_text = new_text[:start] + reference_html + new_text[end:]
                text.replace_with(BeautifulSoup(new_text, "html.parser"))

            return str(soup), used_refs_ordered
        except Exception as e:
            logger.error(f"Error processing references: {str(e)}")
            return markdown.markdown(markdown_text, extensions=MARKDOWN_EXTENSIONS), []

    def reference_list(
        self,
        nodes: List[Any],
        used_refs_ordered: Optional[List[int]] = None,
        unverified: frozenset = frozenset(),
        answer: str = "",
    ) -> List[Dict[str, Any]]:
        """The source list as data, one entry per document, for the page to format.
        With the answer (Markdown with the original [n] numbers) each entry gets a snippet."""
        snippets = self.snippets(nodes, answer)
        if used_refs_ordered is None:
            seen, used_refs_ordered = set(), []
            for idx, node in enumerate(nodes):
                key = paper_key(plain_metadata(node.metadata))
                if key not in seen:
                    seen.add(key)
                    used_refs_ordered.append(idx)
        flagged = {paper_key(plain_metadata(nodes[i].metadata)) for i in unverified if i < len(nodes)}
        entries = []
        for number, ref_idx in enumerate((i for i in used_refs_ordered if i < len(nodes)), start=1):
            data = self.reference_data(nodes[ref_idx])
            entries.append({
                "number": number,
                "authors": data["authors"],
                "authors_short": short_authors(data["authors"]),
                "year": data["year"],
                "title": data["title"],
                "url": data["url"],
                "unverified": paper_key(plain_metadata(nodes[ref_idx].metadata)) in flagged,
                "snippet": snippets.get(paper_key(plain_metadata(nodes[ref_idx].metadata)), ""),
            })
        return entries

    def snippets(self, nodes: List[Any], answer: str) -> Dict[str, str]:
        """Per document: the sentence of a cited chunk that best matches the first answer
        sentence citing it. Only for licences that allow showing a passage."""
        found: Dict[str, str] = {}
        for sentence in re.split(r"(?<=[.!?])\s+", answer):
            claim = re.sub(r"\[\d+\]", "", sentence).strip()
            for ref in sorted({int(m) for m in re.findall(r"\[(\d+)\]", sentence)}):
                if not claim or ref >= len(nodes):
                    continue
                meta = plain_metadata(nodes[ref].metadata)
                key = paper_key(meta)
                if key not in found and passage_allowed(meta.get(LICENCE_KEY)):
                    found[key] = best_snippet(claim, nodes[ref].text)
        return found

    def references_from_nodes(
        self,
        nodes: List[Any],
        used_refs_ordered: Optional[List[int]] = None,
        unverified: frozenset = frozenset(),
    ) -> str:
        """
        Generate the source list, one line per document.

        Args:
            nodes: List of reference nodes
            used_refs_ordered: Node indices in order of appearance (one per document).
                              If None, every document in nodes is listed in order.

        Returns:
            Formatted reference list as a string
        """
        try:
            if used_refs_ordered is None:
                seen = set()
                used_refs_ordered = []
                for idx, node in enumerate(nodes):
                    key = paper_key(plain_metadata(node.metadata))
                    if key not in seen:
                        seen.add(key)
                        used_refs_ordered.append(idx)

            flagged = {paper_key(plain_metadata(nodes[i].metadata)) for i in unverified if i < len(nodes)}
            lines = []
            for number, ref_idx in enumerate(
                (i for i in used_refs_ordered if i < len(nodes)), start=1
            ):
                data = self.reference_data(nodes[ref_idx])
                lines.append(
                    f"[{number}] {data['authors']} ({data['year']}). {data['title']}."
                    + (f" {data['url']}" if data["url"] else "")
                    + (" [not verified]" if paper_key(plain_metadata(nodes[ref_idx].metadata)) in flagged else "")
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error generating references: {str(e)}")
            return "References could not be generated due to an error."


class Qualle:
    """
    Main RAG service implementation that handles queries and responses.
    """

    # set in __init__ when DECISION_ROUTER / FORRT_PAGES are on (class defaults keep test doubles working)
    decisions: Optional[DecisionClient] = None
    forrt_pages: Optional[ForrtPages] = None

    def __init__(
        self, config: Dict[str, Any], chat_manager: ChatManager, embed_model, retriever
    ):
        """
        Initialize the Qualle RAG service.

        Args:
            config: Configuration dictionary
            chat_manager: Chat manager instance
            embed_model: Embedding model
            retriever: Retriever component
        """
        self.config = config
        self.chat_manager = chat_manager
        self._embed_model = embed_model
        self._retriever = retriever

        # Initialize OpenAI client manager
        self.client_manager = OpenAIClientManager(config)

        # Initialize reference processor
        self.reference_processor = ReferenceProcessor(
            load_publication_years(config.get("PUB_YEARS_FILE"))
        )

        # Initialize query processor
        self.query_processor = QueryProcessor(self.client_manager, config, chat_manager)

        # Initialize document retriever
        self.document_retriever = DocumentRetriever(config, retriever)

        # Initialize response generator
        self.response_generator = ResponseGenerator(
            self.client_manager, config, self.reference_processor
        )

        # FORRT lookup mode: three-way routing and a keyword search over the FORRT sheet
        self.forrt_lookup = (
            ForrtLookup(config["FORRT_SHEET_FILE"], config.get("FORRT_LOOKUP_TOP_K", 5))
            if config.get("FORRT_LOOKUP")
            else None
        )

        # Decision-model router and FORRT page router (DECISION_ROUTER, FORRT_PAGES)
        self.decisions = DecisionClient(config) if (config.get("DECISION_ROUTER") or config.get("FORRT_PAGES")) else None
        self.forrt_pages = None
        if config.get("FORRT_PAGES"):
            try:
                self.forrt_pages = ForrtPages(config, embed_model, self.client_manager, self.decisions)
            except Exception as e:  # missing or broken index: start without the FORRT route, never crash
                logger.error(f"FORRT_PAGES is on but the page index could not be loaded ({e}); "
                             "run scripts/build_forrt_pages.py. FORRT questions use the other routes.")

        # Semantic answer cache (off when ANSWER_CACHE_TTL is 0)
        self.answer_cache = (
            AnswerCache(chat_manager.redis, embed_model, config)
            if config.get("ANSWER_CACHE_TTL")
            else None
        )

        # Refusal and error texts in the language of the question (just_os/messages.py)
        msg.preload()

        logger.debug("Qualle service initialized")

    def similarities(self, query: str) -> Tuple[float, float]:
        """bge-m3 cosine of the question to the nearest paper chunk (FAISS) and to the nearest
        FORRT page description (-1 without FORRT pages)."""
        q = np.asarray([self._embed_model.get_query_embedding(query)], dtype=np.float32)
        q /= np.linalg.norm(q)
        vector_retriever = getattr(self._retriever, "vector_retriever", self._retriever)  # bm25 and hybrid wrap it
        distance, _ = vector_retriever._index.vector_store._faiss_index.search(q, 1)
        paper = 1 - float(distance[0][0]) / 2  # squared L2 of unit vectors → cosine
        page = float((self.forrt_pages.vectors @ q[0]).max()) if self.forrt_pages is not None else -1.0
        trace.note(similarity={"paper": round(paper, 4), "page": round(page, 4)})
        return paper, page

    def cosine_route(self, query: str) -> str:
        """Cosine router (no model call): above COSINE_PAPER_MIN → papers, above COSINE_PAGE_MIN →
        FORRT pages, both above → the closer one, neither → off topic.
        Thresholds from eval/questions.jsonl + eval/forrt_questions.jsonl (docs/evaluation.md 3.7)."""
        paper, page = self.similarities(query)
        is_paper = paper >= self.config.get("COSINE_PAPER_MIN", 0.62)
        is_page = page >= self.config.get("COSINE_PAGE_MIN", 0.51)
        logger.info(f"Cosine router: paper {paper:.3f}, page {page:.3f}")
        if is_paper and is_page:
            return "open_science" if paper > page else "forrt"
        return "open_science" if is_paper else ("forrt" if is_page else "off_topic")

    def banded_route(self, query: str) -> Optional[str]:
        """Three bands of similarity (eval/tune_bands.py, docs/evaluation.md 3.11): below both low
        thresholds → off topic, with no model call; close to the papers (at or above BAND_PAPER_HIGH)
        and not close to a FORRT page (below BAND_PAGE_HIGH) → papers, with no model call; anything
        else, including every question close to a FORRT page, → BAND_MIDDLE_ROUTER decides. Paper and
        page similarities are on different scales, so similarity never routes to FORRT on its own.
        The bands are set strictly: answering an off-topic question counts as the worse error."""
        paper, page = self.similarities(query)
        c = {**DEFAULT_CONFIG, **self.config}
        measured = self.forrt_pages is not None  # without FORRT pages, page is -1, not a similarity
        if measured and paper < c["BAND_PAPER_LOW"] and page < c["BAND_PAGE_LOW"]:
            band, route = "low", "off_topic"
        elif paper >= c["BAND_PAPER_HIGH"] and page < c["BAND_PAGE_HIGH"]:
            band, route = "high", "open_science"
        else:
            band = "middle"
            middle = c["BAND_MIDDLE_ROUTER"]
            route = self.route(query, "jev" if middle in ("banded", "") else middle)  # "" would mean ROUTER
        logger.info(f"Banded router: paper {paper:.3f}, page {page:.3f}, {band} band -> {route}")
        return route

    @trace.step("topic check", lambda result, self, query, router=None: {"route": result, "router": router or self.config.get("ROUTER") or ""})
    def route(self, query: str, router: Optional[str] = None) -> Optional[str]:
        """open_science / forrt / both / off_topic / small_talk (or forrt_lookup from the LLM classifier); None = model error.

        router (one of ROUTERS; the chat and arena dropdowns, eval/classify.py) picks one strategy:
        a decision model (clef-flash, clef, jev) with the LLM classifier only when the call fails,
        "llm" (the LLM classifier alone), "cosine" (cosine_route), "banded" (banded_route) or "none" (no check: every question
        gets the papers and the FORRT pages; MIN_RELEVANCE still stops unrelated ones as "no sources").
        Without router (default): DECISION_ROUTER with DECISION_ROUTER_MODEL when it is confident
        enough, else the LLM classifier.
        """
        if small_talk(query):
            return "small_talk"
        router = router or self.config.get("ROUTER") or ""
        if router == "none":
            return "both"
        if router == "cosine":
            return self.cosine_route(query)
        if router == "banded":
            return self.banded_route(query)
        if router in DECISION_ROUTERS:
            self.decisions = self.decisions or DecisionClient(self.config)
            route, p, info = self.decisions.route(DECISION_ROUTERS[router], query)
            logger.info(f"Timing: decision router {router} {info.get('ms')} ms -> {route} (p={p:.2f})")
            if route:
                return "off_topic" if route == "neither" else route
        elif router != "llm" and self.config.get("DECISION_ROUTER") and self.decisions is not None:
            route, p, info = self.decisions.route(self.config.get("DECISION_ROUTER_MODEL", "cloudflare/clef"), query)
            logger.info(f"Timing: decision router {info.get('ms')} ms -> {route} (p={p:.2f})")
            if route and p >= self.config.get("DECISION_ROUTER_MIN_CONFIDENCE", 0.5):
                return "off_topic" if route == "neither" else route
        if (self.config.get("FORRT_LOOKUP") and self.forrt_lookup is not None) or self.forrt_pages is not None:
            return self.query_processor.classify_intent(query)
        is_open_science = self.query_processor.classify_query(query)
        return None if is_open_science is None else ("open_science" if is_open_science else "off_topic")

    def no_relevant_nodes_handler(
        self, query: str, chat_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Handle the case when no relevant nodes are found.

        Args:
            query: User query
            chat_id: Chat session ID

        Yields:
            Response message
        """
        logger.warning(f"No relevant nodes found for query: {query}")
        text = msg.message("no_sources", query)
        self.chat_manager.add_message(chat_id, {"role": "user", "content": query})
        self.chat_manager.add_message(chat_id, {"role": "assistant", "content": text})
        yield {"status": "complete", "message": markdown.markdown(text), "outcome": "no_sources"}

    def get_response(
        self, query: str, chat_id: str, model: Optional[str] = None, stream: bool = False,
        router: Optional[str] = None, debug: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """The response messages (see _respond). Every final message also gets "timings":
        seconds for classify_s (topic check), search_s, rerank_s, answer_s (LLM, with the
        retry) and total_s; a step that did not run is missing (refusals stop early).
        debug: the final message also gets "debug", the trace of the turn (just_os/trace.py)."""
        timings: Dict[str, float] = {}
        start = time.time()
        token = trace.begin() if debug else None
        try:
            if debug:
                trace.note(settings=self.debug_settings(model, router))
            for message in self._respond(query, chat_id, model, stream, router, timings):
                if message.get("status") in ("complete", "error"):
                    done = {k: round(v, 2) for k, v in timings.items()}
                    message = {**message, "timings": {**done, "total_s": round(time.time() - start, 2)}}
                    if debug:
                        message["debug"] = trace.active().export(message["timings"])
                yield message
        finally:
            if token is not None:
                trace.end(token)

    def debug_settings(self, model: Optional[str], router: Optional[str]) -> Dict[str, Any]:
        """The settings that shape an answer, for the debug panel (thresholds next to the scores)."""
        c = self.config
        keys = ("GENERAL_MODEL", "CONTEXT_METHOD", "DECISION_ROUTER", "DECISION_ROUTER_MODEL",
                "DECISION_ROUTER_MIN_CONFIDENCE", "COSINE_PAPER_MIN", "COSINE_PAGE_MIN", "BAND_PAPER_LOW",
                "BAND_PAGE_LOW", "BAND_PAPER_HIGH", "BAND_PAGE_HIGH", "BAND_MIDDLE_ROUTER", "EMBEDDING_MODEL",
                "SEARCH_MODE", "RETRIEVER_TOP_K", "RERANK", "RERANK_MODEL", "MIN_RELEVANCE", "ADAPTIVE_TOP_K",
                "ADAPTIVE_TOP_K_RATIO", "MAX_CHUNKS", "MAX_CHUNKS_PER_DOC", "VERIFY_CITATIONS", "FORRT_PAGES",
                "FORRT_IN_PAPERS", "FORRT_IN_PAPERS_MIN_SCORE", "FORRT_SELECT_MODEL", "FORRT_DECISION_THRESHOLD",
                "FORRT_DECISION_FLOOR", "FORRT_ANSWER_MODEL", "ANSWER_CACHE_TTL")
        return {"answer_model": model or c.get("CITATION_MODEL"), "router": router or c.get("ROUTER") or "",
                **{k.lower(): c.get(k) for k in keys if k in c}}

    def _respond(
        self, query: str, chat_id: str, model: Optional[str], stream: bool,
        router: Optional[str], timings: Dict[str, float],
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate a response to a user query.

        Args:
            query: User query
            chat_id: Chat session ID
            model: Answer model for this request (default CITATION_MODEL)

        Yields:
            Response chunks as dictionaries
        """
        logger.debug("Starting response generation for chat_id: %s", chat_id)
        user_query = query  # the history keeps what the user typed, not the rephrased query

        def remember(answer: str) -> None:
            self.chat_manager.add_message(chat_id, {"role": "user", "content": user_query})
            self.chat_manager.add_message(chat_id, {"role": "assistant", "content": answer})

        try:
            if small_talk(user_query):  # before rephrasing: the history must not turn "thanks" into a question
                about = msg.message("about", user_query)
                remember(about)
                yield {"status": "complete", "message": markdown.markdown(about), "outcome": "small_talk"}
                return

            conversation_history = self.chat_manager.get_history(chat_id)

            # A first question very close to a recent one gets the stored answer
            use_cache = self.answer_cache is not None and not conversation_history
            if use_cache:
                cached = self.answer_cache.lookup(query, model)
                if cached:
                    remember(cached["text"])
                    yield cached["response"]
                    return

            # Follow-up questions (CONTEXT_METHOD): "rephrase" (default), "history" or "hybrid":
            # the rephrased question for the topic check and the search, and the chat as it happened
            # (earlier turns + the question as typed) for the answer (docs/evaluation.md, context methods)
            history_for_answer = None
            answer_query = None
            method = self.config.get("CONTEXT_METHOD", "rephrase")
            if conversation_history:
                if method == "history":
                    history_for_answer = conversation_history[-HISTORY_TURNS:]
                    last_user = [m["content"] for m in conversation_history if m["role"] == "user"][-1:]
                    query = " ".join(last_user + [query])  # retrieval sees the topic of the chat
                else:
                    yield {"status": "in-progress", "message": "Reformulating question"}
                    query = self.query_processor.rephrase_query(query, chat_id)
                    logger.debug(f"Rephrased query: {query}")
                    if method == "hybrid":
                        # the answer sees the user's own words (the rewrite can lose a detail) and the
                        # rewrite (a long chat can point back past the last HISTORY_TURNS messages)
                        history_for_answer = conversation_history[-HISTORY_TURNS:]
                        answer_query = user_query if query.strip() == user_query.strip() else f"{user_query}\n(Meaning: {query})"
            answer_query = answer_query or query

            yield {"status": "in-progress", "message": "Classifying question"}
            step = time.time()
            intent = self.route(query, router)
            timings["classify_s"] = time.time() - step
            logger.debug(f"Query intent: {intent}")

            if intent is None:
                yield {
                    "status": "error",
                    "message": markdown.markdown(msg.message("model_unavailable", user_query)),
                    "outcome": "error",
                }
                return

            if intent in ("forrt", "forrt_lookup") and self.forrt_pages is not None:
                yield {"status": "in-progress", "message": "Reading FORRT pages"}
                step = time.time()
                result = self.forrt_pages.answer(query, model=model, language_text=user_query)
                timings["forrt_pages_s"] = time.time() - step  # page search, live fetch and answer
                if result["text"] is None:
                    error = msg.message("generation_error", user_query)
                    remember(error)
                    yield {"status": "complete", "message": markdown.markdown(error), "outcome": "error"}
                    return
                remember(result["text"])
                refs = page_references(result["sources"])
                yield {"status": "complete", "message": markdown.markdown(result["text"], extensions=MARKDOWN_EXTENSIONS),
                       "outcome": "forrt" if result["found"] else "no_sources",
                       "metadata": {"sources": page_source_lines(refs), "references": refs}}
                return

            if intent in ("forrt", "forrt_lookup") and self.forrt_lookup is not None:
                answer = self.forrt_lookup.answer(user_query if history_for_answer else query)
                remember(answer)
                yield {"status": "complete", "message": markdown.markdown(answer), "outcome": "forrt_lookup"}
                return

            if intent in ("forrt", "forrt_lookup", "both"):
                intent = "both" if intent == "both" else "open_science"  # no FORRT route set up: papers answer

            if intent == "small_talk":  # the rephrased follow-up is small talk
                about = msg.message("about", user_query)
                remember(about)
                yield {"status": "complete", "message": markdown.markdown(about), "outcome": "small_talk"}
                return

            if intent == "off_topic":
                refusal = msg.message("off_topic", user_query)
                remember(refusal)
                yield {"status": "complete", "message": markdown.markdown(refusal), "outcome": "off_topic"}
                return

            yield {"status": "in-progress", "message": "Finding relevant sources"}
            pages_job = self.start_forrt_in_papers(query, intent)
            ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(query, timings)
            page_sources = self.forrt_in_papers_result(pages_job, timings)
            ranked_nodes = list(ranked_nodes) + page_sources
            if not ranked_nodes:
                yield from self.no_relevant_nodes_handler(user_query, chat_id)
                return
            context = self.document_retriever.context_from_nodes(ranked_nodes)

            yield {"status": "in-progress", "message": "Generating response"}
            start = time.time()
            if stream:
                # #41: send what can be shown while the model writes; the complete
                # answer below still gets the citations, sources, cache and history
                raw, shown = "", 0
                for piece in self.response_generator.stream_response(
                    answer_query, context, model, history=history_for_answer
                ):
                    raw += piece
                    visible = visible_answer(raw, self.response_generator.marks_response)
                    if len(visible) > shown:
                        yield {"status": "partial", "delta": visible[shown:]}
                        shown = len(visible)
                # nothing streamed (provider error or an empty answer): the normal call, with its retries
                response_text = raw or self.response_generator.generate_response(
                    answer_query, context, model, history=history_for_answer
                )
            else:
                response_text = self.response_generator.generate_response(
                    answer_query, context, model, history=history_for_answer
                )
            logger.info(f"Timing: answer {time.time() - start:.1f}s ({model or self.config.get('CITATION_MODEL')})")
            timings["answer_s"] = time.time() - start
            # Llama 3.1 8B answered 3 of 7 German questions without any [n]: then the source
            # list shows every retrieved paper and no snippet. Ask once more, but only after a
            # quick first answer: a 150 s Kannada answer asked twice stalled the eval run.
            if (
                response_text
                and not re.search(r"\[\d+\]", response_text)
                and time.time() - start < self.config.get("LLM_TIMEOUT", 60)
            ):
                logger.info("Answer has no [n] citation, asking again")
                response_text = self.response_generator.generate_response(
                    answer_query, context, model, history=history_for_answer
                ) or response_text
                timings["answer_s"] = time.time() - start  # with the retry
            if not response_text:
                logger.error("Failed to generate response")
                error = msg.message("generation_error", user_query)
                remember(error)
                yield {"status": "complete", "message": markdown.markdown(error), "outcome": "error"}
                return

            processed_message = self.response_generator.post_process_response(response_text)
            unverified = set()
            if self.config.get("VERIFY_CITATIONS"):
                yield {"status": "in-progress", "message": "Checking citations"}
                unverified = self.document_retriever.unsupported_citations(processed_message, ranked_nodes)
            html_message, used_refs = self.response_generator.process_with_references(
                processed_message, ranked_nodes, unverified
            )
            remember(processed_message)

            final = {
                "status": "complete",
                "message": html_message,
                "outcome": "answered",
                "metadata": {
                    # text for the forrt.org widget; "references" is the same list as data
                    "sources": self.reference_processor.references_from_nodes(
                        ranked_nodes, used_refs, unverified
                    ),
                    "references": self.reference_processor.reference_list(
                        ranked_nodes, used_refs, unverified, processed_message
                    ),
                },
            }
            if intent == "both" and self.forrt_pages is not None and not page_sources:
                # the question also concerns FORRT itself: add the best forrt.org pages to the
                # Sources box, after the papers (no extra answer call)
                links = self.forrt_pages.links(query)
                if links:
                    refs = final["metadata"]["references"]
                    extra = page_references(links, start=len(refs) + 1)
                    refs.extend(extra)
                    final["metadata"]["sources"] = "\n".join(
                        x for x in (final["metadata"]["sources"], page_source_lines(extra)) if x)
                    final["outcome"] = "both"
            if use_cache:
                self.answer_cache.store(query, final, processed_message, model)
            yield final
        except Exception as e:
            logger.error(f"Error in get_response: {str(e)}")
            yield {
                "status": "error",
                "message": markdown.markdown(msg.message("unexpected_error", user_query)),
                "outcome": "error",
            }

    def start_forrt_in_papers(self, query: str, intent: str):
        """FORRT_IN_PAPERS: look for forrt.org pages that add to a papers answer while the papers are
        searched (a future, or None when off). The `both` route skips the score floor."""
        if getattr(self, "forrt_pages", None) is None or not self.config.get("FORRT_IN_PAPERS"):
            return None
        min_score = None if intent == "both" else self.config.get("FORRT_IN_PAPERS_MIN_SCORE", 0.6)
        pool = ThreadPoolExecutor(1)
        # copy_context: the debug trace also sees the pages job
        job = pool.submit(contextvars.copy_context().run, trace.step("FORRT pages next to papers")(self.forrt_pages.extra_sources),
                          query, min_score)
        pool.shutdown(wait=False)
        return job

    def forrt_in_papers_result(self, job, timings: Dict[str, float]) -> List[TextNode]:
        """The pages of start_forrt_in_papers as source nodes; none when off, slow or failed."""
        if job is None:
            return []
        start = time.time()
        try:
            return page_nodes(job.result(timeout=self.config.get("FORRT_IN_PAPERS_TIMEOUT", 10)))
        except Exception as e:
            logger.warning(f"FORRT pages next to the papers skipped: {e.__class__.__name__}: {e}")
            return []
        finally:
            timings["forrt_wait_s"] = time.time() - start

    def get_arena_response(
        self, query: str, models: List[str], router: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Answer one question with several models from the same sources (arena mode).

        Classification and retrieval run once, so only the answer model differs.
        Single turn: no chat history is read or stored.

        Args:
            query: User query
            models: Models that each write an answer

        Yields:
            Status chunks, then {"status": "complete", "responses": [...]} with one
            {"model", "message", "sources", "seconds"} per model. A refusal or
            "no sources" result has a single "message" instead of "responses".
        """
        try:
            yield {"status": "in-progress", "message": "Classifying question"}
            timings: Dict[str, float] = {}
            step = time.time()
            # Same topic check as the chat (the dropdown, else ROUTER / DECISION_ROUTER); in the
            # arena it only decides answer or refuse: the cards always answer from the papers
            intent = self.route(query, router)
            concerns_open_science = None if intent is None else intent != "off_topic"
            timings["classify_s"] = time.time() - step
            if concerns_open_science is None:
                yield {
                    "status": "error",
                    "message": markdown.markdown(msg.message("model_unavailable", query)),
                }
                return
            if not concerns_open_science or intent == "small_talk":
                yield {
                    "status": "complete",
                    "message": markdown.markdown(msg.message("about" if intent == "small_talk" else "off_topic", query)),
                }
                return

            yield {"status": "in-progress", "message": "Finding relevant sources"}
            ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(query, timings)
            if not ranked_nodes:
                yield {
                    "status": "complete",
                    "message": markdown.markdown(msg.message("no_sources", query)),
                }
                return
            context = self.document_retriever.context_from_nodes(ranked_nodes)

            yield {"status": "in-progress", "message": "Generating responses"}

            def answer(model: str) -> Dict[str, Any]:
                start = time.time()
                text = self.response_generator.generate_response(query, context, model)
                if not text:
                    return {
                        "model": model,
                        "message": markdown.markdown("This model did not answer (API error)."),
                        "sources": "",
                        "error": True,
                        "seconds": round(time.time() - start, 1),
                    }
                processed = self.response_generator.post_process_response(text)
                html_message, used_refs = self.response_generator.process_with_references(
                    processed, ranked_nodes
                )
                return {
                    "model": model,
                    "message": html_message,
                    "sources": self.reference_processor.references_from_nodes(
                        ranked_nodes, used_refs
                    ),
                    "references": self.reference_processor.reference_list(
                        ranked_nodes, used_refs, answer=processed
                    ),
                    "seconds": round(time.time() - start, 1),
                }

            with ThreadPoolExecutor(len(models)) as pool:
                responses = list(pool.map(answer, models))
            # shared steps of the round; each response has its own answer "seconds"
            yield {"status": "complete", "responses": responses, "timings": {k: round(v, 2) for k, v in timings.items()}}
        except Exception as e:
            logger.error(f"Error in get_arena_response: {str(e)}")
            yield {
                "status": "error",
                "message": markdown.markdown(msg.message("unexpected_error", query)),
            }
