// Two DOMPurify cleaners, same tag allowlist as the server (just_os/sanitize.py):
// - sanitizeAnswer: final answers the server built and sanitized; keeps the citation links'
//   class and data-reference so the tooltips work.
// - sanitizeDraft: anything the model wrote (the streaming draft) or that is only read as text;
//   no class and no data-reference, so model markup cannot pose as a citation link.
import DOMPurify from "dompurify";
import { marked } from "marked";

const ALLOWED_TAGS = [
  "p", "br", "strong", "em", "b", "i", "code", "pre", "ul", "ol", "li", "blockquote",
  "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td",
  "hr", "span", "a", "sup", "sub",
];
// Links: http(s), mailto and "#" (reference links) only. DOMPurify checks every attribute value
// against this pattern unless it is marked URI-safe, so the JSON and numbers are exempted.
const ALLOWED_URI_REGEXP = /^(?:https?:|mailto:|#)/i;

const ANSWER_CONFIG = {
  ALLOWED_TAGS,
  ALLOWED_ATTR: ["href", "title", "class", "data-reference", "colspan", "rowspan", "start"],
  ALLOW_DATA_ATTR: false,
  ALLOWED_URI_REGEXP,
  ADD_URI_SAFE_ATTR: ["data-reference", "colspan", "rowspan", "start"],
};

const DRAFT_CONFIG = {
  ALLOWED_TAGS,
  ALLOWED_ATTR: ["href", "title", "colspan", "rowspan", "start"],
  FORBID_ATTR: ["class", "data-reference"],
  ALLOW_DATA_ATTR: false,
  ALLOWED_URI_REGEXP,
  ADD_URI_SAFE_ATTR: ["colspan", "rowspan", "start"],
};

export function sanitizeAnswer(html) {
  return DOMPurify.sanitize(String(html ?? ""), ANSWER_CONFIG);
}

export function sanitizeDraft(html) {
  return DOMPurify.sanitize(String(html ?? ""), DRAFT_CONFIG);
}

// The draft answer while it streams (#41): Markdown from the model
export function markdownToHtml(text) {
  return sanitizeDraft(marked.parse(String(text ?? "")));
}

// Plain text of an HTML message, without ever running it
export function htmlToText(html) {
  const box = document.createElement("div");
  box.innerHTML = sanitizeDraft(html);
  return box.textContent;
}
