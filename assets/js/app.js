import { renderSources, setupReferenceHandlers } from "./references.js";

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
  const plain = text.replace(/\s*\[\d+\]/g, "");
  if (window.marked && window.DOMPurify) {
    draft.innerHTML = DOMPurify.sanitize(marked.parse(plain));
  } else {
    draft.textContent = plain;
  }
}

function removeDraft() {
  document.getElementById("draft-answer")?.remove();
}

function addMessage(message, sender, sources = null, turnId = null) {
  const chatMessages = document.getElementById("chat-messages");

  const messageDiv = document.createElement("div");
  messageDiv.classList.add("message", `${sender}-message`);

  if (sender === "bot") {
    messageDiv.innerHTML = message;
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
  if (turnId) {
    messageDiv.appendChild(feedbackBar(turnId));
  }

  chatMessages.appendChild(messageDiv);

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
}

async function sendMessage(message) {
  const chatMessages = document.getElementById("chat-messages");

  console.log("user message: " + message);
  if (message) {
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
    sendButton.style.display = "block";
    statusMessage.innerText = "";
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
        stream: true,
      }),
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let draft = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete messages
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const message = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);

        if (message) {
          // check for non-empty messages
          try {
            console.log("Received message:", message);
            const data = JSON.parse(message);

            if (data.status === "complete") {
              endStream();
              removeDraft();
              addMessage(data.message, "bot", data.metadata?.references, data.turn_id);
            } else if (data.status === "partial") {
              draft += data.delta;
              baseMessage = "Writing the answer";
              showDraft(draft);
            } else {
              removeDraft();
              baseMessage = data.message;
            }
          } catch (parseError) {
            console.warn("Failed to parse message:", parseError);
            // Add the failed message back to the buffer
            buffer = message + "\n" + buffer;
            break;
          }
        }
      }
    }

    // Process any remaining data in the buffer
    if (buffer.trim()) {
      try {
        console.log("Processing remaining buffer:", buffer);
        const data = JSON.parse(buffer);
        if (data.status === "complete") {
          endStream();
          removeDraft();
          addMessage(data.message, "bot", data.metadata?.references, data.turn_id);
        } else {
          baseMessage = data.message;
        }
      } catch (parseError) {
        console.warn("Failed to parse final buffer:", parseError);
      }
    }
  } catch (error) {
    console.error("Error:", error);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  // Add CSS for new elements
  const style = document.createElement('style');
  const userInput = document.getElementById("user-input");
  const sendButton = document.getElementById("send-button");
  const infoButton = document.getElementById("info-button");
  const newChatButton = document.getElementById("new-chat-button");
  const modal = document.getElementById("info-modal");
  const closeModal = document.querySelector(".close-modal");

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
    userInput.value = "";
    sendMessage(message);
  });

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
    
    // Reset the input field with the default question
    userInput.value = "How does open science reshape the future of interdisciplinary and collaborative research?";
    
  });
});

function requestBody(message) {
  return JSON.stringify({
    message: message,
    chatId: window.chatId,
  });
}

// Initialize chatId as a global variable
window.chatId = crypto.randomUUID();
