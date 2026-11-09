import { setupReferenceHandlers } from "./references.js";

let battleId = null;

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

function setBusy(busy) {
  document.getElementById("user-input").disabled = busy;
  document.getElementById("send-button").disabled = busy;
}

function showAnswers(responses) {
  document.querySelectorAll(".arena-card").forEach((card, i) => {
    const response = responses[i];
    // Server-built HTML, same as the chat page
    card.querySelector(".arena-body").innerHTML = response.message;
    card.querySelector(".sources").textContent = response.sources;
    card.querySelector(".arena-model").textContent = "";
    card.dataset.seconds = response.seconds;
  });
  document.getElementById("arena-answers").hidden = false;
  document.getElementById("arena-votes").hidden = false;
  document.querySelectorAll("#arena-votes button").forEach((b) => (b.disabled = false));
  setupReferenceHandlers();
}

async function ask(question) {
  const status = document.getElementById("status-message");
  const questionBox = document.getElementById("arena-question");
  questionBox.textContent = question;
  questionBox.hidden = false;
  document.getElementById("arena-answers").hidden = true;
  document.getElementById("arena-votes").hidden = true;
  battleId = null;
  setBusy(true);
  status.textContent = "Processing your request…";

  try {
    const response = await fetch("/arena/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
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
        // Refusal, no sources, or error: one message, nothing to vote on
        const tmp = document.createElement("div");
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

async function vote(choice) {
  if (!battleId) return;
  const buttons = document.querySelectorAll("#arena-votes button");
  buttons.forEach((b) => (b.disabled = true));
  const response = await fetch("/arena/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ battle_id: battleId, vote: choice }),
  });
  const data = await response.json();
  if (data.status !== "ok") {
    document.getElementById("status-message").textContent = data.message;
    return;
  }
  battleId = null;
  document.querySelectorAll(".arena-card").forEach((card, i) => {
    card.querySelector(".arena-model").textContent =
      `${data.models[i]} · ${card.dataset.seconds} s`;
  });
  document.querySelector(`#arena-votes button[data-vote="${choice}"]`).classList.add("chosen");
  if (!document.getElementById("leaderboard").hidden) loadLeaderboard();
}

async function loadLeaderboard() {
  const votes = await (await fetch("/arena/votes")).json();
  const stats = {};
  const row = (model) =>
    (stats[model] ??= { battles: 0, wins: 0, losses: 0, tie: 0, bad: 0 });
  for (const v of votes) {
    const a = row(v.model_a);
    const b = row(v.model_b);
    a.battles++;
    b.battles++;
    if (v.vote === "a") { a.wins++; b.losses++; }
    else if (v.vote === "b") { b.wins++; a.losses++; }
    else { a[v.vote]++; b[v.vote]++; }
  }
  const rows = Object.entries(stats)
    .map(([model, s]) => ({ model, ...s, rate: (s.wins + s.tie / 2) / s.battles }))
    .sort((x, y) => y.rate - x.rate);
  const tbody = document.querySelector("#leaderboard tbody");
  tbody.replaceChildren(
    ...rows.map((r) => {
      const tr = document.createElement("tr");
      for (const value of [r.model, r.battles, r.wins, r.losses, r.tie, r.bad, `${Math.round(r.rate * 100)} %`]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      }
      return tr;
    })
  );
  document.getElementById("leaderboard").hidden = false;
}

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("user-input");
  const send = document.getElementById("send-button");

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
  document.querySelectorAll("#arena-votes button").forEach((button) =>
    button.addEventListener("click", () => {
      document.querySelectorAll("#arena-votes button").forEach((b) => b.classList.remove("chosen"));
      vote(button.dataset.vote);
    })
  );
  document.getElementById("leaderboard-button").addEventListener("click", () => {
    const board = document.getElementById("leaderboard");
    if (board.hidden) loadLeaderboard();
    else board.hidden = true;
  });
});
