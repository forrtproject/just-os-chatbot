import html
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Generator, Tuple

import markdown
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion
from sentence_transformers import CrossEncoder

from just_os.chat_manager import ChatManager
from just_os.openscholar import generation_instance_prompts_w_references, system_prompt
from just_os.references import (
    document_key,
    load_publication_years,
    passage_allowed,
    publication_year,
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

# Default response for non-Open Science questions
NON_OS_RESPONSE = "Sorry, I'm only able to answer questions related to Open Science."
# Shown when the language model cannot be reached (not a refusal)
CLASSIFY_ERROR_RESPONSE = (
    "Sorry, the language model is not available at the moment. Please try again later."
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
Classify whether the following query is about Open Science:
"{query}"
Return your answer as a valid JSON object with a single boolean entry "concerns_open_science"
"""
        result = self._structured_output(prompt, "concerns_open_science", "boolean")
        if not isinstance(result, bool):
            logger.error(f"Failed to classify query, got: {result!r}")
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
        self.reranker = CrossEncoder(config["RERANK_MODEL"])
        self.n_context_items = config["MAX_CHUNKS"]
        self.min_relevance = config["MIN_RELEVANCE"]
        self.max_per_doc = config.get("MAX_CHUNKS_PER_DOC", 0)

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
        return f"Title: {node.metadata.get(TITLE_KEY, 'Unknown Title')} Text: {' '.join(node.text.split())}"

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
        nodes = self._retriever.retrieve(query)

        if not nodes:
            return [], []

        try:
            scores = self.reranker.predict(
                [(query, self.node_to_text(node)) for node in nodes]
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
        self.system_prompt = system_prompt
        self.prompt_template = generation_instance_prompts_w_references

    def generate_response(
        self, query: str, context: str, model: Optional[str] = None
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
        # Format prompt
        prompt = self.prompt_template.format(context_items=context, query=query)

        # Prepare messages for the LLM
        history_openai_format = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        # Generate response
        response = self.client_manager.create_chat_completion(
            model=model or self.citation_model,
            messages=history_openai_format,
            temperature=self.config.get("TEMPERATURE", 0.3),
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
        self, processed_message: str, nodes: List[Any]
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
            processed_message, nodes
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
            self._create_client(config.get("OPENSCHOLAR_API_KEY"), config["OPENSCHOLAR_BASE_URL"])
            if config.get("OPENSCHOLAR_BASE_URL")
            else None
        )

    def _client_for(self, model: str) -> Optional[OpenAI]:
        if self.openscholar_client and model == self.config.get("OPENSCHOLAR_MODEL"):
            return self.openscholar_client
        return self.client

    def _create_client(self, api_key: Optional[str], base_url: str) -> Optional[OpenAI]:
        """
        Create an OpenAI client instance.

        Returns:
            OpenAI client or None if initialization fails
        """
        try:
            return OpenAI(api_key=api_key, base_url=base_url)
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

            if tools:
                kwargs["tools"] = tools

            if tool_choice:
                kwargs["tool_choice"] = tool_choice

            return client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return None


class ReferenceProcessor:
    """
    Turns [n] citations into clickable references and a source list.

    One number per document (chunks of the same paper share it), the publication
    year (not the form time stamp), https://doi.org/ links, and the passage only
    when the licence allows it.
    """

    def __init__(self, pub_years: Optional[Dict[str, str]] = None):
        self.pub_years = pub_years or {}

    def reference_data(self, node) -> Dict[str, Any]:
        """Tooltip data for one cited chunk. The front end inserts it as text, not HTML."""
        meta = node.metadata
        return {
            "title": meta.get(TITLE_KEY, "Unknown Title"),
            "authors": meta.get(CREATOR_KEY, "Unknown Author"),
            "year": publication_year(meta, self.pub_years),
            "url": reference_url(meta),
            "text": node.text if passage_allowed(meta.get(LICENCE_KEY)) else "",
        }

    def process_markdown_with_references(
        self, markdown_text: str, references_nodes: List[Any]
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
            html_text = markdown.markdown(markdown_text)
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
                    key = document_key(references_nodes[ref_idx].metadata)
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
                for match in reversed(matches):
                    old_ref_num = int(match.group(1))
                    if old_ref_num not in ref_mapping:
                        continue
                    start, end = match.span()
                    # Each citation keeps the passage of the chunk it cites
                    data_string = json.dumps(
                        self.reference_data(references_nodes[old_ref_num]),
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
            return markdown.markdown(markdown_text), []

    def references_from_nodes(
        self, nodes: List[Any], used_refs_ordered: Optional[List[int]] = None
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
            if not used_refs_ordered:
                seen = set()
                used_refs_ordered = []
                for idx, node in enumerate(nodes):
                    key = document_key(node.metadata)
                    if key not in seen:
                        seen.add(key)
                        used_refs_ordered.append(idx)

            lines = []
            for number, ref_idx in enumerate(
                (i for i in used_refs_ordered if i < len(nodes)), start=1
            ):
                data = self.reference_data(nodes[ref_idx])
                lines.append(
                    f"[{number}] {data['authors']} ({data['year']}). {data['title']}."
                    + (f" {data['url']}" if data["url"] else "")
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error generating references: {str(e)}")
            return "References could not be generated due to an error."


class Qualle:
    """
    Main RAG service implementation that handles queries and responses.
    """

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

        logger.debug("Qualle service initialized")

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
        self.chat_manager.add_message(chat_id, {"role": "user", "content": query})
        self.chat_manager.add_message(
            chat_id,
            {
                "role": "assistant",
                "content": "I couldn't find any relevant information about that topic in Open Science.",
            },
        )
        yield {
            "status": "complete",
            "message": markdown.markdown(
                "I couldn't find any relevant information about that topic in Open Science."
            ),
        }

    def get_response(
        self, query: str, chat_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate a response to a user query.

        Args:
            query: User query
            chat_id: Chat session ID

        Yields:
            Response chunks as dictionaries
        """
        logger.debug("Starting response generation for chat_id: %s", chat_id)

        try:
            # Get conversation history
            conversation_history = self.chat_manager.get_history(chat_id)
            logger.debug("Retrieved conversation history for chat_id: %s", chat_id)

            # Rephrase query if there's conversation history
            if conversation_history:
                yield {"status": "in-progress", "message": "Reformulating question"}
                query = self.query_processor.rephrase_query(query, chat_id)
                logger.debug(f"Rephrased query: {query}")

            # Classify query
            yield {"status": "in-progress", "message": "Classifying question"}
            concerns_open_science = self.query_processor.classify_query(query)
            logger.debug(f"Query classification: {concerns_open_science}")

            if concerns_open_science is None:
                yield {
                    "status": "error",
                    "message": markdown.markdown(CLASSIFY_ERROR_RESPONSE),
                }
                return

            # Process Open Science queries
            if concerns_open_science:
                # Retrieve and rerank relevant sources
                yield {"status": "in-progress", "message": "Finding relevant sources"}
                logger.debug("Retrieving and reranking nodes for query")
                ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(
                    query
                )

                if not ranked_nodes:
                    yield from self.no_relevant_nodes_handler(query, chat_id)
                    return

                # Format context
                context = self.document_retriever.context_from_nodes(ranked_nodes)

                # Generate response
                yield {"status": "in-progress", "message": "Generating response"}
                response_text = self.response_generator.generate_response(
                    query, context
                )

                if not response_text:
                    logger.error("Failed to generate response")
                    self.chat_manager.add_message(
                        chat_id, {"role": "user", "content": query}
                    )
                    self.chat_manager.add_message(
                        chat_id,
                        {
                            "role": "assistant",
                            "content": "I'm sorry, I encountered an error while generating a response.",
                        },
                    )
                    yield {
                        "status": "complete",
                        "message": markdown.markdown(
                            "I'm sorry, I encountered an error while generating a response."
                        ),
                    }
                    return

                # Process response
                processed_message = self.response_generator.post_process_response(
                    response_text
                )
                html_message, used_refs = (
                    self.response_generator.process_with_references(
                        processed_message, ranked_nodes
                    )
                )

                # Save conversation history
                self.chat_manager.add_message(
                    chat_id, {"role": "user", "content": query}
                )
                self.chat_manager.add_message(
                    chat_id, {"role": "assistant", "content": processed_message}
                )

                # Return final response
                yield {
                    "status": "complete",
                    "message": html_message,
                    "metadata": {
                        "sources": self.reference_processor.references_from_nodes(
                            ranked_nodes, used_refs
                        )
                    },
                }
            else:
                # Handle non-Open Science queries
                self.chat_manager.add_message(
                    chat_id, {"role": "user", "content": query}
                )
                self.chat_manager.add_message(
                    chat_id, {"role": "assistant", "content": NON_OS_RESPONSE}
                )

                yield {
                    "status": "complete",
                    "message": markdown.markdown(NON_OS_RESPONSE),
                }
        except Exception as e:
            logger.error(f"Error in get_response: {str(e)}")
            yield {
                "status": "error",
                "message": markdown.markdown(
                    "An unexpected error occurred while processing your request."
                ),
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
                    "message": markdown.markdown(CLASSIFY_ERROR_RESPONSE),
                }
                return
            if not concerns_open_science:
                yield {"status": "complete", "message": markdown.markdown(NON_OS_RESPONSE)}
                return

            yield {"status": "in-progress", "message": "Finding relevant sources"}
            ranked_nodes, _ = self.document_retriever.retrieve_and_rerank(query)
            if not ranked_nodes:
                yield {
                    "status": "complete",
                    "message": markdown.markdown(
                        "I couldn't find any relevant information about that topic in Open Science."
                    ),
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
                    "seconds": round(time.time() - start, 1),
                }

            with ThreadPoolExecutor(len(models)) as pool:
                responses = list(pool.map(answer, models))
            yield {"status": "complete", "responses": responses}
        except Exception as e:
            logger.error(f"Error in get_arena_response: {str(e)}")
            yield {
                "status": "error",
                "message": markdown.markdown(
                    "An unexpected error occurred while processing your request."
                ),
            }
