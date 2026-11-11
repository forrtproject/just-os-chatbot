# Data inventory: from source files to the index

Counts on 11 Nov 2026, after the FORRT cluster papers were added. How the files are stored and how to build an index is in [data.md](data.md); this page is the numbers and the reasons behind them.

## 1. Summary

| | Count |
|---|---|
| Documents in the index (both `vs_latest_bge-m3` and `vs_latest_bge-small-en-v1.5`) | **646** (79,808 chunks) |
| … from JUST-OS PDFs (`NWO JUST-OS/Content/` + Unpaywall downloads), Markdown by marker | 513 (59,473 chunks) |
| … from FORRT cluster PDFs, Markdown by pymupdf4llm | 133 (20,335 chunks) |
| `.docx` files embedded | 0 (see 4.3) |
| PDFs that exist but are not in the index | about 760 (see 3 and 4) |

The index embeds **Markdown only**: every document is a PDF converted to one `.md` file, then chunked (350 tokens) and embedded.

## 2. The two FORRT sheets (latest copies)

| Sheet | File | Rows | Unique | With DOI |
|---|---|---|---|---|
| FORRT Database 2.0 (main resource list) | `data/raw/forrt_sheet1_261111.csv` | 1,507 | 1,482 | 843 |
| clusters_panos (reference list of the FORRT clusters) | `data/raw/forrt_sheet2_261111.csv` | 285 | 265 titles | 252 |

Sheet 1 had 1,504 rows on 28 Oct (3 rows added since); sheet 2 is unchanged. Together 1,693 unique resources (by DOI or title); the coverage audit (`eval/coverage.py`, [data.md](data.md) section 4) gives one reason per resource for those not in the index.

## 3. JUST-OS PDFs (the original index)

Built from the June 2025 copy of sheet 1 (`data/raw/forrt_db_250627.csv`, 1,234 rows, 689 with a DOI).

| Step | Count | Note |
|---|---|---|
| PDFs downloaded by the JUST-OS team (`NWO JUST-OS/Content/<id>.pdf`) | 657 | One per JUST-OS ID |
| Rows marked open access by Unpaywall (`just-os_db_latest.csv`) | 575 (538 unique `doi_hash`) | `bootstrap_local_database.py` keeps only `is_oa` papers with a DOI |
| PDFs downloaded from Unpaywall later (`add_new_resources.py`, from the live sheet) | 44 | No JUST-OS ID; the PDF was not kept, only the Markdown |
| Converted to Markdown (marker) | 546 | `NWO JUST-OS/BOT/markdown/markdown/` |
| **In the index** | **513** | 432 with a PDF in `Content/`, 37 whose PDF is not in `Content/`, 44 Unpaywall downloads |

Why 223 `Content/` PDFs are not in the index:

| Reason | PDFs |
|---|---|
| Not open access (Unpaywall `is_oa` false or not found): left out on purpose (licence) | 190 |
| No DOI in the sheet, so no `doi_hash` (mostly "Reading" and "Primary Source") | 22 |
| Open access and converted, but not embedded (duplicate `doi_hash` / title mismatch, #24) | 11 |

184 of these (165 + 19) already have Markdown, so they could go in without a new conversion if FORRT decides paywalled papers may be indexed (title + link only).

## 4. FORRT cluster PDFs (`data/FORRT Clusters pdfs/`)

### 4.1 Files

| | Count |
|---|---|
| PDF files | 1,061 |
| Unique PDFs (by file content; the same paper is often saved in several sub-clusters) | **814** |
| `.docx` files | 930 |
| Other | 3 `.xlsx` working lists, 1 `.zip`, 2 `Cluster Improvement` notes (`.docx`, top folder) |

PDFs per cluster (files): C1 118, C2 74, C3 83, C4 22, C5 49, C6 69, C7 29, C8 65, C9 229, C10 111, C11 152.

### 4.2 From PDF to index

| Step | Count |
|---|---|
| File name matched to a reference in the latest sheets (`match_cluster_pdfs.py`: first author + year) | 368 files = 229 unique PDFs |
| … of which the reference is in sheet 2 | all 229 (63 files also match sheet 1) |
| Matched title found in the first 3 pages of the PDF (`convert_cluster_pdfs.py`) → **Markdown** | **153 papers** |
| Rejected: the title is not in the PDF (another paper by the same author and year, or a reference without a title) | 71 (`data/processed/cluster_markdown/rejected.csv`) |
| Second file of a paper already converted | 5 |
| Already in the index (same DOI or title as a JUST-OS document) | 20 |
| **Added to both indexes** (`add_to_index.py`) | **133** |

Sheet 2 coverage: 203 of its 285 rows (183 unique references) have a matched PDF; 160 rows have a checked Markdown file.

The added papers have no licence information (`conditions_of_use` empty), so the bot answers from them but shows only title + link, never a passage.

### 4.3 Why the `.docx` files were not converted

They are **Word copies of the same papers**: full text with the journal header and DOI (median about 9,300 words). 898 of the 928 `.docx` in the cluster folders have a PDF with the same name; the other 30 are mostly copies with a `(1)`/`(2)` suffix. Converting them would add duplicates, and Word conversions of PDFs lose page layout, so the PDF is the better source. Only the two `Cluster Improvement Part_*.docx` notes are different documents, and they are notes for the team, not sources.

### 4.4 Why 693 files did not match at all

693 files (593 unique PDFs; 585 after removing files whose same content matched under another name):

| Reason | Files |
|---|---|
| The first author is not in any reference of either sheet | 572 |
| The author is in a sheet, but with another year (often online vs print year) | 61 |
| The file name does not follow `C01_SC01_<topic>_<author>_<year>` (`_c`, `_Version_2`, `(1)`, `_RETRACTED`, no year, …) | 60 |

The main cause is that **sheet 2 lists only 285 references, while the folder holds 814 unique PDFs**: most papers are simply not in any sheet. The working lists do not fill the gap (`01.FORRT_Clusters_Working_Document_v1.xlsx` 121 rows, `FORRT Cluster_s.xlsx` 45 rows, `Inaccessible _ Nonpdf Sources.xlsx` a few rows per cluster).

**Next step:** 450 of the 585 unmatched PDFs print a DOI on their first two pages (406 unique DOIs, 56 already in the index; only 8 PDFs look like scans without text). Reading the DOI from the PDF and taking title, authors, year and licence from OpenAlex or Crossref would match about 350 more papers without a person, and would also give the added papers their authors and licence.

## 5. Things to know

- **Two converters.** The 513 JUST-OS documents were converted with marker, the 133 cluster papers with pymupdf4llm (faster, no GPU). The Markdown differs a little (headings, tables); compare before a full rebuild.
- **Frozen copies.** `data/processed/vs_261111_*_before_clusters/` are the indexes before the cluster papers. `eval/compare_embeddings.py` and `eval/make_retrieval_set.py` read them, so the E1–E6 results stay comparable.
- **Out-of-date shares.** `data/processed/vs_latest_bge-m3.zip` and `share/just-os-team-bundle.zip` still hold the 513-document index; run `python scripts/make_share_bundle.py` again before sharing.
- **Publication years.** `data/raw/pub_years.csv` has a year for 628 of the 638 DOIs in the index; the rest show "n.d.".
- **Licences.** 184 of the 513 JUST-OS documents say "I don't see any of these" and all 133 cluster papers have no licence: the bot shows passages only for CC BY (incl. SA), CC0 and public domain.
- **Metadata defect.** 10 JUST-OS documents still store their metadata as one-item dicts (#24); the code unwraps them, and a full `scripts/embed.py` rebuild removes them.
