# Data, indexes and ingestion

`data/` is git-ignored except the seed CSVs in `data/raw/` and `data/interim/questions_and_text.csv`.
**Some files in `data/NWO JUST-OS/` are private** (grants, MOU, e-mails, logins, meeting notes): never put them in Git, in the index, or in a shared bundle.

## 1. What the index contains

### Live FORRT sheets

`scripts/add_new_resources.py` and `eval/coverage.py` read two published Google Sheets (`URL_FORRT` in `ingest/helpers.py`). Counts on 9 Nov 2026:

| Sheet (document name) | Rows | Unique | With DOI | Match a JUST-OS ID | PDF in `Content/` | Markdown | In the index |
|---|---|---|---|---|---|---|---|
| **FORRT Database 2.0** (`gid=1924034107`): the main resource list | 1,507 | 1,482 | 843 | 1,243 | 669 | 553 | 530 |
| **clusters_panos** (`gid=0`): reference list of the FORRT clusters | 285 | 270 | 252 | 27 | 25 | 15 | 32 |

Counts are rows (a few rows point to the same paper, so a count can be higher than the number of files). The index was **not** built from these live sheets directly: it was built from the June 2025 JUST-OS copy of FORRT Database 2.0 (`data/raw/forrt_db_250627.csv`, with the "JUST-OS internal identifier") plus 44 papers that `add_new_resources.py` added by DOI. The PDFs for `clusters_panos` are in `data/FORRT Clusters pdfs/`; 133 of them were added to the index on 11 Nov 2026 (issue #17, see "FORRT Clusters pdfs" below).


The default index `data/processed/vs_latest_bge-m3/` has **646 documents → 79,808 chunks** (chunk size 350 tokens): the 513 JUST-OS documents (59,473 chunks) plus 133 FORRT cluster papers (11 Nov 2026). The old index `vs_latest_bge-small-en-v1.5` has the same chunks (first built 26 Aug 2025); `scripts/reembed.py` made the bge-m3 index from them. The copies from before the cluster papers are `vs_261111_*_before_clusters/` (section 2).

The full list is in [indexed_documents.csv](indexed_documents.csv) (`just_os_id, title, doi, pdf_path, chunks, licence`). It was made by matching the index metadata (title, then DOI) to `data/raw/forrt_db_250627.csv`:

| Group | Documents | Source PDF |
|---|---|---|
| Matched to a JUST-OS ID, PDF found | 432 | `data/NWO JUST-OS/Content/<id>.pdf` (IDs 950–1299 in sub-folders `950 tot 999/` …; IDs below 1000 there have no leading zero, `950.pdf`) |
| Matched to a JUST-OS ID, PDF not in `Content/` | 37 | Downloaded by `bootstrap_local_database.py`/`add_new_resources.py`; only the Markdown is left |
| No JUST-OS ID (added from the live FORRT sheets by DOI) | 44 | Unpaywall download (`add_new_resources.py`); PDF not kept |

### Why only part of `Content/` is in the index

`Content/` has 657 PDFs. Traced one by one (sheet snapshot → DOI → open-access list `just-os_db_latest.csv` → Markdown → index):

| Stage | PDFs | Has Markdown already | Reason |
|---|---|---|---|
| In the index | 434 | 351 | — |
| **Not open access** (Unpaywall `is_oa` false or not found) | 190 | 165 | Deliberate: `bootstrap_local_database.py` keeps only OA papers, and `embed.py` embeds only Markdown whose `doi_hash` is in the OA list (licence / copyright of shown passages) |
| No DOI in the sheet | 22 | 19 | No DOI → no `doi_hash` → never in the OA list (mostly "Reading" and "Primary Source") |
| Open access + Markdown, but not in the index | 11 | 11 | Probably duplicate `doi_hash` / title mismatch (IDs 161, 423, 455, 568, 579, 609, 614, 675, 927, 1041, 1048); see issue #24 |

So **184 PDFs (165 + 19) are converted already** and could go in without running marker again, **if** the licence allows it. Paywalled papers are a policy question for FORRT: index them for search but show only title + link (issue R5, #6), or leave them out.

How a PDF got in: open access (Unpaywall `is_oa`) **and** a DOI → `data/pdfs/by-doi/<md5(doi)>.pdf` → marker → Markdown → `scripts/embed.py`. The Markdown of the original build is in `data/NWO JUST-OS/BOT/markdown/markdown/` (546 files, `NNNN.md`).

Licence of the 513 documents (field `conditions_of_use`, free text from the form): CC BY (all spellings) ≈ 280, "I don't see any of these" 184, CC BY-NC-ND 14, public domain 8, other. The tooltip shows a passage only for CC BY (incl. SA), CC0 and public domain (`passage_allowed`, issue #6); other sources show title + link.

**Known metadata defect:** 10 documents have every metadata value stored as a one-item dict (`{"<doi_hash>": "title"}`) because `just-os_db_latest.csv` has duplicate `doi_hash` rows and `embed.py` calls `metadata.loc[hash].to_dict()`. Their references showed wrong titles and years. `scripts/embed.py` now keeps one row per `doi_hash` (#24); the current index keeps the defect until it is built again. The references shown to users, `eval/run.py` (`retrieved_dois` and `hit`) and `eval/make_retrieval_set.py` (titles) unwrap these values with `plain_metadata` (`just_os/references.py`), and `eval/coverage.py` and `scripts/get_pub_years.py` unwrap them inline. `scripts/reembed.py` copies the chunks with their metadata, so an index it builds keeps the defect.

## 2. Indexes and vector files

| Path | What | Size | Status |
|---|---|---|---|
| `data/processed/vs_latest_bge-m3/` | **Default index** (FAISS, 1024 dims), 646 documents | 679 MB | Used by the app (`VECTOR_STORE`) |
| `data/processed/vs_latest_bge-m3.zip` | Zipped index for `scripts/get_index.py` | 173 MB | **Out of date**: still the 513-document index |
| `data/processed/vs_latest_bge-small-en-v1.5/` | Old production index (FAISS, 384 dims), 646 documents | 486 MB | English-only option for the app |
| `data/processed/vs_261111_bge-m3_before_clusters/` | bge-m3 index before the cluster papers (513 documents, 59,473 chunks) | 531 MB | E3 in `compare_embeddings.py`; before/after comparisons |
| `data/processed/vs_261111_bge-small-en-v1.5_before_clusters/` | bge-small index before the cluster papers | 387 MB | E1 + chunk texts for `compare_embeddings.py` and `make_retrieval_set.py` (the `emb_cache` rows are these chunks) |
| `data/processed/cluster_markdown/` | Markdown of the 153 checked cluster papers, `metadata.csv`, `rejected.csv` | | Input of `add_to_index.py` (#17) |
| `data/processed/emb_cache/*.npy` | Chunk vectors for E2, E4, E5, E6 (float16, 59,473 rows each) | 959 MB | Eval only (see [evaluation.md](evaluation.md)) |
| `data/NWO JUST-OS/BOT/vs_latest_bge-small-en-v1.5/` | Byte-identical copy of the old index | 406 MB | Not needed (original from Drive) |
| `data/processed/storage_m3/` | Index of Oct 2024 (different chunks, `multi_embed_store.pkl`) | 757 MB | The current code cannot load it. Not used |

To switch the app to the old index, set both lines in `.env` and restart (they must match):
```
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
VECTOR_STORE=data/processed/vs_latest_bge-small-en-v1.5
```

## 3. Data inventory

### In Git (seed data)
| File | Rows | Content |
|---|---|---|
| `data/raw/pub_years.csv` | 628 | Publication year per DOI of the index (OpenAlex, `scripts/get_pub_years.py`); 10 of 638 DOIs have no year → "n.d." |
| `data/raw/forrt_db_250627.csv` | 1,234 | JUST-OS sheet snapshot (June 2025), with "JUST-OS internal identifier" and "Downloaded?" |
| `data/raw/forrt_sheet1_261028.csv` | 1,504 | Live FORRT resource sheet (28 Oct 2026) |
| `data/raw/forrt_sheet2_261028.csv` | 285 | FORRT reference list (28 Oct 2026) |
| `data/raw/forrt_sheet1_261111.csv`, `forrt_sheet2_261111.csv` | 1,507 / 285 | Same sheets, 11 Nov 2026 (used by `match_cluster_pdfs.py`, which takes the newest copy) |
| `data/interim/questions_and_text.csv` | 1,282 | Generated (question, source text) pairs; eval seed |

`ingest/helpers.py` (`URL_FORRT`) reads the live sheets directly; the CSVs are fixed copies. For a new copy, download again and put the date in the name (`YYMMDD`).

### `data/NWO JUST-OS/` (from Google Drive)
| Item | Content | Use |
|---|---|---|
| `Content/` | 657 PDFs named by JUST-OS ID | Source PDFs of the index |
| `BOT/markdown/markdown/` | 546 Markdown files (marker output) | Rebuild the index without marker |
| `BOT/just-os_db_latest.csv` | 575 rows, 538 unique `doi_hash` | Index metadata (use in place of the Drive URL `URL_JUST_OS_DB`) |
| `BOT/Questions.docx`, `Qualification open science.docx`, `Possible conversations.docx`, `Feedback JUST-OS Bot.docx` | Questions with expected sources, in/out-of-scope labels, multi-turn dialogue, bad answers from users | Eval sets |
| `BOT/Inclusion_Exclusion Articles.docx` | Rules for which sources go in | Coverage |
| `Studentassistents/…/FORRT Resource Lists/` | Lists of new resources | Coverage |
| Everything else (`AERN/`, `Application NWO/`, `Grants/`, `Logo_s and designs/`, `Meeting Agendas-Notes/`, `Memorandum of understanding (MOU)_/`, `SURF/`, `Website/`, `Writing/`, `*.pptx`, `Email and Social Media information, Login.docx`) | Project admin, **private** | Not for the bot |

### `data/FORRT Clusters pdfs/`
1,061 PDFs + 930 `.docx` in `Cluster 1–11/` (name `C01_SC01_<topic>_<author>_<year>.pdf`) and two working lists (`01.FORRT_Clusters_Working_Document_v1.xlsx`, `FORRT Cluster_s.xlsx`). **133 papers are in the index** (11 Nov 2026, issue #17):

| Step | Count |
|---|---|
| PDF files (814 unique by content; the same paper is often in several sub-clusters) | 1,061 |
| `.docx` files (not used) | 930 |
| Name matched to a reference in the newest sheets (first author + year, `match_cluster_pdfs.py`); all matches are references of sheet 2, 63 are also in sheet 1 | 368 files, 229 unique |
| Matched title found in the first 3 pages (`convert_cluster_pdfs.py`, pymupdf4llm) → Markdown | 153 papers |
| Rejected: title not in the PDF (a different paper by the same author and year, or a reference without title) | 71 (`rejected.csv`) |
| Already in the index (same DOI or title) | 20 |
| **Added** (`add_to_index.py`, both indexes) | **133** |

Their licence is unknown (`conditions_of_use` empty), so the bot answers from them but shows only title + link. 693 files have no match yet: they need the working lists or a person.

### Other
- `data/archive/`: old prototypes (Oct–Dec 2024: first agent, `storage_m3` build, chunk classification, marker script). The code does not use them; kept for reference.
- `data/*.zip`: the original Google Drive downloads of the two folders above (about 2.3 GB). The folders are already extracted.
- `data/chunked_paragraphs.json`, `data/classified_chunks.json`, `data/interim/chunked_*`: products of the Oct 2024 pipeline. Not used.

## 4. Coverage facts

**Audit of the live sheets (9 Nov 2026, `python eval/coverage.py`, issue #16):** 1,693 unique resources (sheet 1 + sheet 2, by DOI or title). Files: `eval/results/coverage_261109.{csv,md,svg}` (one reason per resource, table, bar chart).

| Reason | Resources | Share | Route to add them |
|---|---|---|---|
| In the index | 519 | 31% | — |
| No DOI: other web page | 370 | 22% | HTML route (#18) |
| DOI, never processed (added after June 2025) | 305 | 18% | Run Unpaywall + download (#25) |
| DOI, checked: not open access | 274 | 16% | Metadata-only "resource cards" (policy question) |
| No DOI: OSF / GitHub page | 136 | 8% | HTML route (#18) |
| No DOI: video | 79 | 5% | Resource card from the FORRT description |
| No DOI and no link | 9 | 1% | Fix in the sheet |
| Excluded by curators | 1 | 0% | — |

Older facts (June 2025 snapshot):

- Snapshot of June 2025: 1,234 rows, 657 downloaded, 689 with a DOI. Only open-access PDFs with a DOI are in the index (513 documents).
- Rows without a DOI are mostly teaching material (Reading 181, Module 63, Syllabus 49, Lecture 43, …) and web pages (osf.io 84, youtube.com 76, datacarpentry.org 27).
- The live sheets have 1,789 rows (1,504 + 285), not ~2,800 as the old plan said.
- Likely largest missing group: web-based teaching material → HTML route (issue C3). Second: paywalled DOIs → metadata-only "resource cards".

## 5. Build an index (ingestion)

**PDF → Markdown tool:** [marker](https://github.com/datalab-to/marker) (`marker-pdf`, `ingest` dependency group), run by `scripts/marker.sh` (no image extraction). On the Meta Science Arena benchmarks (Nov 2026, synthetic + real papers) marker is mid-table: body-text fidelity 0.882 (rank 4 of 12, tied with Docling and pdftotext; GROBID 0.979 is the best tool) and section structure 0.599 (rank 4 of 9). For RAG chunks the text fidelity matters most, so GROBID is worth a test before the next full conversion.


| Step | Command | Input | Output |
|---|---|---|---|
| 1 | `uv run python -m scripts.bootstrap_local_database` | `data/raw/forrt_db_250627.csv` + PDFs in `data/pdfs/by-justos-id/NNNN.pdf` | OA PDFs in `data/pdfs/by-doi/<doi_hash>.pdf` + `data/processed/just-os_db.csv` |
| 2 | `./scripts/marker.sh` | `data/pdfs/by-doi/` | Markdown in `data/processed/markdown/` (GPU recommended) |
| 3 | `uv run python -m scripts.embed` | Markdown + metadata CSV | `data/processed/vs_latest_<model>/` |
| (alt) | `uv run python -m scripts.reembed <index-dir> <model>` | An existing index | Same chunks, new embedding model |

Limits: step 1 does not download PDFs and reads the June 2025 snapshot; step 3 reads metadata from Google Drive (`URL_JUST_OS_DB`); steps 1 and 3 upload to Drive at the end and fail there without `credentials.json` (after the files are written).

## 6. What to share with a teammate (not in Git)

`python scripts/make_share_bundle.py` puts all of it in one file: `share/just-os-team-bundle.zip` (the `share/` folder is git- and docker-ignored). It holds `.env`, the bge-m3 index, `pub_years.csv` and the FORRT sheet 1 (both read by the bot), the bge-small index, `emb_cache/`, FORRT sheet 2, `forrt_db_250627.csv`, `questions_and_text.csv` and `cluster_pdf_metadata.csv`, plus `TEAM_SETUP.md`. `--minimal` keeps only what the bot reads; `--no-env` leaves out your keys. The embedding/re-ranker model weights are not in it: Docker downloads them one time (README step 5).


| Need | Item | How |
|---|---|---|
| Run the bot | `.env` values: own `OPENROUTER_API_KEY`; `OPENSCHOLAR_API_KEY` only if they use OpenScholar | One-to-one, never in chat or issues |
| Run the bot | `data/processed/vs_latest_bge-m3.zip` (173 MB) | Upload (SURFdrive / HF dataset), then `python scripts/get_index.py <url>` |
| Embedding comparison | `emb_cache/` (959 MB) + `vs_latest_bge-small-en-v1.5/` (406 MB) | Same |
| Coverage / ingestion | `BOT/markdown/`, `Content/`, cluster PDFs + xlsx, `just-os_db_latest.csv`, `credentials.json` (Drive upload) | Shared drive; **never** the private admin files |
