import { renderSources, setupReferenceHandlers } from "./references.js";
import { addDebugTurn, debugEnabled, initDebug, resetDebug } from "./debug.js";
import { markdownToHtml, sanitizeHtml } from "./sanitize.js";

// "How was this answer?" under each answer: Good/Bad, then an optional comment, sent once
function feedbackBar(turnId) {
  const bar = document.createElement("div");
  bar.className = "feedback";
  const question = document.createElement("span");
  question.textContent = "How was this answer?";
  const form = document.createElement("form");
  form.className = "feedback-form";
  form.hidden = true;
  const comment = document.createElement("textarea");
  comment.maxLength = 2000;
  comment.placeholder = "Tell us more (optional)";
  comment.setAttribute("aria-label", "Feedback comment");
  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = "Send feedback";
  form.append(comment, send);

  let rating = null;
  const choice = (value, icon, label) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "feedback-choice";
    button.title = label;
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = `<i class="fas ${icon}" aria-hidden="true"></i> ${label}`;
    button.addEventListener("click", () => {
      rating = value;
      bar.querySelectorAll(".feedback-choice").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      form.hidden = false;
      comment.focus();
    });
    return button;
  };
  bar.append(question, choice("good", "fa-thumbs-up", "Good"), choice("bad", "fa-thumbs-down", "Bad"), form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    send.disabled = true;
    try {
      const response = await fetch("/chat/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ turn_id: turnId, rating, comment: comment.value }),
      });
      bar.textContent = response.ok ? "Thanks for your feedback." : "Could not send the feedback.";
    } catch {
      bar.textContent = "Could not send the feedback.";
    }
  });
  return bar;
}

// The answer while it is written (#41): plain Markdown without the [n] numbers, which are
// renumbered at the end. The final message replaces it.
function showDraft(text) {
  let draft = document.getElementById("draft-answer");
  if (!draft) {
    draft = document.createElement("div");
    draft.id = "draft-answer";
    draft.classList.add("message", "bot-message");
    draft.setAttribute("aria-live", "polite");
    document.getElementById("chat-messages").appendChild(draft);
  }
  draft.innerHTML = markdownToHtml(text.replace(/\s*\[\d+\]/g, ""));
}

function removeDraft() {
  document.getElementById("draft-answer")?.remove();
}

// retryQuestion: the question to ask again when this answer is an error (model or network failure)
function addMessage(message, sender, sources = null, turnId = null, retryQuestion = null) {
  const chatMessages = document.getElementById("chat-messages");

  const messageDiv = document.createElement("div");
  messageDiv.classList.add("message", `${sender}-message`);

  if (sender === "bot") {
    messageDiv.innerHTML = sanitizeHtml(message);
    // Setup reference handlers after adding bot message
    setTimeout(() => {
      setupReferenceHandlers();
    }, 0);
  } else {
    messageDiv.textContent = message;
  }

  if (sources && sources.length) {
    messageDiv.appendChild(renderSources(sources));
  }
  if (retryQuestion) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry-button";
    retry.textContent = "Try again";
    retry.addEventListener("click", () => {
      retry.remove();
      sendMessage(retryQuestion, { repeat: true });
    });
    messageDiv.appendChild(retry);
  } else if (turnId) {
    messageDiv.appendChild(feedbackBar(turnId));
  }

  chatMessages.appendChild(messageDiv);
  const added = messageDiv;

  // If this is a bot message, scroll the previous user message to the top
  if (sender === "bot") {
    const messages = chatMessages.getElementsByClassName("message");
    const lastUserMessage = Array.from(messages)
      .reverse()
      .find((msg) => msg.classList.contains("user-message"));
    if (lastUserMessage) {
      const rect = lastUserMessage.getBoundingClientRect();
      const absoluteTop = window.scrollY + rect.top - 20; // 20px padding from top
      console.log("Scrolling to:", absoluteTop);
      window.scrollTo({
        top: absoluteTop,
        behavior: "smooth",
      });
    }
  }
  return added;
}

async function sendMessage(message, { repeat = false } = {}) {
  const chatMessages = document.getElementById("chat-messages");
  const question = message;

  console.log("user message: " + message);
  if (message && !repeat) {
    const userMessageBox = document.createElement("div");
    const messageP = document.createElement("p");
    messageP.innerText = message;
    userMessageBox.appendChild(messageP);
    userMessageBox.classList.add("message", "user-message");
    chatMessages.appendChild(userMessageBox);
  }

  const statusMessage = document.getElementById("status-message");
  let baseMessage = "Processing your request";
  statusMessage.innerText = baseMessage;
  let dotCount = 0;
  function updateMessage() {
    dotCount = (dotCount % 4) + 1;
    let newMessage = baseMessage + ".".repeat(dotCount - 1);
    statusMessage.innerText = newMessage;
  }
  let messageInterval = setInterval(updateMessage, 1000);

  const messageInput = document.getElementById("user-input");
  const sendButton = document.getElementById("send-button");

  messageInput.disabled = true;
  sendButton.disabled = true;
  //  sendButton.style.display = "none";
  window.scrollTo(0, document.body.scrollHeight, { behavior: "smooth" });

  function endStream() {
    clearInterval(messageInterval);
    messageInput.disabled = false;
    sendButton.disabled = false;
    sendButton.style.display = "block";
    statusMessage.innerText = "";
  }

  // The final message: an answer, a refusal, or an error (status "error", or outcome "error" when the
  // answer model returned nothing); errors get a Try again button, refusals and answers do not
  let finished = false;
  function finish(data) {
    if (finished) return;
    finished = true;
    endStream();
    removeDraft();
    const failed = data.status === "error" || data.outcome === "error";
    const shown = addMessage(data.message, "bot", data.metadata?.references, data.turn_id, failed ? question : null);
    addDebugTurn(shown, data, question);
  }

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: message,
        chat_id: window.chatId,
        model: document.getElementById("model-select")?.value,
        router: document.getElementById("router-select")?.value || undefined,
        stream: true,
        debug: debugEnabled() || undefined,
      }),
    });
    // 400 (message too short or long), 429 (rate limit), 5xx from a proxy: no stream to read
    if (!response.ok) {
      let text = "";
      if (response.headers.get("Content-Type")?.includes("json")) {
        try {
          text = (await response.json()).message || "";
        } catch {
          text = "";
        }
      }
      const p = document.createElement("p");
      p.textContent = text || `The bot could not answer (error ${response.status}). Please try again.`;
      finish({ status: "error", message: p.outerHTML });
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let draft = "";

    const handle = (line) => {
      const data = JSON.parse(line); // a broken line is an error (caught below)
      if (data.status === "complete" || data.status === "error") {
        finish(data);
      } else if (data.status === "partial") {
        draft += data.delta;
        baseMessage = "Writing the answer";
        showDraft(draft);
      } else {
        removeDraft();
        baseMessage = data.message;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (line) handle(line);
      }
      if (done) break;
    }
    if (buffer.trim()) handle(buffer.trim());

    // The stream ended without a final message (server restart, proxy timeout)
    if (!finished) {
      finish({ status: "error", message: "<p>The answer was interrupted. Please try again.</p>" });
    }
  } catch (error) {
    console.error("Error:", error);
    finish({ status: "error", message: "<p>The bot could not be reached or sent a broken reply. Please try again.</p>" });
  } finally {
    endStream(); // never leave the input disabled
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const userInput = document.getElementById("user-input");
  const sendButton = document.getElementById("send-button");
  const infoButton = document.getElementById("info-button");
  const newChatButton = document.getElementById("new-chat-button");
  const modal = document.getElementById("info-modal");
  const closeModal = document.querySelector(".close-modal");
  initDebug();

  userInput.value =
    "How does open science reshape the future of interdisciplinary and collaborative research?";

  userInput.addEventListener("input", function () {
    sendButton.disabled = this.value.length < 3;
  });

  userInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!sendButton.disabled) {
        sendButton.click();
      }
    }
  });

  sendButton.addEventListener("click", function () {
    const message = userInput.value;
    if (message.trim().length < 3) return; // the button is enabled again after each answer
    userInput.value = "";
    showSuggestions(false);
    sendMessage(message);
  });

  // Example questions, one per FORRT cluster: four at random until the first question is sent
  document.querySelectorAll("#suggestions .suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      showSuggestions(false);
      sendMessage(button.innerText);
    });
  });
  showSuggestions(true);

  // Modal functionality
  infoButton.addEventListener("click", function () {
    modal.style.display = "block";
  });

  closeModal.addEventListener("click", function () {
    modal.style.display = "none";
  });

  window.addEventListener("click", function (event) {
    if (event.target === modal) {
      modal.style.display = "none";
    }
  });
  
  // New chat button functionality
  newChatButton.addEventListener("click", function() {
    // Clear chat messages
    const chatMessages = document.getElementById("chat-messages");
    chatMessages.innerHTML = "";
    
    // Generate a new chat ID
    window.chatId = crypto.randomUUID();
    resetDebug();
    showSuggestions(true);
    
    // Reset the input field with the default question
    userInput.value = "How does open science reshape the future of interdisciplinary and collaborative research?";
    
  });
});

function showSuggestions(show) {
  const box = document.getElementById("suggestions");
  if (!box) return;
  const buttons = [...box.querySelectorAll(".suggestion")];
  buttons.sort(() => Math.random() - 0.5).forEach((b, i) => { b.hidden = i >= 4; });
  box.hidden = !show || document.getElementById("chat-messages").children.length > 0;
}

// Initialize chatId as a global variable
window.chatId = crypto.randomUUID();
