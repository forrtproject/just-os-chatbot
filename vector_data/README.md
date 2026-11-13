# vector_data/

Small vector indexes kept in Git (`data/` stays git-ignored).

## `forrt_pages/` — FORRT page index (`FORRT_PAGES`, `just_os/forrt_pages.py`)

**Links and short descriptions only, no page content.** The index tells the FORRT page router which
forrt.org pages to read for a question; the content of those pages is always fetched live from forrt.org
at question time (in-memory cache `FORRT_CACHE_TTL`). No page text is stored here.

| File | Content |
|---|---|
| `index.json` | One record per page (~160): `url` (fetched live), `title`, `section`, `lastmod`, `date`, `chars`, and an LLM-written description used only to find the right page: `summary`, `use_when`, `example_questions`, `page_kind`, `freshness`, `key_links` (`{url, label}`), `described_by` |
| `vectors.npy` | float32, one row per record (same order): the bge-m3 (`EMBEDDING_MODEL`) vector of the description, not of the page |

Scope: forrt.org menu pages, announcements (`/post/`), newsletters, Educators' Corner, Pedagogies,
Neurodiversity lesson bank, Replication Hub and the project sites in `config/forrt_extra_urls.txt`
(including the 12 chapters of the Replication Handbook, `replication-handbook/<chapter>.html`).
Not included: curated resources, clusters, glossary terms (open-science content for the papers path).

Rebuild after site changes and commit the result:

    python -m scripts.build_forrt_pages            # incremental (sitemap lastmod); needs LLM_API_KEY
    python -m scripts.build_forrt_pages --force    # describe every page again

Details: [docs/architecture.md](../docs/architecture.md) (index format), [docs/data.md](../docs/data.md).
