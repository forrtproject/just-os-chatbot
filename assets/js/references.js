// Shared by app.js (chat) and arena.js (arena).
export function setupReferenceHandlers() {
  document.querySelectorAll(".reference-link").forEach((link) => {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      // Remove any existing tooltips
      document
        .querySelectorAll(".reference-tooltip")
        .forEach((t) => t.remove());

      // Create tooltip
      const tooltip = document.createElement("div");
      tooltip.className = "reference-tooltip";

      const data = JSON.parse(this.getAttribute("data-reference"));

      // Metadata comes from a public form: insert it as text, never as HTML
      const add = (tag, className, text) => {
        const el = document.createElement(tag);
        el.className = className;
        el.textContent = text;
        tooltip.appendChild(el);
        return el;
      };
      add("div", "title", data.title);
      add("div", "metadata", `${data.authors} (${data.year})`);
      if (data.unverified) {
        add("div", "unverified", "Not verified: the citation check did not find this claim in the passage.");
      }
      add(
        "div",
        "content",
        data.text || "The licence of this source does not allow showing the passage."
      );
      if (/^https?:\/\//i.test(data.url || "")) {
        const a = add("a", "source-link", "View source →");
        a.href = data.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      }

      // Position tooltip near the click
      const rect = this.getBoundingClientRect();
      const tooltipX = Math.min(
        rect.left,
        window.innerWidth - 520 // account for tooltip width + margin
      );

      tooltip.style.left = `${tooltipX}px`;
      tooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;

      // Add tooltip to document
      document.body.appendChild(tooltip);

      // Adjust position if tooltip goes off-screen
      const tooltipRect = tooltip.getBoundingClientRect();
      if (tooltipRect.right > window.innerWidth) {
        tooltip.style.left = `${window.innerWidth - tooltipRect.width - 20}px`;
      }
      if (tooltipRect.bottom > window.innerHeight) {
        tooltip.style.top = `${
          rect.top + window.scrollY - tooltipRect.height - 5
        }px`;
      }

      // Close tooltip when clicking outside
      function closeTooltip(e) {
        if (!tooltip.contains(e.target) && e.target !== link) {
          tooltip.remove();
          document.removeEventListener("click", closeTooltip);
        }
      }

      // Add delay before adding click listener to prevent immediate closing
      setTimeout(() => {
        document.addEventListener("click", closeTooltip);
      }, 0);
    });
  });
}

// Numbered source list from response.references (all text inserted with textContent).
// Falls back to the plain text list for old responses.
export function renderSources(references, fallbackText = "") {
  const box = document.createElement("div");
  box.className = "sources";
  if (!references || !references.length) {
    box.textContent = fallbackText || "";
    return box;
  }
  const heading = document.createElement("div");
  heading.className = "sources-heading";
  heading.textContent = "Sources";
  const list = document.createElement("ol");
  list.className = "source-list";
  for (const ref of references) {
    const item = document.createElement("li");
    item.value = ref.number;
    const span = (className, text) => {
      const el = document.createElement("span");
      el.className = className;
      el.textContent = text;
      return el;
    };
    // forrt.org pages have no authors or year: title and link only
    if (ref.authors || ref.year) {
      item.append(span("source-authors", ref.authors_short || ref.authors || "Unknown author"), ` (${ref.year}). `);
    }
    item.append(span("source-title", ref.title || "Untitled"));
    if (/^https?:\/\//i.test(ref.url || "")) {
      const link = document.createElement("a");
      link.href = ref.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "source-link";
      link.textContent = ref.url.replace(/^https?:\/\/(www\.)?/i, "");
      if (ref.authors_short !== ref.authors) link.title = ref.authors;
      item.append(" ", link);
    }
    if (ref.unverified) item.append(" ", span("source-unverified", "not verified"));
    // The sentence of the source that the answer used (only for open licences)
    if (ref.snippet) {
      const quote = document.createElement("blockquote");
      quote.className = "source-snippet";
      quote.textContent = `“${ref.snippet}”`;
      item.append(quote);
    }
    list.appendChild(item);
  }
  box.append(heading, list);
  return box;
}
