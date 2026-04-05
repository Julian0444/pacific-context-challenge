// app.js — QueryTrace frontend logic
// Sends queries to the FastAPI backend and renders retrieved context chunks.

const API_BASE = "http://localhost:8000";

document.getElementById("query-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const query = document.getElementById("query-input").value.trim();
  const role = document.getElementById("role-select").value;
  const resultsEl = document.getElementById("results");

  if (!query) return;

  resultsEl.innerHTML = "<p>Loading...</p>";

  // TODO: call POST /query and render results
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, role, top_k: 5 }),
    });
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    resultsEl.innerHTML = `<p class="error">Error: ${err.message}</p>`;
  }
});

function renderResults(data) {
  const resultsEl = document.getElementById("results");
  if (!data.context || data.context.length === 0) {
    resultsEl.innerHTML = "<p>No results found.</p>";
    return;
  }

  resultsEl.innerHTML = data.context
    .map(
      (chunk) => `
    <div class="chunk">
      <div class="chunk-meta">
        <span class="doc-id">${chunk.doc_id}</span>
        <span class="score">score: ${chunk.score.toFixed(3)}</span>
      </div>
      <p class="chunk-content">${chunk.content}</p>
    </div>`
    )
    .join("");
}
