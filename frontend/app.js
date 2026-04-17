// app.js — QueryTrace Context Policy Lab

const API_BASE = "http://localhost:8000";
const DEFAULT_TOP_K = 8;

// ── Policy metadata (label, description, CSS variant) ──

const POLICY_META = {
  naive_top_k: {
    label: "No Filters",
    desc: "Raw retrieval — no permissions, no freshness, no budget. Dangerous baseline.",
    variant: "naive",
    skipFreshness: true,
  },
  permission_aware: {
    label: "Permissions Only",
    desc: "Role-based access control + token budget. No freshness scoring.",
    variant: "rbac",
    skipFreshness: true,
  },
  full_policy: {
    label: "Full Pipeline",
    desc: "Permissions + freshness + token budget. Production-grade.",
    variant: "full",
    skipFreshness: false,
  },
};

// Canonical display order for compare columns
const COMPARE_ORDER = ["naive_top_k", "permission_aware", "full_policy"];

// Raw excerpt storage for expand/collapse — keyed by card index, avoids data-attr innerHTML
const _cardExcerpts = new Map();

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

// ── Policy description + warning ──

function updatePolicyDescription(policy) {
  const descEl = document.getElementById("policy-description");
  const warningEl = document.getElementById("policy-warning");
  if (!descEl || !warningEl) return;
  const meta = POLICY_META[policy] || {};
  descEl.style.opacity = "0";
  setTimeout(() => {
    descEl.textContent = meta.desc || "";
    descEl.style.opacity = "1";
  }, 80);
  warningEl.hidden = policy !== "naive_top_k";
}

document.querySelectorAll('input[name="policy"]').forEach((radio) => {
  radio.addEventListener("change", () => updatePolicyDescription(radio.value));
});

// Initialize with the default checked policy
updatePolicyDescription(
  document.querySelector('input[name="policy"]:checked')?.value || "full_policy"
);

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

  // Build stale lookup keyed by doc_id — used as fallback when chunk.superseded_by is absent
  const staleMap = new Map(
    (trace?.demoted_as_stale || []).map((s) => [s.doc_id, s])
  );

  const cardsHTML = data.context
    .map((chunk, i) => singleCardHTML(chunk, i, policy, staleMap))
    .join("");

  const blockedSectionHTML = buildBlockedSectionHTML(
    trace?.blocked_by_permission || [],
    role
  );

  const traceHTML = trace
    ? buildTracePanelHTML(trace, false, role)
    : "";

  resultsSection.innerHTML = summaryHTML + cardsHTML + blockedSectionHTML + traceHTML;

  // Wire trace toggles, expand buttons, and blocked-section toggle
  wireTraceToggles(resultsSection);
  wireExpandButtons(resultsSection);
  wireBlockedSectionToggle(resultsSection);
}

// ── Render: single result card ──

function singleCardHTML(chunk, index, policy, staleMap = new Map()) {
  const score = chunk.score ?? 0;
  const freshness = chunk.freshness_score ?? 0;
  const scorePct = Math.round(score * 100);
  const freshPct = Math.round(freshness * 100);
  const skipFreshness = (POLICY_META[policy] || {}).skipFreshness === true;

  const accentColor =
    score > 0.6
      ? "var(--score-high)"
      : score > 0.35
      ? "var(--score-mid)"
      : "var(--score-low)";

  const tagsHTML = (chunk.tags || [])
    .map((t) => `<span class="tag">${escapeHTML(t)}</span>`)
    .join("");

  const title = chunk.title || chunk.doc_id;
  const docTypeLabel = formatDocType(chunk.doc_type);
  const dateLabel = formatDate(chunk.date);
  const metaParts = [
    `<span class="card-meta-badge">${escapeHTML(chunk.doc_id)}</span>`,
    docTypeLabel ? escapeHTML(docTypeLabel) : null,
    dateLabel ? escapeHTML(dateLabel) : null,
  ].filter(Boolean).join(" · ");

  // Staleness detection: prefer chunk.superseded_by (IDEA 2), fall back to trace staleMap
  const staleInfo = staleMap.get(chunk.doc_id);
  const supersededBy = chunk.superseded_by || staleInfo?.superseded_by || null;
  const isSuperseded = supersededBy != null;
  const penaltyLabel = staleInfo?.penalty_applied != null
    ? `${staleInfo.penalty_applied}×`
    : "0.5×";

  const staleHTML = isSuperseded ? `
    <div class="stale-badge">
      <span class="stale-icon">⚠</span>
      <span class="stale-text">Superseded by <strong>${escapeHTML(supersededBy)}</strong> — freshness penalized ${escapeHTML(penaltyLabel)}</span>
    </div>` : "";

  const rawShort = (chunk.content || "").slice(0, 200);
  const rawFull = chunk.content || "";
  const hasMore = rawFull.length > 200;
  _cardExcerpts.set(index, { short: rawShort, full: rawFull });

  const freshnessMetricHTML = skipFreshness
    ? `<div class="metric">
        <div class="metric-label">Freshness</div>
        <span class="metric-na">N/A — skipped by policy</span>
       </div>`
    : `<div class="metric">
        <div class="metric-label">Freshness</div>
        <div class="metric-bar-container">
          <div class="metric-bar">
            <div class="metric-bar-fill freshness" style="width: ${freshPct}%"></div>
          </div>
          <span class="metric-value">${freshness.toFixed(2)}</span>
        </div>
       </div>`;

  return `
    <article class="result-card" data-card-idx="${index}" style="--card-accent: ${accentColor}; animation-delay: ${index * 50}ms">
      <div class="card-header">
        <span class="card-title">${escapeHTML(title)}</span>
        <span class="card-rank">#${index + 1}</span>
      </div>
      <div class="card-meta">${metaParts}</div>
      ${staleHTML}
      <div class="card-content">
        <p class="card-content-text">${escapeHTML(rawShort)}</p>
      </div>
      ${hasMore ? `<button class="card-expand-btn" type="button">Show more ▾</button>` : ""}
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
        ${freshnessMetricHTML}
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
      buildCompareColumnHTML(policyName, data.results[policyName], { blockedInFull }, colIdx, data.role)
    )
    .join("");

  // Wire all trace toggles in the compare grid
  wireTraceToggles(compareGrid);
}

// ── Build compare column HTML ──

function buildCompareColumnHTML(policyName, result, highlights, colIdx, userRole) {
  const meta = POLICY_META[policyName] || {
    label: policyName.toUpperCase(),
    desc: "",
    variant: "unknown",
    skipFreshness: false,
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
            return buildCompareCardHTML(doc, i, wouldBeBlocked, policyName);
          })
          .join("")
      : `<div class="col-empty">No documents included</div>`;

  // Trace panel — starts open in compare mode so the comparison is immediately visible
  const traceHTML = trace
    ? `<div class="col-trace">${buildTracePanelHTML(trace, true, userRole)}</div>`
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

function buildCompareCardHTML(doc, index, wouldBeBlocked, policyName) {
  const score = doc.score ?? 0;
  const freshness = doc.freshness_score ?? 0;
  const scorePct = Math.min(100, Math.round(score * 100));
  const freshPct = Math.min(100, Math.round(freshness * 100));
  const skipFreshness = (POLICY_META[policyName] || {}).skipFreshness === true;

  const accentColor =
    score > 0.6
      ? "var(--score-high)"
      : score > 0.35
      ? "var(--score-mid)"
      : "var(--score-low)";

  const flagHTML = wouldBeBlocked
    ? `<span class="doc-flag flag-blocked" title="Blocked in full_policy for this role">blocked in full</span>`
    : "";

  const compareStaleHTML = doc.superseded_by
    ? `<span class="compare-stale-badge" title="Superseded by ${escapeHTML(doc.superseded_by)}">⚠ Superseded</span>`
    : "";

  const compareTitle = (doc.title || doc.doc_id).slice(0, 60);
  const docTypeLabel = formatDocType(doc.doc_type);
  const dateLabel = formatDate(doc.date);
  const compareMetaParts = [
    `<span class="card-meta-badge">${escapeHTML(doc.doc_id)}</span>`,
    docTypeLabel ? escapeHTML(docTypeLabel) : null,
    dateLabel ? escapeHTML(dateLabel) : null,
  ].filter(Boolean).join(" · ");

  const contentSnippet = escapeHTML((doc.content || "").slice(0, 120));

  const freshnessHTML = skipFreshness
    ? `<div class="mini-metric"><span class="mini-na">freshness N/A</span></div>`
    : `<div class="mini-metric">
        <span class="mini-bar-wrap">
          <span class="mini-bar" style="width: ${freshPct}%; background: var(--fresh-high)"></span>
        </span>
        <span class="mini-val">${freshness.toFixed(2)}</span>
       </div>`;

  return `
    <article class="compare-card" style="--card-accent: ${accentColor}; animation-delay: ${index * 35}ms">
      <div class="compare-card-header">
        <span class="compare-card-title">${escapeHTML(compareTitle)}</span>
        ${flagHTML}
      </div>
      <div class="card-meta compare-card-meta">${compareMetaParts}</div>
      ${compareStaleHTML}
      <p class="compare-card-content">${contentSnippet}</p>
      <div class="compare-card-scores">
        <div class="mini-metric">
          <span class="mini-bar-wrap">
            <span class="mini-bar" style="width: ${scorePct}%; background: var(--score-high)"></span>
          </span>
          <span class="mini-val">${score.toFixed(2)}</span>
        </div>
        ${freshnessHTML}
      </div>
    </article>`;
}

// ── Render: blocked documents section (single mode) ──

function buildBlockedSectionHTML(blocked, userRole) {
  if (!blocked || blocked.length === 0) return "";

  const count = blocked.length;
  const headerLabel = `${count} document${count === 1 ? "" : "s"} blocked by permissions`;

  const cardsHTML = blocked
    .map((b) => {
      const title = b.title || b.doc_id;
      const typeLabel = formatDocType(b.doc_type);
      const reason = b.reason === "unknown_min_role"
        ? `Unknown role requirement: <strong>${escapeHTML(b.required_role)}</strong>`
        : `Requires <strong>${escapeHTML(b.required_role)}</strong> role — you are <strong>${escapeHTML(userRole || b.user_role)}</strong>`;

      const metaParts = [
        `<span class="card-meta-badge">${escapeHTML(b.doc_id)}</span>`,
        typeLabel ? escapeHTML(typeLabel) : null,
      ].filter(Boolean).join(" · ");

      return `
        <div class="blocked-card">
          <div class="blocked-card-title">${escapeHTML(title)}</div>
          <div class="card-meta blocked-card-meta">${metaParts}</div>
          <div class="blocked-card-reason">${reason}</div>
        </div>`;
    })
    .join("");

  return `
    <section class="blocked-section" aria-label="Documents blocked by permissions">
      <button class="blocked-header" type="button" aria-expanded="false">
        <span class="blocked-header-icon" aria-hidden="true">🔒</span>
        <span class="blocked-header-label">${escapeHTML(headerLabel)}</span>
        <span class="blocked-caret" aria-hidden="true">▾</span>
      </button>
      <div class="blocked-body">
        <div class="blocked-body-inner">${cardsHTML}</div>
      </div>
    </section>`;
}

function wireBlockedSectionToggle(container) {
  container.querySelectorAll(".blocked-section").forEach((section) => {
    const btn = section.querySelector(".blocked-header");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const isOpen = section.classList.toggle("open");
      btn.setAttribute("aria-expanded", isOpen);
    });
  });
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
    { label: "Precision@5", value: (agg.avg_precision_at_5 ?? 0).toFixed(4), color: "var(--accent)", hint: "Accuracy of the top 5 results" },
    { label: "Recall", value: (agg.avg_recall ?? 0).toFixed(4), color: "var(--score-high)", hint: "Coverage of expected documents" },
    { label: "Permission Violations", value: fmtPct(agg.permission_violation_rate ?? 0), color: agg.permission_violation_rate > 0 ? "var(--trace-blocked)" : "var(--score-high)", hint: "Restricted docs leaked to context" },
    { label: "Avg Context Docs", value: (agg.avg_context_docs ?? 0).toFixed(1), color: "var(--text-secondary)", hint: "Documents per assembled context" },
    { label: "Avg Total Tokens", value: (agg.avg_total_tokens ?? 0).toFixed(0), color: "var(--text-secondary)", hint: "Token consumption per query" },
    { label: "Avg Freshness", value: (agg.avg_freshness_score ?? 0).toFixed(4), color: "var(--fresh-high)", hint: "Document recency (1 = newest)" },
    { label: "Avg Blocked", value: (agg.avg_blocked_count ?? 0).toFixed(1), color: "var(--trace-blocked)", hint: "Docs excluded per query by RBAC" },
    { label: "Avg Stale", value: (agg.avg_stale_count ?? 0).toFixed(1), color: "var(--trace-stale)", hint: "Superseded docs flagged per query" },
    { label: "Avg Dropped", value: (agg.avg_dropped_count ?? 0).toFixed(1), color: "var(--trace-dropped)", hint: "Docs cut by token budget" },
    { label: "Avg Budget Util", value: fmtPct(agg.avg_budget_utilization ?? 0), color: "var(--accent)", hint: "Token budget utilization" },
  ];

  const cardsHTML = cards
    .map(
      (c, i) => `
      <div class="metric-card" style="animation-delay: ${i * 40}ms">
        <span class="metric-card-label">${escapeHTML(c.label)}</span>
        <span class="metric-card-value" style="color: ${c.color}">${escapeHTML(c.value)}</span>
        <span class="metric-card-hint">${escapeHTML(c.hint)}</span>
      </div>`
    )
    .join("");

  const narrativeHTML = buildEvalsNarrative(agg);

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
      const qText = q.query || "";
      const qTextTrunc = qText.length > 50 ? qText.slice(0, 50) + "…" : qText;
      return `
        <tr class="${hasViolation ? "evals-row-violation" : ""}">
          <td class="evals-query-cell">
            <span class="evals-qid">${escapeHTML(q.id)}</span>
            <span class="evals-qtext" title="${escapeHTML(qText)}">${escapeHTML(qTextTrunc)}</span>
          </td>
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
    ${narrativeHTML}
    <div class="metrics-grid">${cardsHTML}</div>
    <div class="evals-table-wrap">
      <table class="evals-table">
        <thead>${headerRow}</thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    <p class="evals-footer">Queries run: ${agg.queries_run ?? 0} · Failed: ${agg.queries_failed ?? 0}</p>`;
}

// ── Narrative banner for Evals (IDEA 6) ──

function buildEvalsNarrative(agg) {
  const queriesRun = agg.queries_run ?? 0;
  if (queriesRun === 0) return "";

  const sentences = [];
  const violationRate = agg.permission_violation_rate ?? 0;
  const recall = agg.avg_recall ?? 0;
  const budgetUtil = agg.avg_budget_utilization ?? 0;

  // Sentence 1 — permission violations
  if (violationRate === 0) {
    sentences.push(
      `Zero permission violations across <strong>${queriesRun}</strong> test ${queriesRun === 1 ? "query" : "queries"} — the context layer never leaked restricted documents.`
    );
  } else {
    sentences.push(
      `<strong>Warning:</strong> ${fmtPct(violationRate)} of queries had permission violations across <strong>${queriesRun}</strong> test ${queriesRun === 1 ? "query" : "queries"}.`
    );
  }

  // Sentence 2 — recall
  if (recall === 1.0) {
    sentences.push("<strong>100% recall</strong> — every expected document was found.");
  } else {
    sentences.push(
      `Recall: <strong>${recall.toFixed(2)}</strong> — some expected documents were missed.`
    );
  }

  // Sentence 3 — budget utilization tier
  let tier;
  if (budgetUtil < 0.60) tier = "efficient";
  else if (budgetUtil <= 0.80) tier = "moderate";
  else tier = "heavy";
  sentences.push(
    `Average budget utilization: <strong>${fmtPct(budgetUtil)}</strong>, meaning the system assembles <strong>${tier}</strong> context packs.`
  );

  return `<div class="evals-narrative">${sentences.join(" ")}</div>`;
}

function fmtPct(v) {
  return (v * 100).toFixed(1) + "%";
}

// ── Build natural-language Decision Trace summary (IDEA 4) ──

function buildTraceSummary(trace, userRole, compact) {
  const m = trace.metrics || {};
  const included = m.included_count ?? (trace.included || []).length;
  const tokens = m.total_tokens ?? 0;
  const budgetPct = Math.round((m.budget_utilization ?? 0) * 100);
  const blockedCount = m.blocked_count ?? 0;
  const droppedCount = m.dropped_count ?? 0;
  const staleList = trace.demoted_as_stale || [];
  const blockedList = trace.blocked_by_permission || [];

  const sentences = [];

  // a) INCLUDED — always emitted; grammatical guard for zero
  if (included === 0) {
    sentences.push(`No documents made it into context (0 tokens, ${budgetPct}% of budget).`);
  } else {
    const noun = included === 1 ? "document was" : "documents were";
    sentences.push(
      `<strong>${included}</strong> ${noun} included in context (${tokens} tokens, ${budgetPct}% of budget).`
    );
  }

  // b) BLOCKED — only when blocked_count > 0
  if (blockedCount > 0) {
    const uniqueRoles = Array.from(
      new Set(blockedList.map((b) => b.required_role).filter(Boolean))
    );
    const rolesLabel = uniqueRoles.length > 0
      ? uniqueRoles.map((r) => `<strong>${escapeHTML(r)}</strong>`).join(" and ")
      : "higher";
    const roleClause = userRole
      ? `your role (<strong>${escapeHTML(userRole)}</strong>) cannot access ${rolesLabel}-level materials`
      : `your role cannot access ${rolesLabel}-level materials`;
    const noun = blockedCount === 1 ? "document was" : "documents were";
    sentences.push(`<strong>${blockedCount}</strong> ${noun} blocked — ${roleClause}.`);
  }

  // c) STALE — only when demoted_as_stale is non-empty
  if (staleList.length > 0) {
    if (compact) {
      // Compare mode: one compact sentence, no per-doc details
      const noun = staleList.length === 1 ? "document was" : "documents were";
      sentences.push(`<strong>${staleList.length}</strong> ${noun} demoted as superseded.`);
    } else {
      // Single mode: detail the first (up to 2) with penalty
      const toList = staleList.slice(0, 2);
      toList.forEach((s) => {
        const penalty = s.penalty_applied != null ? `${s.penalty_applied}×` : "0.5×";
        sentences.push(
          `<strong>${escapeHTML(s.doc_id)}</strong> was demoted (superseded by <strong>${escapeHTML(s.superseded_by)}</strong>, freshness penalized by ${escapeHTML(penalty)}).`
        );
      });
      if (staleList.length > toList.length) {
        const rest = staleList.length - toList.length;
        sentences.push(`${rest} additional stale document${rest === 1 ? "" : "s"} listed below.`);
      }
    }
  }

  // d) DROPPED — always emitted (positive or negative), unless compact+zero
  if (droppedCount > 0) {
    const noun = droppedCount === 1 ? "document" : "documents";
    sentences.push(
      `<strong>${droppedCount}</strong> ${noun} passed all filters but ${droppedCount === 1 ? "was" : "were"} dropped because ${droppedCount === 1 ? "it" : "they"} exceeded the token budget.`
    );
  } else if (!compact) {
    sentences.push("No documents were dropped by budget.");
  }

  return sentences.join(" ");
}

// ── Build Decision Trace panel HTML ──

function buildTracePanelHTML(trace, startOpen, userRole) {
  const m = trace.metrics || {};
  const budgetPct = Math.min(100, Math.round((m.budget_utilization ?? 0) * 100));
  const summaryHTML = buildTraceSummary(trace, userRole, startOpen === true);

  const includedChips = (trace.included || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-included" title="score: ${d.score.toFixed(2)} · ${d.token_count} tokens">${escapeHTML(d.doc_id)}</span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const blockedChips = (trace.blocked_by_permission || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-blocked" title="requires: ${escapeHTML(d.required_role)}">${escapeHTML(d.doc_id)}<em> ·${escapeHTML(d.required_role)}</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const staleChips = (trace.demoted_as_stale || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-stale" title="superseded by: ${escapeHTML(d.superseded_by)} · penalty: ${d.penalty_applied}×">${escapeHTML(d.doc_id)}<em> →${escapeHTML(d.superseded_by)}</em></span>`
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
        <div class="trace-summary${startOpen ? " trace-summary-compact" : ""}">${summaryHTML}</div>
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
            <span class="budget-label" title="Percentage of the 2048-token budget used by assembled context">Budget</span>
            <div class="budget-bar-wrap">
              <div class="budget-bar-fill" style="width: ${budgetPct}%"></div>
            </div>
            <span class="budget-pct">${budgetPct}%</span>
          </div>
          <div class="trace-numbers">
            <span title="Average relevance score of included documents (0–1)">avg score <strong>${(m.avg_score ?? 0).toFixed(2)}</strong></span>
            <span title="Average freshness score — 1.0 = newest document in corpus">avg freshness <strong>${(m.avg_freshness_score ?? 0).toFixed(2)}</strong></span>
            <span title="Time-to-First-Token proxy — estimated latency before an LLM starts generating">ttft <strong>${Math.round(trace.ttft_proxy_ms ?? 0)}ms</strong></span>
          </div>
        </div>
      </div>
    </div>`;
}

// ── Wire trace toggle expand/collapse ──

function wireExpandButtons(container) {
  container.querySelectorAll(".card-expand-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".result-card");
      const idx = parseInt(card.dataset.cardIdx, 10);
      const excerpts = _cardExcerpts.get(idx);
      const contentEl = card.querySelector(".card-content");
      const textEl = contentEl.querySelector(".card-content-text");
      const expanded = contentEl.classList.toggle("expanded");
      textEl.textContent = expanded ? excerpts.full : excerpts.short;
      btn.textContent = expanded ? "Hide ▴" : "Show more ▾";
    });
  });
}

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

function formatDocType(raw) {
  return (raw || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const [year, month] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function escapeHTML(str) {
  const el = document.createElement("span");
  el.textContent = String(str ?? "");
  return el.innerHTML;
}
