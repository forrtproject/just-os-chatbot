"""Quotes only from open licences, cluster list with a BOM, early exclusions, reference-list chunks in a paper lookup,
adaptive top-k without the re-ranker, manifest.json of an index, and the ingestion script fixes. Offline."""

import csv
import json
import socket
from types import SimpleNamespace

import faiss
import httpx
import numpy as np
import pandas as pd
import pytest
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.vector_stores.faiss import FaissVectorStore

from just_os import clusters, manifest, qualle, rag_service, trace
from just_os.forrt_pages import check_page_index
from just_os.reference_lookup import Paper, ReferenceLookup
from just_os.references import metadata_passage_allowed, passage_allowed
from scripts import (add_to_index, build_abstract_cards, build_glossary, convert_cluster_pdfs, curate, embed,
                     fetch_web_resources, justos_markdown_metadata, make_share_bundle)

REFERENCE_LIST = " ".join(f"Smith, J. ({1990 + i}). Title {i}. Journal, {i}(2), 10-20. et al." for i in range(12))
PROSE = ("Preregistration means writing down the hypotheses, the design and the analysis plan before the data are "
         "collected, so that readers can tell planned tests from exploratory ones and judge the evidence fairly.")


# --- 1. quotes only from open licences


@pytest.mark.parametrize("meta, allowed", [
    ({"conditions_of_use": "FORRT cluster PDF (open access)", "licence": "", "oa_status": "gold"}, False),  # unknown licence
    # the OpenAlex licence belongs to one open-access copy, not to the cluster PDF: it never allows a quote
    ({"conditions_of_use": "FORRT cluster PDF (open access)", "licence": "cc-by", "oa_status": "gold"}, False),
    ({"conditions_of_use": "FORRT cluster PDF (CC BY)", "licence": "cc-by", "oa_status": "gold"}, False),
    ({"conditions_of_use": "", "licence": "cc-by", "oa_status": "gold", "source_file": "a.pdf"}, False),
    ({"conditions_of_use": "cc-by", "licence": "cc-by", "oa_status": "gold", "source_file": "a.pdf"}, True),  # checked
    ({"conditions_of_use": "cc-by", "licence": "cc-by", "oa_status": "closed"}, False),  # closed access wins
    ({"conditions_of_use": "CC BY 4.0", "oa_status": " Closed "}, False),
    ({"conditions_of_use": "CC BY 4.0", "licence": "cc-by-nc"}, False),  # NC in either field
    ({"conditions_of_use": "", "licence": "public-domain", "oa_status": "green"}, False),  # licence alone: no
    # negated or restricted text in either field vetoes the quote
    ({"conditions_of_use": "Not open access (Unpaywall)", "licence": "cc-by"}, False),
    ({"conditions_of_use": "CC BY", "licence": "Not licensed under CC BY"}, False),
    ({"conditions_of_use": "Not licensed under CC BY"}, False),
    ({"conditions_of_use": "Creative Commons Attribution No Derivatives"}, False),
    ({"conditions_of_use": "CC BY", "licence": "closed"}, False),
    ({"conditions_of_use": "CC BY", "licence": "All rights reserved"}, False),
    ({"conditions_of_use": "closed", "licence": "", "oa_status": "closed"}, False),
    ({"conditions_of_use": "CC0"}, True),  # older metadata without oa_status or licence
    ({"conditions_of_use": {"abc": "CC BY"}}, True),  # dict-valued metadata (#24)
    ({}, False),
])
def test_quotes_need_an_open_licence_and_no_closed_access(meta, allowed):
    assert metadata_passage_allowed(meta) is allowed
    assert passage_allowed(meta) is allowed  # a dict goes to the metadata check
    assert passage_allowed("CC BY") is True and passage_allowed(None) is False  # strings as before


@pytest.mark.parametrize("text", [
    "Not licensed under CC BY", "not open access", "Not open access (Unpaywall)", "closed", "CC BY, closed",
    "All rights reserved", "Copyright 2020 the authors, CC BY", "\u00a9 Elsevier", "some-rights-reserved",
    "Creative Commons Attribution No Derivatives", "Creative Commons Attribution-NoDerivatives 4.0",
    "Creative Commons Attribution Non Commercial", "Creative Commons Attribution-NonCommercial 4.0", "CC BY NC",
    "CC BY ND", "cc-by-nd", "CC BY, I don't see any of these", "FORRT cluster PDF (open access)",
])
def test_negated_and_restricted_licence_text_vetoes_the_quote(text):
    assert passage_allowed(text) is False
    assert metadata_passage_allowed({"conditions_of_use": text}) is False
    assert metadata_passage_allowed({"conditions_of_use": "CC BY", "licence": text}) is False


@pytest.mark.parametrize("text", ["CC BY", "cc-by", "CC BY 4.0", "CC BY-SA", "Creative Commons Attribution 4.0 International",
                                  "CC0", "CC-0", "Public Domain", "public-domain", "Creative Commons Public Domain Dedication"])
def test_open_licences_still_allow_the_quote(text):
    assert passage_allowed(text) is True and metadata_passage_allowed({"conditions_of_use": text}) is True


def test_closed_and_unknown_cluster_pdfs_show_no_passage_and_cc_by_ones_do():
    processor = qualle.ReferenceProcessor()

    def cluster_pdf(licence, oa_status):
        return SimpleNamespace(text=PROSE, metadata={"title": "Cluster paper", "creators": "A", "doi": "10.1234/x",
                                                     "conditions_of_use": "FORRT cluster PDF (open access)",
                                                     "licence": licence, "oa_status": oa_status})

    assert processor.reference_data(cluster_pdf("", "closed"))["text"] == ""
    assert processor.reference_data(cluster_pdf("", "bronze"))["text"] == ""
    assert processor.reference_data(cluster_pdf("cc-by", "closed"))["text"] == ""
    # OpenAlex's cc-by is the licence of another copy: the cluster PDF itself shows no passage
    assert processor.reference_data(cluster_pdf("cc-by", "gold"))["text"] == ""
    answer = "Preregistration separates planned tests from exploratory ones [0]."
    assert processor.snippets([cluster_pdf("", "closed")], answer) == {}
    assert processor.snippets([cluster_pdf("cc-by", "gold")], answer) == {}
    checked = cluster_pdf("cc-by", "gold")  # a licence checked for the local copy, in conditions_of_use
    checked.metadata["conditions_of_use"] = "CC BY 4.0"
    assert processor.reference_data(checked)["text"] == PROSE
    assert processor.snippets([checked], answer) != {}


def test_converted_cluster_pdfs_never_take_the_openalex_licence_as_their_own():
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "closed", "licence": "cc-by"}) == "closed"
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "gold", "licence": "cc-by"}) == ""
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "gold", "licence": "public-domain"}) == ""
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "hybrid", "licence": "cc-by-nc-nd"}) == ""
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "", "licence": ""}) == ""
    assert not hasattr(convert_cluster_pdfs, "CLUSTER_LICENCE")


def test_grobid_tei_makes_its_cache_folder(tmp_path, monkeypatch):
    import requests

    cache = tmp_path / "fresh" / "grobid_tei"
    monkeypatch.setattr(convert_cluster_pdfs, "TEI_CACHE", cache)
    monkeypatch.setattr(requests, "post", lambda *a, **k: SimpleNamespace(status_code=200, text="<TEI/>"))
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    assert convert_cluster_pdfs.grobid_tei(pdf, "hash") == "<TEI/>"
    assert (cache / "hash.xml").read_text(encoding="utf-8") == "<TEI/>"


# --- 2. cluster list with a byte-order mark


def test_cluster_list_with_a_bom_gives_clusters_by_title(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text("title,doi,url,clusters\nOpen Code For All,,https://example.org/code,FAIR data and materials\n",
                    encoding="utf-8-sig")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    table = clusters.document_clusters(str(path))
    assert clusters.clusters_of({"title": "Open code for all"}, table) == ["FAIR Data and Materials"]


# --- 3. documents excluded in config/index_corrections.json, before every score


EXCLUDED = "10.1234/excluded"


def scored(doi, distance, text=PROSE, **meta):
    return NodeWithScore(node=TextNode(text=text, metadata={"title": doi, "doi": doi, **meta}), score=distance)


def plain_retriever(nodes, **settings):
    r = object.__new__(qualle.DocumentRetriever)
    r._retriever = SimpleNamespace(retrieve=lambda query: list(nodes))
    r.rerank, r.search_mode, r.min_vector_similarity = False, "vector", 0.5
    r.excluded, r.n_context_items, r.max_per_doc, r.skip_reference_chunks = {EXCLUDED}, 7, 0, False
    r.adaptive_top_k, r.adaptive_ratio, r.adaptive_min = False, 0.5, 1
    for key, value in settings.items():
        setattr(r, key, value)
    return r


def test_an_excluded_document_cannot_lift_the_similarity_floor():
    nodes = [scored(EXCLUDED, 0.0), scored("10.1234/far", 1.4)]  # cosine 1.0 (excluded) and 0.3
    ranked, retrieved = plain_retriever(nodes).retrieve_and_rerank("q")
    assert ranked == [] and EXCLUDED not in [n.metadata["doi"] for n in retrieved]
    assert plain_retriever(nodes).search_order("q", nodes) == []  # called directly, too


def test_the_re_ranker_never_scores_an_excluded_document():
    seen = []
    nodes = [scored(EXCLUDED, 0.0), scored("10.1234/a", 0.5)]
    r = plain_retriever(nodes, rerank=True, min_relevance=0.1,
                        reranker=SimpleNamespace(predict=lambda pairs: seen.extend(pairs) or [0.9] * len(pairs)))
    ranked, _ = r.retrieve_and_rerank("q")
    assert [n.metadata["doi"] for n in ranked] == ["10.1234/a"] and len(seen) == 1


class RowsFaiss:
    """FAISS double: search returns the rows in the order given, k at most."""

    def __init__(self, rows, d=2):
        self.rows, self.d, self.ntotal = rows, d, len(rows)
        self.k = None

    def search(self, q, k):
        self.k = k
        hits = self.rows[:k]
        return np.array([[d for _, d in hits]]), np.array([[r for r, _ in hits]])


def similarity_qualle(faiss_index, vector=(1.0, 0.0)):
    docs = {"n0": TextNode(text="t", metadata={"doi": EXCLUDED}), "n1": TextNode(text="t", metadata={"doi": "10.1234/a"})}
    index = SimpleNamespace(vector_store=SimpleNamespace(_faiss_index=faiss_index),
                            index_struct=SimpleNamespace(nodes_dict={"0": "n0", "1": "n1"}),
                            docstore=SimpleNamespace(docs=docs))
    q = object.__new__(qualle.Qualle)
    q._embed_model = SimpleNamespace(get_query_embedding=lambda text: list(vector))
    q._retriever = SimpleNamespace(_index=index)
    q.document_retriever = SimpleNamespace(excluded={EXCLUDED})
    q.forrt_pages = None
    return q


def test_similarities_skip_excluded_documents_and_survive_an_empty_embedding():
    faiss_index = RowsFaiss([(0, 0.0), (1, 0.8)])  # the excluded chunk is the exact match
    paper, page = similarity_qualle(faiss_index).similarities("q")
    assert faiss_index.k == 2 and paper == pytest.approx(0.6) and page == -1.0
    paper, page = similarity_qualle(RowsFaiss([(1, 0.8)]), vector=(0.0, 0.0)).similarities("q")
    assert (paper, page) == (-1.0, -1.0)  # no NaN


def test_cluster_centroids_leave_out_excluded_documents():
    vectors = np.array([[1, 0], [0, 1]], dtype=np.float32)
    docs = {"n0": TextNode(text="t", metadata={"doi": EXCLUDED}), "n1": TextNode(text="t", metadata={"doi": "10.1234/a"})}
    faiss_index = SimpleNamespace(d=2, ntotal=2, reconstruct_n=lambda start, n: vectors[start:start + n])
    index = SimpleNamespace(vector_store=SimpleNamespace(_faiss_index=faiss_index),
                            index_struct=SimpleNamespace(nodes_dict={"0": "n0", "1": "n1"}),
                            docstore=SimpleNamespace(docs=docs))
    table = {EXCLUDED: ["Research Integrity"], "10.1234/a": ["Research Integrity"]}
    k = clusters.CLUSTERS.index("Research Integrity")
    assert np.allclose(clusters.centroids(index, table)[k], [2 ** -0.5, 2 ** -0.5])
    assert np.allclose(clusters.centroids(index, table, excluded={EXCLUDED})[k], [0, 1])


def test_glossary_citations_match_dois_in_links_and_the_cap_reads_dict_valued_metadata():
    entry = SimpleNamespace(text="t", metadata={"title": "HARKing (FORRT Glossary, English)", "language": "english",
                                                "material_type": "FORRT Glossary", "reference_dois": "10.1234/cited"})
    other = SimpleNamespace(text="t", metadata={"title": "Other", "doi": "10.1234/other"})
    cited = SimpleNamespace(text="t", metadata={"title": "Cited", "link_to_resource": "https://doi.org/10.1234/CITED"})
    kept = plain_retriever([]).limit_per_document([entry, other, cited], "What is HARKing?")
    assert kept == [entry, cited, other]  # the cited paper (DOI only in its link) moves up
    wrapped = [SimpleNamespace(text="t", metadata={"title": {"h": "Same"}, "doi": {"h": "10.1234/same"}}) for _ in range(3)]
    assert len(plain_retriever([], max_per_doc=2).limit_per_document(wrapped)) == 2


# --- ADAPTIVE_TOP_K without the re-ranker


def test_adaptive_top_k_uses_the_best_cosine_of_all_chunks_and_keeps_exact_matches():
    nodes = [scored("10.1234/a", 0.6), scored("10.1234/b", 0.7), scored("10.1234/c", 0.0)]  # boosted order; c is an exact match
    r = plain_retriever(nodes, adaptive_top_k=True, adaptive_ratio=0.9, adaptive_min=1, min_vector_similarity=0)
    kept = r.search_order("q", nodes)
    assert [n.metadata["doi"] for n in kept] == ["10.1234/a", "10.1234/c"]  # cut-off 0.9 x 1.0; b (0.65) goes
    glossary_first = [scored("10.1234/g", None), *nodes]  # a swapped-in glossary entry has no score
    kept = plain_retriever(glossary_first, adaptive_top_k=True, adaptive_ratio=0.9, adaptive_min=1,
                           min_vector_similarity=0).search_order("q", glossary_first)
    assert [n.metadata["doi"] for n in kept] == ["10.1234/g", "10.1234/c"]


# --- SKIP_REFERENCE_CHUNKS in a paper lookup


class FakeFaiss:
    def __init__(self, vectors):
        self.vectors = vectors

    def reconstruct(self, row):
        return self.vectors[row]


def lookup():
    papers = [Paper("p", "Paper", "10.1234/p", ""), Paper("refs", "Only refs", "10.1234/r", "")]
    chunks = {"p": [TextNode(text=REFERENCE_LIST, metadata={"title": "refs of p"}),
                    TextNode(text=PROSE, metadata={"title": "prose of p"}),
                    TextNode(text="A short card.", metadata={"title": "card", "material_type": "FORRT abstract card: Article"})],
              "refs": [TextNode(text=REFERENCE_LIST, metadata={"title": "all refs"})]}
    vectors = np.array([[1, 0], [0.6, 0.8], [0, 1], [1, 0]], dtype=np.float32)
    return ReferenceLookup(papers, chunks, {"p": [0, 1, 2], "refs": [3]}, FakeFaiss(vectors),
                           SimpleNamespace(get_query_embedding=lambda q: [1.0, 0.0])), papers


def test_paper_lookup_skips_reference_lists_unless_a_paper_has_nothing_else():
    ref_lookup, papers = lookup()
    titles = lambda nodes: [n.node.metadata["title"] for n in nodes]  # noqa: E731
    assert titles(ref_lookup.chunks("q", papers[:1], 7)) == ["refs of p", "prose of p", "card"]  # off: as before
    dropped = []
    got = ref_lookup.chunks("q", papers, 7, skip_reference_chunks=True, dropped=dropped)
    assert titles(got) == ["all refs", "prose of p", "card"]  # the card is short on purpose; "Only refs" keeps its chunk
    assert titles(dropped) == ["refs of p"]


def test_paper_lookup_passes_the_setting_and_traces_what_it_left_out():
    from test_qualle import make_qualle
    from test_reference_lookup import PAPERS

    calls = []
    left_out = scored("10.1234/p", 0.1, text=REFERENCE_LIST)

    def chunks(query, found, n, skip_reference_chunks=False, dropped=None):
        calls.append(skip_reference_chunks)
        dropped.append(left_out)
        return [scored("10.1234/p", 0.4)]

    q = make_qualle(False, [], [], "Flexible analyses inflate false positives [0].")
    q.document_retriever.n_context_items, q.document_retriever.skip_reference_chunks = 7, True
    q.document_retriever.min_vector_similarity, q.document_retriever.max_per_doc = 0.5, 0
    q.document_retriever.min_relevance = 0.1
    q.references = SimpleNamespace(match=lambda *questions: ([PAPERS[0]], "title"), chunks=chunks)
    token = trace.begin()
    try:
        final = list(q.get_response("What did False-Positive Psychology show?", "chat"))[-1]
        info = trace.active().info
    finally:
        trace.end(token)
    assert final["status"] == "complete" and calls == [True]
    assert info["reference_lookup"]["reference_chunks_left_out"] == 1
    rows = info["sources"]["chunks"]
    assert [(r["sent"], r["why"]) for r in rows] == [(False, "reference list"), (True, None)]


# --- 4. manifest.json


def test_manifest_round_trip_and_checks(tmp_path):
    path = manifest.write_manifest(tmp_path, "BAAI/bge-m3", 1024, 512, 3, 40)
    saved = manifest.read_manifest(tmp_path)
    assert path.name == "manifest.json" and saved["embedding_model"] == "BAAI/bge-m3" and saved["dimension"] == 1024
    assert {"chunk_size", "document_count", "vector_count", "created_at"} <= set(saved)
    manifest.check_manifest(saved, "BAAI/bge-m3", 1024)  # fine
    with pytest.raises(ValueError, match="1024"):
        manifest.check_manifest(saved, "BAAI/bge-m3", 384)
    with pytest.raises(ValueError, match="voyage-4-large"):  # another model: never a mixed index
        manifest.check_manifest(saved, "mongodb/voyage-4-large", 1024)
    assert manifest.read_manifest(tmp_path / "old_index") is None
    manifest.check_manifest(None, "anything", 7)  # an index without manifest loads as before
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{not json", encoding="utf-8")
    assert manifest.read_manifest(tmp_path / "broken") is None


def test_the_app_refuses_an_index_of_another_vector_size(tmp_path, monkeypatch):
    manifest.write_manifest(tmp_path, "BAAI/bge-m3", 1024)
    monkeypatch.setattr(rag_service.FaissVectorStore, "from_persist_dir",
                        lambda path: SimpleNamespace(_faiss_index=SimpleNamespace(d=384)))
    with pytest.raises(ValueError, match="rebuild"):
        rag_service.load_index({"VECTOR_STORE": str(tmp_path), "EMBEDDING_MODEL": "BAAI/bge-m3"}, None)


def test_forrt_page_index_needs_one_vector_per_page_and_the_manifest_size(tmp_path):
    records = [{"url": "a"}, {"url": "b"}]
    check_page_index(tmp_path, records, np.zeros((2, 4)), "m")  # no manifest: fine
    with pytest.raises(ValueError, match="2 pages"):
        check_page_index(tmp_path, records, np.zeros((3, 4)), "m")
    manifest.write_manifest(tmp_path, "m", 8)
    with pytest.raises(ValueError):
        check_page_index(tmp_path, records, np.zeros((2, 4)), "m")


def test_add_to_index_writes_a_manifest_with_the_counts(tmp_path):
    store = FaissVectorStore(faiss_index=faiss.IndexFlatL2(8))
    index = VectorStoreIndex.from_documents(
        [Document(text="one", metadata={"title": "A"}), Document(text="two", metadata={"title": "B"})],
        storage_context=StorageContext.from_defaults(vector_store=store), embed_model=MockEmbedding(embed_dim=8))
    manifest.write_manifest(tmp_path / "src", "model", 8, chunk_size=256)
    add_to_index.update_manifest(index, tmp_path / "out", tmp_path / "src", "model", 512)
    saved = manifest.read_manifest(tmp_path / "out")
    assert (saved["dimension"], saved["chunk_size"], saved["document_count"], saved["vector_count"]) == (8, 256, 2, 2)


# --- 5. ingestion scripts


def test_excluded_metadata_keys_are_a_sorted_list():
    keys = embed.excluded_keys(pd.DataFrame(columns=["title", "doi", "creators", "conditions_of_use"]))
    assert keys == ["conditions_of_use", "creators", "doi"]


def test_link_only_recommendations_are_kept_apart_and_duplicates_dropped(tmp_path):
    path = tmp_path / "recommendations.jsonl"
    lines = [{"doi": "", "link_to_resource": "https://osf.io/aaaa1/"}, {"doi": "", "link_to_resource": "https://osf.io/bbbb2/"},
             {"doi": "", "link_to_resource": "https://osf.io/aaaa1"}, {"doi": "10.1234/X", "link_to_resource": ""},
             {"doi": "", "link_to_resource": "https://doi.org/10.1234/x", "title": "Other title, same DOI"}]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    rows = curate.read_rows(None, recommendations=str(path))
    assert [(r["doi"], r["link_to_resource"]) for r in rows] == [
        ("", "https://osf.io/aaaa1/"), ("", "https://osf.io/bbbb2/"), ("10.1234/x", "")]


def test_curate_runs_one_job_per_file_and_a_resumed_run_keeps_the_found_metadata(tmp_path, monkeypatch):
    calls = []

    def first_run(row, work):
        calls.append(row["doi"])
        row.update(title="Found title", creators="Found author", conditions_of_use="cc-by")
        return "converted", "# Found title\n\nText."

    monkeypatch.setattr(curate, "pdf_markdown", first_run)
    row = lambda **kw: {"doi": "10.1234/x", "title": "", "link_to_resource": "", "creators": "", **kw}  # noqa: E731
    report, metadata = curate.curate([row(), row(title="Same DOI, other title")], set(), tmp_path, workers=2)
    assert calls == ["10.1234/x"] and [r["outcome"] for r in report] == ["converted", "duplicate"]
    assert len(metadata) == 1

    monkeypatch.setattr(curate, "pdf_markdown", lambda row, work: pytest.fail("a resumed run converts nothing again"))
    report, metadata = curate.curate([row()], set(), tmp_path)
    assert report[0]["outcome"] == "converted"
    assert (metadata[0]["title"], metadata[0]["creators"], metadata[0]["conditions_of_use"]) == (
        "Found title", "Found author", "cc-by")


@pytest.fixture
def fake_dns(monkeypatch):
    table = {"example.org": "93.184.216.34", "intranet.local": "10.0.0.5", "localhost": "127.0.0.1",
             "metadata.cloud": "169.254.169.254", "v6.local": "fe80::1"}

    def getaddrinfo(host, port, *a, **k):
        if host not in table and not host.replace(".", "").isdigit():
            raise socket.gaierror("unknown host")
        address = table.get(host, host)
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize("url, public", [
    ("https://example.org/guide", True),
    ("http://example.org:8080/x", True),
    ("file:///etc/passwd", False),
    ("ftp://example.org/x", False),
    ("http://localhost:8000/admin", False),
    ("http://127.0.0.1/", False),
    ("http://intranet.local/", False),
    ("http://metadata.cloud/latest/meta-data/", False),
    ("http://v6.local/", False),
    ("http://no-such-host.invalid/", False),
    ("", False),
])
def test_only_public_http_links_are_fetched(fake_dns, url, public):
    assert fetch_web_resources.is_public_url(url) is public


def test_blocked_links_are_reported(fake_dns):
    assert curate.web_markdown({"title": "T", "link_to_resource": "http://localhost/secret"})[0] == "blocked_link"


def test_ingestion_scripts_write_a_header_when_nothing_is_found(tmp_path):
    for module in (convert_cluster_pdfs, build_abstract_cards, justos_markdown_metadata):
        module.write_metadata(tmp_path / f"{module.__name__}.csv", [])
        with open(tmp_path / f"{module.__name__}.csv", encoding="utf-8") as f:
            assert next(csv.reader(f))[0] in ("doi_hash", "title")
    build_glossary.write_documents(tmp_path / "glossary", [])
    assert (tmp_path / "glossary" / "metadata.csv").read_text(encoding="utf-8").startswith("doi_hash,title")


def test_ingestion_script_headers_match_the_rows_they_write(tmp_path):
    docs = build_glossary.documents([{"english": [{"title": "Preregistration", "definition": "Planning first."}]}], {})
    build_glossary.write_documents(tmp_path / "glossary", docs)  # DictWriter raises on a missing field
    sheet_row = {"title": "T", "url": "https://doi.org/10.1234/a", "just-os internal identifier": "7"}
    justos_markdown_metadata.write_metadata(tmp_path / "j.csv", [justos_markdown_metadata.metadata_row(sheet_row, {})])
    convert_cluster_pdfs.write_metadata(tmp_path / "c.csv", [{
        "doi_hash": "h", "title": "T", "creators": "", "doi": "", "oa_status": "", "licence": "", "material_type": "Reading",
        "conditions_of_use": "", "link_to_resource": "u", "source_file": "f.pdf"}])
    build_abstract_cards.write_metadata(tmp_path / "a.csv", [{
        "doi_hash": "card-1", "title": "T", "creators": "", "doi": "", "link_to_resource": "", "material_type": "x",
        "conditions_of_use": "", "FORRT_clusters": ""}])
    for name in ("j.csv", "c.csv", "a.csv"):
        assert len(pd.read_csv(tmp_path / name)) == 1


def test_share_bundle_leaves_out_env_by_default_and_has_the_default_index(tmp_path):
    (tmp_path / ".env").write_text("KEY=secret\n", encoding="utf-8")
    parts, with_env = make_share_bundle.options(["make_share_bundle.py"], root=tmp_path)
    assert with_env is False
    paths = [p for p, _ in parts]
    assert "data/processed/vs_latest_bge-m3_glossary" in paths and "data/curation/forrt_article_list.csv" in paths
    assert "data/processed/vs_latest_bge-m3" not in paths
    assert make_share_bundle.options(["x", "--include-env"], root=tmp_path)[1] is True
    assert make_share_bundle.options(["x", "--include-env"], root=tmp_path / "no_env")[1] is False
    minimal, _ = make_share_bundle.options(["x", "--minimal"], root=tmp_path)
    assert [p for p, _ in minimal] == [p for p, _ in make_share_bundle.RUN]


def test_load_url_has_a_timeout(monkeypatch):
    from ingest import helpers

    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"a,b\n"

    monkeypatch.setattr(helpers.urllib.request, "urlopen", lambda url, timeout=None: seen.update(timeout=timeout) or Response())
    assert helpers.load_url("https://example.org/x.csv") == "a,b\n" and seen["timeout"] == 60


# --- review fixes: SSRF at connection time


class FakeSocket:
    def setsockopt(self, *args):
        pass

    def close(self):
        pass


def test_public_only_backend_connects_to_the_address_it_checked(monkeypatch):
    """DNS rebinding: the first answer is public, every later one private. The backend resolves once and connects to
    that checked address, never to the host name (which the OS would resolve again)."""
    answers = iter(["93.184.216.34", "127.0.0.1", "127.0.0.1"])
    lookups, connected = [], []

    def getaddrinfo(host, port, *a, **k):
        lookups.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", lambda address, *a, **k: connected.append(address) or FakeSocket())
    fetch_web_resources.PublicOnlyBackend().connect_tcp("rebind.example", 443)
    assert lookups == ["rebind.example"] and connected == [("93.184.216.34", 443)]


def test_public_only_backend_refuses_private_hosts_before_connecting(fake_dns, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("no connection to a private host"))
    backend = fetch_web_resources.PublicOnlyBackend()
    for host in ("intranet.local", "localhost", "metadata.cloud", "v6.local", "127.0.0.1", "no-such-host.invalid"):
        with pytest.raises(fetch_web_resources.BlockedConnect):
            backend.connect_tcp(host, 80)
    with pytest.raises(fetch_web_resources.BlockedConnect):
        backend.connect_unix_socket("/var/run/docker.sock")


def test_public_clients_use_the_guarded_backend_and_no_env_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
    for http in (fetch_web_resources.public_client(), curate.guarded_client()):
        assert isinstance(http._transport, fetch_web_resources.PublicOnlyTransport)
        assert isinstance(http._transport._pool._network_backend, fetch_web_resources.PublicOnlyBackend)
        assert not http._mounts  # an env proxy would connect for the client, unchecked
        assert http.follow_redirects
    with pytest.raises(ValueError):
        fetch_web_resources.PublicOnlyTransport(proxy="http://127.0.0.1:3128")


@pytest.fixture
def public_site(fake_dns, monkeypatch):
    """A local web server that the fake DNS's public example.org reaches: /page is HTML, /hop redirects to a private
    host. Only connections the backend allowed are made (to 93.184.216.34, rerouted to the local server)."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/hop":
                self.send_response(302)
                self.send_header("Location", "http://intranet.local/admin")
                self.end_headers()
                return
            body = b"<html><body><main>" + b"Open data lets others check results. " * 30 + b"</main></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    real = socket.create_connection
    connected = []

    def create_connection(address, *args, **kwargs):
        connected.append(address[0])
        assert address[0] == "93.184.216.34", f"connection to {address} was not checked"
        return real(("127.0.0.1", server.server_address[1]), *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", create_connection)
    yield f"http://example.org:{server.server_address[1]}", connected
    server.shutdown()
    server.server_close()


def test_fetch_follows_public_pages_and_refuses_a_redirect_to_a_private_host(public_site):
    base, connected = public_site
    assert "Open data lets others check results." in fetch_web_resources.fetch(base + "/page")
    with pytest.raises(fetch_web_resources.BlockedURL, match="intranet.local"):
        fetch_web_resources.fetch(base + "/hop")
    assert curate.web_markdown({"title": "T", "link_to_resource": base + "/hop"})[0] == "blocked_link"
    with curate.guarded_client() as http, pytest.raises(httpx.ConnectError):  # a failed source for pdf_sources
        http.get(base + "/hop")
    assert set(connected) == {"93.184.216.34"}


# --- review fixes: manifest mismatch raises


class SizedEmbedder:
    def __init__(self, size):
        self._model = SimpleNamespace(get_sentence_embedding_dimension=lambda: size)


def test_the_huggingface_embedder_exposes_its_size_where_embedder_dimension_reads_it():
    """No weights downloaded: the attribute chain embedder_dimension relies on exists in the installed packages."""
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from sentence_transformers import SentenceTransformer

    assert "_model" in HuggingFaceEmbedding.__private_attributes__
    assert callable(getattr(SentenceTransformer, "get_embedding_dimension", None)
                    or getattr(SentenceTransformer, "get_sentence_embedding_dimension", None))
    fake = object.__new__(SentenceTransformer)  # bypass loading; answer as a loaded model would
    fake.__dict__["get_embedding_dimension"] = lambda: 1024
    assert manifest.embedder_dimension(SimpleNamespace(_model=fake)) == 1024


def test_embedder_dimension_is_read_without_embedding():
    assert manifest.embedder_dimension(SizedEmbedder(1024)) == 1024
    assert manifest.embedder_dimension(SimpleNamespace()) is None  # Voyage, test doubles
    assert manifest.embedder_dimension(SizedEmbedder(None)) is None
    with pytest.raises(ValueError, match="384"):
        manifest.check_manifest(None, "BAAI/bge-small-en-v1.5", 1024, embedder_size=384)  # no manifest, wrong size
    manifest.check_manifest(None, "any", 1024, embedder_size=None)  # no manifest, size unknown: loads as before
    manifest.check_manifest(None, "any", 1024, embedder_size=1024)


def test_the_app_refuses_an_index_of_another_model_or_embedder_size(tmp_path, monkeypatch):
    monkeypatch.setattr(rag_service.FaissVectorStore, "from_persist_dir",
                        lambda path: SimpleNamespace(_faiss_index=SimpleNamespace(d=1024)))
    monkeypatch.setattr(rag_service.StorageContext, "from_defaults", lambda **kwargs: object())
    monkeypatch.setattr(rag_service, "load_index_from_storage", lambda **kwargs: "index")
    config = {"VECTOR_STORE": str(tmp_path), "EMBEDDING_MODEL": "BAAI/bge-m3"}
    assert rag_service.load_index(config, None) == "index"  # no manifest: as before
    with pytest.raises(ValueError, match="384"):
        rag_service.load_index(config, SizedEmbedder(384))
    manifest.write_manifest(tmp_path, "mongodb/voyage-4-large", 1024)
    with pytest.raises(ValueError, match="voyage-4-large"):
        rag_service.load_index(config, None)
    manifest.write_manifest(tmp_path, "BAAI/bge-m3", 1024)
    assert rag_service.load_index(config, SizedEmbedder(1024)) == "index"


def test_forrt_page_index_refuses_another_model_or_embedder_size(tmp_path):
    records = [{"url": "a"}, {"url": "b"}]
    with pytest.raises(ValueError):
        check_page_index(tmp_path, records, np.zeros((2, 4)), "m", embedder_size=8)
    manifest.write_manifest(tmp_path, "other-model", 4)
    with pytest.raises(ValueError, match="other-model"):
        check_page_index(tmp_path, records, np.zeros((2, 4)), "m")
    check_page_index(tmp_path, records, np.zeros((2, 4)), "other-model", embedder_size=4)


def test_add_to_index_refuses_to_append_with_another_model(tmp_path):
    store = FaissVectorStore(faiss_index=faiss.IndexFlatL2(8))
    index = VectorStoreIndex.from_documents([Document(text="one", metadata={"title": "A"})],
                                            storage_context=StorageContext.from_defaults(vector_store=store),
                                            embed_model=MockEmbedding(embed_dim=8))
    add_to_index.check_index(index, tmp_path, "model")  # no manifest: as before
    with pytest.raises(ValueError):
        add_to_index.check_index(index, tmp_path, "model", SizedEmbedder(16))
    manifest.write_manifest(tmp_path, "old-model", 8)
    with pytest.raises(ValueError, match="old-model"):
        add_to_index.check_index(index, tmp_path, "new-model")
    add_to_index.check_index(index, tmp_path, "old-model", SizedEmbedder(8))
    assert manifest.read_manifest(tmp_path)["embedding_model"] == "old-model"  # not overwritten


# --- review fixes: excluded chunks never take a top-k place


def chunk(node_id, text, doi):
    return TextNode(id_=node_id, text=text, metadata={"title": doi, "doi": doi})


def test_vector_search_returns_top_k_eligible_chunks_when_excluded_ones_rank_first():
    from just_os.hybrid import ExcludingRetriever, excluded_node_ids, search_retriever

    nodes = [chunk("x1", "t", EXCLUDED), chunk("x2", "t", EXCLUDED), chunk("a", "t", "10.1/a"), chunk("b", "t", "10.1/b"),
             chunk("c", "t", "10.1/c")]
    ids = excluded_node_ids(nodes, {EXCLUDED})
    assert ids == {"x1", "x2"}
    # the wrapped retriever fetches top_k + 2 (create_retriever), the excluded two first
    vector = SimpleNamespace(retrieve=lambda q: [NodeWithScore(node=n, score=0.1 * i) for i, n in enumerate(nodes[:4])])
    retriever = search_retriever("vector", vector, [], 2, ids)
    assert isinstance(retriever, ExcludingRetriever) and retriever.vector_retriever is vector
    assert [h.node.node_id for h in retriever.retrieve("q")] == ["a", "b"]
    assert search_retriever("vector", vector, [], 2) is vector  # no exclusions: as before


def test_hybrid_and_keyword_search_leave_excluded_chunks_out_before_the_cut():
    from just_os.hybrid import HybridRetriever, KeywordRetriever

    nodes = [chunk("x", "HARKing HARKing HARKing", EXCLUDED), chunk("a", "HARKing twice HARKing", "10.1/a"),
             chunk("b", "HARKing once", "10.1/b"), chunk("c", "open data", "10.1/c")]
    keyword = KeywordRetriever(nodes, top_k=2, excluded_ids={"x"})
    assert [h.node.node_id for h in keyword.retrieve("HARKing")] == ["a", "b"]
    assert [h.node.node_id for h in KeywordRetriever(nodes, top_k=2).retrieve("HARKing")] == ["x", "a"]  # as before
    vector = SimpleNamespace(retrieve=lambda q: [NodeWithScore(node=nodes[0], score=0.0),
                                                 NodeWithScore(node=nodes[3], score=0.5)])
    hits = HybridRetriever(vector, nodes, top_k=3, excluded_ids={"x"}).retrieve("HARKing")
    assert "x" not in [h.node.node_id for h in hits] and len(hits) == 3


def test_create_retriever_fetches_the_excluded_chunks_in_addition(tmp_path):
    corrections = tmp_path / "corrections.json"
    corrections.write_text(json.dumps({"exclude": {EXCLUDED: "another work"}}), encoding="utf-8")
    docs = {"x1": chunk("x1", "t", EXCLUDED), "x2": chunk("x2", "t", EXCLUDED), "a": chunk("a", "t", "10.1/a")}
    asked = []
    index = SimpleNamespace(docstore=SimpleNamespace(docs=docs),
                            as_retriever=lambda similarity_top_k: asked.append(similarity_top_k) or SimpleNamespace())
    retriever = rag_service.create_retriever({"RETRIEVER_TOP_K": 20, "SEARCH_MODE": "vector",
                                              "INDEX_CORRECTIONS_FILE": str(corrections)}, None, index)
    assert asked == [22] and retriever.top_k == 20 and retriever.excluded_ids == {"x1", "x2"}
    rag_service.create_retriever({"RETRIEVER_TOP_K": 20, "SEARCH_MODE": "vector"}, None, index)
    assert asked[-1] == 20


# --- review fixes: link-only resources, URL case, resume sidecars


def test_untitled_links_get_their_own_document_key_and_survive_add_to_index(tmp_path):
    from just_os.references import document_key, normalize_url

    assert document_key({"link_to_resource": "HTTPS://OSF.io/Guide/"}) == "url:https://osf.io/Guide"
    assert document_key({"link_to_resource": "https://osf.io/guide"}) != document_key({"link_to_resource": "https://osf.io/Guide"})
    assert document_key({"title": "T", "link_to_resource": "https://x.org"}) == "t"  # a title still comes first
    assert document_key({}) == ""
    assert normalize_url("https://Example.ORG/Path?Q=A#Frag") == "https://example.org/Path?Q=A#Frag"
    assert document_key({"link_to_resource": "https://app.org/#/a"}) != document_key({"link_to_resource": "https://app.org/#/b"})
    for name in ("p1", "p2"):
        (tmp_path / f"{name}.md").write_text("Some page text.", encoding="utf-8")
    metadata = pd.DataFrame([{"doi_hash": "p1", "title": "", "doi": "", "link_to_resource": "https://a.org/one"},
                             {"doi_hash": "p2", "title": "", "doi": "", "link_to_resource": "https://a.org/two"}]).set_index("doi_hash")
    docs = add_to_index.new_documents(tmp_path, metadata, set())
    assert [d.metadata["link_to_resource"] for d in docs] == ["https://a.org/one", "https://a.org/two"]
    assert add_to_index.new_documents(tmp_path, metadata, {"url:https://a.org/one"})[0].metadata["link_to_resource"] == "https://a.org/two"
    index = SimpleNamespace(docstore=SimpleNamespace(docs={d.doc_id: d for d in docs}))  # both are in the index
    assert add_to_index.indexed_keys(index) == {"url:https://a.org/one", "url:https://a.org/two"}
    store = tmp_path / "store"
    store.mkdir()
    (store / "docstore.json").write_text(json.dumps({"docstore/data": {
        d.doc_id: {"__data__": {"metadata": d.metadata}} for d in docs}}), encoding="utf-8")
    assert curate.indexed_keys(store) == {"url:https://a.org/one", "url:https://a.org/two"}


def test_curate_dedup_keeps_the_case_of_paths_and_queries():
    assert curate.dedup_key({"link_to_resource": "https://OSF.IO/AbCd1/"}) == curate.dedup_key({"link_to_resource": "https://osf.io/AbCd1"})
    assert curate.dedup_key({"link_to_resource": "https://osf.io/AbCd1"}) != curate.dedup_key({"link_to_resource": "https://osf.io/abcd1"})
    assert curate.dedup_key({"link_to_resource": "https://x.org/p?id=A"}) != curate.dedup_key({"link_to_resource": "https://x.org/p?id=a"})


@pytest.mark.parametrize("sidecar", ["null", "[1, 2]", "{broken", '"text"'])
def test_a_resumed_run_survives_a_sidecar_that_is_not_an_object(tmp_path, monkeypatch, sidecar):
    markdown_dir = tmp_path / "markdown"
    markdown_dir.mkdir()
    row = {"title": "", "doi": "", "link_to_resource": "https://x.org/page", "creators": "", "conditions_of_use": "",
           "material_type": ""}
    key = curate.resource_key(row)
    (markdown_dir / f"{key}.md").write_text("# T\n\ntext", encoding="utf-8")
    (markdown_dir / f"{key}.json").write_text(sidecar, encoding="utf-8")
    monkeypatch.setattr(curate, "web_markdown", lambda row: pytest.fail("a resumed run converts nothing again"))
    report, metadata = curate.curate([row], set(), tmp_path)
    assert report[0]["outcome"] == "converted" and metadata[0]["doi_hash"] == key
    assert isinstance(json.loads((markdown_dir / f"{key}.json").read_text(encoding="utf-8")), dict)  # rewritten whole


def test_write_atomic_leaves_no_partial_file(tmp_path, monkeypatch):
    import os
    import stat

    target = tmp_path / "a.md"
    curate.write_atomic(target, "first")
    assert target.read_text(encoding="utf-8") == "first"
    umask = os.umask(0)
    os.umask(umask)
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~umask  # the usual permissions, readable from the host

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(curate.os, "replace", failing_replace)
    with pytest.raises(OSError):
        curate.write_atomic(target, "second, cut short")
    assert target.read_text(encoding="utf-8") == "first"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md"]  # no temporary file left, none named *.md


# --- review fixes: debug trace, answer cache, eval, docs


def test_the_debug_trace_shows_excerpts_only_for_open_licences():
    r = plain_retriever([])
    r.min_relevance = 0.1
    open_chunk = scored("10.1234/open", 0.2, conditions_of_use="CC BY")
    cluster_chunk = scored("10.1234/cluster", 0.3, conditions_of_use="FORRT cluster PDF (open access)", licence="cc-by")
    token = trace.begin()
    try:
        r.trace_sources([(0.9, open_chunk), (0.8, cluster_chunk)], [open_chunk, cluster_chunk], None, "rerank")
        rows = trace.active().info["sources"]["chunks"]
    finally:
        trace.end(token)
    assert rows[0]["text"].startswith("Preregistration") and rows[1]["text"] == ""


def test_the_answer_cache_key_carries_the_quote_rule_version(monkeypatch):
    from just_os import answer_cache

    config = {"ANSWER_CACHE_TTL": 60, "ANSWER_CACHE_MIN_SIMILARITY": 0.9, "ANSWER_CACHE_MAX_ITEMS": 10}
    key = answer_cache.AnswerCache(None, None, config).key
    monkeypatch.setattr(answer_cache, "CACHE_VERSION", answer_cache.CACHE_VERSION + 1)
    assert answer_cache.AnswerCache(None, None, config).key != key


def test_cluster_boost_eval_leaves_excluded_chunks_out_before_the_boost(monkeypatch):
    import importlib
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    cluster_boost = importlib.import_module("cluster_boost")
    limiter = cluster_boost.boost_limiter({"MAX_CHUNKS": 7, "MAX_CHUNKS_PER_DOC": 0, "SKIP_REFERENCE_CHUNKS": True}, {EXCLUDED})
    assert limiter.skip_reference_chunks is True
    boosted_with = []
    monkeypatch.setattr(cluster_boost, "boosted", lambda nodes, *a: boosted_with.extend(nodes) or nodes)
    nodes = [scored(EXCLUDED, 0.0), scored("10.1234/a", 0.5), scored("10.1234/refs", 0.6, text=REFERENCE_LIST)]
    kept = cluster_boost.boost_and_limit(limiter, nodes, "some cluster", 0.02, {})
    assert EXCLUDED not in [n.metadata["doi"] for n in boosted_with]
    assert [n.metadata["doi"] for n in kept] == ["10.1234/a"]


def test_architecture_doc_names_the_licence_of_the_license_file():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert "Apache License" in (root / "LICENSE").read_text(encoding="utf-8")[:200]
    line = next(line for line in (root / "docs/architecture.md").read_text(encoding="utf-8").splitlines()
                if line.lstrip("│├└─ ").startswith("LICENSE"))
    assert "Apache 2.0" in line
