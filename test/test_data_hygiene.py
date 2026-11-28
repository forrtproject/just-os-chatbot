"""Quotes only from open licences, cluster list with a BOM, early exclusions, reference-list chunks in a paper lookup,
adaptive top-k without the re-ranker, manifest.json of an index, and the ingestion script fixes. Offline."""

import csv
import json
import logging
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
    ({"conditions_of_use": "FORRT cluster PDF (open access)", "licence": "cc-by", "oa_status": "gold"}, True),
    ({"conditions_of_use": "cc-by", "licence": "cc-by", "oa_status": "closed"}, False),  # closed access wins
    ({"conditions_of_use": "CC BY 4.0", "oa_status": " Closed "}, False),
    ({"conditions_of_use": "CC BY 4.0", "licence": "cc-by-nc"}, False),  # NC in either field
    ({"conditions_of_use": "", "licence": "public-domain", "oa_status": "green"}, True),
    ({"conditions_of_use": "closed", "licence": "", "oa_status": "closed"}, False),
    ({"conditions_of_use": "CC0"}, True),  # older metadata without oa_status or licence
    ({"conditions_of_use": {"abc": "CC BY"}}, True),  # dict-valued metadata (#24)
    ({}, False),
])
def test_quotes_need_an_open_licence_and_no_closed_access(meta, allowed):
    assert metadata_passage_allowed(meta) is allowed
    assert passage_allowed(meta) is allowed  # a dict goes to the metadata check
    assert passage_allowed("CC BY") is True and passage_allowed(None) is False  # strings as before


def test_closed_and_unknown_cluster_pdfs_show_no_passage_and_cc_by_ones_do():
    processor = qualle.ReferenceProcessor()

    def cluster_pdf(licence, oa_status):
        return SimpleNamespace(text=PROSE, metadata={"title": "Cluster paper", "creators": "A", "doi": "10.1234/x",
                                                     "conditions_of_use": "FORRT cluster PDF (open access)",
                                                     "licence": licence, "oa_status": oa_status})

    assert processor.reference_data(cluster_pdf("", "closed"))["text"] == ""
    assert processor.reference_data(cluster_pdf("", "bronze"))["text"] == ""
    assert processor.reference_data(cluster_pdf("cc-by", "closed"))["text"] == ""
    assert processor.reference_data(cluster_pdf("cc-by", "gold"))["text"] == PROSE
    answer = "Preregistration separates planned tests from exploratory ones [0]."
    assert processor.snippets([cluster_pdf("", "closed")], answer) == {}
    assert processor.snippets([cluster_pdf("cc-by", "gold")], answer) != {}


def test_converted_cluster_pdfs_record_the_real_licence():
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "closed", "licence": "cc-by"}) == "closed"
    assert convert_cluster_pdfs.cluster_conditions({"oa_status": "gold", "licence": "cc-by"}) == "cc-by"
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


def test_manifest_round_trip_and_checks(tmp_path, caplog):
    path = manifest.write_manifest(tmp_path, "BAAI/bge-m3", 1024, 512, 3, 40)
    saved = manifest.read_manifest(tmp_path)
    assert path.name == "manifest.json" and saved["embedding_model"] == "BAAI/bge-m3" and saved["dimension"] == 1024
    assert {"chunk_size", "document_count", "vector_count", "created_at"} <= set(saved)
    manifest.check_manifest(saved, "BAAI/bge-m3", 1024)  # fine
    with pytest.raises(ValueError, match="1024"):
        manifest.check_manifest(saved, "BAAI/bge-m3", 384)
    with caplog.at_level(logging.ERROR):
        manifest.check_manifest(saved, "mongodb/voyage-4-large", 1024)
    assert "voyage-4-large" in caplog.text
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


def test_blocked_links_are_reported_and_redirects_are_checked(fake_dns):
    assert curate.web_markdown({"title": "T", "link_to_resource": "http://localhost/secret"})[0] == "blocked_link"
    with pytest.raises(fetch_web_resources.BlockedURL):
        fetch_web_resources._CheckedRedirects().redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/")

    def handler(request):
        if request.url.host == "example.org":
            return httpx.Response(302, headers={"Location": "http://intranet.local/admin"})
        return httpx.Response(200, text="private")

    http = curate.guarded_client(httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    with pytest.raises(httpx.HTTPError):  # a failed source, as pdf_sources skips it
        http.get("https://example.org/paper.pdf")
    with pytest.raises(httpx.HTTPError):
        http.get("http://localhost/")


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
