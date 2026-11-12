"""Eval and ingestion scripts: judge (#8), classifier comparison (#9), cluster PDFs (#17),
HTML route (#18), adding to an index (#25), team bundle, dict-valued metadata in eval (#24)."""

import json
import stat
import sys
import zipfile
from pathlib import Path

import faiss
import pandas as pd
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.vector_stores.faiss import FaissVectorStore

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import classify  # noqa: E402
import export_questions  # noqa: E402
import judge  # noqa: E402
import make_retrieval_set  # noqa: E402
import run  # noqa: E402
from just_os import qualle  # noqa: E402
from scripts import add_to_index, convert_cluster_pdfs, fetch_web_resources, justos_markdown_metadata, make_share_bundle, match_cluster_pdfs  # noqa: E402
from test_qualle import CONFIG, FakeChatManager, FakeClient, completion  # noqa: E402


def processor(*responses):
    return qualle.QueryProcessor(FakeClient(*responses), CONFIG, FakeChatManager())


# --- #8 judge


def test_judge_scores_answered_rows_only():
    row = {"outcome": "answered", "answer": "Open data helps [0].", "passages": '["open data passage"]'}
    assert judge.judge_row(processor(completion(tool_arguments='{"supported_share": 0.75}')), row) == 0.75
    assert judge.judge_row(processor(), {**row, "outcome": "refused"}) == ""
    assert judge.judge_row(processor(completion(tool_arguments='{"supported_share": 7}')), row) == 1.0


# --- #9 classifier comparison


def test_classifier_summary():
    results = [("open_science", "open_science", 1.0, 0.001), ("open_science", "off_topic", 1.0, 0.001),
               ("off_topic", "open_science", 1.0, 0.001), ("off_topic", None, 1.0, 0.0)]
    assert classify.summarize("m", results) == "| m | 4 | 0.25 | 1 | 1 | 1 | 1.0 | 0.75 |"
    assert classify.gold({"expect": "refuse", "intent": "forrt_lookup"}, intent=True) == "forrt_lookup"
    assert classify.gold({"expect": "refuse", "intent": "forrt_lookup"}, intent=False) == "off_topic"


def test_router_gold_and_counting():
    assert classify.route_gold({"route": "both", "expect": "answer"}) == "both"
    assert classify.route_gold({"expect": "refuse"}) == "neither"
    assert classify.route_gold({"question": "Which FORRT teams can I join?"}) == "forrt"  # eval/forrt_questions.jsonl
    # refusing a forrt question is a false refusal; answering a neither question a false answer
    results = [("forrt", "neither", 1.0, 0.0), ("neither", "both", 1.0, 0.0), ("both", "both", 1.0, 0.0)]
    assert classify.summarize("router: jev", results) == "| router: jev | 3 | 0.33 | 1 | 1 | 0 | 1.0 | 0.00 |"


# --- #17 cluster PDF names


def test_cluster_pdf_name_and_match():
    assert match_cluster_pdfs.parse_name("C01_SC01_HistRC_Crüwell_2019") == (1, 1, "histrc", "cruwell", "2019")
    assert match_cluster_pdfs.parse_name("C03_SC02_Topic_Arel-Bundock_2025_b")[3:] == ("arel-bundock", "2025")
    assert match_cluster_pdfs.parse_name("Introduction to research") is None
    assert match_cluster_pdfs.first_author("Crüwell, S., Doorn, J. van (2019). Seven easy steps") == "cruwell"
    refs = [{"author": "cruwell", "year": "2019", "title": "Seven easy steps"}, {"author": "baker", "year": "2016"}]
    assert match_cluster_pdfs.match((1, 1, "t", "cruwell", "2019"), refs)["title"] == "Seven easy steps"
    assert match_cluster_pdfs.match((1, 1, "t", "cruwell", "2020"), refs) is None


def test_cluster_pdf_title_check():
    page = "Seven Easy Steps to Open\nSci-\nence: An Annotated Reading List\nSophia Crüwell"
    assert convert_cluster_pdfs.title_in_text("Seven easy steps to open science: an annotated reading list", page)
    assert not convert_cluster_pdfs.title_in_text("Designing a research integrity promotion plan", page)
    assert not convert_cluster_pdfs.title_in_text("Open", page)  # too short to tell
    with_doi = {"doi": "10.1/x", "title": "A"}
    assert convert_cluster_pdfs.doi_hash(with_doi) == convert_cluster_pdfs.doi_hash({**with_doi, "title": "B"})


TEI_XML = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>
<titleStmt><title>Seven Easy Steps to Open Science</title></titleStmt>
<sourceDesc><biblStruct><analytic>
<author><persName><forename>Sophia</forename><surname>Crüwell</surname></persName></author>
<idno type="DOI">10.1027/2151-2604/A000387</idno></analytic></biblStruct></sourceDesc></fileDesc>
<profileDesc><abstract><p>An annotated reading list.</p></abstract></profileDesc></teiHeader>
<text><body><div><head n="1">Open  access</head><p>Papers should be <ref>(Suber, 2012)</ref> free.</p>
<figure><head>Figure 1</head><figDesc>The steps.</figDesc><table><row><cell>42</cell></row></table></figure></div></body>
<back><div type="references"><listBibl><biblStruct><note>Suber reference</note></biblStruct></listBibl></div>
<div type="annex"><div><head>Appendix</head><p>Extra material.</p></div></div></back></text></TEI>"""


def test_cluster_pdf_grobid_markdown():
    meta, markdown = convert_cluster_pdfs.tei_to_markdown(TEI_XML)
    assert meta == {"title": "Seven Easy Steps to Open Science", "creators": "Sophia Crüwell", "doi": "10.1027/2151-2604/a000387"}
    assert "## 1 Open access\n\nPapers should be (Suber, 2012) free." in markdown
    assert "## Abstract\n\nAn annotated reading list." in markdown and "Figure 1 The steps." in markdown
    assert "Suber reference" not in markdown and "42" not in markdown  # no reference list, no table cells
    assert "Extra material." in markdown  # the appendix is kept


def test_cluster_pdf_doi_is_checked_against_the_first_pages():
    page = "Seven Easy Steps to Open Science\nhttps://doi.org/10.1027/2151-2604/a000387. See also doi:10.1234/other"
    assert convert_cluster_pdfs.find_dois(page) == ["10.1027/2151-2604/a000387", "10.1234/other"]
    works = {"10.1234/other": {"title": "A paper that this one cites"}, "10.1027/2151-2604/a000387": {"title": "Seven easy steps to open science"}, "10.9999/gone": None}
    chosen = convert_cluster_pdfs.choose_work(["10.9999/gone", "10.1234/other", "10.1027/2151-2604/a000387"], works, page)
    assert chosen["title"] == "Seven easy steps to open science"
    assert convert_cluster_pdfs.choose_work(["10.1234/other"], works, page) is None


def test_justos_metadata_marks_papers_outside_the_open_access_list():
    row = {"title": "A", "url/doi (please check)": "https://doi.org/10.1234/closed", "conditions of use": "CC BY",
           "just-os internal identifier": "7", "provider/creators": "Ann"}
    open_access = {"B": "10.1234/open"}
    closed = justos_markdown_metadata.metadata_row(row, open_access)
    assert (closed["doi_hash"], closed["creators"], closed["conditions_of_use"]) == ("0007", "Ann", justos_markdown_metadata.NOT_OA)
    by_title = justos_markdown_metadata.metadata_row({**row, "title": "B", "url/doi (please check)": "https://example.org"}, open_access)
    assert (by_title["doi"], by_title["conditions_of_use"]) == ("10.1234/open", "CC BY")  # DOI known only by title
    no_doi = justos_markdown_metadata.metadata_row({**row, "url/doi (please check)": "https://example.org"}, open_access)
    assert (no_doi["doi"], no_doi["conditions_of_use"]) == ("", "CC BY")  # never checked by Unpaywall


# --- #18 HTML route


def test_main_text_drops_menus_and_scripts():
    html = """<html><body><nav>Home | About</nav><script>alert(1)</script>
    <main><h1>Open data course</h1><p>Lesson one   explains   licences.</p></main><footer>(c)</footer></body></html>"""
    assert fetch_web_resources.main_text(html) == "Open data course\nLesson one explains licences."


# --- #25 add documents to an existing index


def test_add_to_index_skips_documents_already_in_it(tmp_path):
    embed = MockEmbedding(embed_dim=8)
    store = FaissVectorStore(faiss_index=faiss.IndexFlatL2(8))
    index = VectorStoreIndex.from_documents(
        [Document(text="old text", metadata={"title": "Old", "doi": "10.1234/old"})],
        storage_context=StorageContext.from_defaults(vector_store=store),
        embed_model=embed,
    )
    index.storage_context.persist(tmp_path / "index")

    markdown = tmp_path / "md"
    markdown.mkdir()
    (markdown / "a.md").write_text("new text [1]", encoding="utf-8")
    (markdown / "b.md").write_text("old again", encoding="utf-8")
    metadata = pd.DataFrame({"doi_hash": ["a", "b"], "title": ["New", "Old"], "doi": ["10.1234/new", "10.1234/old"]}).set_index("doi_hash")

    loaded = add_to_index.load_index(str(tmp_path / "index"), embed)
    before = len(loaded.docstore.docs)
    documents = add_to_index.new_documents(markdown, metadata, add_to_index.indexed_keys(loaded))
    assert [d.metadata["title"] for d in documents] == ["New"]
    assert documents[0].text == "new text "  # citation marks removed, as in embed.py
    assert add_to_index.add_documents(loaded, documents) == 1
    assert len(loaded.docstore.docs) == before + 1


# --- team bundle


def test_bundle_env_is_private_whatever_its_mode(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"OPENROUTER_API_KEY=secret\n")  # write_text gives \r\n on Windows
    env.chmod(0o666)
    with zipfile.ZipFile(tmp_path / "b.zip", "w") as archive:
        make_share_bundle.add_env(archive, env)
    with zipfile.ZipFile(tmp_path / "b.zip") as archive:
        info = archive.getinfo(".env")
        assert stat.S_IMODE(info.external_attr >> 16) == 0o600
        assert archive.read(".env") == b"OPENROUTER_API_KEY=secret\n"


# --- dict-valued metadata of the 10 documents from #24 in the eval scripts


class Node:
    def __init__(self, metadata):
        self.metadata = metadata


def test_eval_run_unwraps_dict_valued_dois():
    wrapped = Node({"doi": {"15971e768acb8a3c4817369e0d6b1f95": "10.1002/ICD.2315"}})
    assert run.doi_of(wrapped) == "10.1002/icd.2315"
    assert run.doi_of(Node({"doi": "https://doi.org/10.1177/1745691612459058"})) == "10.1177/1745691612459058"
    assert run.doi_of(Node({})) == ""


def test_retrieval_set_unwraps_dict_valued_titles(tmp_path, monkeypatch):
    def node(doc_id, title):
        return {"__data__": {"text": "t", "metadata": {"title": title}, "relationships": {"1": {"node_id": doc_id}}}}

    store = {"docstore/data": {"a": node("d1", {"hash": "Scientific Utopia II"}), "b": node("d2", "Plain title")}}
    path = tmp_path / "docstore.json"
    path.write_text(json.dumps(store), encoding="utf-8")
    monkeypatch.setattr(make_retrieval_set, "DOCSTORE", str(path))
    _, titles = make_retrieval_set.load_documents()
    assert titles == {"d1": "Scientific Utopia II", "d2": "Plain title"}



def test_reviewer_sheet_maps_citations_to_dois():
    # Source 1 has no DOI (empty slot); [3] is out of range; [2] is cited twice
    row = {"retrieved_dois": "10.1/a  10.1/c 10.1/a", "answer": "x [0]. y [2] [2]. z [1] [3]."}
    assert export_questions.bot_dois(row) == (["10.1/a", "10.1/c"], ["10.1/a", "10.1/c"])
    assert export_questions.bot_dois({"retrieved_dois": float("nan"), "answer": "no refs"}) == ([], [])
