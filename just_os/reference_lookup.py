"""Questions about one specific reference: find the paper by DOI, title or authors, and answer from it alone.

Only the chunk text is embedded and searched; titles, authors and DOIs are metadata (just_os/rag_service.py). So
"Why did Simmons, Nelson and Simonsohn start the replication crisis?" matched the ~1,800 chunks of other papers that
cite them, not their paper. This lookup runs before the search (REFERENCE_LOOKUP), on the question as typed and on
its rewrite, and matches:
  1. a DOI in the question;
  2. a title: all of its content words (titles of at least MIN_TITLE_WORDS), or TITLE_COVERAGE of them when the
     question refers to a work (paper, article, et al., a year, quotes), are in the question,
     or its short title (before the colon, at least two uncommon words) as a phrase ("the False-Positive Psychology
     paper");
  3. authors: the surnames of two of the same paper's authors, or one surname and the paper's publication year (a
     person's own name, "Who is Gilad Feldman?", is one author: no match); between papers
     with as many names, the one with more of its title words in the question.
More than MAX_MATCHES papers is too vague (a common surname): the normal search runs instead. An author team often
has several papers in the library (Simmons, Nelson and Simonsohn: 8); the answer then reads the closest chunks of all. On a match, the
answer comes from the matched papers' chunks only, ranked by cosine to the question, without the per-paper cap and
the similarity floor. A DOI or title match skips the topic check (a question naming a paper of the library is in
scope); after an author match the topic check still runs, so a question about a person or a FORRT course still goes
to FORRT's pages, and only "off topic" is overruled (two of the paper's authors were named).
"""

import csv
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from just_os.references import DOI_PATTERN, GLOSSARY_TYPE, normalize_doi, plain_metadata

TITLE_COVERAGE = 0.8
MIN_TITLE_WORDS = 4
MAX_MATCHES = 10
WORD = re.compile(r"[^\W\d_]{3,}", re.U)
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# words that are the name of some author but mostly ordinary words in a question
COMMON = set("""the and for with from that this what which when where who why how does did are was were has have had
about into over under after before between their there these those than then them they your you our out not but all any
can could would should will may might must also more most many much such some other open science research data study
studies paper papers article review reviews new young brown green white black wood field rich hope king best long short
good less fair free well hall bell page center centre university institute psychology psychological registration
association society foundation conference european american international journal network team project committee
group department school college science sciences council office forrt training framework teaching education
reproducible reproducibility replication replicability slack community initiative lab laboratory""".split())
# function words, left out of titles (COMMON is for author names: "science" or "reproducible" are real title words)
STOP = set("""the and for with from that this what which when where who why how does are was were has have had about
into over under after before between their there these those than then them they your you our not but all any can
its via why""".split())
# a short title is often a topic term too ("Registered report: a survey ..."): it names a paper only when the question
# refers to a work (or names one of its authors, or quotes)
WORK = re.compile(r"\b(paper|papers|article|study|publication|preprint|book|chapter|titled|entitled|et al)\b|[\"“”]",
                  re.I)


def words(text: str) -> set:
    return {w.lower() for w in WORD.findall(text or "")}


def authors(creators: str) -> List[str]:
    """The surname of each author of a list: the last name word of each part ("Joseph P. Simmons" -> simmons, "Anna van
    der Berg" -> berg, "Open Science Collaboration" -> collaboration). APA's "Simmons, J. P., Nelson, L. D." works too:
    its parts with initials only are dropped. First names and particles (van, der) are left out on purpose: they are
    ordinary words in questions."""
    out = []
    for part in re.split(r"\s*(?:;|,|&|\band\b)\s*", creators or ""):
        names = [w for w in WORD.findall(part.lower()) if w not in COMMON]
        if names:
            out.append(names[-1])
    return out


def name_words(creators: str) -> set:
    """The surnames of an author list."""
    return set(authors(creators))


def short_title(title: str) -> str:
    """The title before its colon as lower-case words, when that has two uncommon or three content words ("" otherwise:
    "Open Science: a primer" names no paper)."""
    head = WORD.findall(re.split(r"[:?]", title or "", maxsplit=1)[0].lower())
    distinct = len([w for w in head if w not in COMMON]) >= 2 or len([w for w in head if w not in STOP]) >= 3
    return " ".join(head) if distinct and len(head) <= 8 else ""


@dataclass
class Paper:
    key: str
    title: str
    doi: str = ""
    year: str = ""
    names: set = field(default_factory=set)
    authors: List[str] = field(default_factory=list)
    title_words: set = field(default_factory=set)
    short_title: str = ""  # the words before the colon, as a phrase ("false positive psychology")


def match(question: str, papers: Iterable[Paper]) -> Tuple[List[Paper], str]:
    """(the papers the question names, why), or ([], "") when it names none or too many."""
    papers = list(papers)
    dois = {normalize_doi(d) for d in DOI_PATTERN.findall(question or "")} - {None}
    if dois:
        hit = [p for p in papers if p.doi in dois]
        if hit:
            return hit[:MAX_MATCHES], "DOI"
    asked = words(question)
    years = set(YEAR.findall(question or ""))
    cue = bool(WORK.search(question or "")) or bool(years)
    scored = [(len(p.title_words & asked) / len(p.title_words), p) for p in papers
              if len(p.title_words) >= MIN_TITLE_WORDS]
    best = max((s for s, _ in scored), default=0)
    # all of a title's words, or most of them in a question that refers to a work: titles of generic words
    # ("Is it time to share qualitative research data?") would otherwise catch topic questions
    if best == 1 or (best >= TITLE_COVERAGE and cue):
        hit = [p for s, p in scored if s == best]
        if len(hit) <= MAX_MATCHES:
            return hit, "title"
    phrase = " " + " ".join(WORD.findall((question or "").lower())) + " "
    hit = [p for p in papers if p.short_title and f" {p.short_title} " in phrase and (cue or p.names & asked)]
    if hit and len(hit) <= MAX_MATCHES:
        return hit, "title"
    by_names = []
    for p in papers:
        n = len(set(p.authors) & asked)  # surnames: "Gilad Feldman" is one author
        if n >= 2 or (n == 1 and p.year in years):
            by_names.append(((n + (p.year in years), len(p.title_words & asked)), p))
    if by_names:
        top = max(s for s, _ in by_names)
        hit = [p for s, p in by_names if s == top]
        if len(hit) <= MAX_MATCHES:
            return hit, "authors"
    return [], ""


class ReferenceLookup:
    """The papers of the index (not the glossary entries), their chunks, and where the chunks' vectors are in FAISS
    (rows only: the vectors are read per matched question, so the index is not held twice in memory)."""

    def __init__(self, papers: List[Paper], chunks: Dict[str, List], rows: Dict[str, List[int]], faiss_index, embed_model):
        self.papers, self._chunks, self._rows, self._faiss, self._embed = papers, chunks, rows, faiss_index, embed_model

    @classmethod
    def from_index(cls, index, embed_model, pub_years_file: Optional[str] = None, excluded=()) -> "ReferenceLookup":
        years = {}
        if pub_years_file:
            try:
                with open(pub_years_file, encoding="utf-8") as f:
                    years = {normalize_doi(r["doi"]): r["year"] for r in csv.DictReader(f)}
            except OSError:
                pass
        faiss_index = index.vector_store._faiss_index
        row_of = {node_id: int(row) for row, node_id in index.index_struct.nodes_dict.items()}
        papers: Dict[str, Paper] = {}
        chunks: Dict[str, List] = {}
        for node_id, node in index.docstore.docs.items():
            meta = plain_metadata(node.metadata)
            if meta.get("material_type") == GLOSSARY_TYPE or node_id not in row_of:
                continue
            if (normalize_doi(meta.get("doi")) or normalize_doi(meta.get("link_to_resource")) or "") in excluded:
                continue  # text of another work (config/index_corrections.json)
            key = node.ref_doc_id or node_id
            if key not in papers:
                doi = normalize_doi(meta.get("doi")) or normalize_doi(meta.get("link_to_resource")) or ""
                title = str(meta.get("title") or "")
                creators = str(meta.get("creators") or "")
                papers[key] = Paper(key, title, doi, str(years.get(doi, "")), names=name_words(creators),
                                    authors=authors(creators), title_words=words(title) - STOP,
                                    short_title=short_title(title))
            chunks.setdefault(key, []).append(node)
        rows = {key: [row_of[n.node_id] for n in nodes] for key, nodes in chunks.items()}
        return cls(list(papers.values()), chunks, rows, faiss_index, embed_model)

    def match(self, *questions: str) -> Tuple[List[Paper], str]:
        """The first question (as typed, then the rewrite) that names papers."""
        for question in questions:
            if question:
                found, why = match(question, self.papers)
                if found:
                    return found, why
        return [], ""

    def chunks(self, question: str, found: List[Paper], n: int) -> List:
        """The n chunks of the found papers closest to the question (NodeWithScore; score = FAISS L2 distance of unit
        vectors, as the vector search gives them), any number per paper."""
        from llama_index.core.schema import NodeWithScore

        q = np.asarray(self._embed.get_query_embedding(question), dtype=np.float32)
        q /= np.linalg.norm(q) or 1
        scored = []
        for p in found:
            vectors = np.stack([self._faiss.reconstruct(row) for row in self._rows[p.key]])
            cosine = vectors @ q / np.maximum(np.linalg.norm(vectors, axis=1), 1e-9)
            scored += [(float(c), node) for c, node in zip(cosine, self._chunks[p.key])]
        scored.sort(key=lambda x: -x[0])
        return [NodeWithScore(node=node, score=2 - 2 * c) for c, node in scored[:n]]
