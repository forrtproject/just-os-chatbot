// Debug panel for the chat page, on when the setting DEBUG_PANEL is (config/settings.py, default on).
// Per turn: a one-line summary under the answer; click it for the turn's detail (rewritten question,
// topic check scores, source scores, step times and costs). A bar above the chat sums up the thread.
// Data: the "debug" field of the final /chat message (just_os/trace.py).

const turns = [];
let metric = "time"; // thread chart: "time" or "cost"
let openIndex = null;

// One colour per kind of step, everywhere in the panel
const STEP_COLOURS = {
  "answer cache": "#8c8c8c",
  rephrase: "#7b5ea7",
  "topic check": "#c98a12",
  sources: "#1f7a8c",
  search: "#1f7a8c",
  rerank: "#4fa3b5",
  "FORRT pages": "#3a8f5c",
  "FORRT pages next to papers": "#3a8f5c",
  "page search": "#7fbf95",
  answer: "#004055",
  "citation check": "#6b7a8f",
  other: "#d0d0d0",
};
const STEP_LABELS = {
  "answer cache": "Answer cache",
  rephrase: "Rewrite question",
  "topic check": "Topic check",
  sources: "Find sources",
  search: "search",
  rerank: "re-rank",
  "FORRT pages": "FORRT pages",
  "FORRT pages next to papers": "FORRT pages (next to papers)",
  "page search": "page search",
  answer: "Answer",
  "citation check": "Citation check",
  other: "Other (history, formatting)",
};
const OUTCOMES = {
  answered: ["papers", "ok"],
  forrt: ["FORRT pages", "ok"],
  both: ["papers + FORRT", "ok"],
  forrt_lookup: ["FORRT lookup", "ok"],
  off_topic: ["off topic", "warn"],
  small_talk: ["small talk", "muted"],
  no_sources: ["no sources", "warn"],
  error: ["error", "bad"],
};

export function debugEnabled() {
  return window.JUSTOS_DEBUG_PANEL === true; // set by templates/index.html from DEBUG_PANEL
}

// ---------- small helpers ----------

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const fmtTime = (ms) => (ms == null ? "–" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`);
function fmtCost(cost) {
  if (cost == null) return "–";
  if (cost === 0) return "$0";
  if (cost < 0.0001) return "<$0.0001";
  return "$" + cost.toFixed(cost < 0.01 ? 4 : 3);
}
const fmtTokens = (n) => (n == null ? "–" : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const fmtScore = (s) => (s == null ? "–" : s.toFixed(2));
const pct = (v, max) => `${Math.max(0, Math.min(100, (100 * v) / (max || 1)))}%`;

function stepCost(debug, name) {
  const costs = debug.calls.filter((c) => c.step === name && c.cost != null).map((c) => c.cost);
  return costs.length ? costs.reduce((a, b) => a + b, 0) : null;
}

function outcomeOf(data) {
  const key = data.status === "error" ? "error" : data.outcome || "answered";
  return { key, label: (OUTCOMES[key] || [key])[0], tone: (OUTCOMES[key] || [, "muted"])[1] };
}

// ---------- thread bar ----------

function threadBar() {
  let bar = document.getElementById("debug-thread");
  if (bar) return bar;
  bar = h("section", { id: "debug-thread", "aria-label": "Debug: this conversation" });
  document.getElementById("chat-messages").before(bar);
  return bar;
}

function renderThread() {
  const bar = threadBar();
  bar.replaceChildren();
  const ms = turns.reduce((a, t) => a + (t.debug.totals.ms || 0), 0);
  const costs = turns.map((t) => t.debug.totals.cost).filter((c) => c != null);
  const tokens = turns.reduce((a, t) => a + t.debug.totals.tokens_in + t.debug.totals.tokens_out, 0);

  if (!turns.length) {
    bar.append(h("div", { class: "debug-thread-head" },
      h("span", { class: "debug-tag" }, "Debug"),
      h("span", { class: "debug-muted" }, "Ask a question: each answer gets its trace.")));
    return;
  }

  const toggle = h("div", { class: "debug-seg", role: "group", "aria-label": "Chart shows" },
    ...["time", "cost"].map((m) => h("button", {
      type: "button", "aria-pressed": String(metric === m),
      onclick: () => { metric = m; renderThread(); },
    }, m === "time" ? "Time" : "Cost")));

  bar.append(h("div", { class: "debug-thread-head" },
    h("span", { class: "debug-tag" }, "Debug"),
    h("span", { class: "debug-stats" },
      h("b", {}, `${turns.length} turn${turns.length > 1 ? "s" : ""}`), " · ",
      fmtTime(ms), " · ",
      h("span", { title: costs.length < turns.length ? "Some calls reported no cost" : null },
        costs.length ? fmtCost(costs.reduce((a, b) => a + b, 0)) : "–"), " · ",
      `${fmtTokens(tokens)} tokens`),
    toggle));

  const values = turns.map((t) => (metric === "time" ? t.debug.totals.ms : t.debug.totals.cost) || 0);
  const max = Math.max(...values, 1e-9);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const chart = h("div", { class: "debug-turn-chart" });
  turns.forEach((t, i) => {
    const v = values[i];
    const label = `Turn ${i + 1}: ${metric === "time" ? fmtTime(v) : fmtCost(t.debug.totals.cost)} · ${t.outcome.label}\n${t.question}`;
    chart.append(h("button", {
      type: "button", class: `debug-turn-bar tone-${t.outcome.tone}`, title: label, "aria-label": label,
      "aria-current": openIndex === i ? "true" : null,
      onclick: () => openTurn(i, true),
    }, h("span", { style: `height:${Math.max(6, (100 * v) / max)}%` }),
       h("small", {}, String(i + 1))));
  });
  bar.append(h("div", { class: "debug-chart-wrap" }, chart,
    h("span", { class: "debug-muted debug-chart-note" },
      `${metric === "time" ? "time" : "cost"} per turn · average ${metric === "time" ? fmtTime(avg) : fmtCost(avg)}`)));
}

// ---------- the line under each answer ----------

function turnLine(i) {
  const t = turns[i];
  const d = t.debug;
  const src = d.info.sources;
  const sent = src ? src.chunks.filter((c) => c.sent) : [];
  const top = sent.length ? Math.max(...sent.map((c) => c.score ?? -Infinity)) : null;
  const parts = [
    h("span", {}, fmtTime(d.totals.ms)),
    h("span", {}, fmtCost(d.totals.cost)),
    h("span", { class: `debug-pill tone-${t.outcome.tone}` }, t.outcome.label),
    src && h("span", {}, `${sent.length}/${src.chunks.length} sources`),
    top != null && isFinite(top) && h("span", {}, `top ${fmtScore(top)}`),
  ].filter(Boolean);
  return h("button", { type: "button", class: "debug-line", onclick: () => openTurn(i), title: "Show how this answer was made" },
    h("i", { class: "fas fa-magnifying-glass-chart", "aria-hidden": "true" }),
    ...parts.flatMap((p, k) => (k ? [h("span", { class: "debug-sep" }, "·"), p] : [p])),
    h("span", { class: "debug-line-more" }, "details"));
}

// ---------- panel ----------

function panel() {
  let p = document.getElementById("debug-panel");
  if (p) return p;
  p = h("aside", { id: "debug-panel", "aria-label": "Debug: turn detail", hidden: true });
  document.body.append(p);
  document.addEventListener("keydown", (e) => {
    if (openIndex == null || e.target.closest("textarea, input")) return;
    if (e.key === "Escape") closePanel();
    if (e.key === "ArrowUp" && openIndex > 0) openTurn(openIndex - 1);
    if (e.key === "ArrowDown" && openIndex < turns.length - 1) openTurn(openIndex + 1);
  });
  return p;
}

function closePanel() {
  openIndex = null;
  panel().hidden = true;
  document.body.classList.remove("debug-panel-open");
  document.querySelectorAll(".debug-line[aria-expanded]").forEach((b) => b.removeAttribute("aria-expanded"));
  renderThread();
}

function openTurn(i, scroll = false) {
  openIndex = i;
  const t = turns[i];
  const p = panel();
  p.hidden = false;
  document.body.classList.add("debug-panel-open");
  document.querySelectorAll(".debug-line[aria-expanded]").forEach((b) => b.removeAttribute("aria-expanded"));
  t.line.setAttribute("aria-expanded", "true");
  if (scroll) t.el.scrollIntoView({ behavior: "smooth", block: "nearest" });

  const d = t.debug;
  const nav = (j, icon, label) => h("button", {
    type: "button", class: "debug-icon", title: label, "aria-label": label, disabled: j < 0 || j >= turns.length,
    onclick: () => openTurn(j, true),
  }, h("i", { class: `fas ${icon}`, "aria-hidden": "true" }));

  p.replaceChildren(
    h("header", { class: "debug-panel-head" },
      h("div", {},
        h("div", { class: "debug-kicker" }, `Turn ${i + 1} of ${turns.length}`),
        h("div", { class: "debug-headline" },
          h("span", { class: `debug-pill tone-${t.outcome.tone}` }, t.outcome.label),
          h("b", {}, fmtTime(d.totals.ms)),
          h("b", { title: d.totals.cost_missing ? `${d.totals.cost_missing} call(s) reported no cost` : null },
            fmtCost(d.totals.cost) + (d.totals.cost_missing && d.totals.cost != null ? "+" : "")),
          h("span", { class: "debug-muted" }, `${fmtTokens(d.totals.tokens_in + d.totals.tokens_out)} tokens`))),
      h("div", { class: "debug-head-actions" },
        nav(i - 1, "fa-chevron-up", "Previous turn"), nav(i + 1, "fa-chevron-down", "Next turn"),
        h("button", { type: "button", class: "debug-icon", title: "Close (Esc)", "aria-label": "Close", onclick: closePanel },
          h("i", { class: "fas fa-xmark", "aria-hidden": "true" })))),
    h("div", { class: "debug-panel-body" },
      questionSection(t), routeSection(t), sourcesSection(t), stepsSection(t), rawSection(t)),
  );
  p.querySelector(".debug-panel-body").scrollTop = 0;
  renderThread();
}

function section(title, aside, ...body) {
  return h("section", { class: "debug-section" },
    h("h3", {}, title, aside ? h("span", { class: "debug-muted" }, aside) : null), ...body);
}

// 1. what it understood
function questionSection(t) {
  const step = t.debug.steps.find((s) => s.name === "rephrase");
  const cache = t.debug.steps.find((s) => s.name === "answer cache");
  const rows = [h("div", { class: "debug-q" }, h("span", { class: "debug-label" }, "Typed"), h("span", {}, t.question))];
  if (step) {
    const same = (step.to || "").trim() === (step.from || "").trim();
    rows.push(h("div", { class: "debug-q" }, h("span", { class: "debug-label" }, "Rewritten"),
      same ? h("span", { class: "debug-muted" }, "unchanged") : h("span", { class: "debug-rewritten" }, step.to)));
  } else if (t.index > 0) {
    rows.push(h("div", { class: "debug-q" }, h("span", { class: "debug-label" }, "Rewritten"),
      h("span", { class: "debug-muted" }, `not rewritten (context method: ${t.debug.info.settings?.context_method || "?"})`)));
  }
  if (cache?.hit) rows.push(h("div", { class: "debug-note" }, "Answer came from the answer cache: no model calls."));
  return section("Question", null, ...rows);
}

// 2. what it decided
function scoreRow(label, value, { max = 1, threshold = null, chosen = false, dim = false, right = null, title = null } = {}) {
  return h("div", { class: `debug-score${chosen ? " chosen" : ""}${dim ? " dim" : ""}`, title },
    h("span", { class: "debug-score-label" }, label),
    h("span", { class: "debug-track" },
      h("span", { class: "debug-fill", style: `width:${pct(value ?? 0, max)}` }),
      threshold != null ? h("span", { class: "debug-threshold", style: `left:${pct(threshold, max)}`, title: `threshold ${threshold}` }) : null),
    h("span", { class: "debug-score-value" }, right ?? fmtScore(value)));
}

function routeSection(t) {
  const d = t.debug;
  const step = d.steps.find((s) => s.name === "topic check");
  if (!step) return null;
  const s = d.info.settings || {};
  const router = step.router || "";
  const routerName = router || (s.decision_router ? `default (${s.decision_router_model || "decision model"})` : "default (LLM classifier)");
  const body = [];
  const decision = d.calls.find((c) => c.step === "topic check" && c.kind === "decision");
  const llm = d.calls.filter((c) => c.step === "topic check" && c.kind === "llm");
  const sim = d.info.similarity;

  if (sim && (router === "cosine" || router === "banded")) {
    const [pT, gT] = router === "cosine" ? [s.cosine_paper_min, s.cosine_page_min] : [s.band_paper_high, s.band_page_high];
    body.push(h("div", { class: "debug-sub" }, "Similarity to the nearest", router === "banded" ? " (line: high band)" : " (line: threshold)"),
      scoreRow("paper chunk", sim.paper, { threshold: pT, chosen: sim.paper >= pT }),
      scoreRow("FORRT page", sim.page, { threshold: gT, chosen: sim.page >= gT }));
  }
  if (decision) {
    const probs = decision.questions?.route?.probabilities || {};
    const chosen = decision.questions?.route?.choice;
    const threshold = !router && s.decision_router ? s.decision_router_min_confidence : null;
    body.push(h("div", { class: "debug-sub" }, decision.model, threshold != null ? ` · needs ${threshold} to be used` : ""));
    Object.entries(probs).sort((a, b) => b[1] - a[1]).forEach(([k, v]) =>
      body.push(scoreRow(k, v, { threshold, chosen: k === chosen })));
    if (decision.error) body.push(h("div", { class: "debug-note bad" }, `Decision model failed: ${decision.error}`));
  }
  if (llm.length) {
    body.push(h("div", { class: "debug-sub" },
      decision ? "Decision model unsure or failed, so the LLM classifier decided: " : "LLM classifier: ",
      llm.map((c) => c.model).join(", ")));
  }
  const margin = (() => {
    const probs = Object.values(decision?.questions?.route?.probabilities || {}).sort((a, b) => b - a);
    return probs.length > 1 ? probs[0] - probs[1] : null;
  })();
  const warn = margin != null && margin < 0.2
    ? h("div", { class: "debug-note warn" }, `Close call: the top two routes are ${margin.toFixed(2)} apart.`) : null;
  return section("Topic check", `${routerName} → ${step.route ?? "error"}`, ...body, warn);
}

// 3. what it used
function citedKeys(t) {
  const refs = t.data.metadata?.references || [];
  return new Set(refs.flatMap((r) => [r.url, (r.title || "").toLowerCase()]).filter(Boolean));
}

function sourcesSection(t) {
  const d = t.debug;
  const out = [];
  const cited = citedKeys(t);
  const src = d.info.sources;
  if (src) {
    const isCited = (c) => cited.has(c.url) || cited.has((c.title || "").toLowerCase());
    const max = Math.max(1, ...src.chunks.map((c) => c.score || 0));
    const threshold = src.min_relevance ?? null;
    const sent = src.chunks.filter((c) => c.sent);
    const dropped = src.chunks.filter((c) => !c.sent);
    const row = (c) => {
      const tag = c.sent ? (isCited(c) ? "cited" : "sent") : c.why;
      const item = h("details", { class: `debug-chunk${c.sent ? "" : " dropped"}` },
        h("summary", {},
          scoreRow(c.title, c.score, { max, threshold, chosen: c.sent && isCited(c), dim: !c.sent,
            right: fmtScore(c.score) }),
          h("span", { class: `debug-chunk-tag${tag === "cited" ? " cited" : ""}` }, c.sent ? `[${c.n}] ${tag}` : tag)),
        h("p", {}, c.text), c.url ? h("a", { href: c.url, target: "_blank", rel: "noopener" }, c.url) : null);
      return item;
    };
    const legend = [
      { rerank: "re-ranker score", cosine: "similarity to the question (no re-ranker)", search: "search score (no re-ranker)" }[src.kind]
        + (threshold != null ? `, line = minimum ${threshold}` : ""),
      src.cutoff != null ? `adaptive cut-off ${src.cutoff.toFixed(2)}` : null,
    ].filter(Boolean).join(" · ");
    out.push(h("div", { class: "debug-sub" }, legend));
    sent.forEach((c) => out.push(row(c)));
    if (dropped.length) {
      const more = h("details", { class: "debug-more" },
        h("summary", {}, `${dropped.length} not sent to the model`), ...dropped.map(row));
      out.push(more);
    }
    if (!sent.length) out.push(h("div", { class: "debug-note warn" }, "No chunk passed: the answer is \"no sources\"."));
  }
  for (const pages of forrtPageGroups(t, cited)) out.push(pages);
  if (!out.length) return null;
  const count = src ? `${src.chunks.filter((c) => c.sent).length} of ${src.chunks.length} chunks sent` : null;
  return section("Sources", count, ...out);
}

// FORRT pages: search score, then the decision model's yes-probability per page
function forrtPageGroups(t, cited) {
  const d = t.debug;
  const s = d.info.settings || {};
  const groups = [];
  for (const parent of ["FORRT pages", "FORRT pages next to papers", null]) {
    const search = d.steps.find((st) => st.name === "page search" && (st.parent || null) === parent);
    if (!search) continue;
    const decision = d.calls.find((c) => c.kind === "decision" && c.step === (parent || "other") && c.questions?.page_1);
    const yes = {};
    Object.values(decision?.questions || {}).forEach((q) => { yes[q.label] = q.yes; });
    const threshold = s.forrt_decision_threshold;
    const title = parent === "FORRT pages next to papers" ? "FORRT pages next to the papers"
      : parent ? "FORRT pages" : "FORRT links (papers + FORRT)";
    const rows = search.pages.map((p) => {
      const read = cited.has(p.url) || cited.has((p.title || "").toLowerCase());
      return scoreRow(p.title, yes[p.title] ?? null, {
        threshold, chosen: read, dim: !read,
        right: `${yes[p.title] != null ? fmtScore(yes[p.title]) : "–"}`,
        title: `search score ${fmtScore(p.score)}${read ? " · read for the answer" : ""}\n${p.url}`,
      });
    });
    groups.push(h("div", { class: "debug-group" },
      h("div", { class: "debug-sub" }, `${title}: decision model's "worth reading" probability`,
        threshold != null ? `, line = ${threshold}` : "", decision ? "" : " (no decision call)"),
      ...rows));
  }
  return groups;
}

// 4. where the time and money went
function stepsSection(t) {
  const d = t.debug;
  const total = Math.max(d.totals.ms || 1, 1);
  const steps = [];
  const seen = {};
  for (const s of d.steps) {
    seen[s.name] = (seen[s.name] || 0) + 1;
    steps.push({ ...s, label: (STEP_LABELS[s.name] || s.name) + (seen[s.name] > 1 ? ` (try ${seen[s.name]})` : "") });
    if (s.name === "sources") {
      // the search / re-rank split the pipeline already measures
      const tm = d.timings || {};
      let at = s.start_ms;
      for (const [k, key] of [["search", "search_s"], ["rerank", "rerank_s"]]) {
        if (tm[key] == null) continue;
        const ms = Math.round(tm[key] * 1000);
        steps.push({ name: k, label: STEP_LABELS[k], start_ms: at, ms, parent: "sources", derived: true });
        at += ms;
      }
    }
  }
  // time no step covers: chat history, formatting the answer, the citation retry wait, ...
  const covered = mergeIntervals(steps.filter((s) => !s.parent).map((s) => [s.start_ms, s.start_ms + s.ms]));
  const other = total - covered;
  if (other > Math.max(50, total * 0.05)) steps.push({ name: "other", label: STEP_LABELS.other, start_ms: null, ms: other });
  const slowest = steps.filter((s) => !s.parent && s.name !== "other").sort((a, b) => b.ms - a.ms)[0];

  const rows = steps.map((s) => {
    const cost = s.derived || s.name === "other" ? null : stepCost(d, s.name);
    const calls = d.calls.filter((c) => c.step === s.name);
    const models = [...new Set(calls.map((c) => c.model))].join(", ");
    const colour = STEP_COLOURS[s.name] || "#999";
    const bar = s.start_ms == null
      ? h("span", { class: "debug-wf-bar other", style: `left:${pct(total - s.ms, total)};width:${pct(s.ms, total)}` })
      : h("span", { class: "debug-wf-bar", style: `left:${pct(s.start_ms, total)};width:max(2px,${pct(s.ms, total)});background:${colour}` });
    const tokens = calls.reduce((a, c) => a + (c.tokens_in || 0) + (c.tokens_out || 0), 0);
    return h("div", {
      class: `debug-wf-row${s.parent ? " child" : ""}${s === slowest ? " slowest" : ""}${s.error ? " failed" : ""}`,
      title: [models && `models: ${models}`, tokens && `${fmtTokens(tokens)} tokens`, s.error].filter(Boolean).join("\n") || null,
    },
      h("span", { class: "debug-wf-label" }, h("i", { style: `background:${colour}` }), s.label),
      h("span", { class: "debug-wf-track" }, bar),
      h("span", { class: "debug-wf-num" }, fmtTime(s.ms)),
      h("span", { class: "debug-wf-num" }, cost == null ? "" : fmtCost(cost)));
  });

  const share = slowest ? Math.round((100 * slowest.ms) / total) : null;
  const aside = slowest ? `${slowest.label.toLowerCase()} took ${share}%` : null;
  return section("Time and cost", aside,
    h("div", { class: "debug-wf" }, ...rows),
    callsTable(d));
}

function mergeIntervals(list) {
  const sorted = list.filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  let sum = 0, end = -Infinity;
  for (const [a, b] of sorted) {
    if (a > end) { sum += b - a; end = b; } else if (b > end) { sum += b - end; end = b; }
  }
  return sum;
}

function callsTable(d) {
  if (!d.calls.length) return h("div", { class: "debug-muted" }, "No model calls.");
  const rows = d.calls.map((c) => h("tr", { class: c.error ? "failed" : null },
    h("td", {}, STEP_LABELS[c.step] || c.step),
    h("td", { class: "debug-model", title: c.model }, c.model.split("/").pop(),
      c.attempts > 1 ? h("small", {}, ` ×${c.attempts}`) : null),
    h("td", {}, fmtTime(c.ms)),
    h("td", {}, c.kind === "decision" ? "–" : `${fmtTokens(c.tokens_in)} → ${fmtTokens(c.tokens_out)}`,
      c.tokens_cached ? h("small", { title: "cached input tokens" }, ` (${fmtTokens(c.tokens_cached)} cached)`) : null),
    h("td", {}, fmtCost(c.cost))));
  return h("details", { class: "debug-more" },
    h("summary", {}, `${d.calls.length} model call${d.calls.length > 1 ? "s" : ""}: ${fmtTokens(d.totals.tokens_in)} in, ${fmtTokens(d.totals.tokens_out)} out`),
    h("table", { class: "debug-calls" },
      h("thead", {}, h("tr", {}, ...["Step", "Model", "Time", "Tokens", "Cost"].map((x) => h("th", {}, x)))),
      h("tbody", {}, ...rows)));
}

// 5. everything else, for when the summary is not enough
function rawSection(t) {
  const json = JSON.stringify({ question: t.question, turn_id: t.data.turn_id, outcome: t.data.outcome, debug: t.debug }, null, 2);
  const copy = h("button", { type: "button", class: "debug-copy", onclick: async (e) => {
    e.preventDefault();
    try { await navigator.clipboard.writeText(json); copy.textContent = "Copied"; } catch { copy.textContent = "Copy failed"; }
    setTimeout(() => { copy.textContent = "Copy JSON"; }, 1500);
  } }, "Copy JSON");
  const settings = Object.entries(t.debug.info.settings || {}).filter(([, v]) => v !== null && v !== "");
  return h("section", { class: "debug-section debug-raw" },
    h("details", { class: "debug-more" }, h("summary", {}, "Settings used"),
      h("dl", { class: "debug-settings" }, ...settings.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, String(v))]))),
    h("details", { class: "debug-more" }, h("summary", {}, "Raw trace", copy), h("pre", {}, json)));
}

// ---------- entry points for app.js ----------

export function initDebug() {
  if (!debugEnabled()) return;
  document.body.classList.add("debug-on");
  renderThread();
}

export function addDebugTurn(messageEl, data, question) {
  if (!data?.debug || !debugEnabled()) return;
  const index = turns.length;
  const t = { index, el: messageEl, data, debug: data.debug, question, outcome: outcomeOf(data) };
  turns.push(t);
  t.line = turnLine(index);
  messageEl.append(t.line);
  renderThread();
  if (openIndex != null) openTurn(index); // the panel follows the conversation
}

export function resetDebug() {
  turns.length = 0;
  if (openIndex != null) closePanel();
  if (debugEnabled()) renderThread();
}
