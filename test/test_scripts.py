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
import judge  # noqa: E402
import make_retrieval_set  # noqa: E402
import run  # noqa: E402
from just_os import qualle  # noqa: E402
from scripts import add_to_index, convert_cluster_pdfs, fetch_web_resources, make_share_bundle, match_cluster_pdfs  # noqa: E402
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

