# Web resources without a DOI: sample of 50 (C3, #18)

Run on 12 November 2026:

```
docker compose run --rm -T -v "<repo>\data\processed:/app/data/processed:rw" web python -m scripts.fetch_web_resources --sample 50
```

(On Windows use PowerShell for this command: Git Bash rewrites the `-v` path, and the folder stays read-only.)

The sample is 50 of the 506 FORRT sheet rows that `eval/coverage.py` marks `web_page` or `code_or_osf` (`eval/results/coverage_261109.csv`, seed 1). Output: `data/processed/web_markdown/` (33 Markdown files and `metadata.csv`). **Nothing is in the index yet.**

| Result | Pages |
|---|---|
| Kept, text is good | 20 |
| Kept, but the text needs a look (menus, a listing, off-topic) | 13 |
| Skipped: OSF project (JavaScript page, no text) | 11 |
| Skipped: other (paywall, blocked, too short, moved) | 6 |

## What to do

Work through the four lists below, then add the pages to a copy of the index and compare the eval (last section). Tick a box when done.

### 1. Kept, text is good: no action

These went through with their main text. Index them as they are.

| Title | URL |
|---|---|
| OpenRefine for Social Science Data | https://datacarpentry.org/openrefine-socialsci/ |
| Writing a Data Management Plan for Grant Applications | https://nyu-dataservices.github.io/WritingDMP-GrantApplications/ |
| Python for Harvesting Data on the Web | https://nyu-dataservices.github.io/DataHarvesting-Python/ |
| IIT vs. GNWT and the meaning of evidence in consciousness science | https://elusiveself.wordpress.com/2023/09/09/iit-vs-gnwt-and-the-meaning-of-evidence-in-consciousness-science/ |
| Who Would Have Thought That We Needed Another Listserv? | https://scholarlykitchen.sspnet.org/2024/02/05/who-would-have-thought-that-we-needed-another-listserv/ |
| Qualitative Open Science Practices | https://forrt.org/educators-corner/006-qualitative-os-practices/ |
| Using the 'Transparency Checklist Guidelines' as an Educational tool | https://forrt.org/educators-corner/002-transparencychecklist-balazsaczel/ |
| Navigating Open scholarship for neurodivergent researchers | https://forrt.org/educators-corner/010-neurodiversity/ |
| Programming with MATLAB | http://swcarpentry.github.io/matlab-novice-inflammation/ |
| Programming with Python | https://swcarpentry.github.io/python-novice-inflammation/ |
| Social Science Workshop Overview | https://datacarpentry.org/socialsci-workshop/ |
| Introduction to Geospatial Concepts (lesson retired) | https://datacarpentry.org/organization-geospatial/ |
| International collaboration to help implement open research (UKRN) | https://www.ukrn.org/2023/02/03/unesco-collaboration-feb2023/ |
| The Bayesian Reproducibility Project | https://alexanderetz.com/2015/08/30/the-bayesian-reproducibility-project/ |
| Understanding Bayes: Visualization of the Bayes Factor | http://alexanderetz.com/2015/08/09/understanding-bayes-visualization-of-bf/ |
| The Buffet Approach to Open Science | https://cogtales.wordpress.com/2023/04/16/the-buffet-approach-to-open-science/ |
| When Great Minds Think Unalike: Inside Science's 'Replication Crisis' (NPR) | https://www.npr.org/2016/05/24/477921050/when-great-minds-think-unlike-inside-sciences-replication-crisis |
| Symposium "Qualitative Open Science" | https://www.opennaturallyoccurringdata.com/symposium-event |
| PathOS: Open Science Impact Pathways | https://pathos-project.eu/ |
| teaching psych science | http://www.teachpsychscience.org/ |

### 2. Kept, but check the text

Open the Markdown file (`data/processed/web_markdown/<doi_hash>.md`, see `metadata.csv`) and decide: keep, delete the file and its `metadata.csv` row, or replace the text.

- [ ] **TOP Guidelines** (https://www.cos.io/initiatives/top-guidelines): starts with the site menu. Keep; optionally cut the menu lines at the top.
- [ ] **Open Research Community Accelerator** (https://www.orcaopen.org/): letters of the headings are spaced out ("B u i l d i n g"). Keep, or fix the headings.
- [ ] **The Hardest Science** (https://hardsci.wordpress.com/): the blog's home page, 99,000 characters of many posts. Replace with the one or two posts the sheet means, or delete.
- [ ] **Reproducible Science Curriculum: Automation** (https://github.com/datacarpentry/rr-automation): GitHub's file list, not the lesson. Use the README or the lesson site instead.
- [ ] **Introduction to web scraping** (https://github.com/carpentries-incubator/lc-webscraping/): same as above (GitHub page; archived repository).
- [ ] **Comparing Published Scientific Journal Articles to Their Pre-print Versions** (https://arxiv.org/abs/1604.05363): only the arXiv abstract page. It has a DOI (10.48550/arXiv.1604.05363): put it through the PDF route ([curators.md](curators.md)) and delete this file.
- [ ] **Replicating and Extending Soroka, Fournier, and Nir** (https://www.cogitatiopress.com/mediaandcommunication/article/view/7807): journal page around the abstract. Find its DOI and use the PDF route.
- [ ] **DATA AND OPEN SCIENCE** (https://periodicos.fgv.br/rae/article/view/80767): journal page; DOI 10.1590/S0034-759020190601. Use the PDF route.
- [ ] **Responsible conduct of research (Coursera)** (https://www.coursera.org/learn/research-integrity): course marketing page. Probably delete.
- [ ] **Open Access Tracking Project** (https://cyber.harvard.edu/hoap/Open_Access_Tracking_Project): wiki page with navigation. Keep.
- [ ] **Cognitive Science StackExchange** (http://cogsci.stackexchange.com): a list of questions that changes daily. Delete.
- [ ] **PewTranslate Census Language Lookup** (https://pewtranslate.com/en/guides/languages-spoken-by-zip-code): a US ZIP-code lookup, not about open science. Delete, and ask whether the sheet row is right.
- [ ] **How racist policing took over American cities** (Vox, https://www.vox.com/2020/6/6/21280643/police-brutality-violence-protests-racism-khalil-muhammad): not about open science. Delete, and ask whether the sheet row is right.

### 3. Skipped: OSF projects (11)

OSF pages are a JavaScript app, so the download has no text. The content is in the project's files or wiki. For each: open it, find the main document (syllabus, slides, PDF), and either add it by hand ([curators.md](curators.md)) or note "skip".

- [ ] course syllabi for open and reproducible science: https://osf.io/vkhbt/wiki/home/ (the wiki text is at `https://api.osf.io/v2/nodes/vkhbt/wikis/`)
- [ ] Open Science Session GSA 2019: https://osf.io/yvrch/
- [ ] Repository of Psychological Instruments in Serbian (REPOPSI): https://osf.io/5zb8p/ (a data repository: probably skip)
- [ ] Materials for the Webinar "Helping Science Succeed": https://osf.io/n8dv2/
- [ ] Psychology's Credibility Revolution (syllabus): https://osf.io/9v2sy/
- [ ] Oxford-Berlin Open Research summer school 2019: https://osf.io/6ytne/
- [ ] Practical steps for increasing openness and reproducibility: https://osf.io/48up3/
- [ ] Syllabus replicability: https://osf.io/staze
- [ ] Draft syllabus dated 2016-01-11: https://osf.io/3e2pg/
- [ ] Ciência aberta e reprodutível (syllabus): https://osf.io/wmakh/
- [ ] If most of these have their text in a wiki or one main file: an OSF route that reads it through the OSF API would cover all 136 `code_or_osf` rows. Worth an issue.

### 4. Skipped: other (6)

- [ ] **Data Management for Psychological Science** (Google Doc, https://docs.google.com/document/d/1z15bL9cP84re6d4zdkO60q06lnknnN3xEktN7GnLFFQ/edit): the edit page has no text. Try `.../export?format=txt` in the browser; if it opens, save it as Markdown and add it by hand.
- [ ] **Millions of research papers at risk of disappearing** (Nature news, DOI 10.1038/d41586-024-00616-5): use the PDF route; skip if it is not open access.
- [ ] **Degrees of Freedom Tutorial** (http://ron.dotsch.org/degrees-of-freedom/): no text returned (JavaScript, or gone). Check in the browser; skip if empty.
- [ ] **SWIRL** (https://swirlstats.com/): landing page of an R package. Skip.
- [ ] **Schools should teach children how to spot conspiracy theories** (Telegraph): paywall (HTTP 402). Skip.
- [ ] **Open Access Directory** (https://oad.simmons.edu/oadwiki/Main_Page): the site blocks scripts (HTTP 403). Save the page from the browser, or skip.
- The FORRT glossary row (https://forrt.org/glossary/) moved to /glossary/english/. The bot already reads it through the FORRT pages, so it does not need to be in the paper index.

## Then: add to a copy of the index and compare

1. After the clean-up, add the pages to a copy (the live index stays unchanged), in PowerShell:
   ```
   docker compose run --rm -T -v "<repo>\data:/app/data:rw" web python -m scripts.add_to_index data/processed/web_markdown data/processed/web_markdown/metadata.csv --output data/processed/vs_web_sample
   ```
2. Add a configuration to `eval/configs.json`, for example `"web-sample": {"VECTOR_STORE": "data/processed/vs_web_sample"}`, and run `python eval/scorecard.py baseline web-sample` (see [evaluation.md](evaluation.md)).
3. The licence of these pages is unknown, so the bot cites them but does not show their passages (`passage_allowed`).
