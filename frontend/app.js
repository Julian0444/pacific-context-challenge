// app.js — QueryTrace Context Policy Lab

// API_BASE picks absolute localhost for file:// and local dev, empty (same-origin)
// elsewhere. When the page is served from /app/ on the deployed host, fetches
// resolve against the page origin (e.g. https://host/query) — no CORS required.
const API_BASE = (() => {
  const h = window.location.hostname;
  if (h === "localhost" || h === "127.0.0.1" || h === "") return "http://localhost:8000";
  return "";
})();
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

// ── Workspace state (Fase 2) ────────────────────────────────────────────────
// Everything corpus-specific (roles, scenarios, examples, placeholders) is
// rendered from GET /workspaces/{slug}/meta. Switching workspace persists the
// slug and reloads for a clean re-bootstrap (same pattern as login).

const WORKSPACE_STORAGE_KEY = "qt_workspace";
let WORKSPACES = []; // [{slug, name, description, doc_count}]
let DEFAULT_WORKSPACE = "pe-deal";
let CURRENT_WORKSPACE = null; // slug
let WORKSPACE_META = null; // /workspaces/{slug}/meta payload

// Role maps — rebuilt per workspace from /meta ("Sees N of M docs" is
// computed server-side from metadata, never hardcoded here).
let ROLE_DESCRIPTIONS = {};
let ROLE_RANKS = {};

// Offline fallback (server unreachable): keeps the form usable so submit can
// surface the "Backend unavailable" error card instead of a dead page.
const FALLBACK_META = {
  slug: "pe-deal",
  name: "QueryTrace",
  description: "",
  total_docs: 0,
  doc_types: [],
  roles: [
    { name: "analyst", access_rank: 1, hint: "", docs_visible: 0 },
    { name: "vp", access_rank: 2, hint: "", docs_visible: 0 },
    { name: "partner", access_rank: 3, hint: "", docs_visible: 0 },
  ],
  scenarios: [],
  example_queries: [],
  search_placeholder: "Type a query…",
  empty_state_description: "",
  personas: [],
};

// Raw excerpt storage for expand/collapse — keyed by card index, avoids data-attr innerHTML
const _cardExcerpts = new Map();

// ── Stale-state tracking (UI-B) ─────────────────────────────────────────────
// Records the (role, policy) used for the currently rendered Single result.
// When either radio diverges from these values, a stale banner is shown above
// the cards until the user presses Run. Cleared on: render success, mode
// switch out of single, and Single preset-button clicks.
let _lastRenderedRole = null;
let _lastRenderedPolicy = null;

function buildStaleBannerHTML() {
  return `
    <div id="stale-results-banner"
         class="stale-results-banner"
         role="status"
         aria-live="polite"
         aria-atomic="true">
      <span class="stale-banner-icon" aria-hidden="true">↻</span>
      <span class="stale-banner-text">Controls changed — press <strong>Run</strong> to refresh these results.</span>
    </div>`;
}

function clearSingleStale() {
  const banner = document.getElementById("stale-results-banner");
  if (banner) banner.remove();
  resultsSection.classList.remove("results-stale");
}

function evaluateSingleStale() {
  // Gate: only relevant when a trusted Single result is on screen. Presence of
  // .summary-bar is authoritative — excludes #empty-state, skeleton, no-results,
  // and error states.
  const hasResult = resultsSection.querySelector(".summary-bar") !== null;
  if (!hasResult) {
    clearSingleStale();
    return;
  }
  const currentRole =
    document.querySelector('input[name="role"]:checked')?.value || null;
  const currentPolicy =
    document.querySelector('input[name="policy"]:checked')?.value || null;
  const matches =
    currentRole === _lastRenderedRole && currentPolicy === _lastRenderedPolicy;
  if (matches) {
    clearSingleStale();
    return;
  }
  if (!document.getElementById("stale-results-banner")) {
    resultsSection.insertAdjacentHTML("afterbegin", buildStaleBannerHTML());
  }
  resultsSection.classList.add("results-stale");
}

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
const sessionAuditContent = document.getElementById("session-audit-content");
const adminSection = document.getElementById("admin-section");

// ── Mode state ──

let currentMode = "single"; // "single" | "compare" | "evals" | "admin"
let evalsLoaded = false;

// ── Session state (Fase P) ──────────────────────────────────────────────────
// SESSION is null for guests (lab mode — everything behaves as before).
// With a session, role (and policy for non-admins) derive server-side from
// the signed cookie; the UI mirrors that so controls never lie.

let SESSION = null; // {username, name, role, is_admin, workspace} | null
let INGEST_ENABLED = null; // from /health; null until probed
let ASK_ENABLED = null; // from /health; Ask mode exists only with a model key

// ── Workspace loading + rendering (Fase 2) ──────────────────────────────────

async function loadWorkspaces() {
  try {
    const res = await fetch(`${API_BASE}/workspaces`);
    if (!res.ok) throw new Error(`workspaces ${res.status}`);
    const data = await res.json();
    WORKSPACES = data.workspaces || [];
    DEFAULT_WORKSPACE = data.default || DEFAULT_WORKSPACE;
  } catch (_err) {
    WORKSPACES = [];
  }
}

function resolveInitialWorkspace() {
  // Session binding wins; then the persisted picker choice; then the default.
  if (SESSION?.workspace) return SESSION.workspace;
  const stored = sessionStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (stored && WORKSPACES.some((w) => w.slug === stored)) return stored;
  return DEFAULT_WORKSPACE;
}

async function loadWorkspaceMeta(slug) {
  try {
    const res = await fetch(`${API_BASE}/workspaces/${encodeURIComponent(slug)}/meta`);
    if (!res.ok) throw new Error(`meta ${res.status}`);
    WORKSPACE_META = await res.json();
  } catch (_err) {
    WORKSPACE_META = FALLBACK_META;
  }
}

function setWorkspace(slug) {
  if (!slug || slug === CURRENT_WORKSPACE) return;
  sessionStorage.setItem(WORKSPACE_STORAGE_KEY, slug);
  const proceed = () => location.reload(); // clean re-bootstrap, like login
  if (SESSION && SESSION.workspace !== slug) {
    // Sessions are bound to one workspace server-side; switching signs out
    // and lands on the new workspace's login screen.
    sessionStorage.removeItem("qt_guest");
    fetch(`${API_BASE}/logout`, { method: "POST" })
      .catch(() => {})
      .finally(proceed);
  } else {
    proceed();
  }
}

function renderWorkspacePickers() {
  const options = WORKSPACES.map(
    (w) =>
      `<option value="${escapeHTML(w.slug)}"${w.slug === CURRENT_WORKSPACE ? " selected" : ""}>${escapeHTML(w.name)}</option>`
  ).join("");
  [
    document.getElementById("workspace-picker"),
    document.getElementById("login-workspace-picker"),
  ].forEach((sel) => {
    if (!sel) return;
    if (WORKSPACES.length === 0) {
      sel.hidden = true;
      const label = document.querySelector(".workspace-switch-label");
      if (label) label.hidden = true;
      return;
    }
    sel.innerHTML = options;
    sel.value = CURRENT_WORKSPACE;
    sel.addEventListener("change", () => setWorkspace(sel.value));
  });
}

function onboardCardHTML(s) {
  return `
    <div class="onboard-card" data-story="${escapeHTML(s.key || "")}">
      <span class="onboard-card-head">
        <span class="onboard-card-subtitle">${escapeHTML(s.subtitle || s.role || "")}</span>
      </span>
      <span class="onboard-card-title">${escapeHTML(s.title || "")}</span>
      <span class="onboard-hint">${escapeHTML(s.hint || "")}</span>
      <div class="onboard-actions">
        <button type="button"
                class="example-btn onboard-primary"
                data-query="${escapeHTML(s.query || "")}"
                data-role="${escapeHTML(s.role || "")}"
                data-mode="single"
                title="${escapeHTML(s.single_tooltip || "")}">
          Run in Single
        </button>
        <button type="button"
                class="example-btn onboard-secondary"
                data-query="${escapeHTML(s.query || "")}"
                data-role="${escapeHTML(s.role || "")}"
                data-mode="compare"
                title="${escapeHTML(s.compare_tooltip || "")}">
          Open in Compare →
        </button>
      </div>
    </div>`;
}

function compareOnboardCardHTML(s) {
  return `
    <button type="button"
            class="example-btn onboard-card onboard-card-compact"
            data-query="${escapeHTML(s.query || "")}"
            data-role="${escapeHTML(s.role || "")}"
            data-mode="compare"
            data-story="${escapeHTML(s.key || "")}"
            title="${escapeHTML(s.compare_card_tooltip || s.compare_tooltip || "")}">
      <span class="onboard-card-head">
        <span class="onboard-card-subtitle">${escapeHTML(s.compare_subtitle || s.subtitle || "")}</span>
      </span>
      <span class="onboard-card-title">${escapeHTML(s.title || "")}</span>
      <span class="onboard-hint">${escapeHTML(s.compare_hint || s.hint || "")}</span>
    </button>`;
}

function renderRoleControls() {
  const container = document.getElementById("role-options");
  if (!container) return;
  const roles = WORKSPACE_META.roles || [];
  ROLE_RANKS = {};
  ROLE_DESCRIPTIONS = {};
  roles.forEach((r) => {
    ROLE_RANKS[r.name] = r.access_rank;
    const seen = `Sees ${r.docs_visible} of ${WORKSPACE_META.total_docs} docs`;
    ROLE_DESCRIPTIONS[r.name] = r.hint ? `${seen} — ${r.hint}.` : `${seen}.`;
  });
  container.innerHTML = roles
    .map(
      (r, i) => `
      <label class="role-option">
        <input type="radio" name="role" value="${escapeHTML(r.name)}"${i === 0 ? " checked" : ""} />
        <span class="role-chip">${escapeHTML(roleLabel(r.name))}</span>
      </label>`
    )
    .join("");
  container.querySelectorAll('input[name="role"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      updateRoleDescription(radio.value);
      evaluateSingleStale();
    });
  });
  updateRoleDescription(roles[0]?.name || "");
}

function roleLabel(name) {
  // Short role names render as acronyms (vp → VP); words get capitalized.
  if (!name) return "";
  if (name.length <= 3) return name.toUpperCase();
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function renderExamples() {
  const container = document.getElementById("examples");
  if (!container) return;
  const examples = WORKSPACE_META.example_queries || [];
  const rows = [
    { mode: "single", label: "Single" },
    { mode: "compare", label: "Compare" },
  ]
    .map(({ mode, label }) => {
      const btns = examples
        .filter((e) => (e.mode || "single") === mode)
        .map(
          (e) => `
          <button class="example-btn${mode === "compare" ? " scenario-btn" : ""}"
                  data-query="${escapeHTML(e.query || "")}"
                  data-role="${escapeHTML(e.role || "")}"
                  data-mode="${escapeHTML(mode)}"
                  title="${escapeHTML(e.tooltip || "")}">${escapeHTML(e.label || "")}</button>`
        )
        .join("");
      if (!btns) return "";
      return `<div class="examples-row"><span class="examples-label">${label}</span>${btns}</div>`;
    })
    .join("");
  container.innerHTML = rows;
}

function renderAdminFormOptions() {
  const roleSel = document.getElementById("admin-min-role");
  const typeSel = document.getElementById("admin-doc-type");
  if (roleSel) {
    roleSel.innerHTML = (WORKSPACE_META.roles || [])
      .map((r) => `<option value="${escapeHTML(r.name)}">${escapeHTML(r.name)}</option>`)
      .join("");
  }
  if (typeSel) {
    typeSel.innerHTML = (WORKSPACE_META.doc_types || [])
      .map((t) => `<option value="${escapeHTML(t)}">${escapeHTML(t)}</option>`)
      .join("");
  }
}

function renderWorkspaceUI() {
  renderWorkspacePickers();
  renderRoleControls();
  renderExamples();
  renderAdminFormOptions();

  if (input && WORKSPACE_META.search_placeholder) {
    input.placeholder = WORKSPACE_META.search_placeholder;
  }

  const emptyDesc = document.getElementById("empty-description");
  if (emptyDesc) emptyDesc.textContent = WORKSPACE_META.empty_state_description || "";

  const scenarios = WORKSPACE_META.scenarios || [];
  const onboardGrid = document.getElementById("onboard-grid");
  if (onboardGrid) onboardGrid.innerHTML = scenarios.map(onboardCardHTML).join("");
  const compareGridEl = document.getElementById("compare-onboard-grid");
  if (compareGridEl) {
    compareGridEl.innerHTML = scenarios.map(compareOnboardCardHTML).join("");
  }

  const loginName = document.getElementById("login-workspace-name");
  if (loginName) loginName.textContent = WORKSPACE_META.name || "";

  // Letterhead classification line (D.4) — name comes from the manifest, the
  // marking itself is generic product furniture (credible in any workspace).
  const classLine = document.getElementById("classification-line");
  if (classLine) {
    const wsName = WORKSPACE_META.name || "";
    classLine.textContent = wsName
      ? `Private & Confidential · ${wsName}`
      : "Private & Confidential";
    classLine.hidden = false;
  }
}

// Business-card personas (Fase 6 Etapa E): NAME · ROLE · CLEARANCE from the
// workspace meta (access ranks render as roman numerals — corpus-agnostic).
function romanRank(n) {
  return ["", "I", "II", "III", "IV", "V"][n] || String(n);
}

function personaCardHTML(p) {
  const initials = p.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const adminBadge = p.is_admin ? '<span class="persona-admin-badge">admin</span>' : "";
  const rank = ROLE_RANKS[p.role];
  const clearance = rank ? ` · Clearance ${romanRank(rank)}` : "";
  return `
    <button class="persona-card" type="button"
            data-username="${escapeHTML(p.username)}" data-password="${escapeHTML(p.password_hint)}">
      <span class="persona-avatar" aria-hidden="true">${initials}</span>
      <span class="persona-body">
        <span class="persona-name">${escapeHTML(p.name)} ${adminBadge}</span>
        <span class="persona-card-line">${escapeHTML(p.role)}${escapeHTML(clearance)}</span>
        <span class="persona-role">sees ${p.docs_visible} of ${p.total_docs} docs</span>
        <span class="persona-creds">${escapeHTML(p.username)} / ${escapeHTML(p.password_hint)}</span>
      </span>
    </button>`;
}

function showLoginScreen() {
  const screen = document.getElementById("login-screen");
  const cardsEl = document.getElementById("persona-cards");
  if (!screen || !cardsEl) return;
  screen.hidden = false;
  if (cardsEl.childElementCount > 0) return; // already rendered

  // Personas ship with the workspace meta (Fase 2) — no extra fetch, and the
  // cards always match the workspace shown in the picker.
  const personas = WORKSPACE_META?.personas || [];
  if (personas.length === 0) {
    cardsEl.innerHTML =
      '<p class="login-error">Could not load personas — is the server running?</p>';
    return;
  }
  cardsEl.innerHTML = personas.map(personaCardHTML).join("");
  cardsEl.querySelectorAll(".persona-card").forEach((card) => {
    card.addEventListener("click", async () => {
      card.disabled = true;
      try {
        const res = await fetch(`${API_BASE}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: card.dataset.username,
            password: card.dataset.password,
            workspace: CURRENT_WORKSPACE, // session binds to this workspace
          }),
        });
        if (!res.ok) throw new Error(`login ${res.status}`);
        sessionStorage.removeItem("qt_guest");
        location.reload(); // clean re-bootstrap with the session cookie set
      } catch (err) {
        card.disabled = false;
        cardsEl.insertAdjacentHTML(
          "beforeend",
          `<p class="login-error">Sign-in failed (${escapeHTML(String(err.message || err))}). Try again.</p>`
        );
      }
    });
  });
}

document.getElementById("guest-link")?.addEventListener("click", () => {
  sessionStorage.setItem("qt_guest", "1");
  const screen = document.getElementById("login-screen");
  if (screen) screen.hidden = true;
});

function renderSessionChip() {
  const chip = document.getElementById("session-chip");
  if (!chip) return;
  if (SESSION) {
    const initials = SESSION.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    chip.innerHTML = `
      <span class="chip-avatar" aria-hidden="true">${initials}</span>
      <span class="chip-identity">
        <span class="chip-name">${escapeHTML(SESSION.name)}</span>
        <span class="chip-role">${escapeHTML(SESSION.role)}${SESSION.is_admin ? " · admin" : ""}${SESSION.workspace ? ` · ${escapeHTML(SESSION.workspace)}` : ""}</span>
      </span>
      <button class="chip-logout" id="logout-btn" type="button">Sign out</button>`;
    document.getElementById("logout-btn").addEventListener("click", async () => {
      try {
        await fetch(`${API_BASE}/logout`, { method: "POST" });
      } catch (_err) { /* cookie may already be gone */ }
      sessionStorage.removeItem("qt_guest");
      location.reload();
    });
  } else {
    chip.innerHTML =
      '<button class="chip-signin" id="signin-btn" type="button">Sign in</button>';
    document.getElementById("signin-btn").addEventListener("click", () => {
      sessionStorage.removeItem("qt_guest");
      showLoginScreen();
    });
  }
}

function syncRoleControlsForMode() {
  // Admin sessions: /query always runs as the session role, so lock the role
  // radios in Single mode; Side-by-side keeps free role choice ("View as…").
  if (!SESSION || !SESSION.is_admin) return;
  const lock = currentMode === "single";
  document.querySelectorAll('input[name="role"]').forEach((r) => {
    r.disabled = lock;
  });
  if (lock) {
    const rr = document.querySelector(`input[name="role"][value="${SESSION.role}"]`);
    if (rr) rr.checked = true;
    updateRoleDescription(SESSION.role);
  }
  const note = document.getElementById("session-role-note");
  if (note) note.hidden = !lock;
}

function applySessionUI() {
  if (!SESSION) return;
  // Mirror the server-derived controls so downstream logic (stale banner,
  // descriptions) stays coherent even while the selectors are hidden/locked.
  const roleRadio = document.querySelector(`input[name="role"][value="${SESSION.role}"]`);
  if (roleRadio) roleRadio.checked = true;
  updateRoleDescription(SESSION.role);

  if (!SESSION.is_admin) {
    document.body.classList.add("product-mode");
    const policyRadio = document.querySelector('input[name="policy"][value="full_policy"]');
    if (policyRadio) policyRadio.checked = true;
    updatePolicyDescription("full_policy");
    // Product sessions get Query only (see the Fase P capability table).
    document
      .querySelectorAll('.mode-btn[data-mode="compare"], .mode-btn[data-mode="evals"]')
      .forEach((b) => { b.hidden = true; });
  } else {
    document.body.classList.add("admin-mode");
    if (INGEST_ENABLED !== false) {
      const adminBtn = document.querySelector('.mode-btn[data-mode="admin"]');
      if (adminBtn) adminBtn.hidden = false;
    }
    const roleGroup = document.querySelector(".role-selector-group");
    if (roleGroup && !document.getElementById("session-role-note")) {
      roleGroup.insertAdjacentHTML(
        "beforeend",
        `<p class="session-role-note" id="session-role-note">Query mode runs as your session role (${escapeHTML(SESSION.role)}). Use Side-by-side to view as other roles.</p>`
      );
    }
    syncRoleControlsForMode();
  }
}

// ── Mode toggle ──

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    switchMode(btn.dataset.mode);
  });
});

function switchMode(mode) {
  if (mode === currentMode) return;
  const leavingSingle = currentMode === "single" && mode !== "single";
  const enteringSingle = currentMode !== "single" && mode === "single";
  currentMode = mode;

  document.querySelectorAll(".mode-btn").forEach((b) => {
    const active = b.dataset.mode === mode;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", active);
  });

  const isCompare = mode === "compare";
  const isEvals = mode === "evals";
  const isAdmin = mode === "admin";

  singlePolicySelector.hidden = isCompare || isEvals || isAdmin;
  resultsSection.hidden = isCompare || isEvals || isAdmin;
  compareSection.hidden = !isCompare;
  evalsSection.hidden = !isEvals;
  if (adminSection) adminSection.hidden = !isAdmin;
  mainEl.classList.toggle("compare-mode", isCompare);

  // Hide query form in evals and admin modes — not relevant
  document.querySelector(".search-section").hidden = isEvals || isAdmin;

  // Fade-in the incoming section (CSS animation via .mode-enter).
  const entering = isCompare
    ? compareSection
    : isEvals
    ? evalsSection
    : isAdmin
    ? adminSection
    : resultsSection;
  if (entering) playModeEnter(entering);

  // Auto-fetch evals on first switch; session audit on every switch
  if (isEvals) {
    if (!evalsLoaded) runEvals();
    fetchSessionAudit();
  }

  // Stale banner bookkeeping (UI-B). Leaving Single removes any visible banner
  // (the rendered content is preserved for when the user returns). Entering
  // Single re-evaluates staleness against the last-rendered (role, policy) so
  // a round trip with a diverged role radio still surfaces the banner.
  if (leavingSingle) clearSingleStale();
  if (enteringSingle) evaluateSingleStale();

  // Admin sessions: role radios lock in Single (server derives the role),
  // unlock in Side-by-side ("View as…").
  syncRoleControlsForMode();

  // Ask AI only exists in Single mode (and only when the server has a key).
  updateAskButtonVisibility();
}

function playModeEnter(el) {
  if (!el) return;
  el.classList.remove("mode-enter");
  // Force reflow so re-adding the class restarts the animation.
  void el.offsetWidth;
  el.classList.add("mode-enter");
  const onEnd = () => {
    el.classList.remove("mode-enter");
    el.removeEventListener("animationend", onEnd);
  };
  el.addEventListener("animationend", onEnd);
}

// ── Theme toggle (Fase 6, D6.3) ──
// data-theme on <html> is the explicit user choice (persisted in localStorage
// and applied pre-paint by the boot script in index.html); without it the
// prefers-color-scheme media query decides. The attribute wins both ways.

const themeToggle = document.getElementById("theme-toggle");

function effectiveTheme() {
  const forced = document.documentElement.getAttribute("data-theme");
  if (forced === "dark" || forced === "light") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function updateThemeToggleLabel() {
  if (!themeToggle) return;
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  const label = `Switch to ${next} theme`;
  themeToggle.setAttribute("aria-label", label);
  themeToggle.title = label;
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("qt_theme", next);
    } catch (_err) {
      /* storage unavailable — the choice lasts for this page only */
    }
    updateThemeToggleLabel();
  });
  const colorSchemeMq = window.matchMedia("(prefers-color-scheme: dark)");
  if (colorSchemeMq.addEventListener) {
    colorSchemeMq.addEventListener("change", updateThemeToggleLabel);
  }
  updateThemeToggleLabel();
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
  radio.addEventListener("change", () => {
    updatePolicyDescription(radio.value);
    evaluateSingleStale();
  });
});

// Initialize with the default checked policy
updatePolicyDescription(
  document.querySelector('input[name="policy"]:checked')?.value || "full_policy"
);

// ── Role description (shown under the role selector) ──

function updateRoleDescription(role) {
  const descEl = document.getElementById("role-description");
  if (!descEl) return;
  descEl.style.opacity = "0";
  setTimeout(() => {
    descEl.textContent = ROLE_DESCRIPTIONS[role] || "";
    descEl.style.opacity = "1";
  }, 80);
}

// Role radios are rendered (and wired) per workspace in renderRoleControls().

// ── Bootstrap: health probe (capabilities + cold start) + session probe ──
// If /health takes more than ~2.5s (Render free tier waking up, ~45-60s),
// show a banner instead of a silent dead UI.

(async function bootstrap() {
  let coldStartBanner = null;
  const coldStartTimer = setTimeout(() => {
    coldStartBanner = document.createElement("div");
    coldStartBanner.className = "cold-start-banner";
    coldStartBanner.setAttribute("role", "status");
    coldStartBanner.textContent =
      "⏳ Waking up the free-tier server — this first load can take ~45 seconds. Everything is instant once it's up.";
    document.body.prepend(coldStartBanner);
  }, 2500);

  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      INGEST_ENABLED = !!(data && data.ingest_enabled);
      ASK_ENABLED = !!(data && data.ask_enabled);
      updateAskButtonVisibility();
      if (data && data.default_workspace) DEFAULT_WORKSPACE = data.default_workspace;
    }
  } catch (_err) {
    // Non-fatal: offline or old server — leave capabilities at defaults.
  } finally {
    clearTimeout(coldStartTimer);
    if (coldStartBanner) coldStartBanner.remove();
  }

  // Session probe: 401 → guest (lab). The login screen only appears when the
  // visitor hasn't explicitly chosen the guest path this browser session.
  try {
    const res = await fetch(`${API_BASE}/me`);
    if (res.ok) SESSION = await res.json();
  } catch (_err) {
    SESSION = null;
  }

  // Workspace resolution (Fase 2): session binding > stored choice > default.
  // All corpus-specific UI (roles, scenarios, examples, personas) renders
  // from the workspace meta before any session UI touches those controls.
  await loadWorkspaces();
  CURRENT_WORKSPACE = resolveInitialWorkspace();
  sessionStorage.setItem(WORKSPACE_STORAGE_KEY, CURRENT_WORKSPACE);
  await loadWorkspaceMeta(CURRENT_WORKSPACE);
  renderWorkspaceUI();

  renderSessionChip();
  if (SESSION) {
    applySessionUI();
  } else if (!sessionStorage.getItem("qt_guest")) {
    showLoginScreen();
  }
})();

// ── Form submission ──

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) return;

  // With a session, the role is server-derived; the radio is just a mirror.
  const role = SESSION
    ? SESSION.role
    : document.querySelector('input[name="role"]:checked').value;

  if (currentMode === "compare") {
    await runCompare(query, role);
  } else {
    const policy =
      SESSION && !SESSION.is_admin
        ? "full_policy"
        : document.querySelector('input[name="policy"]:checked')?.value ||
          "full_policy";
    await runSingleQuery(query, role, policy);
  }
});

// ── Example / scenario buttons ──
// Delegated: scenario cards and shortcut rows are re-rendered per workspace
// (Fase 2), so a document-level listener replaces per-button wiring.

document.addEventListener("click", (e) => {
  const btn = e.target.closest?.(".example-btn");
  if (btn) handleExampleClick(btn);
});

function handleExampleClick(btn) {
  {
    const query = btn.dataset.query;
    // Product/admin sessions can't impersonate roles in Query mode — the
    // scenario runs as the session identity (that's the point of the mode).
    const role = SESSION && btn.dataset.mode !== "compare"
      ? SESSION.role
      : btn.dataset.role;
    const targetMode = btn.dataset.mode;

    input.value = query;

    const roleRadio = document.querySelector(
      `input[name="role"][value="${role}"]`
    );
    if (roleRadio) roleRadio.checked = true;
    // Programmatic checked assignment does not fire "change" — sync description manually
    updateRoleDescription(role);

    // Single presets are deterministic: force full_policy and sync the radio +
    // description so controls stay coherent with the rendered result (UI-B).
    if (targetMode === "single") {
      const policyRadio = document.querySelector(
        'input[name="policy"][value="full_policy"]'
      );
      if (policyRadio) policyRadio.checked = true;
      updatePolicyDescription("full_policy");
    }

    clearSingleStale();

    if (targetMode && targetMode !== currentMode) {
      switchMode(targetMode);
    }

    if (currentMode === "compare") {
      runCompare(query, role);
    } else {
      runSingleQuery(query, role, "full_policy");
    }
  }
}

// ── Single-policy query ──

async function runSingleQuery(query, role, policy = "full_policy") {
  setLoadingSingle(true);
  try {
    // Sessions: omit role (server derives it from the cookie; sending a
    // conflicting one is a 400 by design). Non-admins also omit policy.
    // Workspace always travels along (it matches the session binding).
    const body = { query, top_k: DEFAULT_TOP_K, workspace: CURRENT_WORKSPACE };
    if (!SESSION) {
      body.role = role;
      body.policy_name = policy;
    } else if (SESSION.is_admin) {
      body.policy_name = policy;
    }
    const res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
      body: JSON.stringify({
        query,
        role,
        top_k: DEFAULT_TOP_K,
        workspace: CURRENT_WORKSPACE,
      }),
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

// ── Ask mode (Fase 4) ──
// Same request shape and session rules as /query; the response adds an
// AI answer with mechanically validated [doc_id] citations. The button is
// hidden unless /health reports ask_enabled (i.e. the deploy has a key).

const askBtn = document.getElementById("ask-btn");

function updateAskButtonVisibility() {
  if (!askBtn) return;
  askBtn.hidden = !(ASK_ENABLED === true && currentMode === "single");
}

if (askBtn) {
  askBtn.addEventListener("click", async () => {
    const query = input.value.trim();
    if (!query || currentMode !== "single") return;
    const role = SESSION
      ? SESSION.role
      : document.querySelector('input[name="role"]:checked').value;
    const policy =
      SESSION && !SESSION.is_admin
        ? "full_policy"
        : document.querySelector('input[name="policy"]:checked')?.value ||
          "full_policy";
    await runAsk(query, role, policy);
  });
}

async function runAsk(query, role, policy = "full_policy") {
  setLoadingAsk(true);
  try {
    const body = { query, top_k: DEFAULT_TOP_K, workspace: CURRENT_WORKSPACE };
    if (!SESSION) {
      body.role = role;
      body.policy_name = policy;
    } else if (SESSION.is_admin) {
      body.policy_name = policy;
    }
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }

    const data = await res.json();
    // The Ask response is a superset of /query — render the normal result
    // view (cards, blocked section, trace) and put the answer panel on top.
    renderSingleResult(data, role, policy);
    resultsSection.insertAdjacentHTML("afterbegin", buildAskPanelHTML(data));
    wireAskPanel(resultsSection);
  } catch (err) {
    renderError(err, resultsSection);
  } finally {
    setLoadingAsk(false);
  }
}

function setLoadingAsk(on) {
  askBtn.disabled = on;
  askBtn.classList.toggle("loading", on);
  submitBtn.disabled = on;
  if (on) {
    document.getElementById("empty-state")?.remove();
    resultsSection.classList.remove("results-stale");
    resultsSection.innerHTML = skeletonSingleHTML();
  }
}

function buildAskPanelHTML(data) {
  const validity = new Map((data.citations || []).map((c) => [c.doc_id, c.valid]));
  const answerHTML = escapeHTML(data.answer || "").replace(
    /\[(doc_\d+)\]/g,
    (_m, id) => {
      if (validity.get(id) === false) {
        return (
          `<span class="citation-chip citation-invalid" ` +
          `title="Cited a document that was not in the context — flagged by mechanical citation validation">${id}</span>`
        );
      }
      return (
        `<button type="button" class="citation-chip" data-cite="${id}" ` +
        `title="Jump to ${id} in the context below">${id}</button>`
      );
    }
  );

  const trace = data.decision_trace;
  const blockedCount = trace?.blocked_summary
    ? trace.blocked_summary.count
    : (trace?.blocked_by_permission || []).length;
  const grounded = data.grounded_doc_count || 0;
  const groundingParts = [
    `Grounded in ${grounded} ${grounded === 1 ? "doc" : "docs"}`,
  ];
  if (blockedCount > 0) {
    groundingParts.push(
      `${blockedCount} blocked ${blockedCount === 1 ? "doc" : "docs"} never reached the model`
    );
  }

  const usage = data.usage || { input_tokens: 0, output_tokens: 0 };
  const usageNote =
    `${escapeHTML(data.model || "")} · ` +
    `${usage.input_tokens.toLocaleString()} tokens in / ` +
    `${usage.output_tokens.toLocaleString()} out` +
    (data.cached ? " · served from cache (no new tokens spent)" : "");

  return `
    <div class="ask-panel">
      <div class="ask-panel-header">
        <span class="ask-panel-title">✦ AI answer</span>
        <span class="ask-grounding">${groundingParts.join(" · ")}</span>
      </div>
      <p class="ask-answer">${answerHTML}</p>
      <p class="ask-usage">${usageNote}</p>
    </div>`;
}

function wireAskPanel(container) {
  container.querySelectorAll(".citation-chip[data-cite]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const target = container.querySelector(
        `.result-card[data-doc-id="${chip.dataset.cite}"]`
      );
      if (!target) return;
      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      target.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "center",
      });
      target.classList.remove("card-highlight");
      void target.offsetWidth; // restart the highlight animation
      target.classList.add("card-highlight");
      setTimeout(() => target.classList.remove("card-highlight"), 1800);
    });
  });
}

// ── Loading states ──

function setLoadingSingle(on) {
  submitBtn.disabled = on;
  submitBtn.classList.toggle("loading", on);
  if (on) {
    document.getElementById("empty-state")?.remove();
    // Drop the stale-results modifier before the skeleton renders so it
    // doesn't inherit the 60% opacity applied to stale cards (UI-B).
    resultsSection.classList.remove("results-stale");
    resultsSection.innerHTML = skeletonSingleHTML();
  }
}

function setLoadingCompare(on) {
  submitBtn.disabled = on;
  submitBtn.classList.toggle("loading", on);
  if (on) {
    // UI-C: drop the Compare onboarding empty state once a comparison starts.
    document.getElementById("compare-empty-state")?.remove();
    const compareBanner = document.getElementById("compare-banner");
    if (compareBanner) compareBanner.hidden = false;
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

// ── Chunk grouping (Fase 5 Etapa B) ──
// Context items are chunks; the UI renders one card per parent DOCUMENT:
// best-scoring chunk visible, all matched chunks available via expand.

function groupContextByDoc(context) {
  const groups = new Map();
  (context || []).forEach((item) => {
    if (!groups.has(item.doc_id)) groups.set(item.doc_id, []);
    groups.get(item.doc_id).push(item);
  });
  return Array.from(groups.values()).map((chunks) => {
    const ordered = chunks
      .slice()
      .sort((a, b) => (a.chunk_index ?? 0) - (b.chunk_index ?? 0));
    const best = chunks.reduce((a, b) => ((b.score ?? 0) > (a.score ?? 0) ? b : a), chunks[0]);
    return {
      ...best,
      matchedSections: chunks.length,
      totalSections: best.chunk_count ?? chunks.length,
      fullContent: ordered.map((c) => c.content || "").join("\n[…]\n"),
    };
  });
}

// Dedupe chunk-level trace entries to one row per parent doc (first wins),
// collecting the sibling chunk ids for display.
function groupTraceEntries(list) {
  const groups = new Map();
  (list || []).forEach((e) => {
    if (!groups.has(e.doc_id)) groups.set(e.doc_id, { ...e, chunk_ids: [] });
    if (e.chunk_id) groups.get(e.doc_id).chunk_ids.push(e.chunk_id);
  });
  return Array.from(groups.values());
}

function docCount(metrics, key) {
  // Prefer the doc-level counts (post-chunking traces); fall back to raw.
  return metrics?.[`${key}_doc_count`] ?? metrics?.[`${key}_count`] ?? 0;
}

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
  const docs = groupContextByDoc(data.context);

  // Memo letterhead (Fase 6 D.1): hairline field table instead of pills.
  // Class stays .summary-bar — the stale-results gate (UI-B) keys off it.
  const budgetPctHeader = metrics
    ? Math.round((metrics.budget_utilization ?? 0) * 100)
    : null;
  const memoFields = [
    { label: "Prepared for", value: escapeHTML(roleLabel(role)), cls: "memo-role" },
    { label: "Policy", value: escapeHTML(meta.label), cls: `policy-stat-${meta.variant}` },
    {
      label: docs.length === 1 ? "Document" : "Documents",
      value: String(docs.length),
    },
    {
      label: "Tokens",
      value: budgetPctHeader != null
        ? `${data.total_tokens.toLocaleString()} · ${budgetPctHeader}% of budget`
        : data.total_tokens.toLocaleString(),
    },
  ];
  if (metrics) {
    const blockedN = docCount(metrics, "blocked");
    const staleN = docCount(metrics, "stale");
    memoFields.push({
      label: "Blocked",
      value: String(blockedN),
      cls: blockedN > 0 ? "memo-blocked" : "",
    });
    memoFields.push({
      label: "Stale",
      value: String(staleN),
      cls: staleN > 0 ? "memo-stale" : "",
    });
  }
  const summaryHTML = `
    <div class="summary-bar">
      ${memoFields
        .map(
          (f) => `
        <div class="memo-field">
          <span class="memo-label">${f.label}</span>
          <span class="memo-value${f.cls ? ` ${f.cls}` : ""}">${f.value}</span>
        </div>`
        )
        .join("")}
      <button class="export-btn" id="export-single" type="button" aria-label="Download the full query response as JSON" title="Download the full /query response as JSON">
        <span class="export-btn-icon" aria-hidden="true">⤓</span><span class="export-btn-label">Download filing</span>
      </button>
    </div>`;

  // Build stale lookup keyed by doc_id — used as fallback when chunk.superseded_by is absent
  const staleMap = new Map(
    (trace?.demoted_as_stale || []).map((s) => [s.doc_id, s])
  );

  const cardsHTML = docs
    .map((doc, i) => singleCardHTML(doc, i, policy, staleMap))
    .join("");

  // Product sessions receive a server-redacted trace: blocked docs arrive as
  // {count, required_roles} only (P.4). Render the withheld strip instead of
  // the detailed blocked section — the titles never reached the browser.
  const blockedSectionHTML = trace?.blocked_summary
    ? buildWithheldStripHTML(trace.blocked_summary)
    : buildBlockedSectionHTML(trace?.blocked_by_permission || [], role);

  const traceHTML = trace
    ? buildTracePanelHTML(trace, true, role)
    : "";

  resultsSection.innerHTML = summaryHTML + cardsHTML + blockedSectionHTML + traceHTML;

  // Wire trace toggles, expand buttons, and blocked-section toggle
  wireTraceToggles(resultsSection);
  wireExpandButtons(resultsSection);
  wireBlockedSectionToggle(resultsSection);
  animateBars(resultsSection);

  const exportBtn = resultsSection.querySelector("#export-single");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      downloadJSON(data, `querytrace_${role}_${policy}.json`);
    });
  }

  // Record the (role, policy) pair tied to the rendered result so subsequent
  // radio changes can be detected as stale (UI-B).
  _lastRenderedRole = role;
  _lastRenderedPolicy = policy;
}

// ── Render: single result card ──

function singleCardHTML(chunk, index, policy, staleMap = new Map()) {
  const score = chunk.score ?? 0;
  const freshness = chunk.freshness_score ?? 0;
  const scorePct = Math.round(score * 100);
  const freshPct = Math.round(freshness * 100);
  const skipFreshness = (POLICY_META[policy] || {}).skipFreshness === true;

  const tagsHTML = (chunk.tags || [])
    .map((t) => `<span class="tag">${escapeHTML(t)}</span>`)
    .join("");

  const title = chunk.title || chunk.doc_id;
  const docTypeLabel = formatDocType(chunk.doc_type);
  const dateLabel = formatDate(chunk.date);
  // Sections badge (Fase 5 Etapa B): how many of the doc's chunks matched
  const matched = chunk.matchedSections ?? 1;
  const totalSections = chunk.totalSections ?? chunk.chunk_count ?? 1;
  const sectionsLabel = totalSections > 1
    ? `matched ${matched} of ${totalSections} section${totalSections === 1 ? "" : "s"}`
    : null;
  const metaParts = [
    `<span class="card-meta-badge">REF: ${escapeHTML(chunk.doc_id)}</span>`,
    docTypeLabel ? escapeHTML(docTypeLabel) : null,
    dateLabel ? escapeHTML(dateLabel) : null,
    sectionsLabel
      ? `<span class="card-sections-badge" title="The document is indexed as ${totalSections} chunks; ${matched} made it into this context">${escapeHTML(sectionsLabel)}</span>`
      : null,
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
      <span class="stamp stamp-superseded" aria-hidden="true">Superseded</span>
      <span class="stale-text">Superseded by <strong>${escapeHTML(supersededBy)}</strong> — freshness penalized ${escapeHTML(penaltyLabel)}</span>
    </div>` : "";

  const rawShort = (chunk.content || "").slice(0, 200);
  // Expand shows every matched chunk of the doc, joined with […] separators
  const rawFull = chunk.fullContent || chunk.content || "";
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
            <div class="metric-bar-fill freshness" style="width: 0%" data-w="${freshPct}"></div>
          </div>
          <span class="metric-value">${freshness.toFixed(2)}</span>
        </div>
       </div>`;

  return `
    <article class="result-card" data-card-idx="${index}" data-doc-id="${escapeHTML(chunk.doc_id)}" style="animation-delay: ${index * 50}ms">
      <div class="card-header">
        <span class="card-title">${escapeHTML(title)}</span>
        <span class="card-folio">Exhibit ${String(index + 1).padStart(2, "0")}</span>
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
              <div class="metric-bar-fill relevance" style="width: 0%" data-w="${scorePct}"></div>
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
  // Verdict stamps (Fase 6 F.1): naive leaks whatever full_policy blocks —
  // the doc-level count travels in full's trace metrics.
  const fullBlockedDocs = fullResult
    ? docCount(fullResult.decision_trace?.metrics, "blocked")
    : null;

  const columns = COMPARE_ORDER.filter((p) => data.results[p]);

  compareGrid.innerHTML = columns
    .map((policyName, colIdx) =>
      buildCompareColumnHTML(
        policyName,
        data.results[policyName],
        { blockedInFull, fullBlockedDocs },
        colIdx,
        data.role
      )
    )
    .join("");

  // Wire all trace toggles in the compare grid
  wireTraceToggles(compareGrid);
  animateBars(compareGrid);

  // Append (or replace) the Export JSON button in the compare banner.
  const compareBanner = document.getElementById("compare-banner");
  if (compareBanner) {
    compareBanner
      .querySelectorAll(".export-btn")
      .forEach((b) => b.remove());
    const btn = document.createElement("button");
    btn.className = "export-btn";
    btn.id = "export-compare";
    btn.type = "button";
    btn.setAttribute("aria-label", "Download the full comparison as JSON");
    btn.title = "Download full /compare response as JSON";
    btn.innerHTML =
      '<span class="export-btn-icon" aria-hidden="true">⤓</span><span class="export-btn-label">Download filing</span>';
    btn.addEventListener("click", () => {
      downloadJSON(data, `querytrace_compare_${data.role}.json`);
    });
    compareBanner.appendChild(btn);
  }
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

  // Stats cells — doc-level counts (chunk entries deduped to parent docs)
  const groupedDocs = groupContextByDoc(result.context);
  const blockedVal = docCount(metrics, "blocked");
  const staleVal = docCount(metrics, "stale");
  const droppedVal = docCount(metrics, "dropped");
  const ttftMs = trace ? Math.round(trace.ttft_proxy_ms) : "—";

  const statsHTML = `
    <div class="col-stats">
      <div class="col-stat">
        <span class="col-stat-val">${groupedDocs.length}</span>
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

  // Document cards — one per parent doc (chunks grouped)
  const docsHTML =
    groupedDocs.length > 0
      ? groupedDocs
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
    ? `<div class="col-trace">${buildTracePanelHTML(trace, true, userRole, true)}</div>`
    : "";

  // Verdict stamp (F.1): the contrast that sells the product, readable
  // without the numbers. Naive gets LEAKED N DOCS only when full_policy
  // actually blocks something for this role; full gets CLEAN.
  let verdictHTML = "";
  if (policyName === "naive_top_k" && (highlights.fullBlockedDocs ?? 0) > 0) {
    const n = highlights.fullBlockedDocs;
    verdictHTML = `<span class="stamp stamp-blocked col-verdict" aria-label="This baseline leaked ${n} restricted ${n === 1 ? "document" : "documents"}">Leaked ${n} ${n === 1 ? "doc" : "docs"}</span>`;
  } else if (policyName === "full_policy" && highlights.fullBlockedDocs != null) {
    verdictHTML = `<span class="stamp stamp-approved col-verdict" aria-label="No restricted documents reached this context">Clean</span>`;
  }

  return `
    <div class="compare-col" data-policy="${escapeHTML(policyName)}" style="animation-delay: ${colIdx * 60}ms">
      <div class="col-header col-header-${meta.variant}">
        <span class="col-badge col-badge-${meta.variant}">${escapeHTML(meta.label)}</span>
        <div class="col-policy-info">
          <span class="col-policy-name">${escapeHTML(policyName)}</span>
          <span class="col-policy-desc">${escapeHTML(meta.desc)}</span>
        </div>
        ${verdictHTML}
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

  const flagHTML = wouldBeBlocked
    ? `<span class="doc-flag flag-blocked" title="Blocked in full_policy for this role">blocked in full</span>`
    : "";

  const compareStaleHTML = doc.superseded_by
    ? `<span class="compare-stale-badge" title="Superseded by ${escapeHTML(doc.superseded_by)}">⚠ Superseded</span>`
    : "";

  const compareTitle = (doc.title || doc.doc_id).slice(0, 60);
  const docTypeLabel = formatDocType(doc.doc_type);
  const dateLabel = formatDate(doc.date);
  const compareSections = (doc.totalSections ?? 1) > 1
    ? `${doc.matchedSections ?? 1}/${doc.totalSections} sections`
    : null;
  const compareMetaParts = [
    `<span class="card-meta-badge">REF: ${escapeHTML(doc.doc_id)}</span>`,
    docTypeLabel ? escapeHTML(docTypeLabel) : null,
    dateLabel ? escapeHTML(dateLabel) : null,
    compareSections ? escapeHTML(compareSections) : null,
  ].filter(Boolean).join(" · ");

  const contentSnippet = escapeHTML((doc.content || "").slice(0, 120));

  const freshnessHTML = skipFreshness
    ? `<div class="mini-metric"><span class="mini-na">freshness N/A</span></div>`
    : `<div class="mini-metric">
        <span class="mini-bar-wrap">
          <span class="mini-bar" style="width: 0%; background: var(--fresh-high)" data-w="${freshPct}"></span>
        </span>
        <span class="mini-val">${freshness.toFixed(2)}</span>
       </div>`;

  return `
    <article class="compare-card" style="animation-delay: ${index * 35}ms">
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
            <span class="mini-bar" style="width: 0%; background: var(--score-high)" data-w="${scorePct}"></span>
          </span>
          <span class="mini-val">${score.toFixed(2)}</span>
        </div>
        ${freshnessHTML}
      </div>
    </article>`;
}

// ── Render: blocked documents section (single mode) ──

function buildWithheldStripHTML(summary) {
  if (!summary || summary.count === 0) return "";
  const req = summary.required_roles || [];
  const minReq = req.length
    ? req.reduce((a, b) => ((ROLE_RANKS[a] || 9) <= (ROLE_RANKS[b] || 9) ? a : b))
    : null;
  const reqLabel = minReq ? `requires ${escapeHTML(minReq)}+` : "requires higher clearance";
  const myRole = SESSION?.role || "guest";
  const myRank = ROLE_RANKS[myRole] ?? "?";
  const reqDetail = [...req]
    .sort((a, b) => (ROLE_RANKS[a] || 9) - (ROLE_RANKS[b] || 9))
    .map((r) => `${escapeHTML(r)} (${ROLE_RANKS[r] ?? "?"})`)
    .join(", ");
  const plural = summary.count === 1 ? "document" : "documents";
  return `
    <div class="withheld-strip" role="note">
      <span class="withheld-lock" aria-hidden="true">🔒</span>
      <span class="withheld-text">${summary.count} ${plural} withheld · ${reqLabel}</span>
      <details class="withheld-why">
        <summary>Why?</summary>
        <div class="withheld-why-body">
          Your role: <strong>${escapeHTML(myRole)} (${myRank})</strong> &lt; required:
          <strong>${reqDetail}</strong>. Access is enforced server-side — the withheld
          titles were never sent to your browser.
        </div>
      </details>
    </div>`;
}

function buildBlockedSectionHTML(blockedRaw, userRole) {
  // Entries are per-chunk since Fase 5 Etapa B — dedupe to parent docs
  const blocked = groupTraceEntries(blockedRaw);
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
        `<span class="card-meta-badge">REF: ${escapeHTML(b.doc_id)}</span>`,
        typeLabel ? escapeHTML(typeLabel) : null,
      ].filter(Boolean).join(" · ");

      return `
        <div class="blocked-card">
          <span class="stamp stamp-blocked" aria-hidden="true">Blocked</span>
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
    const res = await fetch(
      `${API_BASE}/evals?workspace=${encodeURIComponent(CURRENT_WORKSPACE || "")}`
    );
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
      <p class="evals-loading-text">Running the benchmark queries…</p>
    </div>`;
}

// CERTIFIED plaque (Fase 6 F.2): the headline verdict of the benchmark. The
// stamp only exists when the violation rate is exactly zero — otherwise the
// plaque turns into a warning without any seal of approval.
function buildCertifiedPlaqueHTML(agg) {
  const rate = agg.permission_violation_rate ?? 0;
  const queriesRun = agg.queries_run ?? 0;
  if (rate === 0) {
    return `
      <div class="certified-plaque">
        <div class="certified-figure">
          <span class="certified-value">0%</span>
          <span class="certified-label">permission violations · ${queriesRun} benchmark ${queriesRun === 1 ? "query" : "queries"}</span>
        </div>
        <span class="stamp stamp-approved certified-stamp">Certified</span>
      </div>`;
  }
  return `
    <div class="certified-plaque plaque-warning">
      <div class="certified-figure">
        <span class="certified-value certified-value-warning">${fmtPct(rate)}</span>
        <span class="certified-label">permission violations · ${queriesRun} benchmark ${queriesRun === 1 ? "query" : "queries"} — restricted documents reached the context</span>
      </div>
    </div>`;
}

function renderEvals(data) {
  const agg = data.aggregate;
  const queries = data.per_query;

  // Financial statement rows (F.2) — figures in Fraunces at two decimals
  const metricRows = [
    { label: "Precision@5", value: (agg.avg_precision_at_5 ?? 0).toFixed(2), color: "var(--accent)", note: "Accuracy of the top 5 results" },
    { label: "Recall", value: (agg.avg_recall ?? 0).toFixed(2), color: "var(--score-high)", note: "Coverage of expected documents" },
    { label: "Avg Context Docs", value: (agg.avg_context_docs ?? 0).toFixed(1), color: "var(--text-primary)", note: "Documents per assembled context" },
    { label: "Avg Total Tokens", value: (agg.avg_total_tokens ?? 0).toFixed(0), color: "var(--text-primary)", note: "Token consumption per query" },
    { label: "Avg Freshness", value: (agg.avg_freshness_score ?? 0).toFixed(2), color: "var(--fresh-high)", note: "Document recency (1 = newest)" },
    { label: "Avg Blocked", value: (agg.avg_blocked_count ?? 0).toFixed(1), color: "var(--trace-blocked)", note: "Docs excluded per query by RBAC" },
    { label: "Avg Stale", value: (agg.avg_stale_count ?? 0).toFixed(1), color: "var(--trace-stale)", note: "Superseded docs flagged per query" },
    { label: "Avg Dropped", value: (agg.avg_dropped_count ?? 0).toFixed(1), color: "var(--trace-dropped)", note: "Docs cut by token budget" },
    { label: "Avg Budget Util", value: fmtPct(agg.avg_budget_utilization ?? 0), color: "var(--accent)", note: "Token budget utilization" },
  ];

  const metricsTableHTML = `
    <div class="evals-table-wrap metrics-statement">
      <table class="evals-table metrics-table">
        <tbody>
          ${metricRows
            .map(
              (r) => `
            <tr>
              <td class="metrics-label">${escapeHTML(r.label)}</td>
              <td class="metrics-value" style="color: ${r.color}">${escapeHTML(r.value)}</td>
              <td class="metrics-note">${escapeHTML(r.note)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;

  const narrativeHTML = buildEvalsNarrative(agg);
  const plaqueHTML = buildCertifiedPlaqueHTML(agg);

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
      return `
        <tr class="${hasViolation ? "evals-row-violation" : ""}">
          <td class="evals-query-cell">
            <span class="evals-qid">${escapeHTML(q.id)}</span>
            <span class="evals-qtext">${escapeHTML(qText)}</span>
            ${copyBtnHTML(qText)}
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
          ${budgetCellHTML(q.budget_utilization)}
          <td class="mono-cell${hasViolation ? " val-violation" : " val-ok"}">${hasViolation ? q.permission_violations.join(", ") : "none"}</td>
        </tr>`;
    })
    .join("");

  evalsContent.innerHTML = `
    ${narrativeHTML}
    ${plaqueHTML}
    ${metricsTableHTML}
    <h3 class="evals-section-label">Benchmark Questions</h3>
    <div class="evals-table-wrap">
      <table class="evals-table">
        <thead>${headerRow}</thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    <p class="evals-footer">Queries run: ${agg.queries_run ?? 0} · Failed: ${agg.queries_failed ?? 0}</p>`;

  const subtitle = document.getElementById("evals-subtitle");
  if (subtitle) {
    const wsName = WORKSPACE_META?.name || CURRENT_WORKSPACE || "";
    subtitle.textContent =
      `Precision@5 · recall · permission safety · trace counts — ` +
      `${queries.length} corpus-grounded test queries · ${wsName}`;
  }

  wireCopyButtons(evalsContent);
  animateBars(evalsContent);
}

// Budget cell with an inline fill bar (F.2) — animated by animateBars (A.7)
function budgetCellHTML(utilization) {
  const pct = Math.min(100, Math.round((utilization ?? 0) * 100));
  return `
    <td class="mono-cell evals-budget-cell">
      <span class="budget-cell-bar" aria-hidden="true"><span class="mini-bar" style="width: 0%; background: var(--azul)" data-w="${pct}"></span></span>${fmtPct(utilization ?? 0)}
    </td>`;
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

const _copyTexts = [];

function copyBtnHTML(text) {
  const idx = _copyTexts.length;
  _copyTexts.push(text);
  return `<button class="copy-query-btn" data-copy-idx="${idx}" title="Copy query">⎘</button>`;
}

function wireCopyButtons(container) {
  container.querySelectorAll(".copy-query-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const text = _copyTexts[Number(btn.dataset.copyIdx)] ?? "";
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = "✓";
        setTimeout(() => { btn.textContent = "⎘"; }, 1200);
      }).catch(() => {});
    });
  });
}

// ── Session Audit (MET-B) ──

async function fetchSessionAudit() {
  try {
    const res = await fetch(`${API_BASE}/session-audit`);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    renderSessionAudit(data);
  } catch (err) {
    sessionAuditContent.innerHTML = `<div class="session-audit-section">
      <h3 class="evals-section-label">Session Audit</h3>
      <p class="session-audit-error">Failed to load session audit: ${escapeHTML(err.message)}</p>
    </div>`;
  }
}

function fmtRelativeTime(isoStr) {
  const now = Date.now();
  const then = new Date(isoStr).getTime();
  const diffS = Math.max(0, Math.floor((now - then) / 1000));
  if (diffS < 60) return `${diffS}s ago`;
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `${diffM}m ago`;
  const diffH = Math.floor(diffM / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return `${Math.floor(diffH / 24)}d ago`;
}

function renderSessionAudit(data) {
  const entries = data.entries || [];
  const sessionStart = data.session_started_at || "";

  const disclaimerHTML = `<div class="session-audit-disclaimer">Shared demo log — visible to all visitors on this server instance. Do not enter sensitive information. Resets on server restart.</div>`;

  if (entries.length === 0) {
    sessionAuditContent.innerHTML = `
      <hr class="evals-divider">
      <div class="session-audit-section">
        <h3 class="evals-section-label">Session Audit</h3>
        ${disclaimerHTML}
        <div class="session-audit-empty">Run a query in <strong>Query</strong> mode and it will appear here as q013.</div>
      </div>`;
    return;
  }

  const sessionTime = sessionStart ? new Date(sessionStart).toLocaleString() : "unknown";

  const headerRow = `<tr>
    <th>Query</th>
    <th>Time</th>
    <th>Role</th>
    <th>Policy</th>
    <th>Docs</th>
    <th>Tokens</th>
    <th>Freshness</th>
    <th>Blocked</th>
    <th>Stale</th>
    <th>Dropped</th>
    <th>Budget</th>
  </tr>`;

  const bodyRows = entries.map((e) => {
    const m = e.metrics || {};
    const policyKey = e.policy_name || "";
    const meta = POLICY_META[policyKey] || { label: policyKey, skipFreshness: false };
    const freshness = meta.skipFreshness ? "N/A" : (m.avg_freshness_score ?? 0).toFixed(3);
    const docIds = e.doc_ids || {};
    const hasDetail = (docIds.included && docIds.included.length) ||
                      (docIds.blocked && docIds.blocked.length) ||
                      (docIds.stale && docIds.stale.length) ||
                      (docIds.dropped && docIds.dropped.length);
    const detailId = `sa-detail-${escapeHTML(e.id)}`;

    let detailRow = "";
    if (hasDetail) {
      const chips = (arr, cls) => (arr || []).map(id => `<span class="sa-chip sa-chip-${cls}">${escapeHTML(id)}</span>`).join("");
      detailRow = `<tr class="sa-detail-row" id="${detailId}" hidden>
        <td colspan="11" class="sa-detail-cell">
          ${docIds.included?.length ? `<span class="sa-chip-label">Included</span> ${chips(docIds.included, "included")}` : ""}
          ${docIds.blocked?.length ? `<span class="sa-chip-label">Blocked</span> ${chips(docIds.blocked, "blocked")}` : ""}
          ${docIds.stale?.length ? `<span class="sa-chip-label">Stale</span> ${chips(docIds.stale, "stale")}` : ""}
          ${docIds.dropped?.length ? `<span class="sa-chip-label">Dropped</span> ${chips(docIds.dropped, "dropped")}` : ""}
        </td>
      </tr>`;
    }

    return `<tr class="sa-entry-row">
      <td class="evals-query-cell">
        <span class="evals-qid">${escapeHTML(e.id)}</span>
        <span class="evals-qtext">${escapeHTML(e.query || "")}</span>
        ${copyBtnHTML(e.query || "")}
      </td>
      <td class="mono-cell sa-time" title="${escapeHTML(e.created_at || "")}">${fmtRelativeTime(e.created_at)}</td>
      <td><span class="evals-role-chip">${escapeHTML(e.role || "")}</span></td>
      <td class="mono-cell">${escapeHTML(meta.label)}</td>
      <td class="mono-cell">${m.included_count ?? 0}</td>
      <td class="mono-cell">${m.total_tokens ?? 0}</td>
      <td class="mono-cell">${freshness}</td>
      <td class="mono-cell${(m.blocked_count ?? 0) > 0 ? " val-blocked" : ""}">${m.blocked_count ?? 0}</td>
      <td class="mono-cell${(m.stale_count ?? 0) > 0 ? " val-stale" : ""}">${m.stale_count ?? 0}</td>
      <td class="mono-cell${(m.dropped_count ?? 0) > 0 ? " val-dropped" : ""}">${m.dropped_count ?? 0}</td>
      ${budgetCellHTML(m.budget_utilization)}
    </tr>${hasDetail ? `<tr class="sa-toggle-row"><td colspan="11"><button class="sa-toggle-btn" data-target="${detailId}">▸ docs</button></td></tr>${detailRow}` : ""}`;
  }).join("");

  sessionAuditContent.innerHTML = `
    <hr class="evals-divider">
    <div class="session-audit-section">
      <h3 class="evals-section-label">Session Audit</h3>
      <p class="session-audit-meta">Session started: ${escapeHTML(sessionTime)} · ${entries.length} ${entries.length === 1 ? "query" : "queries"}</p>
      ${disclaimerHTML}
      <div class="evals-table-wrap">
        <table class="evals-table sa-table">
          <thead>${headerRow}</thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    </div>`;

  sessionAuditContent.querySelectorAll(".sa-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      const showing = !target.hidden;
      target.hidden = showing;
      btn.textContent = showing ? "▸ docs" : "▾ docs";
    });
  });

  wireCopyButtons(sessionAuditContent);
  animateBars(sessionAuditContent);
}

// ── Build natural-language Decision Trace summary (IDEA 4) ──

function buildTraceSummary(trace, userRole, compact) {
  const m = trace.metrics || {};
  // Doc-level counts throughout — users reason about documents, not chunks
  const included = m.included_doc_count
    ?? m.included_count
    ?? (trace.included || []).length;
  const tokens = m.total_tokens ?? 0;
  const budgetPct = Math.round((m.budget_utilization ?? 0) * 100);
  const blockedCount = docCount(m, "blocked");
  const droppedCount = docCount(m, "dropped");
  const staleList = groupTraceEntries(trace.demoted_as_stale || []);
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

// ── Decision Record rows (Fase 6 D.2) ──
// One ledger row per parent doc per ACTION: TITLE · REF · flat action mark ·
// readable basis. Inline basis text replaces the old chip tooltips (which
// were unreachable on touch). All dynamic strings are escaped by the callers.

function recordRowHTML(action, stampCls, title, ref, basisHTML) {
  const titleHTML = title
    ? `<span class="record-title">${escapeHTML(title)}</span>`
    : `<span class="record-untitled">—</span>`;
  return `
    <tr>
      <td class="record-doc">${titleHTML}</td>
      <td class="record-ref">${escapeHTML(ref)}</td>
      <td class="record-action"><span class="stamp stamp-flat ${stampCls}">${action}</span></td>
      <td class="record-basis">${basisHTML}</td>
    </tr>`;
}

function buildDecisionRecordHTML(trace, userRole) {
  const rows = [];

  groupTraceEntries(trace.included || []).forEach((d) => {
    const sections =
      (d.chunk_ids || []).length > 1 ? ` · ${d.chunk_ids.length} sections` : "";
    rows.push(
      recordRowHTML(
        "Included", "stamp-approved", d.title, d.doc_id,
        `score ${(d.score ?? 0).toFixed(2)} · ${d.token_count} tokens${sections}`
      )
    );
  });

  groupTraceEntries(trace.demoted_as_stale || []).forEach((d) => {
    rows.push(
      recordRowHTML(
        "Demoted", "stamp-superseded", d.title, d.doc_id,
        `superseded by ${escapeHTML(d.superseded_by)} · freshness ×${d.penalty_applied ?? 0.5}`
      )
    );
  });

  groupTraceEntries(trace.dropped_by_budget || []).forEach((d) => {
    rows.push(
      recordRowHTML(
        "Dropped", "stamp-overbudget", d.title, d.doc_id,
        `${d.token_count} tokens · score ${(d.score ?? 0).toFixed(2)} · over budget`
      )
    );
  });

  groupTraceEntries(trace.blocked_by_permission || []).forEach((d) => {
    const basis = d.reason === "unknown_min_role"
      ? `unknown role requirement: ${escapeHTML(d.required_role)}`
      : `requires ${escapeHTML(d.required_role)} — you are ${escapeHTML(userRole || d.user_role || "")}`;
    rows.push(recordRowHTML("Blocked", "stamp-blocked", d.title, d.doc_id, basis));
  });

  // Product sessions (D.3): the server redacts blocked docs to a count +
  // required_roles. One count-only row — no titles, no refs, no tooltips.
  const summary = trace.blocked_summary;
  if ((trace.blocked_by_permission || []).length === 0 && summary && summary.count > 0) {
    const req = (summary.required_roles || []).map((r) => escapeHTML(r)).join(" / ");
    rows.push(
      recordRowHTML(
        "Blocked", "stamp-blocked", null,
        `${summary.count} withheld`,
        req ? `requires ${req} — titles withheld server-side` : "titles withheld server-side"
      )
    );
  }

  const bodyHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="4" class="record-empty">No documents retrieved</td></tr>`;

  return `
    <div class="record-table-wrap">
      <table class="record-table">
        <thead>
          <tr><th>Document</th><th>Ref</th><th>Action</th><th>Basis</th></tr>
        </thead>
        <tbody>${bodyHTML}</tbody>
      </table>
    </div>`;
}

// Compact chips — Compare columns only (the acta table needs more width)
function buildTraceChipsHTML(trace) {
  const chunkSuffix = (d) =>
    (d.chunk_ids || []).length > 1 ? `<em> ·${d.chunk_ids.length} chunks</em>` : "";
  const chunkTitle = (d) =>
    (d.chunk_ids || []).length ? ` · ${escapeHTML(d.chunk_ids.join(", "))}` : "";

  const includedChips = groupTraceEntries(trace.included || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-included" title="score: ${d.score.toFixed(2)} · ${d.token_count} tokens${chunkTitle(d)}">${escapeHTML(d.doc_id)}${chunkSuffix(d)}</span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const blockedChips = groupTraceEntries(trace.blocked_by_permission || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-blocked" title="requires: ${escapeHTML(d.required_role)}${chunkTitle(d)}">${escapeHTML(d.doc_id)}<em> ·${escapeHTML(d.required_role)}</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const staleChips = groupTraceEntries(trace.demoted_as_stale || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-stale" title="superseded by: ${escapeHTML(d.superseded_by)} · penalty: ${d.penalty_applied}×${chunkTitle(d)}">${escapeHTML(d.doc_id)}<em> →${escapeHTML(d.superseded_by)}</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  const droppedChips = groupTraceEntries(trace.dropped_by_budget || [])
    .map(
      (d) =>
        `<span class="trace-chip trace-chip-dropped" title="${d.token_count} tokens · score: ${d.score.toFixed(2)}${chunkTitle(d)}">${escapeHTML(d.doc_id)}<em> ·${d.token_count}t</em></span>`
    )
    .join("") || `<span class="trace-chip-empty">none</span>`;

  return `
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
    </div>`;
}

// startOpen controls only the initial expanded state; compact selects the
// tighter Compare-column variant (chips + compact summary). They are
// independent (A.6): Single opens the full "Decision Record" acta.
function buildTracePanelHTML(trace, startOpen, userRole, compact = false) {
  const m = trace.metrics || {};
  const budgetPct = Math.min(100, Math.round((m.budget_utilization ?? 0) * 100));
  const summaryHTML = buildTraceSummary(trace, userRole, compact === true);

  const blockedCount = docCount(m, "blocked");
  const staleCount = docCount(m, "stale");
  const droppedCount = docCount(m, "dropped");
  const toggleSummary = `${blockedCount} blocked · ${staleCount} stale · ${droppedCount} dropped`;

  const detailHTML = compact
    ? buildTraceChipsHTML(trace)
    : buildDecisionRecordHTML(trace, userRole);

  return `
    <div class="trace-panel${startOpen ? " open" : ""}">
      <button class="trace-toggle" aria-expanded="${startOpen}">
        <span class="trace-toggle-label">${compact ? "Decision Trace" : "Decision Record"}</span>
        <span class="trace-toggle-summary">${escapeHTML(toggleSummary)}</span>
        <span class="trace-caret" aria-hidden="true">▾</span>
      </button>
      <div class="trace-body">
        <div class="trace-summary${compact ? " trace-summary-compact" : ""}">${summaryHTML}</div>
        ${detailHTML}
        <div class="trace-metrics-strip">
          <div class="budget-row">
            <span class="budget-label" title="Percentage of the 2048-token budget used by assembled context">Budget</span>
            <div class="budget-bar-wrap">
              <div class="budget-bar-fill" style="width: 0%" data-w="${budgetPct}"></div>
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

// ── Fill-bar entrance (A.7) ──
// Bars render at width:0 with the real percentage in data-w; setting the
// final width one frame later lets the CSS width transition actually play.
// Under prefers-reduced-motion the transition is disabled, so bars snap.
function animateBars(container) {
  const bars = container.querySelectorAll("[data-w]");
  if (bars.length === 0) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      bars.forEach((bar) => {
        bar.style.width = `${bar.dataset.w}%`;
      });
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

// ── Export: download the complete API response payload as JSON ──
// Uses Blob + createObjectURL; revokes the object URL after the click to
// avoid leaking Blob references for the lifetime of the document.
function downloadJSON(data, filename) {
  try {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } catch (err) {
    console.error("Export failed:", err);
  }
}

// ── Admin / ingest ──

const adminForm = document.getElementById("admin-form");
const adminSubmit = document.getElementById("admin-submit");
const adminStatus = document.getElementById("admin-status");
const adminFileInput = document.getElementById("admin-file");

function setAdminStatus(kind, message) {
  if (!adminStatus) return;
  adminStatus.hidden = false;
  adminStatus.className = `admin-status admin-status-${kind}`;
  adminStatus.innerHTML = message;
}

function clearAdminStatus() {
  if (!adminStatus) return;
  adminStatus.hidden = true;
  adminStatus.className = "admin-status";
  adminStatus.textContent = "";
}

// Human labels for the ingest job states (Fase 3: POST /ingest → 202 + job).
const JOB_STATE_LABELS = {
  queued: "Queued — waiting for the ingest worker…",
  extracting: "Persisting extracted text…",
  embedding: "Generating embeddings…",
  indexing: "Updating FAISS + BM25 indexes…",
};
const JOB_STATE_ORDER = ["queued", "extracting", "embedding", "indexing"];
const JOB_POLL_MS = 1000;
const JOB_POLL_MAX = 120; // give up after ~2 minutes

function renderJobProgress(state) {
  const idx = JOB_STATE_ORDER.indexOf(state);
  const steps = JOB_STATE_ORDER.map((s, i) => {
    const cls = i < idx ? "job-step done" : i === idx ? "job-step active" : "job-step";
    return `<span class="${cls}" title="${escapeHTML(JOB_STATE_LABELS[s])}"></span>`;
  }).join("");
  const label = JOB_STATE_LABELS[state] || state;
  return `<span class="job-progress">${steps}</span> ${escapeHTML(label)}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollIngestJob(jobId) {
  for (let i = 0; i < JOB_POLL_MAX; i++) {
    const res = await fetch(`${API_BASE}/ingest/jobs/${encodeURIComponent(jobId)}`);
    const job = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(job?.detail || `HTTP ${res.status}`);
    }
    if (job.state === "done" || job.state === "failed") return job;
    setAdminStatus("loading", renderJobProgress(job.state));
    await sleep(JOB_POLL_MS);
  }
  throw new Error("Timed out waiting for the ingest job to finish.");
}

async function uploadDocument(event) {
  event.preventDefault();
  if (!adminForm || !adminSubmit) return;

  const file = adminFileInput?.files?.[0];
  if (!file) {
    setAdminStatus("error", "Please pick a file (.pdf, .txt, .md or .docx).");
    return;
  }

  const fd = new FormData(adminForm);
  fd.set("workspace", CURRENT_WORKSPACE || ""); // ingest into the active workspace
  adminSubmit.disabled = true;
  adminSubmit.classList.add("loading");
  setAdminStatus("loading", "Uploading and validating the file…");

  try {
    const res = await fetch(`${API_BASE}/ingest`, { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail = data?.detail || `HTTP ${res.status}`;
      setAdminStatus("error", `Upload failed: ${escapeHTML(detail)}`);
      return;
    }

    // 202: validated + queued. Poll the job until it reaches a terminal state.
    setAdminStatus("loading", renderJobProgress(data.state || "queued"));
    const job = await pollIngestJob(data.job_id);

    if (job.state === "failed") {
      const detail = job.error?.detail || "Ingest job failed.";
      setAdminStatus("error", `Upload failed: ${escapeHTML(detail)}`);
      return;
    }

    const result = job.result || {};
    setAdminStatus(
      "success",
      `Indexed <strong>${escapeHTML(result.doc_id)}</strong> — ${escapeHTML(
        result.title
      )}. Corpus now contains ${result.total_documents} documents. It is searchable in Single and Compare modes.`
    );
    adminForm.reset();
  } catch (err) {
    setAdminStatus(
      "error",
      `Network error: ${escapeHTML(err?.message || String(err))}`
    );
  } finally {
    adminSubmit.disabled = false;
    adminSubmit.classList.remove("loading");
  }
}

if (adminForm) {
  adminForm.addEventListener("submit", uploadDocument);
}
