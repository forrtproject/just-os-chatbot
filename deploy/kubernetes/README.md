# JUST-OS on Kubernetes

`just-os.yaml` runs the public bot (the `web-prod` service of `compose.yaml`) on a cluster: two web pods with `PROD_MODE=true` (no chat log or feedback saved, no team pages), Redis for the chat memory (kept 1 hour after a chat's last message, at most 20 messages) and rate limits, and an Ingress for the forrt.org widget. Its production settings match `web-prod` in `compose.yaml` (`test/test_deploy_config.py` fails when they drift). No autoscaler: uniGPT takes 4 parallel requests per key, and 2 pods × `MAX_CONCURRENT_LLM_CALLS` 2 already use them (see Updating). Sizes and reasons: [docs/deployment-checklist.md](../../docs/deployment-checklist.md), task 3.

## 1. Build and push the image

```bash
docker build --target app -t <registry>/just-os/web:$(git rev-parse --short HEAD) .
docker push <registry>/just-os/web:$(git rev-parse --short HEAD)
```

Put that name in `just-os.yaml` instead of `IMAGE`, and the bot's host name instead of `HOST` (twice). If the cluster needs a storage class, add `storageClassName` to the two PersistentVolumeClaims.

## 2. Keys

```bash
kubectl create namespace just-os
kubectl -n just-os create secret generic just-os-keys \
  --from-literal=UNIGPT_API_KEY=<uniGPT project key> \
  --from-literal=OPENROUTER_API_KEY=<OpenRouter key, for the decision models Jev and Clef>
```

The keys never go into the image or Git.

## 3. Apply

```bash
kubectl -n just-os apply -f deploy/kubernetes/just-os.yaml
```

The web pods wait (startup probe on `/ready`) until step 4 has filled the two volumes; a pod whose load fails is restarted by Kubernetes when the startup probe runs out.

## 4. Copy the data and the model once

`data/` is not in the image. The data volume is mounted read-only at `/app/data` and needs:

| Path in the volume | From this repository | Size |
|---|---|---|
| `processed/vs_latest_bge-m3_glossary/` | `data/processed/vs_latest_bge-m3_glossary/` (papers + FORRT glossary, the default `VECTOR_STORE`; git-ignored) | 1.4 GB |
| `raw/pub_years.csv` | `data/raw/pub_years.csv` | 36 KB |
| `raw/forrt_sheet1_261028.csv` | `data/raw/forrt_sheet1_261028.csv` | small |
| `curation/forrt_article_list.csv` | `data/curation/forrt_article_list.csv` (FORRT cluster of each resource, `CLUSTER_BOOST`; without it the search runs without the boost) | 4 MB |

The model volume is mounted at `/home/python/.cache/huggingface` and needs `hub/models--BAAI--bge-m3/` (about 2.3 GB): copy it from the `hf-cache` Docker volume of a machine that ran the bot, or let one pod download it once with `HF_HUB_OFFLINE` removed from the ConfigMap and the volume writable.

Both claims are `ReadWriteMany`, so a helper pod can write them while the web pods (on any node) mount them read-only:

```bash
kubectl -n just-os run copy --image=busybox --restart=Never --overrides='{"spec":{"containers":[{"name":"copy","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"data","mountPath":"/data"},{"name":"models","mountPath":"/models"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"just-os-data"}},{"name":"models","persistentVolumeClaim":{"claimName":"just-os-models"}}]}}'
kubectl -n just-os cp data/processed/vs_latest_bge-m3_glossary copy:/data/processed/vs_latest_bge-m3_glossary
kubectl -n just-os cp data/raw/pub_years.csv copy:/data/raw/pub_years.csv
kubectl -n just-os cp data/raw/forrt_sheet1_261028.csv copy:/data/raw/forrt_sheet1_261028.csv
kubectl -n just-os cp data/curation/forrt_article_list.csv copy:/data/curation/forrt_article_list.csv
kubectl -n just-os cp <hf-cache>/hub/models--BAAI--bge-m3 copy:/models/hub/models--BAAI--bge-m3
kubectl -n just-os delete pod copy
kubectl -n just-os rollout restart deployment/just-os-web
```

**Upgrading from an earlier version of `just-os.yaml` whose claims were `ReadOnlyMany`:** the access mode of a bound PersistentVolumeClaim cannot be changed, so `kubectl apply` refuses the new manifest. Delete and recreate both claims, then copy the data again: scale the web pods down (`kubectl -n just-os scale deployment/just-os-web --replicas=0`), `kubectl -n just-os delete pvc just-os-data just-os-models` (with a `Delete` reclaim policy this deletes the data; keep a copy of the model cache or copy it from `hf-cache` again), `kubectl apply`, run the copy steps above, and scale back to 2. Leaving the old claims in place also works: they are only read by the web pods.

If the cluster's storage class has no `ReadWriteMany` (many block-storage classes only offer `ReadWriteOnce`), ask the cluster team to fill the volumes, or bake the index and model into the image (a second Dockerfile stage) instead.

## 5. Check

```bash
kubectl -n just-os get pods                      # 2 web + 1 redis Running, READY 1/1
kubectl -n just-os port-forward svc/just-os-web 8080:80
curl localhost:8080/up                            # ok (liveness: the process answers)
curl localhost:8080/ready                         # {"status": "ready", "rag": "ok", "redis": "ok"}; 503 while loading
curl -s localhost:8080/eval -o /dev/null -w "%{http_code}"   # 404: the team pages are off
```

Then ask one question on `http://localhost:8080/` and check the answer cites papers.

Probes: `startupProbe` and `readinessProbe` call `/ready` with a 5 s timeout (200 once the models and index are loaded; 503 with `rag: loading|failed` before), `livenessProbe` calls `/up` (200 while the process answers). Redis does not decide readiness: when it does not answer `PING` within `REDIS_TIMEOUT` (2 s, no retries), `/ready` gives 200 with `{"status": "degraded", "rag": "ok", "redis": "error"}` and the pods keep their traffic, because `/chat` still answers (without chat memory for follow-ups; the rate limiter lets requests through, `swallow_errors`). Each pod makes at most `MAX_CONCURRENT_LLM_CALLS` (2) uniGPT calls at once; further calls wait up to `LLM_TIMEOUT`, and a call that gets no slot ends with an error instead of waiting again.

## Updating

- **Code:** build and push a new image tag, set it in the Deployment, `kubectl apply`. If an earlier version installed the optional 4-replica HPA, delete it first (`kubectl -n just-os delete hpa just-os-web --ignore-not-found`) so `kubectl apply` does not leave it active. The rolling update replaces one pod at a time without a third pod (`maxSurge: 0`, `maxUnavailable: 1`, `terminationGracePeriodSeconds: 30`): the terminating pod drains before the replacement pod finishes loading models (~60 s) and passes `/ready`, keeping active pods within uniGPT's 4-call limit.
- **More pods:** only after uniGPT raises the 4 parallel requests per key, or with `MAX_CONCURRENT_LLM_CALLS: "1"` (up to 4 pods). Keep (replicas + `maxSurge`) × `MAX_CONCURRENT_LLM_CALLS` and an HPA's `maxReplicas` × `MAX_CONCURRENT_LLM_CALLS` within the limit; `test/test_deploy_config.py` checks both.
- **Index** (glossary, new papers): copy the new `vs_latest_bge-m3_glossary` into the data volume as in step 4, then `kubectl rollout restart deployment/just-os-web`.
- **Model or settings:** edit the ConfigMap, apply, restart the Deployment.
