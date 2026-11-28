// Answers arrive as HTML that the server has already sanitized (just_os/sanitize.py); DOMPurify
// cleans them again before they reach innerHTML. Same allowlist as the server, plus the
// reference links' class and data-reference so the tooltips keep working.
import DOMPurify from "dompurify";
import { marked } from "marked";

const CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "strong", "em", "b", "i", "code", "pre", "ul", "ol", "li", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td",
    "hr", "span", "a", "sup", "sub",
  ],
  ALLOWED_ATTR: ["href", "title", "class", "data-reference", "colspan", "rowspan", "start"],
  ALLOW_DATA_ATTR: false,
  // Links: http(s), mailto and "#" (reference links) only. DOMPurify checks every attribute value
  // against this pattern unless it is marked URI-safe, so the JSON and numbers are exempted here.
  ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|#)/i,
  ADD_URI_SAFE_ATTR: ["data-reference", "colspan", "rowspan", "start"],
};

export function sanitizeHtml(html) {
  return DOMPurify.sanitize(String(html ?? ""), CONFIG);
}

// The draft answer while it streams (#41): Markdown from the model
export function markdownToHtml(text) {
  return sanitizeHtml(marked.parse(String(text ?? "")));
}

// Plain text of an HTML message, without ever running it
export function htmlToText(html) {
  const box = document.createElement("div");
  box.innerHTML = sanitizeHtml(html);
  return box.textContent;
}
