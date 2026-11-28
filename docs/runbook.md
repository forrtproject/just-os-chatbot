# Runbook: running the public bot

For the people who keep JUST-OS running on the University of Münster servers. Setup: [deploy/kubernetes/README.md](../deploy/kubernetes/README.md); why things are as they are: [deployment-checklist.md](deployment-checklist.md).

## Deploy a new version

1. Run the tests on the commit you deploy: `docker compose exec web python -m pytest -q` (all green).
2. Build and push the image with the commit as tag: `docker build --target app -t <registry>/just-os/web:$(git rev-parse --short HEAD) .` and `docker push …`.
3. Set the new tag in `deploy/kubernetes/just-os.yaml` and `kubectl -n just-os apply -f deploy/kubernetes/just-os.yaml`. The rolling update keeps one pod serving.
4. Check: `kubectl -n just-os get pods` (all ready), `curl https://<host>/up` (`ok`) and `curl https://<host>/ready` (`"status": "ready"`), one question on the forrt.org widget that cites papers, and `https://<host>/eval` gives 404.

## Update the index (new papers, glossary, abstract cards)

The live index is `data/processed/vs_latest_bge-m3_glossary`: the papers, the FORRT glossary and the abstract cards. Build on a copy, never on the live folder:

1. `cp -r data/processed/vs_latest_bge-m3_glossary data/processed/vs_<YYMMDD>` (keep the old one: it is the rollback).
2. Add what is new, in this order (full text first, so it wins over a card):
   - full texts: `./run curate --csv rows.csv --no-index`, then `python -m scripts.add_to_index data/curation/<YYMMDD>/markdown data/curation/<YYMMDD>/metadata.csv --index data/processed/vs_<YYMMDD>` ([curators.md](curators.md));
   - glossary changes: `python -m scripts.build_glossary`, then `add_to_index` with `data/processed/glossary_markdown`;
   - abstract cards: `python -m scripts.forrt_article_list`, `python -m scripts.build_abstract_cards`, then `add_to_index` with `data/processed/abstract_cards`.
3. `python -m scripts.fix_index_titles data/processed/vs_<YYMMDD>` (corrected titles of `config/index_corrections.json`).
4. Run the eval on the copy (`python eval/scorecard.py <config with VECTOR_STORE=data/processed/vs_<YYMMDD>> --route open_science`) and compare with the last run ([evaluation.md](evaluation.md)).
5. Copy the folder into the data volume ([deploy/kubernetes/README.md](../deploy/kubernetes/README.md) step 4), set `VECTOR_STORE` in the ConfigMap, apply, `kubectl -n just-os rollout restart deployment/just-os-web`.

Embedding is slow on one CPU core, and the web service sets `OMP_NUM_THREADS=1` for its containers: run `add_to_index` with `-e OMP_NUM_THREADS=8` (`docker compose run --rm -T --no-deps -e OMP_NUM_THREADS=8 -v ./data/processed:/app/data/processed web python -m scripts.add_to_index …`). On one core, 141 full papers (~4,600 chunks) took about 4 hours.

A document whose text turns out to be another work: add its DOI to `exclude` in `config/index_corrections.json` and deploy (no index change needed).

## Roll back

- **Code:** set the previous image tag in the Deployment and apply.
- **Index:** set `VECTOR_STORE` back to the previous folder (still in the data volume) and restart the Deployment.
- **Model:** set `CITATION_MODEL` / `GENERAL_MODEL` in the ConfigMap and restart.

## Rotate a key

1. Make the new key (uniGPT: the uniGPT team; OpenRouter: openrouter.ai, Keys).
2. `kubectl -n just-os create secret generic just-os-keys --from-literal=UNIGPT_API_KEY=… --from-literal=OPENROUTER_API_KEY=… --dry-run=client -o yaml | kubectl -n just-os apply -f -`
3. `kubectl -n just-os rollout restart deployment/just-os-web`, ask one question, then revoke the old key.

Never put a key in the image, in Git or in a team bundle.

## When something is wrong

| Symptom | Look at | Usual cause |
|---|---|---|
| Every answer: "I'm sorry, I encountered an error" | pod logs: `OpenAI API error (… 401 …)` | uniGPT key wrong or expired: rotate it |
| Same, with `429` or time-outs | pod logs | uniGPT busy or over its parallel-request limit; ask the uniGPT team for a higher limit |
| Many questions refused as off-topic | pod logs: `decision` errors | OpenRouter's decision API down; the LLM classifier takes over, less accurate |
| Pods restart | `kubectl describe pod` | out of memory (raise the limit) or the startup probe too short (the model loads for ~1 min) |
| A source shows a wrong title or the wrong paper | the document's DOI | add it to `config/index_corrections.json` |
