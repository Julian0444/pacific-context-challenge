// app.js — QueryTrace Context Policy Lab

const API_BASE = "http://localhost:8000";
const DEFAULT_TOP_K = 8;

// ── Policy metadata (label, description, CSS variant) ──

const POLICY_META = {
  naive_top_k: {
    label: "NAIVE",
    desc: "raw retrieval · no filters",
    variant: "naive",
  },
  permission_aware: {
    label: "RBAC",
    desc: "role-based access control · budget enforced",
    variant: "rbac",
  },
  full_policy: {
    label: "FULL",
    desc: "rbac · freshness · budget",
    variant: "full",
  },
};

// Canonical display order for compare columns
const COMPARE_ORDER = ["naive_top_k", "permission_aware", "full_policy"];

// ── DOM references ──

const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const resultsSection = document.getElementById("results-section");
const compareSection = document.getElementById("compare-section");
const compareGrid = document.getElementById("compare-grid");
const compareBannerText = document.getElementById("compare-banner-text");
const mainEl = document.getElementById("main");
const singlePolicySelector = document.getElementById("single-policy-selector");
const evalsSection = document.getElementById("evals-section");
const evalsContent = document.getElementById("evals-content");

// ── Mode state ──

let currentMode = "single"; // "single" | "compare" | "evals"
let evalsLoaded = false;

// ── Mode toggle ──

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    switchMode(btn.dataset.mode);
  });
});

function switchMode(mode) {
  if (mode === currentMode) return;
  currentMode = mode;

  document.querySelectorAll(".mode-btn").forEach((b) => {
    const active = b.dataset.mode === mode;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", active);
  });

  const isCompare = mode === "compare";
  const isEvals = mode === "evals";

  singlePolicySelector.hidden = isCompare || isEvals;
  resultsSection.hidden = isCompare || isEvals;
  compareSection.hidden = !isCompare;
  evalsSection.hidden = !isEvals;
  mainEl.classList.toggle("compare-mode", isCompare);

  // Hide query form in evals mode — it's not relevant
  document.querySelector(".search-section").hidden = isEvals;

  // Auto-fetch evals on first switch
  if (isEvals && !evalsLoaded) {
    runEvals();
  }
}

// ── Form submission ──

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) return;

  const role = document.querySelector('input[name="role"]:checked').value;

  if (currentMode === "compare") {
    await runCompare(query, role);
  } else {
    const policy =
      document.querySelector('input[name="policy"]:checked')?.value ||
      "full_policy";
    await runSingleQuery(query, role, policy);
  }
});

// ── Example / scenario buttons ──

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const query = btn.dataset.query;
    const role = btn.dataset.role;
    const targetMode = btn.dataset.mode;

    input.value = query;

    const roleRadio = document.querySelector(
      `input[name="role"][value="${role}"]`
    );
    if (roleRadio) roleRadio.checked = true;

    if (targetMode && targetMode !== currentMode) {
      switchMode(targetMode);
    }

    if (currentMode === "compare") {
      runCompare(query, role);
    } else {
      const policy =
        document.querySelector('input[name="policy"]:checked')?.value ||
        "full_policy";
      runSingleQuery(query, role, policy);
    }
  });
});

// ── Single-policy query ──

async function runSingleQuery(query, role, policy = "full_policy") {
  setLoadingSingle(true);
  try {
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        role,
        top_k: DEFAULT_TOP_K,
        policy_name: policy,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }

    const data = await res.json();
    renderSingleResult(data, role, policy);
  } catch (err) {
    renderError(err, resultsSection);
  } finally {
    setLoadingSingle(false);
  }
}

// ── Compare query ──

async function runCompare(query, role) {
  setLoadingCompare(true);
  try {
    const res = await fetch(`${API_BASE}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, role, top_k: DEFAULT_TOP_K }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }

    const data = await res.json();
    renderCompare(data);
  } catch (err) {
    renderError(err, compareGrid);
    compareBannerText.innerHTML = "Compare failed";
  } finally {
    setLoadingCompare(false);
  }
}

// ── Loading states ──

function setLoadingSingle(on) {
  submitBtn.disabled = on;
  submitBtn.classList.toggle("loading", on);
  if (on) {
    document.getElementById("empty-state")?.remove();
    resultsSection.innerHTML = skeletonSingleHTML();
  }
}

function setLoadingCompare(on) {
  submitBtn.disabled = on;
  submitBtn.classList.toggle("loading", on);
  if (on) {
    compareGrid.innerHTML = skeletonCompareHTML();
    compareBannerText.innerHTML = "Running comparison…";
  }
}

function skeletonSingleHTML() {
  return Array.from({ length: 3 }, () => `
    <div class="skeleton-card">
      <div class="skeleton-line short"></div>
      <div class="skeleton-line long"></div>
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line tiny"></div>
    </div>
  `).join("");
}

function skeletonCompareHTML() {
  return `
    <div class="compare-skeleton">
      ${["naive", "rbac", "full"]
        .map(
          () => `
        <div class="compare-skeleton-col">
          <div class="compare-skeleton-header"></div>
          <div class="compare-skeleton-stats"></div>
          <div class="compare-skeleton-body">
            <div class="skeleton-line short"></div>
            <div class="skeleton-line medium"></div>
            <div class="skeleton-line long"></div>
            <div class="skeleton-line tiny"></div>
          </div>
        </div>`
        )
        .join("")}
    </div>`;
}

// ── Render: single-policy result ──

function renderSingleResult(data, role, policy) {
  if (!data.context || data.context.length === 0) {
    resultsSection.innerHTML = `
      <div class="no-results">
        <p class="no-results-text">No documents matched your query for this access level and policy.</p>
      </div>`;
    return;
  }

  const meta = POLICY_META[policy] || { label: policy, variant: "full" };
  const trace = data.decision_trace;
  const metrics = trace?.metrics;

  const summaryHTML = `
    <div class="summary-bar">
      <div class="summary-stat">
        <span class="stat-value">${data.context.length}</span>
        <span class="stat-label">${data.context.length === 1 ? "doc" : "docs"}</span>
      </div>
      <span class="summary-divider"></span>
      <div class="summary-stat">
        <span class="stat-value">${data.total_tokens.toLocaleString()}</span>
        <span class="stat-label">tokens</span>
      </div>
      <span class="summary-divider"></span>
      <div class="summary-stat role-stat">
        <span class="stat-value">${escapeHTML(role)}</span>
        <span class="stat-label">role</span>
      </div>
      <span class="summary-divider"></span>
      <div class="summary-stat policy-stat-${meta.variant}">
        <span class="stat-value">${escapeHTML(meta.label)}</span>
        <span class="stat-label">policy</span>
      </div>
      ${metrics ? `
        <span class="summary-divider"></span>
        <div class="summary-stat">
          <span class="stat-value">${metrics.blocked_count}</span>
          <span class="stat-label">blocked</span>
        </div>
        <span class="summary-divider"></span>
        <div class="summary-stat">
          <span class="stat-value">${metrics.stale_count}</span>
          <span class="stat-label">stale</span>
        </div>
      ` : ""}
    </div>`;

  const cardsHTML = data.context
    .map((chunk, i) => singleCardHTML(chunk, i))
    .join("");

  const traceHTML = trace
    ? buildTracePanelHTML(trace, false)
    : "";

  resultsSection.innerHTML = summaryHTML + cardsHTML + traceHTML;

  // Wire trace toggles
  wireTraceToggles(resultsSection);
}

// ── Render: single result card ──

function singleCardHTML(chunk, index) {
  const score = chunk.score ?? 0;
  const freshness = chunk.freshness_score ?? 0;
  const scorePct = Math.round(score * 100);
  const freshPct = Math.round(freshness * 100);

  const accentColor =
    score > 0.6
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

// ── Render: compare view ──

function renderCompare(data) {
  compareBannerText.innerHTML = `Policy comparison — <strong>${escapeHTML(data.role)}</strong> role`;

  // Build cross-policy highlights: which doc_ids are blocked or dropped in full_policy?
  const fullResult = data.results["full_policy"];
  const blockedInFull = new Set(
    (fullResult?.decision_trace?.blocked_by_permission || []).map((b) => b.doc_id)
  );

  const columns = COMPARE_ORDER.filter((p) => data.results[p]);

  compareGrid.innerHTML = columns
    .map((policyName, colIdx) =>
      buildCompareColumnHTML(policyName, data.results[policyName], { blockedInFull }, colIdx)
    )
    .join("");

  // Wire all trace toggles in the compare grid
  wireTraceToggles(compareGrid);
}

// ── Build compare column HTML ──

function buildCompareColumnHTML(policyName, result, highlights, colIdx) {
  const meta = POLICY_META[policyName] || {
    label: policyName.toUpperCase(),
    desc: "",
    variant: "full",
  };
  const trace = result.decision_trace;
  const metrics = trace?.metrics;

  // Stats cells
  const blockedVal = metrics?.blocked_count ?? 0;
  const staleVal = metrics?.stale_count ?? 0;
  const droppedVal = metrics?.dropped_count ?? 0;
  const ttftMs = trace ? Math.round(trace.ttft_proxy_ms) : "—";

  const statsHTML = `
    <div class="col-stats">
      <div class="col-stat">
        <span class="col-stat-val">${result.context.length}</span>
        <span class="col-stat-lbl">included</span>
      </div>
      <div class="col-stat">
        <span class="col-stat-val">${result.total_tokens.toLocaleString()}</span>
        <span class="col-stat-lbl">tokens</span>
      </div>
      <div class="col-stat stat-blocked">
        <span class="col-stat-val${blockedVal === 0 ? " zero" : ""}">${blockedVal}</span>
        <span class="col-stat-lbl">blocked</span>
      </div>
      <div class="col-stat stat-stale">
        <span class="col-stat-val${staleVal === 0 ? " zero" : ""}">${staleVal}</span>
        <span class="col-stat-lbl">stale</span>
      </div>
      <div class="col-stat stat-dropped">
        <span class="col-stat-val${droppedVal === 0 ? " zero" : ""}">${droppedVal}</span>
        <span class="col-stat-lbl">dropped</span>
      </div>
      <div class="col-stat">
        <span class="col-stat-val">${ttftMs}ms</span>
        <span class="col-stat-lbl">ttft</span>
      </div>
    </div>`;

  // Document cards
  const docsHTML =
    result.context.length > 0
      ? result.context
          .map((doc, i) => {
            const wouldBeBlocked =
              policyName === "naive_top_k" &&
              highlights.blockedInFull.has(doc.doc_id);
            return buildCompareCardHTML(doc, i, wouldBeBlocked);
          })
          .join("")
      : `<div class="col-empty">No documents included</div>`;

  // Trace panel — starts open in compare mode so the comparison is immediately visible
  const traceHTML = trace
    ? `<div class="col-trace">${buildTracePanelHTML(trace, true)}</div>`
    : "";

  return `
    <div class="compare-col" data-policy="${escapeHTML(policyName)}" style="animation-delay: ${colIdx * 60}ms">
      <div class="col-header col-header-${meta.variant}">
        <span class="col-badge col-badge-${meta.variant}">${escapeHTML(meta.label)}</span>
        <div class="col-policy-info">
          <span class="col-policy-name">${escapeHTML(policyName)}</span>
          <span class="col-policy-desc">${escapeHTML(meta.desc)}</span>
        </div>
      </div>
      ${statsHTML}
      <div class="col-docs">${docsHTML}</div>
      ${traceHTML}
    </div>`;
}

// ── Build compact compare card ──

function buildCompareCardHTML(doc, index, wouldBeBlocked) {
  const score = doc.score ?? 0;
  const freshness = doc.freshness_score ?? 0;
  const scorePct = Math.min(100, Math.round(score * 100));
  const freshPct = Math.min(100, Math.round(freshness * 100));

  const accentColor =
    score > 0.6
      ? "var(--score-high)"
      : score > 0.35
      ? "var(--score-mid)"
      : "var(--score-low)";

  const flagHTML = wouldBeBlocked
    ? `<span class="doc-flag flag-blocked" title="Blocked in full_policy for this role">blocked in full</span>`
    : "";

  const contentSnippet = escapeHTML((doc.content || "").slice(0, 160));

  return `
    <article class="compare-card" style="--card-accent: ${accentColor}; animation-delay: ${index * 35}ms">
      <div class="compare-card-header">
        <span class="compare-card-id">${escapeHTML(doc.doc_id)}</span>
        ${flagHTML}
      </div>
      <p class="compare-card-content">${contentSnippet}</p>
      <div class="compare-card-scores">
        <div class="mini-metric">
          <span class="mini-bar-wrap">
            <span class="mini-bar" style="width: ${scorePct}%; background: var(--score-high)"></span>
          </span>
          <span class="mini-val">${score.toFixed(2)}</span>
        </div>
        <div class="mini-metric">
          <span class="mini-bar-wrap">
            <span class="mini-bar" style="width: ${freshPct}%; background: var(--fresh-high)"></span>
          </span>
          <span class="mini-val">${freshness.toFixed(2)}</span>
        </div>
      </div>
    </article>`;
}

// ── Evals dashboard ──

async function runEvals() {
  evalsContent.innerHTML = skeletonEvalsHTML();
  try {
    const res = await fetch(`${API_BASE}/evals`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }
    const data = await res.json();
    evalsLoaded = true;
    renderEvals(data);
  } catch (err) {
    renderError(err, evalsContent);
  }
}

function skeletonEvalsHTML() {
  return `
    <div class="evals-loading">
      <div class="evals-loading-spinner"></div>
      <p class="evals-loading-text">Running 8 pipeline queries…</p>
    </div>`;
}

function renderEvals(data) {
  const agg = data.aggregate;
  const queries = data.per_query;

  const cards = [
    { label: "Precision@5", value: (agg.avg_precision_at_5 ?? 0).toFixed(4), color: "var(--accent)" },
    { label: "Recall", value: (agg.avg_recall ?? 0).toFixed(4), color: "var(--score-high)" },
    { label: "Permission Violations", value: fmtPct(agg.permission_violation_rate ?? 0), color: agg.permission_violation_rate > 0 ? "var(--trace-blocked)" : "var(--score-high)" },
    { label: "Avg Context Docs", value: (agg.avg_context_docs ?? 0).toFixed(1), color: "var(--text-secondary)" },
    { label: "Avg Total Tokens", value: (agg.avg_total_tokens ?? 0).toFixed(0), color: "var(--text-secondary)" },
    { label: "Avg Freshness", value: (agg.avg_freshness_score ?? 0).toFixed(4), color: "var(--fresh-high)" },
    { label: "Avg Blocked", value: (agg.avg_blocked_count ?? 0).toFixed(1), color: "var(--trace-blocked)" },
    { label: "Avg Stale", value: (agg.avg_stale_count ?? 0).toFixed(1), color: "var(--trace-stale)" },
    { label: "Avg Dropped", value: (agg.avg_dropped_count ?? 0).toFixed(1), color: "var(--trace-dropped)" },
    { label: "Avg Budget Util", value: fmtPct(agg.avg_budget_utilization ?? 0), color: "var(--accent)" },
  ];

  const cardsHTML = cards
    .map(
      (c, i) => `
      <div class="metric-card" style="animation-delay: ${i * 40}ms">
        <span class="metric-card-label">${escapeHTML(c.label)}</span>
        <span class="metric-card-value" style="color: ${c.color}">${escapeHTML(c.value)}</span>
      </div>`
    )
    .join("");

  const headerRow = `
    <tr>
      <th>Query</th>
      <th>Role</th>
      <th>P@5</th>
      <th>Recall</th>
      <th>Docs</th>
      <th>Tokens</th>
      <th>Freshness</th>
      <th>Blocked</th>
      <th>Stale</th>
      <th>Dropped</th>
      <th>Budget</th>
      <th>Violations</th>
    </tr>`;

  const bodyRows = queries
    .map((q) => {
      if (q.error) {
        return `<tr class="evals-row-error"><td>${escapeHTML(q.id)}</td><td colspan="11" class="evals-error-cell">${escapeHTML(q.error)}</td></tr>`;
      }
      const hasViolation = q.permission_violations && q.permission_violations.length > 0;
      return `
        <tr class="${hasViolation ? "evals-row-violation" : ""}">
          <td class="evals-id-cell">${escapeHTML(q.id)}</td>
          <td><span class="evals-role-chip">${escapeHTML(q.role)}</span></td>
          <td class="mono-cell">${(q.precision_at_5 ?? 0).toFixed(2)}</td>
          <td class="mono-cell">${(q.recall ?? 0).toFixed(2)}</td>
          <td class="mono-cell">${q.context_docs ?? 0}</td>
          <td class="mono-cell">${q.total_tokens ?? 0}</td>
          <td class="mono-cell">${(q.avg_freshness_score ?? 0).toFixed(3)}</td>
          <td class="mono-cell${q.blocked_count > 0 ? " val-blocked" : ""}">${q.blocked_count ?? 0}</td>
          <td class="mono-cell${q.stale_count > 0 ? " val-stale" : ""}">${q.stale_count ?? 0}</td>
          <td class="mono-cell${q.dropped_count > 0 ? " val-dropped" : ""}">${q.dropped_count ?? 0}</td>
          <td class="mono-cell">${fmtPct(q.budget_utilization ?? 0)}</td>
          <td class="mono-cell${hasViolation ? " val-violation" : " val-ok"}">${hasViolation ? q.permission_violations.join(", ") : "none"}</td>
        </tr>`;
    })
    .join("");

  evalsContent.innerHTML = `
    <div class="metrics-grid">${cardsHTML}</div>
    <div class="evals-table-wrap">
      <table class="evals-table">
        <thead>${headerRow}</thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    <p class="evals-footer">Queries run: ${agg.queries_run ?? 0} · Failed: ${agg.queries_failed ?? 0}</p>`;
}

function fmtPct(v) {
  return (v * 100).toFixed(1) + "%";
}

// ── Build Decision Trace panel HTML ──

function buildTracePanelHTML(trace, startOpen) {
  const m = trace.metrics || {};
  const budgetPct = Math.min(100, Math.round((m.budget_utilization ?? 0) * 100));

  const includedChips = (trace.included || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-included" title="score: ${d.score.toFixed(2)} · ${d.token_count} tokens">${escapeHTML(d.doc_id)}</span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const blockedChips = (trace.blocked_by_permission || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-blocked" title="requires: ${d.required_role}">${escapeHTML(d.doc_id)}<em> ·${d.required_role}</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const staleChips = (trace.demoted_as_stale || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-stale" title="superseded by: ${d.superseded_by} · penalty: ${d.penalty_applied}×">${escapeHTML(d.doc_id)}<em> →${d.superseded_by}</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const droppedChips = (trace.dropped_by_budget || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-dropped" title="${d.token_count} tokens · score: ${d.score.toFixed(2)}">${escapeHTML(d.doc_id)}<em> ·${d.token_count}t</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const blockedCount = m.blocked_count ?? 0;
  const staleCount = m.stale_count ?? 0;
  const droppedCount = m.dropped_count ?? 0;
  const toggleSummary = `${blockedCount} blocked · ${staleCount} stale · ${droppedCount} dropped`;

  return `
    <div class="trace-panel${startOpen ? " open" : ""}">
      <button class="trace-toggle" aria-expanded="${startOpen}">
        <span class="trace-toggle-label">Decision Trace</span>
        <span class="trace-toggle-summary">${escapeHTML(toggleSummary)}</span>
        <span class="trace-caret" aria-hidden="true">▾</span>
      </button>
      <div class="trace-body">
        <div class="trace-row">
          <div class="trace-section">
            <span class="trace-section-label trace-label-included">✓ Included</span>
            <div class="trace-chips">${includedChips}</div>
          </div>
          <div class="trace-section">
            <span class="trace-section-label trace-label-blocked">🔒 Blocked</span>
            <div class="trace-chips">${blockedChips}</div>
          </div>
        </div>
        <div class="trace-row">
          <div class="trace-section">
            <span class="trace-section-label trace-label-stale">⏱ Stale</span>
            <div class="trace-chips">${staleChips}</div>
          </div>
          <div class="trace-section">
            <span class="trace-section-label trace-label-dropped">✂ Dropped</span>
            <div class="trace-chips">${droppedChips}</div>
          </div>
        </div>
        <div class="trace-metrics-strip">
          <div class="budget-row">
            <span class="budget-label">Budget</span>
            <div class="budget-bar-wrap">
              <div class="budget-bar-fill" style="width: ${budgetPct}%"></div>
            </div>
            <span class="budget-pct">${budgetPct}%</span>
          </div>
          <div class="trace-numbers">
            <span>avg score <strong>${(m.avg_score ?? 0).toFixed(2)}</strong></span>
            <span>avg freshness <strong>${(m.avg_freshness_score ?? 0).toFixed(2)}</strong></span>
            <span>ttft <strong>${Math.round(trace.ttft_proxy_ms ?? 0)}ms</strong></span>
          </div>
        </div>
      </div>
    </div>`;
}

// ── Wire trace toggle expand/collapse ──

function wireTraceToggles(container) {
  container.querySelectorAll(".trace-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = btn.closest(".trace-panel");
      const isOpen = panel.classList.toggle("open");
      btn.setAttribute("aria-expanded", isOpen);
    });
  });
}

// ── Error state ──

function renderError(err, container) {
  const isNetwork =
    err.message === "Failed to fetch" ||
    err.message.includes("NetworkError");
  const title = isNetwork ? "Backend unavailable" : "Query failed";
  const detail = isNetwork
    ? "Start the server: uvicorn src.main:app --reload"
    : err.message;

  container.innerHTML = `
    <div class="error-state">
      <div class="error-icon">!</div>
      <p class="error-title">${escapeHTML(title)}</p>
      <p class="error-detail">${escapeHTML(detail)}</p>
    </div>`;
}

// ── Utility ──

function escapeHTML(str) {
  const el = document.createElement("span");
  el.textContent = String(str ?? "");
  return el.innerHTML;
}
