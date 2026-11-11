// Stable URL for the self-hosted OpenScholar server. Forwards every request
// (path, query, headers incl. the Bearer key, body) to the running RunPod pod named
// POD_NAME, found through the RunPod API (secret RUNPOD_API_KEY). The pod changes each
// time scripts/openscholar_pod.sh (or the GitHub Action) starts a new one.
const POD_NAME = "openscholar-8b-q5";
const CACHE_MS = 30_000;
let cached = { podId: null, at: 0 };

async function currentPod(env) {
  if (Date.now() - cached.at < CACHE_MS) return cached.podId;
  const res = await fetch(
    `https://rest.runpod.io/v1/pods?name=${POD_NAME}&desiredStatus=RUNNING`,
    { headers: { Authorization: `Bearer ${env.RUNPOD_API_KEY}` } },
  );
  if (!res.ok) throw new Error(`RunPod API ${res.status}`);
  const pods = (await res.json()).filter((p) => p.name === POD_NAME && p.desiredStatus === "RUNNING");
  // Newest pod first, in case a start is replacing a broken one
  pods.sort((a, b) => String(b.lastStartedAt || "").localeCompare(String(a.lastStartedAt || "")));
  cached = { podId: pods[0]?.id ?? null, at: Date.now() };
  return cached.podId;
}

export default {
  async fetch(request, env) {
    let podId;
    try {
      podId = await currentPod(env);
    } catch (e) {
      return Response.json({ error: { message: `Cannot reach RunPod: ${e.message}`, type: "proxy_error" } }, { status: 502 });
    }
    if (!podId) {
      return Response.json(
        { error: { message: "OpenScholar server is stopped (start it with the 'OpenScholar server' GitHub Action)", type: "server_stopped" } },
        { status: 503 },
      );
    }
    const url = new URL(request.url);
    const target = `https://${podId}-8080.proxy.runpod.net${url.pathname}${url.search}`;
    return fetch(new Request(target, request));
  },
};
