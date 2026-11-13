# JUST-OS documentation

| File | Read it when you want to know |
|---|---|
| [architecture.md](architecture.md) | What each code file does, how the files link, the request flow, caching and state, the index format |
| [data.md](data.md) | What is in `data/`, which PDFs are embedded, the indexes, how to build an index, what to share with a teammate |
| [data-inventory.md](data-inventory.md) | How many PDFs, `.docx` and sheet rows there are, how many became Markdown and went into the index, and why the rest did not |
| [indexed_documents.csv](indexed_documents.csv) | The 513 JUST-OS documents in the index (the 133 cluster papers are in `data/processed/cluster_markdown/metadata.csv`) (JUST-OS ID, title, DOI, source PDF, chunks, licence) |
| [evaluation.md](evaluation.md) | How we measure (metric definitions), the embedding and answer-model results, model candidates |
| [project-plan.md](project-plan.md) | Purpose, decisions, requirements, bug status, designs, roadmap, risks |
| [hackathon.md](hackathon.md) | Hackathon 11–13 Nov: setup check, rules, tracks, schedule, demo |
| [issues.md](issues.md) | Source text of the GitHub issues |
| [curators.md](curators.md) | How a curator adds new FORRT resources to the index with one command (`./run curate`) |
| [web-resources.md](web-resources.md) | The sample of 50 web resources without DOI (#18): which pages came through, and what to do with the rest |
| [judge-check.md](judge-check.md) | 20 English questions (open science, FORRT, both, should-refuse): the bot's answers, sources and the LLM judge's scores, to check by hand (#8); the same questions without the judge's scores are on `/review` |
| [team-testing.md](team-testing.md) | How to run a team test session through the tunnel without losing chats, arena ratings or reviews; the 100-question sheet and the `/review` page |

Setup and the `/chat` API are in the [root README](../README.md).

**Keep the docs current:** a PR that adds, moves or changes a code file, a setting, a route or a cache also updates the matching section here (usually `architecture.md`; settings also in the README model table).
