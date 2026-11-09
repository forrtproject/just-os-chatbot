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

      tooltip.innerHTML = `
                <div class="title">${data.title}</div>
                <div class="metadata">${data.authors} (${data.year})</div>
                <div class="content">${data.text}</div>
                ${
                  data.url
                    ? `<a href="${data.url}" target="_blank" class="source-link">View source →</a>`
                    : ""
                }
            `;

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
