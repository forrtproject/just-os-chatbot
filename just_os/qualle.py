import html
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Generator, Iterator, Tuple

import markdown
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion
import torch
from sentence_transformers import CrossEncoder

from just_os.answer_cache import AnswerCache
from just_os.chat_manager import ChatManager
from just_os.decisions import DecisionClient
from just_os.forrt_lookup import ForrtLookup
from just_os.forrt_pages import ForrtPages
from just_os import messages as msg
from just_os.openscholar import generation_instance_prompts_w_references, system_prompt
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

# CONTEXT_METHOD=history: number of earlier messages passed to the answer model
HISTORY_TURNS = 4
INTENTS = ("open_science", "forrt_lookup", "off_topic")


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

        # Build prompt
        prompt = "Given the following dialogue history:\n"
        for message in conversation_history:
            prompt += f"Role: {message['role']}\nContent: {message['content']}\n"
        prompt += f"""

You should reformulate a new question by the user in such a way that it makes sense in isolation.
As an example, if a user follows up a question about open science with a question like "Does it also have disadvantages?",
a proper reformulation would be "Does Open Science also have disadvantages?"
If the question is not related to open science, return the original question.
Now reformulate the following question such that it makes sense in isolation:\n{query}"""

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
        self.reranker = CrossEncoder(config["RERANK_MODEL"])
        self.verify_min_score = config.get("VERIFY_MIN_SCORE", 0.1)
        self.n_context_items = config["MAX_CHUNKS"]
        self.min_relevance = config["MIN_RELEVANCE"]
        self.max_per_doc = config.get("MAX_CHUNKS_PER_DOC", 0)

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
        if not pairs:
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

    def retrieve_and_rerank(self, query: str) -> Tuple[List[Any], List[Any]]:
        """
        Retrieve and rerank documents for a query.

        Args:
            query: User query

        Returns:
            Tuple of (ranked nodes, all retrieved nodes)
        """
        # Retrieve relevant nodes
        start = time.time()
        nodes = self._retriever.retrieve(query)
        retrieved = time.time()

        if not nodes:
            return [], []

        try:
            scores = self.reranker.predict(
                [(query, self.node_to_text(node)) for node in nodes]
            )
            logger.info(
                f"Timing: retrieval {retrieved - start:.1f}s, re-rank {time.time() - retrieved:.1f}s "
                f"({len(nodes)} chunks)"
            )
        except Exception as e:
            # Fall back to vector order so a reranker failure never empties the answer
            logger.error(f"Reranking failed, using vector order: {str(e)}")
            return self.limit_per_document(nodes), nodes

        ranked = sorted(zip(scores, nodes), key=lambda pair: pair[0], reverse=True)

        # Filter and limit ranked nodes
        ranked_nodes = self.limit_per_document(
            [node for score, node in ranked if score > self.min_relevance]
        )

        return ranked_nodes, nodes


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
            return response
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
        self, api_key: Optional[str], base_url: str, timeout: Optional[float] = None, retries: int = 1
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
                max_retries=retries,
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            return None

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

        try:
            kwargs = {"model": model, "messages": messages, "temperature": temperature}
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            if tools:
                kwargs["tools"] = tools

            if tool_choice:
                kwargs["tool_choice"] = tool_choice

            return client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return None

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
        try:
            for chunk in client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, stream=True,
                **({"max_tokens": max_tokens} if max_tokens else {}),
            ):
                for choice in chunk.choices:
                    if choice.delta.content:
                        yield choice.delta.content
        except Exception as e:
            logger.error(f"OpenAI API error (stream): {str(e)}")


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

    def route(self, query: str) -> Optional[str]:
        """open_science / forrt / both / off_topic (or forrt_lookup from the LLM classifier); None = model error.

        DECISION_ROUTER: a decision model decides when it is confident enough; otherwise, and when it fails,
        the LLM classifier decides (three classes when a FORRT route is set up, else open science or not).
        """
        if self.config.get("DECISION_ROUTER") and self.decisions is not None:
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
        self, query: str, chat_id: str, model: Optional[str] = None, stream: bool = False
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
            conversation_history = self.chat_manager.get_history(chat_id)

            # A first question very close to a recent one gets the stored answer
            use_cache = self.answer_cache is not None and not conversation_history
            if use_cache:
                cached = self.answer_cache.lookup(query, model)
                if cached:
                    remember(cached["text"])
                    yield cached["response"]
                    return

            # Follow-up questions: rephrase (default) or pass the history (CONTEXT_METHOD=history)
            history_for_answer = None
            if conversation_history:
                if self.config.get("CONTEXT_METHOD", "rephrase") == "history":
                    history_for_answer = conversation_history[-HISTORY_TURNS:]
                    last_user = [m["content"] for m in conversation_history if m["role"] == "user"][-1:]
                    query = " ".join(last_user + [query])  # retrieval sees the topic of the chat
                else:
                    yield {"status": "in-progress", "message": "Reformulating question"}
                    query = self.query_processor.rephrase_query(query, chat_id)
                    logger.debug(f"Rephrased query: {query}")

            yield {"status": "in-progress", "message": "Classifying question"}
            intent = self.route(query)
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
                result = self.forrt_pages.answer(query, model=model, language_text=user_query)
                if result["text"] is None:
                    error = msg.message("generation_error", user_query)
                    remember(error)
                    yield {"status": "complete", "message": markdown.markdown(error), "outcome": "error"}
                    return
                remember(result["text"])
                yield {"status": "complete", "message": markdown.markdown(result["text"], extensions=MARKDOWN_EXTENSIONS),
                       "outcome": "forrt" if result["found"] else "no_sources"}
                return

            if intent in ("forrt", "forrt_lookup") and self.forrt_lookup is not None:
                answer = self.forrt_lookup.answer(user_query if history_for_answer else query)
                remember(answer)
                yield {"status": "complete", "message": markdown.markdown(answer), "outcome": "forrt_lookup"}
                return

            if intent in ("forrt", "forrt_lookup", "both"):
                intent = "both" if intent == "both" else "open_science"  # no FORRT route set up: papers answer

            if intent == "off_topic":
                refusal = msg.message("off_topic", user_query)
                remember(refusal)
                yield {"status": "complete", "message": markdown.markdown(refusal), "outcome": "off_topic"}
                return

            yield {"status": "in-progress", "message": "Finding relevant sources"}
            ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(query)
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
                    query, context, model, history=history_for_answer
                ):
                    raw += piece
                    visible = visible_answer(raw, self.response_generator.marks_response)
                    if len(visible) > shown:
                        yield {"status": "partial", "delta": visible[shown:]}
                        shown = len(visible)
                response_text = raw or None
            else:
                response_text = self.response_generator.generate_response(
                    query, context, model, history=history_for_answer
                )
            logger.info(f"Timing: answer {time.time() - start:.1f}s ({model or self.config.get('CITATION_MODEL')})")
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
                    query, context, model, history=history_for_answer
                ) or response_text
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
            if intent == "both" and self.forrt_pages is not None:
                # the question also concerns FORRT itself: add the best forrt.org pages (no extra answer call)
                links = self.forrt_pages.links(query)
                if links:
                    final["message"] += markdown.markdown(
                        "**On forrt.org:**\n\n" + "\n".join(f"- [{link['title']}]({link['url']})" for link in links))
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

    def get_arena_response(
        self, query: str, models: List[str]
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
            concerns_open_science = self.query_processor.classify_query(query)
            if concerns_open_science is None:
                yield {
                    "status": "error",
                    "message": markdown.markdown(msg.message("model_unavailable", query)),
                }
                return
            if not concerns_open_science:
                yield {
                    "status": "complete",
                    "message": markdown.markdown(msg.message("off_topic", query)),
                }
                return

            yield {"status": "in-progress", "message": "Finding relevant sources"}
            ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(query)
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
            yield {"status": "complete", "responses": responses}
        except Exception as e:
            logger.error(f"Error in get_arena_response: {str(e)}")
            yield {
                "status": "error",
                "message": markdown.markdown(msg.message("unexpected_error", query)),
            }
