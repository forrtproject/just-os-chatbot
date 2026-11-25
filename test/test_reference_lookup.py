"""just_os/reference_lookup.py: a question naming one paper is answered from that paper alone."""

from types import SimpleNamespace

import numpy as np

from just_os.reference_lookup import COMMON, Paper, ReferenceLookup, authors, match, name_words, short_title, words
from test_qualle import make_qualle, node


def paper(key, title, doi="", year="", creators=""):
    return Paper(key, title, doi, year, names=name_words(creators), authors=authors(creators),
                 title_words=words(title) - COMMON, short_title=short_title(title))


PAPERS = [
    paper("fpp", "False-Positive Psychology: Undisclosed Flexibility in Data Collection and Analysis Allows Presenting "
          "Anything as Significant", "10.1177/0956797611417632", "2011", "Joseph P. Simmons, Leif D. Nelson, Uri Simonsohn"),
    paper("fpc", "False-Positive Citations", "10.1177/1745691617698146", "2018",
          "Joseph P. Simmons, Leif D. Nelson, and Uri Simonsohn"),
    paper("rr", "Registered Reports: A Method to Increase the Credibility of Published Results", "10.1027/1864-9335/a000192",
          "2014", "Brian A. Nosek, Daniel Lakens"),
    paper("other", "Power failure: why small sample size undermines the reliability of neuroscience", "10.1038/nrn3475",
          "2013", "Katherine S. Button, John P. A. Ioannidis"),
]


def keys(question):
    found, why = match(question, PAPERS)
    return sorted(p.key for p in found), why


def test_a_doi_names_its_paper():
    assert keys("What does https://doi.org/10.1038/NRN3475 conclude?") == (["other"], "DOI")


def test_most_of_a_title_names_its_paper():
    assert keys("Summarise 'Registered reports: a method to increase credibility of published results'") == (["rr"], "title")
    assert keys("What is a registered report?") == ([], "")  # two title words are not the title
    assert keys("What did the false positive psychology paper find?") == (["fpp"], "title")  # the short title
    assert short_title("Open Science: a primer") == ""  # common words are no short title
    rr_survey = [paper("rs", "Registered report: Survey on attitudes and experiences")]
    assert match("What is a registered report?", rr_survey) == ([], "")  # a topic term, not a reference
    assert [p.key for p in match("What did the registered report survey paper find?", rr_survey)[0]] == ["rs"]


def test_two_authors_or_one_author_and_the_year_name_a_paper():
    # both papers of the team fit: the answer reads both, unless title words tell them apart
    assert keys("What did Simmons, Nelson and Simonsohn write?") == (["fpc", "fpp"], "authors")
    assert keys("What did Simmons, Nelson and Simonsohn say about false citations?") == (["fpc"], "authors")
    assert keys("What did Simmons et al. (2011) find?") == (["fpp"], "authors")
    assert keys("What did Simmons find?") == ([], "")  # one name alone is too vague
    assert keys("Is open data good for young researchers?") == ([], "")  # ordinary words are no names
    org = [paper("t", "A template", "", "2025", "Society for the Improvement of Psychological Science, Registration Team")]
    assert match("What is the registration fee for the 2025 conference on psychology?", org) == ([], "")


def test_one_person_named_in_full_is_not_a_reference():
    assert authors("Simmons, J. P., Nelson, L. D., & Simonsohn, U.") == ["simmons", "nelson", "simonsohn"]
    assert authors("Joseph P. Simmons and Anna van der Berg; Open Science Collaboration") == ["simmons", "berg", "collaboration"]
    people = [paper("f", "Increasing the transparency of systematic reviews", creators="Gilad Feldman, Jane Doe")]
    assert match("Who is Gilad Feldman and how does he teach open science?", people) == ([], "")
    assert [p.key for p in match("What did Feldman and Doe propose?", people)[0]] == ["f"]


def test_too_many_papers_is_no_match():
    many = [paper(f"p{i}", f"Paper {i}", creators="Anna Smith, Ben Jones") for i in range(11)]
    assert match("What did Smith and Jones show?", many) == ([], "")


class FakeFaiss:
    def __init__(self, vectors):
        self.vectors = vectors

    def reconstruct(self, row):
        return self.vectors[row]


def test_chunks_come_from_the_matched_papers_only_best_first_without_a_cap():
    from llama_index.core.schema import TextNode

    chunks = {k: [TextNode(text="t", metadata={"title": t}) for t in titles]
              for k, titles in {"fpp": ["FPP 1", "FPP 2", "FPP 3"], "other": ["Other"]}.items()}
    vectors = np.array([[1, 0], [0.6, 0.8], [0, 1], [1, 0]], dtype=np.float32)
    lookup = ReferenceLookup(PAPERS, chunks, {"fpp": [0, 1, 2], "other": [3]}, FakeFaiss(vectors),
                             SimpleNamespace(get_query_embedding=lambda q: [0.0, 1.0]))
    got = lookup.chunks("question", [PAPERS[0]], 7)
    assert [n.node.metadata["title"] for n in got] == ["FPP 3", "FPP 2", "FPP 1"]  # all three, closest first
    assert round(1 - got[0].score / 2, 3) == 1.0  # the score is an L2 distance, like the vector search's


def test_a_named_paper_skips_the_topic_check_and_the_search():
    q = make_qualle(False, [], [], "They showed flexible analyses inflate false positives [0].")
    q.route = lambda query, router=None: (_ for _ in ()).throw(AssertionError("no topic check after a title match"))
    q.document_retriever.retrieve_and_rerank = lambda *a: (_ for _ in ()).throw(AssertionError("no search"))
    q.document_retriever.n_context_items = 7
    q.references = SimpleNamespace(match=lambda *questions: ([PAPERS[0]], "title"),
                                   chunks=lambda query, found, n: [node("False-Positive Psychology")])
    final = list(q.get_response("Why did Simmons, Nelson and Simonsohn kick off the crisis?", "chat"))[-1]
    assert final["status"] == "complete" and "False-Positive Psychology" in final["metadata"]["sources"]


def test_after_an_author_match_the_topic_check_still_sends_people_to_forrt_and_overrules_only_off_topic():
    def ask(intent):
        q = make_qualle(False, [node("Ordinary search")], [], "Answer [0].")
        q.route = lambda query, router=None: intent
        q.start_forrt_in_papers = lambda query, intent: None
        q.forrt_in_papers_result = lambda job, timings: []
        q.document_retriever.n_context_items = 7
        q.references = SimpleNamespace(match=lambda *questions: ([PAPERS[0]], "authors"),
                                       chunks=lambda query, found, n: [node("False-Positive Psychology")])
        return list(q.get_response("What did Simmons and Nelson show?", "chat"))[-1]

    assert "False-Positive Psychology" in ask("off_topic")["metadata"]["sources"]  # overruled
    assert "False-Positive Psychology" in ask("open_science")["metadata"]["sources"]
