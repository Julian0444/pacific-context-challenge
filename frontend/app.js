// app.js — QueryTrace frontend

const API_BASE = "http://localhost:8000";
const DEFAULT_TOP_K = 8;

const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const resultsSection = document.getElementById("results-section");
const emptyState = document.getElementById("empty-state");

// ── Form submission ──

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) return;

  const role = document.querySelector('input[name="role"]:checked').value;
  await runQuery(query, role);
});

// ── Example query buttons ──

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const query = btn.dataset.query;
    const role = btn.dataset.role;

    input.value = query;
    const radio = document.querySelector(`input[name="role"][value="${role}"]`);
    if (radio) radio.checked = true;

    runQuery(query, role);
  });
});

// ── Core query function ──

async function runQuery(query, role) {
  setLoading(true);

  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, role, top_k: DEFAULT_TOP_K }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }

    const data = await res.json();
    renderResults(data, role);
  } catch (err) {
    renderError(err);
  } finally {
    setLoading(false);
  }
}

// ── Loading state ──

function setLoading(on) {
  submitBtn.disabled = on;
  submitBtn.classList.toggle("loading", on);

  if (on) {
    emptyState?.remove();
    resultsSection.innerHTML = skeletonHTML();
  }
}

function skeletonHTML() {
  return Array.from({ length: 3 }, () => `
    <div class="skeleton-card">
      <div class="skeleton-line short"></div>
      <div class="skeleton-line long"></div>
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line tiny"></div>
    </div>
  `).join("");
}

// ── Render results ──

function renderResults(data, role) {
  if (!data.context || data.context.length === 0) {
    resultsSection.innerHTML = `
      <div class="no-results">
        <p class="no-results-text">No documents matched your query for this access level.</p>
      </div>`;
    return;
  }

  const summaryHTML = `
    <div class="summary-bar">
      <div class="summary-stat">
        <span class="stat-value">${data.context.length}</span>
        <span class="stat-label">${data.context.length === 1 ? "document" : "documents"}</span>
      </div>
      <span class="summary-divider"></span>
      <div class="summary-stat">
        <span class="stat-value">${data.total_tokens.toLocaleString()}</span>
        <span class="stat-label">tokens</span>
      </div>
      <span class="summary-divider"></span>
      <div class="summary-stat role-stat">
        <span class="stat-value">${role}</span>
        <span class="stat-label">access</span>
      </div>
    </div>`;

  const cardsHTML = data.context
    .map((chunk, i) => cardHTML(chunk, i))
    .join("");

  resultsSection.innerHTML = summaryHTML + cardsHTML;
}

function cardHTML(chunk, index) {
  const score = chunk.score ?? 0;
  const freshness = chunk.freshness_score ?? 0;
  const scorePct = Math.round(score * 100);
  const freshPct = Math.round(freshness * 100);

  const accentColor = score > 0.6
    ? "var(--score-high)"
    : score > 0.35
      ? "var(--score-mid)"
      : "var(--score-low)";

  const tagsHTML = (chunk.tags || [])
    .map((t) => `<span class="tag">${escapeHTML(t)}</span>`)
    .join("");

  const contentPreview = escapeHTML(chunk.content || "").slice(0, 480);

  return `
    <article class="result-card" style="--card-accent: ${accentColor}; animation-delay: ${index * 50}ms">
      <div class="card-header">
        <span class="card-doc-id">${escapeHTML(chunk.doc_id)}</span>
        <span class="card-rank">#${index + 1}</span>
      </div>
      <p class="card-content">${contentPreview}</p>
      <div class="card-metrics">
        <div class="metric">
          <div class="metric-label">Relevance</div>
          <div class="metric-bar-container">
            <div class="metric-bar">
              <div class="metric-bar-fill relevance" style="width: ${scorePct}%"></div>
            </div>
            <span class="metric-value">${score.toFixed(2)}</span>
          </div>
        </div>
        <div class="metric">
          <div class="metric-label">Freshness</div>
          <div class="metric-bar-container">
            <div class="metric-bar">
              <div class="metric-bar-fill freshness" style="width: ${freshPct}%"></div>
            </div>
            <span class="metric-value">${freshness.toFixed(2)}</span>
          </div>
        </div>
      </div>
      ${tagsHTML ? `<div class="card-tags">${tagsHTML}</div>` : ""}
    </article>`;
}

// ── Error state ──

function renderError(err) {
  const isNetwork = err.message === "Failed to fetch" || err.message.includes("NetworkError");
  const title = isNetwork
    ? "Backend unavailable"
    : "Query failed";
  const detail = isNetwork
    ? "Start the server with: uvicorn src.main:app --reload"
    : err.message;

  resultsSection.innerHTML = `
    <div class="error-state">
      <div class="error-icon">!</div>
      <p class="error-title">${escapeHTML(title)}</p>
      <p class="error-detail">${escapeHTML(detail)}</p>
    </div>`;
}

// ── Utility ──

function escapeHTML(str) {
  const el = document.createElement("span");
  el.textContent = str;
  return el.innerHTML;
}
