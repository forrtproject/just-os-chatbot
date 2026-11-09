# Data, indexes and ingestion

`data/` is git-ignored except the seed CSVs in `data/raw/` and `data/interim/questions_and_text.csv`.
**Some files in `data/NWO JUST-OS/` are private** (grants, MOU, e-mails, logins, meeting notes): never put them in Git, in the index, or in a shared bundle.

## 1. What the index contains

The default index `data/processed/vs_latest_bge-m3/` has **513 documents → 59,473 chunks** (chunk size 350 tokens). The old index `vs_latest_bge-small-en-v1.5` has the same chunks (built 26 Aug 2025); `scripts/reembed.py` made the bge-m3 index from them.

The full list is in [indexed_documents.csv](indexed_documents.csv) (`just_os_id, title, doi, pdf_path, chunks, licence`). It was made by matching the index metadata (title, then DOI) to `data/raw/forrt_db_250627.csv`:

| Group | Documents | Source PDF |
|---|---|---|
| Matched to a JUST-OS ID, PDF found | 409 | `data/NWO JUST-OS/Content/<id>.pdf` (IDs 950–1299 in sub-folders `950 tot 999/` …) |
| Matched to a JUST-OS ID, PDF not in `Content/` | 60 | Downloaded by `bootstrap_local_database.py`/`add_new_resources.py`; only the Markdown is left |
| No JUST-OS ID (added from the live FORRT sheets by DOI) | 44 | Unpaywall download (`add_new_resources.py`); PDF not kept |

How a PDF got in: open access (Unpaywall `is_oa`) **and** a DOI → `data/pdfs/by-doi/<md5(doi)>.pdf` → marker → Markdown → `scripts/embed.py`. The Markdown of the original build is in `data/NWO JUST-OS/BOT/markdown/markdown/` (546 files, `NNNN.md`).

Licence of the 513 documents (field `conditions_of_use`, free text from the form): CC BY (all spellings) ≈ 280, "I don't see any of these" 184, CC BY-NC-ND 14, public domain 8, other. Issue R5 uses this to decide where a passage may be shown.

**Known metadata defect:** 10 documents have every metadata value stored as a one-item dict (`{"<doi_hash>": "title"}`) because `just-os_db_latest.csv` has duplicate `doi_hash` rows and `embed.py` calls `metadata.loc[hash].to_dict()`. Their references show wrong titles and years (issue in [issues.md](issues.md)).

## 2. Indexes and vector files

| Path | What | Size | Status |
|---|---|---|---|
| `data/processed/vs_latest_bge-m3/` | **Default index** (FAISS, 1024 dims) | 556 MB | Used by the app (`VECTOR_STORE`) |
| `data/processed/vs_latest_bge-m3.zip` | Same index, zipped for `scripts/get_index.py` | 173 MB | Share with the team |
| `data/processed/vs_latest_bge-small-en-v1.5/` | Old production index (FAISS, 384 dims) | 406 MB | For the E1 baseline and `compare_embeddings.py` (source of the chunk texts) |
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
| `data/raw/forrt_db_250627.csv` | 1,234 | JUST-OS sheet snapshot (June 2025), with "JUST-OS internal identifier" and "Downloaded?" |
| `data/raw/forrt_sheet1_261028.csv` | 1,504 | Live FORRT resource sheet (28 Oct 2026) |
| `data/raw/forrt_sheet2_261028.csv` | 285 | FORRT reference list (28 Oct 2026) |
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
1,061 PDFs + 930 `.docx` in `Cluster 1–11/` (name `C01_SC01_<topic>_<author>_<year>.pdf`) and two working lists (`01.FORRT_Clusters_Working_Document_v1.xlsx`, `FORRT Cluster_s.xlsx`). **Not in the index.** They need a metadata table first (title, authors, year, DOI, licence): a match on first author + year finds only 352 of 963 files (issue C2).

### Other
- `data/archive/`: old prototypes (Oct–Dec 2024: first agent, `storage_m3` build, chunk classification, marker script). The code does not use them; kept for reference.
- `data/*.zip`: the original Google Drive downloads of the two folders above (about 2.3 GB). The folders are already extracted.
- `data/chunked_paragraphs.json`, `data/classified_chunks.json`, `data/interim/chunked_*`: products of the Oct 2024 pipeline. Not used.

## 4. Coverage facts

- Snapshot of June 2025: 1,234 rows, 657 downloaded, 689 with a DOI. Only open-access PDFs with a DOI are in the index (513 documents).
- Rows without a DOI are mostly teaching material (Reading 181, Module 63, Syllabus 49, Lecture 43, …) and web pages (osf.io 84, youtube.com 76, datacarpentry.org 27).
- The live sheets have 1,789 rows (1,504 + 285), not ~2,800 as the old plan said.
- Likely largest missing group: web-based teaching material → HTML route (issue C3). Second: paywalled DOIs → metadata-only "resource cards".

## 5. Build an index (ingestion)

| Step | Command | Input | Output |
|---|---|---|---|
| 1 | `uv run python -m scripts.bootstrap_local_database` | `data/raw/forrt_db_250627.csv` + PDFs in `data/pdfs/by-justos-id/NNNN.pdf` | OA PDFs in `data/pdfs/by-doi/<doi_hash>.pdf` + `data/processed/just-os_db.csv` |
| 2 | `./scripts/marker.sh` | `data/pdfs/by-doi/` | Markdown in `data/processed/markdown/` (GPU recommended) |
| 3 | `uv run python -m scripts.embed` | Markdown + metadata CSV | `data/processed/vs_latest_<model>/` |
| (alt) | `uv run python -m scripts.reembed <index-dir> <model>` | An existing index | Same chunks, new embedding model |

Limits: step 1 does not download PDFs and reads the June 2025 snapshot; step 3 reads metadata from Google Drive (`URL_JUST_OS_DB`); steps 1 and 3 upload to Drive at the end and fail there without `credentials.json` (after the files are written).

## 6. What to share with a teammate (not in Git)

| Need | Item | How |
|---|---|---|
| Run the bot | `.env` values: own `OPENROUTER_API_KEY`; `OPENSCHOLAR_API_KEY` only if they use OpenScholar | One-to-one, never in chat or issues |
| Run the bot | `data/processed/vs_latest_bge-m3.zip` (173 MB) | Upload (SURFdrive / HF dataset), then `python scripts/get_index.py <url>` |
| Embedding comparison | `emb_cache/` (959 MB) + `vs_latest_bge-small-en-v1.5/` (406 MB) | Same |
| Coverage / ingestion | `BOT/markdown/`, `Content/`, cluster PDFs + xlsx, `just-os_db_latest.csv`, `credentials.json` (Drive upload) | Shared drive; **never** the private admin files |
