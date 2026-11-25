# JUST-OS on Kubernetes

`just-os.yaml` runs the public bot (the `web-prod` service of `compose.yaml`) on a cluster: two web pods with `PROD_MODE=true` (nothing saved, no team pages), Redis for the 1-hour chat memory and rate limits, an Ingress for the forrt.org widget, and an optional autoscaler. Sizes and reasons: [docs/deployment-checklist.md](../../docs/deployment-checklist.md), task 3.

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

The web pods wait (startup probe) until step 4 has filled the two volumes.

## 4. Copy the data and the model once

`data/` is not in the image. The data volume is mounted read-only at `/app/data` and needs:

| Path in the volume | From this repository | Size |
|---|---|---|
| `processed/vs_latest_bge-m3_glossary/` | `data/processed/vs_latest_bge-m3_glossary/` (papers + FORRT glossary, the default `VECTOR_STORE`; git-ignored) | 1.3 GB |
| `raw/pub_years.csv` | `data/raw/pub_years.csv` | 36 KB |
| `raw/forrt_sheet1_261028.csv` | `data/raw/forrt_sheet1_261028.csv` | small |

The model volume is mounted at `/home/python/.cache/huggingface` and needs `hub/models--BAAI--bge-m3/` (about 2.3 GB): copy it from the `hf-cache` Docker volume of a machine that ran the bot, or let one pod download it once with `HF_HUB_OFFLINE` removed from the ConfigMap and the volume writable.

A helper pod writes both volumes (the web pods mount them read-only):

```bash
kubectl -n just-os run copy --image=busybox --restart=Never --overrides='{"spec":{"containers":[{"name":"copy","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"data","mountPath":"/data"},{"name":"models","mountPath":"/models"}]}],"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"just-os-data"}},{"name":"models","persistentVolumeClaim":{"claimName":"just-os-models"}}]}}'
kubectl -n just-os cp data/processed/vs_latest_bge-m3_glossary copy:/data/processed/vs_latest_bge-m3_glossary
kubectl -n just-os cp data/raw/pub_years.csv copy:/data/raw/pub_years.csv
kubectl -n just-os cp data/raw/forrt_sheet1_261028.csv copy:/data/raw/forrt_sheet1_261028.csv
kubectl -n just-os cp <hf-cache>/hub/models--BAAI--bge-m3 copy:/models/hub/models--BAAI--bge-m3
kubectl -n just-os delete pod copy
kubectl -n just-os rollout restart deployment/just-os-web
```

If the cluster cannot write a ReadOnlyMany volume through a pod, ask the cluster team to fill it, or bake the index and model into the image (a second Dockerfile stage) instead.

## 5. Check

```bash
kubectl -n just-os get pods                      # 2 web + 1 redis Running, READY 1/1
kubectl -n just-os port-forward svc/just-os-web 8080:80
curl localhost:8080/up                            # ok
curl -s localhost:8080/eval -o /dev/null -w "%{http_code}"   # 404: the team pages are off
```

Then ask one question on `http://localhost:8080/` and check the answer cites papers.

## Updating

- **Code:** build and push a new image tag, set it in the Deployment, `kubectl apply`. The rolling update keeps one pod serving (`maxUnavailable: 0`).
- **Index** (glossary, new papers): copy the new `vs_latest_bge-m3_glossary` into the data volume as in step 4, then `kubectl rollout restart deployment/just-os-web`.
- **Model or settings:** edit the ConfigMap, apply, restart the Deployment.
