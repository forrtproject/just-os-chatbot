#!/usr/bin/env bash
# OpenScholar-8B (Q5_K_M GGUF) on a RunPod GPU, served by llama.cpp with an
# OpenAI-compatible API behind a fixed URL (Cloudflare Worker, scripts/openscholar_proxy/):
#
#   OPENSCHOLAR_BASE_URL=https://openscholar.<subdomain>.workers.dev/v1   (Bearer key)
#
#   scripts/openscholar_pod.sh start    # rent the cheapest working GPU in stock, load the model
#   scripts/openscholar_pod.sh stop     # delete the pod: no GPU or storage charges while stopped
#   scripts/openscholar_pod.sh status   # pod, GPU, $/hr, RunPod balance, health
#   scripts/openscholar_pod.sh test     # auth check + one short chat completion via the fixed URL
#   scripts/openscholar_pod.sh env      # the two .env lines for the app
#   scripts/openscholar_pod.sh setup-proxy  # once: deploy the Worker (needs Cloudflare credentials)
#
# Everyone can also start/stop it with the "OpenScholar server" GitHub Action
# (.github/workflows/openscholar.yml), which runs this script with the repo's secrets.
#
# A stopped RunPod pod is tied to its machine and often cannot be resumed when that GPU
# is rented out, so "stop" deletes the pod and "start" makes a new one; the model
# (5.7 GB) downloads again in a minute or two. Whether a GPU is free is up to RunPod.
# The pod is found by its name, so the script keeps no pod state; the Worker finds the
# running pod the same way, so the URL never changes.
#
# Needs RUNPOD_API_KEY and OPENSCHOLAR_API_KEY (environment, or ~/.claude/api_keys.env and
# .env.openscholar-pod locally). OPENSCHOLAR_PROXY_URL (or PROXY_URL in .env.openscholar-pod)
# is the Worker URL.
set -euo pipefail

cd "$(dirname "$0")/.."
STATE=.env.openscholar-pod
LOCK=.openscholar-pod.lock
API=https://rest.runpod.io/v1
IMAGE=${OPENSCHOLAR_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda-b12282}
HF_MODEL=bartowski/Llama-3.1_OpenScholar-8B-GGUF:Q5_K_M
ALIAS=openscholar-8b
POD_NAME=openscholar-8b-q5  # also in scripts/openscholar_proxy/worker.js
# 4 parallel slots x 8k tokens. Answers are capped at 2048 tokens against runaway output
# (typical answers: 350-500 tokens, 23-27 s with 4 requests at once). The app streams the
# answer: RunPod's proxy cuts requests that send nothing for ~100 s
CTX=32768
PARALLEL=4
MAX_TOKENS=2048
# Highest price accepted ($/hr). Cards with >= 16 GB are tried cheapest first,
# Community and Secure Cloud mixed. 8B Q5 + KV cache needs ~11 GB.
MAX_PRICE=${OPENSCHOLAR_MAX_PRICE:-0.90}
# A pod generating slower than this runs on the CPU (broken GPU host): delete it
MIN_TOKENS_PER_SEC=20
READY_TIMEOUT=420  # seconds for download + load before a pod counts as broken
CF_ENV=$HOME/.config/deploy-html/cloudflare.env
PROXY_DIR=scripts/openscholar_proxy

ENV_KEY=${OPENSCHOLAR_API_KEY:-} PROXY_URL=""
[ -f "$STATE" ] && . "$STATE"
OPENSCHOLAR_API_KEY=${ENV_KEY:-${OPENSCHOLAR_API_KEY:-}}
PROXY_URL=${OPENSCHOLAR_PROXY_URL:-$PROXY_URL}
POD_ID=""
if [ -z "${RUNPOD_API_KEY:-}" ] && [ -f "$HOME/.claude/api_keys.env" ]; then
  RUNPOD_API_KEY=$(grep -E '^RUNPOD_API_KEY=' "$HOME/.claude/api_keys.env" | tail -1 | cut -d= -f2- | tr -d '"'"'" || true)
fi
[ -n "${RUNPOD_API_KEY:-}" ] || { echo "RUNPOD_API_KEY is not set" >&2; exit 1; }

rp() {  # rp METHOD PATH [JSON] -> body, then a last line with the HTTP status
  curl -sS -X "$1" "$API$2" -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -H "Content-Type: application/json" ${3:+-d "$3"} -w '\n%{http_code}'
}
gql() {
  curl -sSf https://api.runpod.io/graphql -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -H "Content-Type: application/json" -d "{\"query\":\"$1\"}"
}
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
pod_url() { echo "https://${POD_ID}-8080.proxy.runpod.net"; }
save_state() {  # local only: the generated key and the Worker URL
  [ -n "${GITHUB_ACTIONS:-}" ] && return 0
  umask 077
  printf 'OPENSCHOLAR_API_KEY=%s\nPROXY_URL=%s\n' "$OPENSCHOLAR_API_KEY" "$PROXY_URL" > "$STATE"
}

find_pod() {  # sets POD_ID to our pod (any state but terminated), or ""
  local out
  out=$(rp GET "/pods?name=$POD_NAME")
  [ "${out##*$'\n'}" = 200 ] || { echo "RunPod API error: $out" >&2; exit 1; }
  POD_ID=$(echo "${out%$'\n'*}" | POD_NAME="$POD_NAME" python3 -c '
import json, os, sys
pods = [p for p in json.load(sys.stdin) if p.get("name") == os.environ["POD_NAME"]
        and p.get("desiredStatus") != "TERMINATED"]
print(pods[0]["id"] if pods else "")')
}

delete_pod() {  # delete $POD_ID and confirm it is gone before forgetting it
  local out code
  out=$(rp DELETE "/pods/$POD_ID"); code=${out##*$'\n'}
  if [ "$code" != 200 ] && [ "$code" != 204 ] && [ "$code" != 404 ]; then
    echo "Deleting pod $POD_ID failed (HTTP $code): ${out%$'\n'*}" >&2
    echo "It may still be billing: check https://console.runpod.io/pods" >&2
    return 1
  fi
  out=$(rp GET "/pods/$POD_ID"); code=${out##*$'\n'}
  if [ "$code" = 200 ] && ! echo "${out%$'\n'*}" | grep -q '"desiredStatus":"TERMINATED"'; then
    echo "Pod $POD_ID still exists after delete; check https://console.runpod.io/pods" >&2
    return 1
  fi
  echo "Deleted pod $POD_ID."
  POD_ID=""
}

wait_ready() {  # poll /health until the model is loaded (download + load ~1-3 min)
  local deadline=$(( $(date +%s) + READY_TIMEOUT ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$(pod_url)/health" || true)" = 200 ] && return 0
    sleep 5
  done
  return 1
}

gpu_speed() {  # tokens/s of a short generation on the pod (CPU fallback gives ~1-5)
  curl -s --max-time 90 "$(pod_url)/v1/chat/completions" \
    -H "Authorization: Bearer $OPENSCHOLAR_API_KEY" -H "Content-Type: application/json" \
    -d '{"model":"openscholar-8b","messages":[{"role":"user","content":"Count from 1 to 40."}],"max_tokens":64}' \
    | json 'int(d["timings"]["predicted_per_second"])' 2>/dev/null || echo 0
}

gpu_candidates() {  # lines "price CLOUD gpu-id", cheapest first, up to MAX_PRICE
  gql '{ gpuTypes { id memoryInGb securePrice communityPrice } }' | MAX_PRICE="$MAX_PRICE" python3 -c '
import json, os, sys
skip = ("MIG", "AMD", "Tesla")  # partitions, ROCm, old/slow cards
rows = []
for g in json.load(sys.stdin)["data"]["gpuTypes"]:
    if (g["memoryInGb"] or 0) < 16 or any(s in g["id"] for s in skip):
        continue
    for cloud, price in (("COMMUNITY", g["communityPrice"]), ("SECURE", g["securePrice"])):
        if price and price <= float(os.environ["MAX_PRICE"]):
            rows.append((price, cloud, g["id"]))
for price, cloud, gid in sorted(rows):
    print(f"{price:.2f} {cloud} {gid}")
'
}

pod_body() {  # pod_body CLOUD GPU
  CLOUD="$1" GPU="$2" POD_NAME="$POD_NAME" IMAGE="$IMAGE" HF_MODEL="$HF_MODEL" ALIAS="$ALIAS" CTX="$CTX" \
    PARALLEL="$PARALLEL" MAX_TOKENS="$MAX_TOKENS" KEY="$OPENSCHOLAR_API_KEY" python3 -c '
import json, os
e = os.environ
print(json.dumps({
    "name": e["POD_NAME"],
    "cloudType": e["CLOUD"],
    "gpuTypeIds": [e["GPU"]],
    "gpuCount": 1,
    "imageName": e["IMAGE"],
    "containerDiskInGb": 20,
    "volumeInGb": 0,  # the API default is a 20 GB volume, billed while the pod exists
    "ports": ["8080/http"],
    "env": {"LLAMA_CACHE": "/root/.cache/llama.cpp", "LLAMA_API_KEY": e["KEY"]},
    "dockerStartCmd": [
        "-hf", e["HF_MODEL"], "--alias", e["ALIAS"],
        "--host", "0.0.0.0", "--port", "8080",
        "-ngl", "99", "-c", e["CTX"], "--parallel", e["PARALLEL"],
        "-n", e["MAX_TOKENS"], "--metrics",
    ],
}))'
}

# One invocation at a time (a second start would rent a second GPU)
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "Another openscholar_pod.sh is running (remove $LOCK if it crashed)." >&2; exit 1
fi
trap 'rmdir "$LOCK"' EXIT

case "${1:-status}" in
  start)
    find_pod
    if [ -n "$POD_ID" ]; then
      echo "Already running: pod $POD_ID. Stop it first to replace it."; exit 0
    fi
    if [ -z "$OPENSCHOLAR_API_KEY" ]; then
      [ -z "${GITHUB_ACTIONS:-}" ] || { echo "OPENSCHOLAR_API_KEY secret is not set" >&2; exit 1; }
      OPENSCHOLAR_API_KEY=$(openssl rand -hex 24); save_state
    fi
    candidates=$(gpu_candidates) || { echo "Could not read GPU prices from RunPod." >&2; exit 1; }
    [ -n "$candidates" ] || { echo "No GPU type up to \$$MAX_PRICE/hr." >&2; exit 1; }
    # Cheapest first. A pod that is not healthy in time, or generates at CPU speed,
    # is on a broken host: delete it and try the next card.
    while read -r price cloud gpu; do
      out=$(rp POST /pods "$(pod_body "$cloud" "$gpu")"); code=${out##*$'\n'}; resp=${out%$'\n'*}
      if [ "$code" != 200 ] && [ "$code" != 201 ]; then
        if echo "$resp" | grep -qi 'no instances\|supply'; then
          echo "  none free: $gpu ($cloud, \$$price)"; continue
        fi
        # The price list names some GPU types the create API does not accept
        if [ "$code" = 400 ] && echo "$resp" | grep -q 'gpuTypeIds/items/enum'; then
          echo "  not rentable via the API: $gpu"; continue
        fi
        echo "Create failed (HTTP $code): $resp" >&2; exit 1
      fi
      POD_ID=$(echo "$resp" | json 'd["id"]')
      cost=$(echo "$resp" | json 'd.get("costPerHr") or 0')
      echo "Pod $POD_ID: $gpu ($cloud), \$$cost/hr"
      if python3 -c "import sys; sys.exit(float('$cost') <= float('$MAX_PRICE'))"; then
        echo "  costs more than \$$MAX_PRICE/hr; deleting it"; delete_pod; continue
      fi
      echo "  loading the model ..."
      if ! wait_ready; then
        echo "  not healthy after $READY_TIMEOUT s (broken host?); deleting it"; delete_pod; continue
      fi
      speed=$(gpu_speed)
      if [ "$speed" -lt "$MIN_TOKENS_PER_SEC" ]; then
        echo "  only $speed tokens/s (GPU not working, CPU fallback); deleting it"; delete_pod; continue
      fi
      echo "Ready: $speed tokens/s."
      break
    done <<< "$candidates"
    [ -n "$POD_ID" ] || { echo "No working GPU up to \$$MAX_PRICE/hr right now; try again later." >&2; exit 1; }
    echo "OpenScholar is running at ${PROXY_URL:-the Worker URL}/v1"
    ;;
  stop)
    find_pod
    if [ -z "$POD_ID" ]; then echo "No pod running."; fi
    for _ in 1 2 3 4 5; do [ -n "$POD_ID" ] || break; delete_pod; sleep 3; find_pod; done
    [ -z "$POD_ID" ] || { echo "Pod $POD_ID still listed; check https://console.runpod.io/pods" >&2; exit 1; }
    echo "Stopped; the fixed URL answers 503 within 30 s."
    ;;
  setup-proxy)  # once, locally: deploy the Worker and give it the RunPod key
    PROXY_URL=$(set -a && . "$CF_ENV" && set +a && cd "$PROXY_DIR" && \
      wrangler deploy 2>&1 | grep -oE 'https://[a-z0-9.-]+\.workers\.dev' | head -1 && \
      printf '%s' "$RUNPOD_API_KEY" | wrangler secret put RUNPOD_API_KEY >/dev/null)
    [ -n "$PROXY_URL" ] || { echo "Worker deploy failed" >&2; exit 1; }
    save_state; echo "Worker: $PROXY_URL"
    ;;
  status)
    gql '{ myself { clientBalance currentSpendPerHr } }' | json '"RunPod balance $%.2f, spending $%.2f/hr" % (d["data"]["myself"]["clientBalance"], d["data"]["myself"]["currentSpendPerHr"])'
    find_pod
    if [ -z "$POD_ID" ]; then echo "No pod (stopped)."; exit 0; fi
    out=$(rp GET "/pods/$POD_ID")
    echo "${out%$'\n'*}" | json '"Pod %s %s  %s  $%s/hr  started %s" % (d.get("id"), d.get("desiredStatus"), (d.get("machine") or {}).get("gpuTypeId","-"), d.get("costPerHr"), d.get("lastStartedAt"))'
    echo "health: $(curl -s --max-time 10 "$(pod_url)/health" || echo unreachable)"
    ;;
  test)
    [ -n "$PROXY_URL" ] || { echo "No fixed URL yet: run '$0 start'" >&2; exit 1; }
    echo "Without key (expect 401): $(curl -s -o /dev/null -w '%{http_code}' "$PROXY_URL/v1/models")"
    echo "Models: $(curl -s "$PROXY_URL/v1/models" -H "Authorization: Bearer $OPENSCHOLAR_API_KEY" | json '[m["id"] for m in d["data"]]')"
    curl -s "$PROXY_URL/v1/chat/completions" -H "Authorization: Bearer $OPENSCHOLAR_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model":"openscholar-8b","messages":[{"role":"user","content":"In two sentences: what is a registered report?"}],"max_tokens":120}' \
      | json 'd["choices"][0]["message"]["content"] + "\n%.0f tokens/s" % d["timings"]["predicted_per_second"]'
    ;;
  env)
    [ -n "$PROXY_URL" ] || { echo "No fixed URL yet: run '$0 start'" >&2; exit 1; }
    echo "OPENSCHOLAR_BASE_URL=$PROXY_URL/v1"
    echo "OPENSCHOLAR_API_KEY=$OPENSCHOLAR_API_KEY"
    ;;
  *) sed -n '2,25p' "$0"; exit 1 ;;
esac
