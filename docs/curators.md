# Adding resources to the bot (for curators, C4, #25)

The bot answers open-science questions from an index of papers and web pages. New resources in the FORRT sheets, or in a small list of your own, are added with **one command**. It does not rebuild the index: it only adds what is new, and it tells you what happened to every resource.

## Before the first run (once)

1. Install Docker Desktop and get the repository (ask the team).
2. Start GROBID, the tool that turns PDFs into text. In a terminal:
   ```
   docker run -d --rm --name grobid -p 8070:8070 grobid/grobid:0.8.2-crf
   ```
   It keeps running until the computer restarts. Run this line again after a restart.

## Adding resources

1. **Choose what to add.**
   - New rows in the FORRT sheets: nothing to prepare; the command reads both sheets.
   - Or a short list: make a spreadsheet with the columns `title` and `link_to_resource` (optional: `doi`, `creators`, `conditions_of_use`, `material_type`) and save it as CSV in the repository folder, for example `new_rows.csv`.
2. **Run the command** in the repository folder (a terminal; on Windows Git Bash):
   ```
   ./run curate --csv new_rows.csv
   ```
   Leave out `--csv new_rows.csv` to use the FORRT sheets. Add `--limit 10` for a first try, or `--no-index` to only download and convert.
3. **Read the report**: `data/curation/<YYMMDD>/report.csv` (opens in Excel). One row per resource, with an `outcome` and what it means:

   | outcome | What it means | What to do |
   |---|---|---|
   | `converted` | Text extracted and added | Nothing |
   | `already_indexed` | The bot has it already | Nothing |
   | `no_open_access_pdf` | It has a DOI, but no free PDF was found | If you have a PDF you may share, give it to the team; else nothing |
   | `pdf_download_failed` | The free link did not give a PDF | Check the link in a browser |
   | `pdf_not_converted` | GROBID read no text (a scan, or GROBID is not running) | Start GROBID (above) and run again |
   | `web_page_failed` | The page could not be opened (blocked, paywall, gone) | Check the link |
   | `web_page_too_short` | The page has almost no text (a menu, an OSF project page) | Link the document itself instead of its landing page |

4. **Switch the bot to the new index.** The command adds the new resources to a copy, `data/processed/vs_curated_<YYMMDD>`, so the running bot is not changed by mistake. To use it, set `VECTOR_STORE=data/processed/vs_curated_<YYMMDD>` in `.env` and restart the bot (`docker compose up -d web`). With `--in-place` the command adds to the live index directly.

## Good to know

- A resource is recognised by its DOI, else by its title: running the command twice does not add anything twice.
- Licences: a page or paper without a known open licence is cited by the bot, but its text is not shown in the source pop-up.
- Web pages keep only their main text (no menus). Check a few new files in `data/curation/<YYMMDD>/markdown/` after a large run; [web-resources.md](web-resources.md) lists the kinds of pages that go wrong.
- Before the new index goes live, the team runs the eval on it (`python eval/scorecard.py baseline <config>`, [evaluation.md](evaluation.md)).
