# Data inventory: from source files to the index

Counts on 12 Nov 2026, after all FORRT cluster PDFs and the JUST-OS papers that the open-access filter had left out were added. How the files are stored and how to build an index is in [data.md](data.md); this page is the numbers and the reasons behind them.

## 1. Summary

| | Count |
|---|---|
| Documents in the index (both `vs_latest_bge-m3` and `vs_latest_bge-small-en-v1.5`) | **1,354** (146,899 chunks) |
| … from JUST-OS PDFs (`NWO JUST-OS/Content/` + Unpaywall downloads), Markdown by marker | 706 (79,860 chunks) |
| … … of which not open access: the bot answers from them, but shows only title + link | 163 (17,458 chunks) |
| … from FORRT cluster PDFs, Markdown by GROBID (books: pymupdf4llm) | 648 (67,039 chunks) |
| Documents whose passage may be shown under the source | 951 |
| `.docx` files embedded | 0 (see 4.3) |
| PDFs that exist but are not in the index | 31 (28 JUST-OS PDFs without Markdown, 3 scanned cluster PDFs) |

The index embeds **Markdown only**: every document is a PDF converted to one `.md` file, then chunked (350 tokens) and embedded.

Earlier states are kept: `vs_261111_*_before_clusters` (513 documents, 10 Nov) and `vs_261111_*_646_documents` (11 Nov, with the first 133 cluster papers).

## 2. The two FORRT sheets (latest copies)

| Sheet | File | Rows | Unique | With DOI |
|---|---|---|---|---|
| FORRT Database 2.0 (main resource list) | `data/raw/forrt_sheet1_261111.csv` | 1,507 | 1,482 | 843 |
| clusters_panos (reference list of the FORRT clusters) | `data/raw/forrt_sheet2_261111.csv` | 285 | 265 titles | 252 |

Sheet 1 had 1,504 rows on 28 Oct (3 rows added since); sheet 2 is unchanged. Together 1,693 unique resources (by DOI or title); the coverage audit (`eval/coverage.py`, [data.md](data.md) section 4) gives one reason per resource for those not in the index. It was last run on 9 Nov, before these additions.

## 3. JUST-OS PDFs

Built from the June 2025 copy of sheet 1 (`data/raw/forrt_db_250627.csv`, 1,234 rows, 689 with a DOI).

| Step | Count | Note |
|---|---|---|
| PDFs downloaded by the JUST-OS team (`NWO JUST-OS/Content/<id>.pdf`) | 657 | One per JUST-OS ID |
| Rows marked open access by Unpaywall (`just-os_db_latest.csv`) | 575 (538 unique `doi_hash`) | `bootstrap_local_database.py` keeps only `is_oa` papers with a DOI |
| PDFs downloaded from Unpaywall later (`add_new_resources.py`, from the live sheet) | 44 | No JUST-OS ID; the PDF was not kept, only the Markdown |
| Converted to Markdown (marker) | 546 | `NWO JUST-OS/BOT/markdown/markdown/` |
| In the index until 11 Nov | 513 | Open access only |
| **Added on 12 Nov** (`justos_markdown_metadata.py` + `add_to_index.py`) | **193** | Every Markdown file that was not in the index |
| **In the index now** | **706** | |

The 193 added papers:

| Group | Papers | Shown to the user |
|---|---|---|
| Not open access (the DOI is not in the Unpaywall open-access list) | 163 | Title + link only (`conditions_of_use` = "Not open access (Unpaywall)") |
| No DOI in the sheet, so never checked by Unpaywall (mostly "Reading" and "Primary Source") | 19 | By the licence in the sheet (most say "I don't see any of these": title + link) |
| Open access and converted, but never embedded (duplicate `doi_hash` / title mismatch, #24) | 11 | By the licence in the sheet |

Still not in the index:

| Reason | Count |
|---|---|
| `Content/` PDFs that were never converted to Markdown (25 not open access, 3 without a DOI) | 28 |
| Markdown files over 1 MB that hold a whole book under the title of one chapter: IDs 0930 and 1044 | 2 |

IDs 0097 and 0238 are the same kind of file (one book under two chapter titles). Both have been in the index since 2025 and still are, so chunks of that book are cited under a chapter title.

## 4. FORRT cluster PDFs (`data/FORRT Clusters pdfs/`)

### 4.1 Files

| | Count |
|---|---|
| PDF files | 1,061 |
| Unique PDFs (by file content; the same paper is often saved in several sub-clusters) | **814** |
| … of which books or reports of more than 80 pages | 17 (7,292 pages, a third of the cluster text) |
| `.docx` files | 930 |
| Other | 3 `.xlsx` working lists, 1 `.zip`, 2 `Cluster Improvement` notes (`.docx`, top folder) |

PDFs per cluster (files): C1 118, C2 74, C3 83, C4 22, C5 49, C6 69, C7 29, C8 65, C9 229, C10 111, C11 152.

### 4.2 From PDF to index (`convert_cluster_pdfs.py`)

Every unique PDF is converted; the file name no longer has to match a sheet row.

| Step | Count |
|---|---|
| Unique PDFs | 814 |
| Rejected: scans without text (Scheliga 2014, Creswell 2017, Creswell 2000) | 3 |
| Second file of a paper already converted (same DOI or title) | 58 |
| **Converted to Markdown** | **753** |
| … body text by GROBID | 733 |
| … body text by pymupdf4llm (the 17 books, and 3 PDFs where GROBID found no body) | 20 |
| Already in the index (same DOI or title as a JUST-OS document) | 105 |
| **Added to both indexes** (`add_to_index.py`) | **648** |

Where title, authors and DOI of the 753 papers come from:

| Source | Papers |
|---|---|
| A DOI printed in the PDF, found by GROBID, or from the sheet match, **and** the OpenAlex title for that DOI is in the first pages → title, authors, licence and open-access status from OpenAlex | 561 |
| No checked DOI: title and authors from GROBID (the title is in the first pages) | 95 |
| No checked DOI: title from the sheet match, the PDF's own title field or the largest text on page 1; no authors | 67 |
| No title found: the file name is the title (for example "C01 SC01 HistRC Edwards 2016") | 30 |

The 192 papers without a DOI have no link and show "n.d." as year.

**Licence.** All cluster papers have `conditions_of_use` = "FORRT cluster PDF (open access)", so the bot shows their passages (decision of the project lead, 12 Nov 2026). OpenAlex does not agree for every paper; its status is kept in the `oa_status` and `licence` columns of `data/processed/cluster_markdown/metadata.csv`:

| OpenAlex open-access status | Papers |
|---|---|
| gold / diamond / hybrid | 314 |
| green (a free copy in a repository) | 94 |
| bronze (free to read, no licence) | 36 |
| **closed** | **117** |
| Unknown (no DOI) | 192 |

The 17 books are in the last two rows; several are commercial textbooks (for example *The SAGE Handbook of Qualitative Research*, 1,867 pages, 6,771 chunks).

### 4.3 Why the `.docx` files were not converted

They are **Word copies of the same papers**: full text with the journal header and DOI (median about 9,300 words). 898 of the 928 `.docx` in the cluster folders have a PDF with the same name; the other 30 are mostly copies with a `(1)`/`(2)` suffix. Converting them would add duplicates, and Word conversions of PDFs lose page layout, so the PDF is the better source. Only the two `Cluster Improvement Part_*.docx` notes are different documents, and they are notes for the team, not sources.

### 4.4 The sheet match (`match_cluster_pdfs.py`)

The file name (`C01_SC01_<topic>_<author>_<year>`) matches a sheet reference for only 368 files (229 unique PDFs), because sheet 2 lists 285 references while the folder holds 814 unique PDFs, and 61 files carry another year than the sheet (online vs print). Until 11 Nov only matched PDFs were converted. The match is now one of three sources for the DOI (see 4.2), so the 693 unmatched files are converted too.

## 5. Converters

Compared on 12 JUST-OS PDFs that have marker Markdown (12 Nov 2026, random sample, same PDFs for every tool):

| Converter | Reference list in the output | Repeated lines (page headers) | Body text kept (two middle pages) | Headings | Seconds per PDF |
|---|---|---|---|---|---|
| marker (the 706 JUST-OS documents) | 13% of the text | 0.2% | 0.77 | 18 | not timed (GPU) |
| pymupdf4llm 2.0 | 13% | 1.2% | 0.74 | 18 | 10.8 |
| **GROBID 0.8.2** (cluster papers) | **0%** | **0%** | 0.73 | 16 | **2.9** |
| Docpluck 2.4.158 | 16% | 0.5% | 0.73 | 20 | 9.2 |

- All four keep about the same share of the body text; the differences there are inside the noise of 12 PDFs.
- GROBID is the only one that leaves out the reference list. In the other three, 13–16% of the text (and so of the chunks) is bibliography, which matches a question by keywords but answers nothing.
- GROBID needs a server (`docker run -p 8070:8070 grobid/grobid:0.8.2-crf`, 5 GB RAM) and is made for articles: books of several hundred pages ran it out of memory, so PDFs over 80 pages get pymupdf4llm.
- Docling was not run here (it needs PyTorch on the host; on the Meta Science Arena it scores like marker on text and is 4–6 times slower).
- "Reference list in the output" is found by a "References" heading, so it is a lower bound. "Body text kept" compares with the plain text of pymupdf, which may favour pymupdf4llm.

This agrees with the [Meta Science Arena](https://metasciencearena.app/arenas/pdf-text-fidelity-v1) (text fidelity: GROBID 0.979, marker / Docling / Docpluck 0.88; section structure: Docpluck 0.815, marker 0.60, GROBID 0.42 because it does not label section roles, its heading text score is 0.73).

**Not done:** the 706 JUST-OS documents still use the marker Markdown with reference lists. Converting them again with GROBID needs their PDFs (81 were not kept) and an eval row before and after (#36).

## 6. Things to know

- **Frozen copies.** `data/processed/vs_261111_*_before_clusters/` are the indexes before any cluster paper. `eval/compare_embeddings.py` and `eval/make_retrieval_set.py` read them, so the E1–E6 results stay comparable.
- **Size.** The bge-m3 index is 1.3 GB on disk (was 679 MB); the web container loads all of it into memory.
- **Shares.** `data/processed/vs_latest_bge-m3.zip` still holds the 513-document index. `share/just-os-team-bundle.zip` is rebuilt with `python scripts/make_share_bundle.py`.
- **Publication years.** `data/raw/pub_years.csv` has a year for 1,156 DOIs of the index; the rest show "n.d.".
- **Licences.** The bot shows passages for CC BY (incl. SA), CC0, public domain and the FORRT cluster PDFs (`passage_allowed`): 951 of 1,354 documents.
- **Metadata defect.** 10 JUST-OS documents still store their metadata as one-item dicts (#24); the code unwraps them, and a full `scripts/embed.py` rebuild removes them.
- **Earlier Markdown.** `data/processed/cluster_markdown_pymupdf4llm/` is the pymupdf4llm output of the first 153 cluster papers (11 Nov), kept for comparison.
