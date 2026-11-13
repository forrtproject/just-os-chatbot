import { renderSources, setupReferenceHandlers } from "./references.js";

let battleId = null;
let criteria = {};
let scale = [1, 2, 3, 4, 5]; // from data-scale (config/criteria.json)

// Read an NDJSON stream and call onChunk for each parsed line.
async function readStream(response, onChunk) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let newline;
    while ((newline = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onChunk(JSON.parse(line));
    }
    if (done) break;
  }
  if (buffer.trim()) onChunk(JSON.parse(buffer));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function selectedModels() {
  return [...document.querySelectorAll('#model-picker input[name="model"]:checked')].map(
    (box) => box.value
  );
}

function updateModelCount() {
  const max = Number(document.getElementById("arena").dataset.maxModels);
  const total = document.querySelectorAll('#model-picker input[name="model"]').length;
  const n = selectedModels().length;
  const count = document.getElementById("model-count");
  count.textContent = `${n} of ${total} selected` + (n > max ? ` (max ${max})` : "");
  count.classList.toggle("too-many", n === 0 || n > max);
}

function setBusy(busy) {
  document.getElementById("user-input").disabled = busy;
  document.getElementById("send-button").disabled = busy;
}

// One scale per criterion: a radio group, keyboard accessible
function ratingScale(label, key, text) {
  const group = el("fieldset", "rating");
  group.appendChild(el("legend", null, text));
  const track = el("div", "rating-scale");
  for (const value of scale) {
    const option = el("label");
    const input = el("input");
    input.type = "radio";
    input.name = `${label}-${key}`;
    input.value = value;
    input.addEventListener("change", updateSubmit);
    option.append(input, el("span", null, String(value)));
    track.appendChild(option);
  }
  group.appendChild(track);
  return group;
}

function answerCard(response) {
  const card = el("section", "arena-card");
  card.dataset.label = response.label;
  const header = el("header");
  header.append(
    el("span", "arena-label", `Answer ${response.label}`),
    el("span", "arena-model", response.model || ""), // empty while ARENA_BLIND hides it
    el("span", "arena-time", `${response.seconds} s`)
  );
  const body = el("div", "arena-body bot-message");
  body.innerHTML = response.message; // server-built HTML, same as the chat page
  card.append(header, body, renderSources(response.references, response.sources));
  if (response.error) {
    card.classList.add("failed");
  } else {
    const ratings = el("div", "ratings");
    for (const [key, text] of Object.entries(criteria)) {
      ratings.appendChild(ratingScale(response.label, key, text));
    }
    card.appendChild(ratings);
  }
  return card;
}

function collectRatings() {
  const ratings = {};
  for (const card of document.querySelectorAll(".arena-card:not(.failed)")) {
    const label = card.dataset.label;
    const scores = {};
    for (const key of Object.keys(criteria)) {
      const checked = card.querySelector(`input[name="${label}-${key}"]:checked`);
      if (!checked) return null; // every answer needs every criterion
      scores[key] = Number(checked.value);
    }
    ratings[label] = scores;
  }
  return Object.keys(ratings).length ? ratings : null;
}

function updateSubmit() {
  document.getElementById("submit-ratings").disabled = !battleId || !collectRatings();
}

function showAnswers(responses) {
  const answers = document.getElementById("arena-answers");
  answers.replaceChildren(...responses.map(answerCard));
  answers.hidden = false;
  document.getElementById("arena-submit").hidden = !responses.some((r) => !r.error);
  updateSubmit();
  setupReferenceHandlers();
}

async function ask(question) {
  const models = selectedModels();
  const status = document.getElementById("status-message");
  const max = Number(document.getElementById("arena").dataset.maxModels);
  if (!models.length || models.length > max) {
    status.textContent = `Choose 1 to ${max} models first.`;
    document.getElementById("model-picker").open = true;
    return;
  }
  const questionBox = document.getElementById("arena-question");
  questionBox.textContent = question;
  questionBox.hidden = false;
  document.getElementById("arena-answers").hidden = true;
  document.getElementById("arena-submit").hidden = true;
  document.getElementById("model-picker").open = false;
  battleId = null;
  setBusy(true);
  status.textContent = `Asking ${models.length} model${models.length > 1 ? "s" : ""}…`;

  try {
    const response = await fetch("/arena/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question, models, router: document.getElementById("router-select")?.value || undefined }),
    });
    if (!response.ok && response.headers.get("Content-Type")?.includes("json")) {
      status.textContent = (await response.json()).message;
      return;
    }
    await readStream(response, (data) => {
      if (data.status === "in-progress") {
        status.textContent = data.message + "…";
      } else if (data.responses) {
        status.textContent = "";
        battleId = data.battle_id;
        showAnswers(data.responses);
      } else {
        // Refusal, no sources, or error: one message, nothing to rate
        const tmp = el("div");
        tmp.innerHTML = data.message;
        status.textContent = tmp.textContent;
      }
    });
  } catch (error) {
    console.error(error);
    status.textContent = "Something went wrong. Please try again.";
  } finally {
    setBusy(false);
  }
}

async function submitRatings() {
  const ratings = collectRatings();
  if (!battleId || !ratings) return;
  const button = document.getElementById("submit-ratings");
  button.disabled = true;
  const response = await fetch("/arena/rate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ battle_id: battleId, ratings }),
  });
  const data = await response.json();
  if (data.status !== "ok") {
    document.getElementById("status-message").textContent = data.message;
    return;
  }
  battleId = null;
  document.querySelectorAll(".arena-card").forEach((card) => {
    card.querySelector(".arena-model").textContent = data.models[card.dataset.label] || "";
    card.querySelectorAll(".ratings input").forEach((input) => (input.disabled = true));
  });
  document.getElementById("status-message").textContent = "Thank you. Your ratings are saved.";
  if (!document.getElementById("leaderboard").hidden) loadLeaderboard();
}

async function loadLeaderboard() {
  const rows = await (await fetch("/arena/leaderboard")).json();
  const tbody = document.querySelector("#leaderboard tbody");
  const columns = ["model", "ratings", ...Object.keys(criteria), "overall", "seconds"];
  tbody.replaceChildren(
    ...rows.map((row) => {
      const tr = el("tr");
      for (const column of columns) tr.appendChild(el("td", null, String(row[column])));
      return tr;
    })
  );
  if (!rows.length) {
    const tr = el("tr");
    const td = el("td", null, "No ratings yet.");
    td.colSpan = columns.length;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  const board = document.getElementById("leaderboard");
  board.hidden = false;
  board.scrollIntoView({ behavior: "smooth", block: "start" }); // it sits below the question box
}

document.addEventListener("DOMContentLoaded", () => {
  // [key, text] pairs: a list keeps the order (tojson would sort an object's keys)
  criteria = Object.fromEntries(JSON.parse(document.getElementById("arena").dataset.criteria));
  scale = JSON.parse(document.getElementById("arena").dataset.scale);
  const input = document.getElementById("user-input");
  const send = document.getElementById("send-button");
  const boxes = document.querySelectorAll('#model-picker input[name="model"]');

  boxes.forEach((box) => box.addEventListener("change", updateModelCount));
  document.getElementById("select-all").addEventListener("click", () => {
    boxes.forEach((box) => (box.checked = true));
    updateModelCount();
  });
  document.getElementById("select-none").addEventListener("click", () => {
    boxes.forEach((box) => (box.checked = false));
    updateModelCount();
  });
  updateModelCount();

  send.addEventListener("click", () => {
    const question = input.value.trim();
    if (question.length < 3) return;
    input.value = "";
    ask(question);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send.click();
    }
  });
  document.getElementById("submit-ratings").addEventListener("click", submitRatings);
  document.getElementById("leaderboard-button").addEventListener("click", () => {
    const board = document.getElementById("leaderboard");
    if (board.hidden) loadLeaderboard();
    else board.hidden = true;
  });
});
