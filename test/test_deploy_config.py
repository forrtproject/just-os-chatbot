"""compose.yaml's web-prod and deploy/kubernetes/just-os.yaml describe the same public bot: their production settings
must not drift, web-prod must not pick up the dev .env or the dev assets, and the Kubernetes deployment must stay
within uniGPT's 4 parallel requests per key at every moment (rollouts and autoscaling included)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Settings that shape the public bot; both files must set each of them, to the same value
CORE = ("PROD_MODE", "BASE_URL", "CITATION_MODEL", "GENERAL_MODEL", "ROUTER", "SEARCH_MODE", "RERANK", "AUTO_DEFAULTS",
        "PROXY_FIX_X_FOR", "HF_HUB_OFFLINE", "OMP_NUM_THREADS", "MAX_CONCURRENT_LLM_CALLS", "FLASK_DEBUG", "WEB_RELOAD",
        "WEB_CONCURRENCY", "WEB_TIMEOUT", "LLAMA_INDEX_CACHE_DIR")
UNIGPT_PARALLEL_REQUESTS = 4  # per key


def web_prod() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["web-prod"]


def kubernetes() -> list:
    return [doc for doc in yaml.safe_load_all((ROOT / "deploy/kubernetes/just-os.yaml").read_text()) if doc]


def kind(name: str) -> list:
    return [doc for doc in kubernetes() if doc["kind"] == name]


def normal(value) -> str:
    return str(value).strip().lower()  # compose has ints and bools, Kubernetes strings


def test_compose_web_prod_and_kubernetes_set_the_same_production_settings():
    compose = web_prod()["environment"]
    config = kind("ConfigMap")[0]["data"]
    missing = {"compose web-prod": [k for k in CORE if k not in compose], "ConfigMap": [k for k in CORE if k not in config]}
    assert missing == {"compose web-prod": [], "ConfigMap": []}
    drift = {k: (compose[k], config[k]) for k in CORE if normal(compose[k]) != normal(config[k])}
    assert drift == {}, f"compose.yaml web-prod and deploy/kubernetes/just-os.yaml differ: {drift}"
    assert normal(config["PROD_MODE"]) == "true" and normal(config["AUTO_DEFAULTS"]) == "false"
    assert normal(config["FLASK_DEBUG"]) == normal(config["WEB_RELOAD"]) == "false"


def test_both_pass_the_same_keys_and_never_the_unigpt_key_to_openrouter():
    compose = web_prod()["environment"]
    container = kind("Deployment")[0]["spec"]["template"]["spec"]["containers"][0]
    secrets = {e["name"]: e["valueFrom"]["secretKeyRef"]["key"] for e in container["env"] if "valueFrom" in e}
    assert secrets == {"LLM_API_KEY": "UNIGPT_API_KEY", "DECISION_API_KEY": "OPENROUTER_API_KEY",
                       "OPENROUTER_API_KEY": "OPENROUTER_API_KEY"}
    # compose: the same keys, with placeholders (an empty key would fall back to another provider's key)
    assert compose["LLM_API_KEY"] == "${UNIGPT_API_KEY:-missing-UNIGPT_API_KEY}"
    assert compose["DECISION_API_KEY"] == compose["OPENROUTER_API_KEY"] == "${OPENROUTER_API_KEY:-missing-OPENROUTER_API_KEY}"


def test_web_prod_reads_neither_the_dev_env_file_nor_the_dev_assets():
    service = web_prod()
    env_files = [f["path"] if isinstance(f, dict) else f for f in service.get("env_file", [])]
    assert ".env" not in env_files and env_files == [".env.prod"]
    assert all(not f.get("required", True) for f in service["env_file"] if isinstance(f, dict))
    # its own volumes: never the host ./public that web mounts (an older web image would overwrite web-prod's assets)
    assert service["volumes"] and not any("public" in volume for volume in service["volumes"])
    assert all(volume.endswith(":ro") or volume.startswith("hf-cache:") for volume in service["volumes"])


def test_the_kubernetes_deployment_stays_within_unigpts_parallel_requests():
    deployment = kind("Deployment")[0]
    assert deployment["metadata"]["name"] == "just-os-web"
    slots = int(kind("ConfigMap")[0]["data"]["MAX_CONCURRENT_LLM_CALLS"])
    replicas = deployment["spec"]["replicas"]
    surge = deployment["spec"]["strategy"]["rollingUpdate"]["maxSurge"]
    assert isinstance(surge, int)  # a percentage would hide the number of extra pods
    assert slots >= 1 and (replicas + surge) * slots <= UNIGPT_PARALLEL_REQUESTS  # also during a rollout
    for hpa in kind("HorizontalPodAutoscaler"):
        assert hpa["spec"]["maxReplicas"] * slots <= UNIGPT_PARALLEL_REQUESTS


def test_the_probes_wait_longer_than_one_redis_timeout():
    from config.settings import DEFAULT_CONFIG

    container = kind("Deployment")[0]["spec"]["template"]["spec"]["containers"][0]
    for probe in ("startupProbe", "readinessProbe"):
        assert container[probe]["httpGet"]["path"] == "/ready"
        assert container[probe]["timeoutSeconds"] > DEFAULT_CONFIG["REDIS_TIMEOUT"], probe
