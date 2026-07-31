# HANDOFF — Ejecución del roadmap de portfolio

Log acumulativo de sesiones de ejecución del roadmap (`plansToPortfolio/README.md`). Cada sesión
nueva agrega una sección `## Session — YYYY-MM-DD` abajo; no se borra historia. Un lector frío
con el repo debería poder retomar leyendo solo este archivo + el README del roadmap.

**Reglas permanentes (README, Reglas de ejecución):** git es 100 % manual del dueño (Claude no
commitea, no pushea, no deploya — solo lee git); todo vive en la rama `feat/ToDeploy` y `main` no
se toca; Python siempre con `.venv/bin/python` (el `python3` del sistema está roto para este repo);
todo número publicado en docs tiene que estar medido, no estimado.

---

## Session — 2026-07-05 → 2026-07-06

### Resumen: qué se hizo

Se ejecutaron **Fase 0 completa**, las **partes locales de Fase 1** y **Fase P completa**, todo en
local y sin commitear (el dueño versiona cuando decida). Además se endurecieron los 8 planes para
que ninguna casilla de DoD asuma push/deploy automático (todo deploy espera acción manual del dueño).

**Fase 0 — Base profesional (9/9 tareas; DoD tildada en `fase-0-base-profesional.md`):**
- Reproducibilidad: pins de torch con markers por plataforma + `requirements-dev.txt` (pytest/httpx/ruff).
  **Desvío resuelto:** el marker del plan (`sys_platform == "linux"`) rompía Docker en Apple Silicon;
  el marker final restringe `+cpu` a `linux and x86_64`. Verificado en venv limpio fuera del repo
  (install → suite → evaluator reproduce métricas → `/health`).
- Los 5 bugs de correctness arreglados con tests: (a) fecha validada con `strptime` real en ingest;
  (b) `/ingest` pasó a `def` (threadpool) — verificado en vivo: `/health` respondió en 1–13 ms durante
  un ingest real de 4.9 s; (c) escrituras atómicas tmp+`os.replace` para artifacts y `metadata.json`
  (helper `_atomic_write_json` en `src/indexer.py`, index FAISS se escribe último); (d) nueva
  `TraceAccountingError(RuntimeError)` → el invariante roto da 500, no 400; (e) bounds de API
  (`top_k` 1–50, `query` 1–2000).
- Dead code borrado: `src/context_assembler.py`, `apply_freshness`, `filter_by_role` y sus tests
  skipped (eran exactamente los 14 skips).
- Eval A/B: `run_evals(..., policy_name=...)` + CLI `python -m src.evaluator --compare`.
  **Número headline medido: naive_top_k 50 % de violation rate → full_policy 0 %** (también P@5
  0.2833 → 0.3333 y ~27 % menos tokens). En el README con tabla.
- Docs honestos: P@5 0.3333 reframeado como techo teórico con footnote del clamping; conteos de
  suite corregidos; links rotos eliminados.
- Limpieza: `docs/` quedó en `architecture.md` (destilado nuevo verificado contra el código) +
  `demo-guide.md`; el resto fue a `docs/archive/`. `frente_3_querytrace.md` movido a `~/Desktop/`
  (fuera del repo) y gitignoreado. `LICENSE` MIT. `.gitignore` += `test-results/`.
- CI: `.github/workflows/ci.yml` (push a cualquier rama + PRs, matrix 3.9/3.11, caches de pip/HF/
  tiktoken, ruff → pytest → `evaluator --compare` como smoke). `pyproject.toml` con config de ruff;
  14 hallazgos arreglados.
- Docker: `python:3.11-slim`, modelo y encoding pre-descargados en build, non-root, HEALTHCHECK.
  **Verificado local:** build OK; contenedor con `ALLOW_INGEST=false` responde `/health`, `/query`,
  `/app/`; `/ingest` → 403. `.dockerignore` incluido.
- README final: badges (CI/Python/MIT), "Why this exists", quickstart, Known Limitations, roadmap.

**Fase 1 — partes locales (deploy en sí queda para el dueño):**
- OG tags + Twitter card con URLs absolutas en `frontend/index.html`; `frontend/favicon.svg` ("QT");
  `frontend/og-card.png` (1200×630, generado con Pillow, muestra el 50 %→0 %).
- `render.yaml` (Blueprint: Docker, `ALLOW_INGEST=false`, health check, rama `feat/ToDeploy`).
- Banner de cold-start en el frontend: si `/health` tarda >2.5 s aparece "Waking up the free-tier
  server (~45 s)…".

**Fase P — Modo producto (completa; DoD tildada en `fase-p-producto.md`):**
- `corpus/users.json`: julia/analyst (`demo-analyst`), victoria/vp (`demo-vp`), patricia/partner+admin
  (`demo-admin`). Passwords SHA-256 + `password_hint` público (deliberado, documentado).
- `src/auth.py`: sesión stateless con cookie firmada HMAC-SHA256 (`qt_session`, TTL 12 h, secret de
  `QUERYTRACE_SECRET_KEY` con default dev que loguea warning fuerte), rate limit de login 10/min por
  IP, `reset_rate_limiter()` para tests.
- Endpoints nuevos en `src/main.py`: `POST /login`, `GET /me`, `POST /logout`, `GET /personas`
  (cards del login con `docs_visible` y `password_hint`).
- Rol server-derived: con sesión, `role` sale de la cookie; body `role` contradictorio → 400.
  Sesiones no-admin fuerzan `full_policy` (policy contradictoria explícita → 400). Guests = lab intacto.
- Redacción del trace en el borde de la API: no-admin recibe `blocked_by_permission=[]` +
  `blocked_summary={count, required_roles}` (modelo nuevo `BlockedSummary`). Knob
  `BLOCKED_DISCLOSURE=count|titles` (default `count`). Admin y guest ven el trace completo.
- Capacidades: `/compare`, `/evals`, `/session-audit` → 403 para sesiones no-admin; `/ingest` exige
  sesión admin (401 guest / 403 no-admin) además del kill-switch `ALLOW_INGEST`. Audit con `user`
  por entrada; viewers no-admin la ven anónima (`user: null`).
- Frontend: pantalla de login con 3 persona cards + "Explore the Lab without signing in →" (guest
  path en `sessionStorage.qt_guest`); chip de identidad con Sign out; `body.product-mode` oculta
  selectores y modos de lab para no-admin; admin conserva todo (radios de rol bloqueados en Query,
  libres en Side-by-side, con nota); strip "🔒 N documents withheld · requires vp+" con popover
  "Why?" cuando la respuesta viene redactada. Botón Upload oculto salvo admin + ingest habilitado.
- Docs: tour de 3 minutos con credenciales arriba del README; Known Limitations actualizado
  (auth demo-grade con upgrade path OIDC); sección Fase P en CLAUDE.md.

### Estado actual

- **Rama:** `feat/ToDeploy` · **HEAD:** `5b3d58c` ("docs") — **TODO el trabajo de esta sesión está
  sin commitear en el working tree** (decisión del dueño).
- **Verificación (2026-07-05/06, todo local):** suite **238 passed / 0 skipped / 0 failed**
  (`.venv/bin/python -m pytest tests/ -q`); `ruff check src/ tests/` limpio; E2E Playwright del flujo
  Fase P: 7/7 checks (login 3 cards → guest intacto → julia product-mode con withheld strip y **cero
  doc_ids bloqueados en el DOM** → patricia admin sin redacción → radios liberados en compare);
  `node --check frontend/app.js` OK; `docker build` + run verificados; evaluator `--compare`
  reproduce 50 % → 0 %.
- **Progresión de conteos de suite (todos medidos):** 184+14 skips (inicio) → 198 (fixes F0) →
  201 (A/B evaluator) → **238** (Fase P). README y CLAUDE.md ya publican 238 (corregido al escribir
  este handoff, 2026-07-06).

### Commits sugeridos (el dueño los ejecuta, en este orden)

1. `F0: platform-aware torch pins + requirements-dev; README quickstart honesto` — `requirements.txt`, `requirements-dev.txt`
2. `F0: fix 5 correctness bugs (fecha real, ingest sync, escrituras atómicas, TraceAccountingError, bounds de API) con tests` — `src/ingest.py`, `src/main.py`, `src/indexer.py`, `src/stages/trace_builder.py`, `src/stages/__init__.py`, `src/models.py`, `tests/test_ingest.py`, `tests/test_indexer.py`, `tests/test_main.py`, `tests/test_stages.py`
3. `F0: remove dead code (context_assembler, apply_freshness, filter_by_role) — suite sin skips` — borrados + `src/freshness.py`, `src/policies.py`, `tests/test_freshness.py`, `tests/test_policies.py`
4. `F0: evaluator --compare (naive 50% vs full 0% violation rate) + docs honestos` — `src/evaluator.py`, `tests/test_evaluator.py`, `README.md`, `CLAUDE.md`
5. `F0: limpieza repo público — docs consolidados, archive/, LICENSE MIT, gitignore` — `docs/*`, `LICENSE`, `.gitignore` (+ `git rm -r --cached test-results/`)
6. `F0: CI GitHub Actions (3.9/3.11, ruff+pytest+eval smoke, caches) + lint fixes` — `.github/workflows/ci.yml`, `pyproject.toml`, `src/retriever.py`, `tests/test_models.py`, `tests/test_pipeline.py`, `tests/test_retriever.py`
7. `F0: Dockerfile CPU con modelo pre-descargado, non-root, healthcheck` — `Dockerfile`, `.dockerignore`
8. `F1: presentación local del deploy — OG tags, favicon, og-card, render.yaml, aviso cold-start` — `frontend/index.html`, `frontend/favicon.svg`, `frontend/og-card.png`, `render.yaml`, bloque cold-start en `frontend/app.js`/`styles.css`
9. `FP: modo producto — login con personas, rol server-derived, redacción de trace, upload solo admin` — `corpus/users.json`, `src/auth.py`, `src/main.py`, `src/models.py`, `frontend/{index.html,app.js,styles.css}`, `tests/test_auth.py`, `tests/test_ingest.py`, `README.md`, `CLAUDE.md`, `plansToPortfolio/*`

Nota: los commits 4/9 comparten `README.md`/`CLAUDE.md` y el 8/9 comparten los archivos del
frontend — si molesta separar hunks, es válido colapsar 8+9 en un solo commit de fase.

### Tareas restantes (en orden)

1. **Dueño:** commits + push a `feat/ToDeploy` → el primer push corre CI y confirma la última
   casilla de Fase 0 ("CI verde"); ahí la tabla de Estado pasa F0 a ✅.
2. **Dueño (Fase 1, cuando quiera deployar):** grabar GIF hero (~15 s, Compare mode, <3 MB) para el
   placeholder `<!-- TODO(Fase 1): demo GIF here -->` del README; en el dashboard de Render: servicio
   a Docker (o conectar `render.yaml`), env vars `ALLOW_INGEST=false` + `QUERYTRACE_SECRET_KEY`
   (¡nueva desde Fase P!), decidir D1/D2; correr la checklist de humo de `fase-1-deploy.md` §1.5;
   activar UptimeRobot.
3. **Siguiente fase a ejecutar: Fase 2 — workspaces genéricos** (`fase-2-workspaces.md`): migrar
   `corpus/` → `corpora/pe-deal/`, API por workspace retro-compatible, segundo corpus SaaS "Nimbus
   Analytics" (14 docs, 3 pares superseded, 12 evals, personas sofia/marcos/alex), picker en el
   frontend. Es la fase más grande (2–3 sesiones). Después: F4 (Ask mode) → F3 (ingesta pro) →
   F5 (opcional).

### Blockers y avisos

- **`docs/HANDOFF.md` resucitó en el working tree** (104 KB, mtime 2026-07-06 00:48, termina con un
  prompt del dueño "…SOLO LEE Y GENERA EL REPORTE"). La limpieza de Fase 0 lo había movido a
  `docs/archive/HANDOFF.md`; el dueño lo restauró/regeneró después, aparentemente para otra sesión
  de solo-lectura. **Decisión del dueño:** conservarlo donde está, borrarlo (la copia archivada
  existe), o re-moverlo. La sesión ejecutora NO lo tocó.
- **D6 (tabla de Decisiones del README):** el working tree tiene las skills de Claude Code borradas
  (`.agents/`, `.claude/skills/handoff/`) y `.gitignore` las ignora — contradice la nota del plan
  que dice conservarlas. Restaurar sería `git checkout -- .agents .claude` + quitar las entradas
  del `.gitignore`. Ojo: `.claude/skills/webapp-testing/` y `handoff/` se usaron esta sesión.
- **Decisión abierta:** ¿`plansToPortfolio/` entra al repo público como bitácora o se gitignorea?
  (Fase 0 §0.6.5; hoy está untracked.)
- **Pillow está instalado en `.venv` pero NO en ningún requirements** (se usó solo para generar
  `og-card.png`; el script vive en el scratchpad efímero de la sesión). Si hay que regenerar la
  card, reinstalar `pillow` y rehacer el script — o pedirlo, es corto.
- **`QUERYTRACE_SECRET_KEY`** debe setearse en cualquier deploy real (sin ella el server usa un
  default dev y loguea warning). Los tests no la necesitan.
- Los tests de login comparten el rate limiter in-process — cualquier test nuevo que llame
  `/login` repetidamente debe usar `auth.reset_rate_limiter()` (ver fixtures de
  `tests/test_auth.py` / `tests/test_ingest.py`).
- El E2E de Fase P (`test_fase_p.py`) vive en el scratchpad de la sesión (efímero). Si se quiere
  permanente, moverlo a `tests/e2e/` con un marker `@pytest.mark.e2e` fuera del run default —
  decisión pendiente, no bloquea nada.

### Primera acción sugerida para la próxima sesión

Leer `plansToPortfolio/README.md` (reglas) + este handoff; verificar con `git log` / `git status`
qué commiteó el dueño desde entonces (esta sesión dejó todo sin commitear); y arrancar **Fase 2**
con `fase-2-workspaces.md`, pasando su fila a 🔨 en la tabla de Estado.

---

## Session — 2026-07-06 (Fase 2: workspaces genéricos)

### Resumen: qué se hizo

Se ejecutó **Fase 2 completa en local** (4 tareas, en orden). 6/7 casillas de la DoD tildadas;
la única pendiente es "demo deployado" que espera push/deploy manual del dueño. La fila de F2 en
la tabla de Estado quedó 🔨 con esa nota.

**Tarea 1 — Migración + resolver + indexer/retriever por workspace:**
- Migración por filesystem (`mv`, no git — ver "Renames" abajo): `corpus/{documents,metadata.json,roles.json,users.json}` → `corpora/pe-deal/`, `evals/test_queries.json` → `corpora/pe-deal/evals.json`, `artifacts/{querytrace.index,index_documents.json,bm25_corpus.json}` → `artifacts/pe-deal/` (byte-idénticos: git detecta renames al stagear).
- Nuevo `corpora/pe-deal/workspace.json` (manifiesto: doc_types, role_hints, scenarios y example_queries extraídos textualmente del HTML que estaba hardcodeado).
- Nuevo `src/workspaces.py`: `get_workspace(slug|None)` cacheado con lock, `list_workspaces()`, `invalidate_workspace_cache()`, `default_workspace()` (env `QUERYTRACE_DEFAULT_WORKSPACE`, default `pe-deal`), validación de slug `^[a-z0-9-]{1,40}$` ANTES de tocar filesystem (`InvalidWorkspaceSlug`→400 / `WorkspaceNotFound`→404) + test de que la validación corre antes de cualquier I/O.
- `src/indexer.py` (todas las funciones toman workspace; CLI `--workspace`, sin flag = todos), `src/retriever.py` (`_bm25` dict por slug; modelo global corpus-independiente; `invalidate_caches(slug)`), `src/ingest.py` (frozensets `VALID_MIN_ROLES`/`VALID_DOC_TYPES` muertos → validación contra roles.json + manifest del workspace; invalida el cache del resolver antes de reindexar), `src/auth.py` (users por workspace; token con claim `workspace`), `src/evaluator.py` (`run_evals(..., workspace)` + CLI `--workspace`).

**Tarea 2 — API por workspace:**
- `workspace` opcional en `QueryRequest`/`CompareRequest`/`LoginRequest` (+ form field en `/ingest`); requests sin workspace → default (compat verificada con test implicit-vs-explicit).
- `main.py` sin estado de corpus a nivel módulo: resolución por request. Endpoints nuevos `GET /workspaces` y `GET /workspaces/{slug}/meta` (roles con `docs_visible` COMPUTADO desde metadata, doc_types, scenarios, example_queries, personas sin hashes).
- Sesión ligada a UN workspace: cookie de otro workspace → **403** (nunca remapeo silencioso); cookies pre-F2 (sin claim) resuelven al default. `/evals?workspace=` con cache por slug (`_evals_cache: dict`); audit con `workspace` por entrada (ids `qNNN` globales, benchmark_count del default); `/ingest` exige que el workspace del admin coincida con el target; `/health` expone `default_workspace`.
- **Desvío documentado:** el knob `blocked_disclosure` pasó al `workspace.json` como fuente primaria, pero el env `BLOCKED_DISCLOSURE` se CONSERVÓ como override operativo (el plan decía "pasa del env al manifest"; se implementó manifest-first + env override para no romper el test de Fase P y mantener la palanca de ops).

**Tarea 3 — Frontend dinámico:**
- Picker de workspace en header + en pantalla de login; switch persiste `sessionStorage.qt_workspace` y hace `location.reload()` (mismo patrón que login); si hay sesión de otro workspace, hace logout primero y cae en el login del nuevo.
- TODO lo corpus-específico se renderiza desde `/meta`: radios de rol ("Sees N of M docs" computado), `ROLE_DESCRIPTIONS`/`ROLE_RANKS` reconstruidos por workspace, onboarding cards (Single dual-action + Compare compactas), filas de ejemplos, placeholder del buscador, descripción del empty state, personas del login, selects min_role/doc_type del Upload. `.example-btn` pasó a delegación a nivel document (los botones se re-renderizan). Todas las llamadas llevan `workspace`. Chip de sesión muestra `rol · workspace`. `FALLBACK_META` para server caído (deja el form usable y el error card de "Backend unavailable" alcanzable).

**Tarea 4 — Segundo corpus "Nimbus Analytics" (saas-internal):**
- 14 docs (6 employee / 4 manager / 4 exec), 3 pares superseded: runbook v1→v2 (failover manual 45min → automatizado 8min), comp bands 2023→2024 (bandas +8-9%, bonus 8%→10%, geo tiers), roadmap draft→final (EU residency adelantada a Q3, mobile replay cortado). Universo de hechos consistente (helios-db, Skyhook, Prism, Gatekeeper, outage 4-mar-2024 con $214K en créditos SLA, Project Alpine como memo exec-only de layoff contingency).
- **Desvío documentado:** docs de ~250 palabras c/u (~3.6K total), NO las ~500-900 del plan — los docs reales del corpus PE tienen ~250 y el criterio del plan era "generados como los del corpus PE"; longitudes 2-3× habrían cambiado el comportamiento del budget packer en las demos.
- `roles.json` (employee 1 < manager 2 < exec 3), `users.json` (sofia/demo-employee, marcos/demo-manager, alex/demo-admin exec+is_admin), `evals.json` (12 queries espejando la estructura PE con expected+forbidden), `workspace.json` (3 escenarios: Permission Wall salary-bands / Stale Runbook / Roadmap Drift + 3 example_queries; hints con números MEDIDOS: la wall bloquea 8, naive surface 14).
- Artifacts generados y listos para versionar: `artifacts/saas-internal/{querytrace.index,index_documents.json,bm25_corpus.json}`.
- Visibilidad por rol: employee 6/14, manager 10/14, exec 14/14.
- Tests nuevos (test_workspaces.py, 65 tests): aislamiento saas↔pe (afirmado por títulos/contenido — **los doc_ids son namespaces por workspace y colisionan por diseño**, igual que el generador de ids del ingest), roles no cruzan (partner inválido en saas → 400), sesión cruzada real julia→saas 403 / sofia→pe 403, sofia login+query OK, wall de comp bands, 3 pares stale demotan, evaluator saas full 0% / naive >0%, `/evals?workspace=` sirve saas, vocabularios de ingest por workspace.
- Docs actualizados con números medidos: README (tabla A/B de ambos corpora, sección Workspaces, personas de ambos, API, estructura, 296 tests), CLAUDE.md (sección Workspaces + todos los endpoints/frontend/deploy), docs/architecture.md y docs/demo-guide.md (rutas).

### Métricas medidas (2026-07-06, local)

| Workspace | naive viol. rate | full viol. rate | P@5 naive→full | tokens naive→full | recall |
|---|---|---|---|---|---|
| pe-deal (16 docs) | 50% | **0%** | 0.2833→0.3333 | 1974→1448 | 1.0 |
| saas-internal (14 docs) | 58% | **0%** | 0.2500→0.2667 | 1934→1262 | 1.0 |

### Estado actual

- **Rama:** `feat/ToDeploy` · **HEAD:** `5b3d58c` — TODO sigue sin commitear (F0+F1+FP de la sesión anterior + F2 de esta, decisión del dueño).
- **Verificación (2026-07-06, todo local):** suite **296 passed / 0 skipped** (`.venv/bin/python -m pytest tests/ -q`; progresión medida: 238 → 265 (T1) → 281 (T2) → 296 (T4)); `ruff check src/ tests/` limpio; `node --check frontend/app.js` OK; E2E Playwright **23/23** (T3: bootstrap dinámico, guest, julia product-mode con withheld strip y cero doc_ids en DOM, patricia admin con selects dinámicos) + **17/17** (T4: picker con ambos workspaces, personas saas en login, roles/escenarios saas, wall con 8 bloqueados, switch ida y vuelta, sofia product-mode sin leak de comp bands); evaluator reproduce 50%→0% (pe-deal) y 58%→0% (saas-internal).

### Renames para el dueño (git los detecta al stagear; contenido byte-idéntico)

```
corpus/documents/*            → corpora/pe-deal/documents/*
corpus/metadata.json          → corpora/pe-deal/metadata.json
corpus/roles.json             → corpora/pe-deal/roles.json
corpus/users.json             → corpora/pe-deal/users.json   (estaba untracked — aparece directo en el destino)
evals/test_queries.json       → corpora/pe-deal/evals.json
artifacts/querytrace.index    → artifacts/pe-deal/querytrace.index
artifacts/index_documents.json→ artifacts/pe-deal/index_documents.json
artifacts/bm25_corpus.json    → artifacts/pe-deal/bm25_corpus.json
```

### Commits sugeridos (F2, después de los 9 de la sesión anterior)

1. `F2: migrate corpus → corpora/pe-deal + workspace resolver; per-workspace indexer/retriever/ingest/evaluator` — renames de arriba, `corpora/pe-deal/workspace.json`, `src/workspaces.py`, `src/{indexer,retriever,ingest,auth,evaluator,main}.py`, `Dockerfile`, `tests/{test_workspaces,test_retriever,test_evaluator,test_ingest,test_policies,test_pipeline,test_stages}.py`
2. `F2: workspace-scoped API — /workspaces + /meta, sesión ligada a workspace, evals cache por slug, audit con workspace` — `src/{main,models}.py`, `tests/{test_workspaces,test_ingest,test_auth}.py`
3. `F2: frontend dinámico por workspace — picker, roles/escenarios/personas desde /meta` — `frontend/{index.html,app.js,styles.css}`
4. `F2: segundo corpus saas-internal (Nimbus Analytics) — 14 docs, 3 pares superseded, 12 evals, artifacts, tests de aislamiento; docs con métricas de ambos workspaces` — `corpora/saas-internal/*`, `artifacts/saas-internal/*`, `tests/test_workspaces.py`, `README.md`, `CLAUDE.md`, `docs/{architecture,demo-guide}.md`, `plansToPortfolio/*`

**Aviso de secuenciación:** los commits F0/F1/FP sugeridos por la sesión anterior comparten archivos con F2 (`src/main.py`, `src/models.py`, `src/auth.py`, `frontend/*`, `README.md`, `CLAUDE.md`, tests). Como el working tree ya contiene TODO junto, separar por fase exige staging por hunks (`git add -p`); si un commit "FP" incluye las versiones post-F2 de esos archivos, ese commit intermedio no bootea (importa `src.workspaces` y `corpora/` llega recién en el commit F2-1). Opciones: (a) hunk-surgery siguiendo las listas por fase (histórico limpio, laborioso), (b) aceptar commits intermedios no booteables (tip verde igual), o (c) colapsar FP+F2 (o todo) en menos commits. Decisión del dueño.

### Blockers y avisos

- **Pendiente del dueño (única casilla abierta de F2):** push a `feat/ToDeploy` + deploy en Render → verificar el picker con los dos mundos en el demo público (checklist de humo de fase-1 aplica). Recordar `QUERYTRACE_SECRET_KEY` y decidir `ALLOW_INGEST`.
- Los E2E de esta sesión (`test_t3_e2e.py`, `test_t4_e2e.py`) viven en el scratchpad efímero de la sesión — mismo status que el E2E de Fase P (mover a `tests/e2e/` con marker si se quieren permanentes; no bloquea).
- `docs/HANDOFF.md` (104 KB, en la raíz de docs/) sigue donde estaba — esta sesión tampoco lo tocó (pendiente de decisión del dueño desde la sesión anterior).
- D6 (skills borradas en working tree vs nota del plan) sigue abierta — sin cambios.
- El `.gitignore` de artifacts (`artifacts/*.faiss|*.pkl|*.npy`) no matchea los artifacts por-workspace (`artifacts/<slug>/…`) — igual que antes: los tres archivos por workspace se versionan.

### Primera acción sugerida para la próxima sesión

Verificar con `git log`/`git status` qué commiteó el dueño; si F2 ya está versionada y deployada, tildar la última casilla de la DoD y pasar F2 a ✅ en la tabla de Estado. Siguiente fase del roadmap: **Fase 4 — Ask mode (RAG completo)** (`fase-4-ask-mode.md`), recomendada antes que F3; requiere resolver D3 (`ANTHROPIC_API_KEY` en el deploy).

---

## Session — 2026-07-06 (Fase 4: Ask mode — RAG completo)

### Resumen: qué se hizo

Se ejecutó **Fase 4 en local**: `/ask` cierra el loop RAG con un LLM real (Claude, SDK `anthropic`),
citas `[doc_id]` validadas mecánicamente y el decision trace viajando con cada respuesta. 3/6
casillas de la DoD tildadas; las 3 restantes **bloquean en la `ANTHROPIC_API_KEY` del dueño**
(no hay key en esta máquina ni pasó nunca por Claude — regla del plan). La fila de F4 quedó 🔨
con ese detalle.

**Tarea 1 — Backend (`src/ask.py` + `POST /ask`):**
- `src/ask.py` nuevo, todo puro salvo `call_model()` (único touchpoint de red; tests mockean
  `_get_client`): `build_prompt()` (system context-only + bloques `<doc id= title= date= type=>`
  con el contenido EXACTO que empaquetó el budget packer), `extract_citations()` (regex
  `\[(doc_\d+)\]`, dedup en orden, `valid` ⟺ id ∈ contexto del prompt), cache TTL por
  `(workspace, query normalizada, role, policy, top_k)` (default 1 h, 256 entradas), rate limiter
  per-IP (`X-Forwarded-For`) + global calcado del de login, `trim_to_context_cap()` (doble
  cinturón sobre el budget de 2048), mapeo de errores del SDK → `AskUpstreamError` → **502 sin
  stack** (timeout / conexión / 5xx / 429 provider / key inválida, mensajes aptos para UI pública).
- `POST /ask` en `main.py` (def → threadpool, como /ingest): request = `QueryRequest`; orden de
  gates: **flag 403 → sesión/workspace/rol (Fase P/2 idénticas a /query) → cache → rate limit 429
  → run_pipeline() → modelo 502**. El cache guarda la respuesta SIN redactar y
  `_redact_trace_for_viewer` se aplica per-viewer al servir (guest y julia comparten entrada y ven
  traces distintos — testeado). `/health` expone `ask_enabled` (= hay key; sacarla es el
  kill-switch). `_to_chunks()` des-duplicó el mapeo IncludedDocument→DocumentChunk de
  /query//compare//ask. Modelos nuevos: `Citation`, `AskUsage`, `AskResponse` (superset de
  QueryResponse incl. `total_tokens` para reusar el render del frontend).
- Modelo default **`claude-haiku-4-5`** (alias vigente verificado contra la referencia de la API
  al implementar, como exigía el plan; $1/$5 por MTok). Knobs por env: `ASK_MODEL`,
  `ASK_MAX_TOKENS` (600), `ASK_TEMPERATURE` (0.2; `none` la omite), `ASK_TIMEOUT_SECONDS` (30),
  `ASK_MAX_PER_MINUTE` (6/IP), `ASK_MAX_PER_MINUTE_GLOBAL` (30), `ASK_CACHE_TTL_SECONDS` (3600),
  `ASK_MAX_CONTEXT_TOKENS` (4096). Dep nueva: **`anthropic==0.116.0`** (pineada: py3.9 local y
  py3.11 CI/Render deben resolver lo mismo).
- **El test de seguridad de la fase** en dos niveles: unit (pipeline real como analyst → ningún
  excerpt ni id de doc bloqueado aparece en el prompt) y API (julia logueada → se captura el
  prompt que llega al cliente fake → cero contenido vp/partner). + shape, cache hit (2º call no
  llama al cliente), 429, XFF por IP, 5 errores de provider → 502, rol/policy/workspace de sesión,
  redacción desde cache. `tests/test_ask.py`: **37 tests** (33 de T1, 4 de T3).

**Tarea 2 — Frontend:**
- Botón **✦ Ask AI** junto a Run (`#ask-btn`), oculto salvo `ask_enabled` && modo Single
  (`updateAskButtonVisibility()` en bootstrap y en cada `switchMode`). `runAsk()` reusa las reglas
  de body de /query (sesión → sin role; no-admin → sin policy) y renderiza el resultado normal
  (`renderSingleResult` — AskResponse es superset) + `.ask-panel` arriba: respuesta con citas como
  chips (válidas = botones que scrollean y pulsan `.card-highlight` sobre la
  `.result-card[data-doc-id]`; inválidas rojas tachadas con tooltip), badge "Grounded in N docs ·
  M blocked docs never reached the model", nota mono de uso (modelo · tokens in/out · "served
  from cache"). Errores 403/429/502 por el error card estándar. CSS con tokens existentes +
  `prefers-reduced-motion`; `.ask-panel` participa del fade stale (UI-B).
- **E2E Playwright 19/19** (script en scratchpad efímero, como los E2E de FP/F2): sin key →
  oculto; con key → visible solo en Single; happy path con `/ask` interceptado (panel, chips,
  highlight, badge, usage); **502 real** con key dummy (mensaje amable, sin traceback); julia
  product-mode (botón visible, badge cuenta bloqueados, withheld strip sin títulos). Gotchas del
  E2E que valen para el futuro: navegar a `localhost:8000` (no `127.0.0.1` — API_BASE hardcodea
  localhost y la cookie es cross-origin si no coinciden) y el server E2E DEBE ir en el puerto 8000.

**Tarea 3 — Evals de fidelidad + goldens:**
- `run_ask_evals()` en `src/evaluator.py` (mismo code path que /ask vía `_ask_once` compartido):
  **citation_validity_rate** (válidas/total, objetivo 100 %), **groundedness_rate** (≥1 cita
  válida), **expected_cited_rate** (expected ∩ citadas), tokens totales. CLI `--ask` (opt-in,
  hard-fail sin key con mensaje de costo) escribe snapshot fechado a
  `evals/results/ask-YYYY-MM-DD-<slug>.json`.
- `run_ask_goldens()` / `--ask-goldens`: llena `corpora/pe-deal/ask_goldens.json` — spec de **3
  pares mismo-query-distinto-rol** verificados contra metadata.json: IC recommendation
  (analyst vs partner, doc_010 partner-only), valuation (analyst = rumor doc_015 vs vp = modelo
  v2 doc_008), customer concentration (analyst vs vp, doc_012 vp-only). `snapshots: null` hasta
  la primera corrida keyed — sin números inventados.
- Tests con `call` fake inyectado: validity 1.0 cuando cita el contexto, 0.0 con cita fabricada,
  goldens arma pares por rol sin escribir (write=False), CLI exige key (SystemExit 2, sin red).

**Tarea 4 — Docs:**
- README: sección "Ask mode" (qué es, demo asesina, tabla de knobs, guardrails, evals de
  fidelidad — SIN métricas inventadas: el número de validity se publica recién con la corrida del
  dueño), upgrade del minuto 2 del tour, /ask en API, bullet de Query mode, Known Limitations
  (prompt injection honesto + guardrails in-process), tech stack, estructura, conteos 296→333.
- CLAUDE.md: sección "Ask endpoint" completa + comandos + health + frontend + env vars de deploy.
  docs/architecture.md: sección Ask mode + tabla API (+ fix de un conteo viejo "201" → 333).
- `render.yaml`: `ANTHROPIC_API_KEY` y `QUERYTRACE_SECRET_KEY` declaradas con `sync: false` (valor
  solo en el dashboard, nunca en el repo).

### Métricas/verificación (2026-07-06, todo local)

- Suite: **333 passed / 0 skipped** (progresión medida: 296 → 329 (T1) → 333 (T3));
  `ruff check src/ tests/` limpio; `node --check frontend/app.js` OK; E2E Playwright **19/19**.
- `python -m src.evaluator --compare` sigue reproduciendo exactamente los baselines publicados
  (pe-deal 50 % → 0 %, P@5 0.2833 → 0.3333, tokens 1974 → 1448) — sin regresión del refactor CLI.
- `--ask` sin key: error claro de argparse con nota de costo, exit 2, cero red.

### Commits sugeridos (F4, después de los 9 de FP/F0 y los 4 de F2)

1. `F4: Ask mode backend — POST /ask con citas validadas, cache TTL, rate limit y kill-switch por env` — `src/ask.py`, `src/models.py`, `src/main.py`, `tests/test_ask.py`, `requirements.txt`
2. `F4: Ask AI frontend — botón feature-flagged, panel con citas clickeables, badge de grounding` — `frontend/{index.html,app.js,styles.css}`
3. `F4: evaluator --ask (citation fidelity) + --ask-goldens; spec de goldens pe-deal` — `src/evaluator.py`, `corpora/pe-deal/ask_goldens.json` (+ comparte `tests/test_ask.py` con el commit 1 — válido colapsar 1+3)
4. `F4: docs Ask mode (README/CLAUDE/architecture) + render.yaml env vars` — `README.md`, `CLAUDE.md`, `docs/architecture.md`, `render.yaml`, `plansToPortfolio/*`

Mismo aviso de secuenciación que dejó F2: el working tree acumula F0+F1+FP+F2+F4 sin commitear y
varios archivos se comparten entre fases (`src/main.py`, `src/models.py`, `README.md`, `CLAUDE.md`,
`frontend/*`); separar por fase exige `git add -p` o colapsar.

### Tareas restantes (en orden)

1. **Dueño:** commits + push (CI verde cierra F0; el deploy con el picker cierra F2).
2. **Dueño (cierra F4, ~USD 0.10 total con Haiku):** exportar su `ANTHROPIC_API_KEY` local y
   correr `python -m src.evaluator --ask-goldens` (llena los snapshots medidos de los 3 goldens)
   y `python -m src.evaluator --ask` (mide citation validity y deja el snapshot en
   `evals/results/`); publicar ese número en la sección Ask del README + sacar la captura
   lado-a-lado (julia vs patricia con la query del IC). En Render: cargar `ANTHROPIC_API_KEY` en
   el dashboard (render.yaml ya la declara) y probar el 429 en prod (7 asks distintos en <60 s).
3. **Siguiente fase a ejecutar: Fase 3 — Ingesta pro** (`fase-3-ingesta-pro.md`), última del
   roadmap principal antes de F5 (opcional).

### Blockers y avisos

- Los heredados siguen sin cambios: `docs/HANDOFF.md` resucitado en la raíz de docs/ (decisión del
  dueño pendiente), D6 (skills borradas vs nota del plan), ¿`plansToPortfolio/` entra al repo?,
  Pillow fuera de requirements, `QUERYTRACE_SECRET_KEY` en deploys reales.
- **`anthropic==0.116.0` quedó pineada en requirements.txt** — al hacer bump, verificar que la
  misma versión resuelva en py3.9 (local) y py3.11 (CI/Render).
- `evals/results/` no existe hasta la primera corrida de `--ask` (se crea solo; hoy no hay nada
  que commitear ahí).
- Los tests de /ask setean `ANTHROPIC_API_KEY=test-key-not-real` vía monkeypatch y mockean
  `_get_client` — CI no necesita secrets ni red. El E2E de Ask (`test_ask_e2e.py`) vive en el
  scratchpad efímero de la sesión, mismo status que los E2E de FP/F2 (mover a `tests/e2e/` con
  marker si se quieren permanentes; no bloquea).
- `/ask` no registra entradas en `/session-audit` (el audit documenta `/query`); extenderlo es un
  follow-up opcional anotado en el plan de F4.

### Primera acción sugerida para la próxima sesión

Verificar con `git log`/`git status` qué commiteó/deployó el dueño; si corrió `--ask`/`--ask-goldens`
con su key, publicar el citation validity medido en el README y tildar las casillas 4–5 de la DoD
de F4 (la 6 cae con el deploy). Después arrancar **Fase 3 — Ingesta pro** (`fase-3-ingesta-pro.md`),
pasando su fila a 🔨 en la tabla de Estado.

---

## Session — 2026-07-06 (Fase 3: Ingesta pro)

### Contexto de arranque

`git log` confirmó HEAD sin moverse (`5b3d58c`) — el dueño no commiteó ni deployó nada desde la
sesión de F4. Tampoco corrió `--ask`/`--ask-goldens` (no existe `evals/results/`, los goldens siguen
`snapshots: null`, sin `ANTHROPIC_API_KEY` en el entorno) → **las casillas 4–6 de F4 siguen
bloqueadas, sin números inventados**. Se ejecutó Fase 3 completa (Etapas A–D; la E es stretch
declarado y no se hizo).

### Resumen: qué se hizo

**Etapa A — Robustez del ingest (`src/ingest.py`, `src/main.py`):**
- `extract_text(file_bytes, filename)` dispatcher multi-formato: .pdf (pdfplumber), .txt (UTF-8 →
  latin-1), .md (frontmatter YAML stripped), .docx (`python-docx==1.2.0`, dep nueva pineada,
  resuelve igual en py3.9 y py3.11). Mínimo 50 chars extraídos para todos.
- `check_magic_bytes`: `%PDF-` en el primer KB / firma ZIP `PK\x03\x04` / sin NUL ni firmas
  binarias para texto → extensión mentirosa = **415**, no crash del parser.
- Tamaño: gate por `Content-Length` (413 antes de leer el body, con 64 KB de overhead multipart) +
  lectura en chunks de 1 MB con tope duro en `MAX_UPLOAD_BYTES` (10 MB; alias `MAX_PDF_BYTES` se
  conserva). El check de `len(file_bytes)` en ingest queda como segundo cinturón.
- Dedup: `compute_content_hash` (sha256 sobre texto whitespace-collapsed + lowercased) guardado
  como `content_hash` en metadata → re-upload idéntico = **409 nombrando el doc_id existente**
  (entradas pre-F3 sin hash nunca matchean). **Desvío:** el check de content-type se eliminó (no
  extendió) — spoofeable e inconsistente entre browsers; extensión + magic bytes son el contrato.

**Etapa B — Jobs asíncronos (`src/jobs.py` nuevo, split de ingest, endpoints):**
- Ingest partido en `prepare_ingest()` (sincrónico: validación/extracción/hash/dedup temprana —
  todos los 4xx salen en el request) y `finalize_ingest(prepared, on_stage)` (pesado: bajo lock,
  re-check de dedup autoritativo, persistencia + reindex). `ingest_document()` sigue existiendo
  como composición sincrónica (tests + CLI).
- `src/jobs.py`: `JobStore` (dict+lock, retención 50, `queued→extracting→embedding→indexing→
  done|failed`) + `ThreadPoolExecutor(max_workers=1)` que **serializa** los reindex. Tests usan
  `jobs.configure(run_inline=True)` + `reset_jobs()`. Trade-off threads-vs-Celery documentado en
  el docstring del módulo y en Known Limitations del README.
- `POST /ingest` → **202 `IngestAccepted{job_id, state, workspace}`**; `GET /ingest/jobs/{id}` y
  `GET /ingest/jobs` (newest first, solo el workspace de la sesión) con gates admin 401/403/403
  cross-workspace/404 expirado. Modelos nuevos: `IngestAccepted`, `IngestJobError`,
  `IngestJobStatus` (`src/models.py`). `build_and_save(..., on_stage=)` reporta estados reales.
- **Rollback testeado:** si el job falla después de escribir el .txt/entrada de metadata, ambos se
  revierten (fix del hallazgo de huérfanos de la auditoría).
- Frontend: `uploadDocument()` postea → 202 → poll de 1 s al job → 4 dots de progreso con labels
  humanos (`.job-progress`/`.job-step` en styles.css, reduced-motion safe) → success/error.
  `accept` del input ampliado a los 4 formatos.
- **E2E medido (server real):** POST /ingest → **202 en 224 ms** (antes el request colgaba el
  rebuild entero); `/health` respondió 3–10 ms DURANTE el job; duplicado → 409 sync; doc
  retrievable post-job; extensión mentirosa → 415. Playwright **6/6** sobre la UI (dots de
  progreso, success con doc_id y conteo, 409 en la UI). pe-deal restaurado byte-idéntico después
  de cada corrida (backup en scratchpad efímero).

**Etapa C — Indexado incremental O(N)→O(1) (`src/indexer.py`):**
- `add_document(workspace, entry, text, on_stage)`: embeddea SOLO el doc nuevo, `index.add()`,
  appendea payload (+`excerpt` de 500 chars) y fila BM25 (**desvío micro:** append en vez de
  re-tokenizar todo — equivalente y O(1)), escritura atómica de los 3 artifacts (index último).
  Fallback defensivo a `build_and_save()` si faltan artifacts o hay drift (conteos desalineados).
  Borrados/ediciones siguen siendo full rebuild (`IndexIDMap` anotado como upgrade path).
- `_embed_texts()` comparte el singleton del modelo con el retriever vía import lazy (un solo
  modelo en memoria, sin import circular). `finalize_ingest` usa `add_document`.
- **Números medidos (warm model, M-series, publicados en README/architecture/CLAUDE):** 16 docs:
  full 0.04 s vs add 0.009 s (~4×); 160 docs sintéticos: full 0.22 s vs add 0.010 s (**~21×**, el
  add queda plano en ~10 ms).

**Etapa D — CLI bring-your-own-corpus (`src/workspace.py` nuevo):**
- `python -m src.workspace create <slug> --from-dir DIR [--roles roles.json] [--name] 
  [--description]` + `list`. Crea `corpora/<slug>/` completo (manifest con `doc_types:
  ["document"]`, roles default viewer(1)<editor(2)<admin(3), `users.json` vacío) y pasa cada
  archivo por el MISMO `prepare_ingest`/`finalize_ingest` del upload HTTP (primer doc → rebuild
  fallback, resto incremental). Defaults: min_role = rank más bajo, date = mtime, title = filename
  humanizado. Duplicados e ilegibles → skip con warning; si nada es ingestable → borra el skeleton
  y exit 2; slug inválido/duplicado → error claro.
- Verificado con corrida real (2 docs → workspace `cli-demo` respondió `/query` y `/meta`,
  apareció en `list`; borrado después). Sin personas: se explora en modo guest/Lab (impreso en el
  summary del comando).

**Docs:** README (Upload bullet con números medidos, API con endpoints de jobs, sección "Bring
your own corpus", Known Limitations con el trade-off de la cola), CLAUDE.md (sección de ingest
reescrita: gates de A + jobs de B + incremental de C + CLI de D; comandos), docs/architecture.md
(pipeline de ingest en dos mitades + tabla API + CLI). Conteos 333 → 391 en todos los docs.

### Métricas/verificación (2026-07-06, todo local)

- Suite: **391 passed / 0 skipped** (progresión medida: 333 → 358 (A) → 376 (B) → 380 (C) → 391 (D));
  `ruff check src/ tests/` limpio; `node --check frontend/app.js` OK.
- E2E API del flujo async (script en scratchpad efímero): 202/224 ms, health responsivo, 409, 415,
  retrieval post-job, lista de jobs. Playwright UI **6/6**. CLI real verificada end-to-end.
- Tests nuevos: `tests/test_jobs.py` (18), `tests/test_workspace_cli.py` (11),
  `tests/test_indexer.py` +4 (add incremental/fallback/drift/stages), `tests/test_ingest.py`
  reescrito al contrato 202 + ~20 tests nuevos de A.

### Commits sugeridos (F3, después de los de FP/F0/F2/F4)

1. `F3a: ingest multi-formato (.pdf/.txt/.md/.docx) con magic bytes, caps de tamaño streaming y dedup 409 por content-hash` — `src/ingest.py`, `src/main.py`, `tests/test_ingest.py`, `requirements.txt`, `frontend/index.html`
2. `F3b: ingesta asíncrona — POST /ingest 202 + job store con worker único, rollback, endpoints de jobs y UI de progreso` — `src/jobs.py`, `src/ingest.py`, `src/main.py`, `src/models.py`, `tests/test_jobs.py`, `tests/test_ingest.py`, `frontend/{app.js,styles.css}`
3. `F3c: indexado incremental O(1) por documento con fallback por drift (medido: 21x a 160 docs)` — `src/indexer.py`, `src/ingest.py`, `tests/test_indexer.py`
4. `F3d: CLI bring-your-own-corpus — python -m src.workspace create/list` — `src/workspace.py`, `tests/test_workspace_cli.py`
5. `F3: docs — ingest async + incremental + CLI en README/CLAUDE/architecture; DoD y estado` — `README.md`, `CLAUDE.md`, `docs/architecture.md`, `plansToPortfolio/*`

Mismo aviso de secuenciación de siempre: el working tree acumula F0+F1+FP+F2+F4+F3 sin commitear;
los commits 1–3 comparten `src/ingest.py`/`src/main.py`/`tests/test_ingest.py` — si separar hunks
molesta, colapsar 1+2+3 en un commit F3 es válido.

### Tareas restantes (en orden)

1. **Dueño:** commits + push (CI verde cierra F0; deploy cierra la casilla de F2).
2. **Dueño (cierra F4):** correr `--ask-goldens` y `--ask` con su `ANTHROPIC_API_KEY`, publicar el
   citation validity medido en el README; key en Render + probar 429 en prod.
3. **Dueño (cierra F3):** en el deploy, decidir si habilita Upload (`ALLOW_INGEST` on + sesión
   admin) y probar un upload end-to-end en prod — única casilla abierta de F3. Ojo: en Render free
   el disco es efímero (uploads se pierden en cada deploy/restart; ya documentado).
4. **Siguiente fase (opcional): Fase 5 — Retrieval depth** (`fase-5-retrieval-depth.md`), la única
   restante del roadmap. Requiere decidir D5 (chunking real → regenerar todas las métricas).

### Blockers y avisos

- Los heredados siguen sin cambios: `docs/HANDOFF.md` resucitado en docs/ (decisión del dueño),
  D6 (skills borradas vs nota del plan), ¿`plansToPortfolio/` al repo público?, Pillow fuera de
  requirements, `QUERYTRACE_SECRET_KEY` en deploys reales, `anthropic==0.116.0` pineada.
- **`python-docx==1.2.0` es dep nueva de runtime** (requirements.txt) — el Dockerfile instala
  requirements completo, no requiere cambios; en un venv viejo hay que re-correr
  `pip install -r requirements.txt`.
- El contrato de `/ingest` cambió: **200 → 202 + job**. Cualquier cliente externo del endpoint
  (no hay ninguno conocido fuera del frontend) debe pasar a pollear `GET /ingest/jobs/{id}`.
- No hay `DELETE /ingest` todavía (la DoD lo menciona como "futuro DELETE"); sigue sin path de
  borrado/edición — full rebuild manual via `python -m src.indexer` si se toca el corpus a mano.
- Los E2E de esta sesión (`e2e_async_ingest.py`, `e2e_upload_ui.py`, scripts de medición) viven en
  el scratchpad efímero, mismo status que los E2E de FP/F2/F4 (mover a `tests/e2e/` con marker si
  se quieren permanentes; no bloquea).
- Los workspaces creados por CLI no tienen personas (`users.json` vacío) — se usan en modo guest.
  El login screen de un workspace sin usuarios muestra 0 cards (comportamiento esperado, no bug).

### Primera acción sugerida para la próxima sesión

Verificar con `git log`/`git status` qué commiteó/deployó el dueño (esta sesión otra vez dejó todo
sin commitear). Si hay deploy: tildar la casilla de F2 ("demo deployado"), la 6 de F3 (upload en
prod, si el dueño habilitó ingest) y las de F4 que dependan de la key. El roadmap principal
(F0→F4) está completo en local: queda **Fase 5 — Retrieval depth (opcional)** o el cierre de
decisiones abiertas (D1/D2/D5/D6, plansToPortfolio al repo, GIF hero de F1).

---

## Addendum — 2026-07-06 (misma sesión, más tarde): cierre keyed de F4

El dueño creó una API key de Console y la corrida keyed se hizo en esta sesión (la key entró por
el chat — **desvío de la regla "la key nunca pasa por Claude", decisión explícita del dueño**; se
le recomendó revocarla al terminar y usar una fresca para Render). Resultados:

- **`--ask-goldens`**: los 3 goldens quedaron MEDIDOS en `corpora/pe-deal/ask_goldens.json` — la
  historia sale perfecta: IC recommendation → analyst "cannot find" (cita doc_005/doc_015) vs
  partner "$340M proceed" (doc_010/doc_014); valuation → analyst/vp citan el rumor doc_015 ($500M);
  customer concentration → analyst sin acceso vs vp cita doc_012/doc_008.
- **`--ask`**: sobre el benchmark pe-deal con `claude-haiku-4-5` — **citation validity 100%,
  groundedness 100%, expected-cited 100%** (26,612 in / 2,909 out ≈ USD 0.04). Snapshot:
  `evals/results/ask-2026-07-06-pe-deal.json` (primer archivo del directorio — ahora existe y se
  versiona). Número publicado en la sección Ask del README.
- **DoD de F4: casillas 4 y 5 tildadas** (la captura de pantalla lado-a-lado sigue opcional);
  queda solo la 6 (deploy con key activa + 429 en prod). Tabla de Estado actualizada a 5/6.
- **Test ajustado**: `test_run_ask_goldens_builds_role_pairs_without_writing` asertaba
  `snapshots: null` en disco; ahora aserta que `write=False` deja el archivo byte-idéntico
  (los snapshots medidos viven legítimamente en el repo). Suite: **391 passed / 0 skipped**.

Commit sugerido adicional (después de los 5 de F3):
`F4: goldens medidos + citation validity 100% publicada (corrida keyed) — snapshots y README` —
`corpora/pe-deal/ask_goldens.json`, `evals/results/ask-2026-07-06-pe-deal.json`, `README.md`,
`tests/test_ask.py`, `plansToPortfolio/*`

Pendiente del dueño sobre la key: **revocar la key usada** (quedó en el transcript de la sesión)
y crear una nueva para cargar en el dashboard de Render cuando deploye.

---

## Session — 2026-07-11

### Resumen: qué se hizo

Se ejecutó la **Fase 5 (retrieval depth) — Etapas A y B completas**; la Etapa C (reranker) NO se
hizo (stretch opcional del plan; queda como roadmap declarado). Además se creó
`plansToPortfolio/detailsToComplete.md` consolidando todos los pendientes de fases anteriores
(decisiones D1/D2/D3/D6, operaciones de git del dueño, casillas que se tildan con el push/deploy).
D5 quedó resuelta (✅ se hizo el chunking). Suite final: **421 passed, 0 skipped** (391 → 421;
+5 embedder, +12 chunker, +13 chunking-pipeline), ruff limpio, evaluator --compare verde en ambos
workspaces. Todo verificado en local, sin commitear (git es del dueño).

**Etapa A — Embedder a ONNX (`fastembed==0.7.4`):**
- `src/embedder.py` nuevo: única costura al runtime de inferencia (`embed(texts) -> np.ndarray`
  normalizado float32 384d, contrato testeado); indexer/retriever dejan de importar
  sentence-transformers. Variante verificada: fp32 `model.onnx` de `qdrant/all-MiniLM-L6-v2-onnx`.
- requirements: fuera torch/transformers/sentence-transformers (+ el extra-index de pytorch y el
  marker por plataforma); entra `fastembed==0.7.4`. torch desinstalado del venv y la suite corre
  sin él (2.4 s vs ~30 s antes — ya no carga torch).
- Gate del plan pasado con el harness: pe-deal IDÉNTICO (P@5 0.3333, recall 1.0, viol 0%);
  saas-internal P@5 full 0.2667→0.2500 (−0.017, dentro de ±0.02). Causa del delta: el tokenizer
  ONNX trunca a 512 tokens vs 256 de torch (cos=1.000000 en textos cortos, ~0.85 en docs largos —
  el ONNX ve MÁS documento). Documentado en README.
- **Medido:** imagen Docker 1.92 GB → **980 MB** (build real + smoke: /health listo en 0.5 s,
  /query 0.39 s, /app/ 200, contenedor `querytrace:onnx`); carga fría del modelo 0.47 s;
  site-packages 555 MB con onnxruntime 60 MB. Dockerfile: pre-download vía fastembed con
  `FASTEMBED_CACHE_PATH=/opt/fastembed_cache` (sin cp de caches); CI: cache
  `~/.cache/fastembed`, env vars con paths concretos (el `~` no se expandía).
- D2 (cold start Render) queda para revisar: el dolor era torch; medir en el deploy real.

**Etapa B — Chunking real:**
- `src/chunker.py`: párrafos → merge greedy a ~350 tokens (tiktoken cl100k, el mismo del packer),
  overlap ~15%, fallback a oraciones y ventanas de tokens; `chunk_id = doc_NNN#cNN`, offsets de
  char exactos contra el texto original (12 tests incl. corpus real).
- Indexado: UNA fila FAISS/BM25 por chunk; payload hereda metadata del doc padre + texto completo
  del chunk como `excerpt` (muere el teaser de 500 chars). `add_document` incremental chunkea
  también. pe-deal: 16 docs → 28 chunks; saas: 14 → 28.
- Identidad de chunk aditiva en models (`chunk_id/chunk_index/chunk_count` opcionales en toda la
  cadena; `doc_id` SIEMPRE es el padre → permisos/freshness/evals/citas sin cambios de clave).
- **H4 resuelto:** `top_k` = máximo de DOCS ÚNICOS en el contexto final (cap en el packer,
  `max_docs`; naive sin cap por diseño); el budget de tokens es el segundo límite. Documentado en
  README + architecture + docstring del packer, testeado.
- **Invariante del trace:** cuenta CHUNKS (blocked+included+dropped == retrieved); TraceMetrics
  suma `*_doc_count` derivados (docs únicos por bucket). Evaluator dedupea `assembled_ids` a docs
  padre (P@5/recall comparables pre/post); session audit y UI muestran conteos doc-level.
- Ask: `build_prompt` agrupa chunks hermanos en UN bloque `<doc>` por documento (citas siguen
  doc-level, sin ids duplicados); test de seguridad "blocked nunca entra al prompt" extendido a
  huellas por chunk.
- Over-retrieval 3×→6× (`retrieve_k = top_k*6`): compensa atrición de permisos + inflación de
  chunks (~2/doc). Sin esto el analyst quedaba con contexto flaco.
- **UI:** `groupContextByDoc()` — una card por doc (mejor chunk visible, expand muestra todos los
  chunks con separadores `[…]`), badge "matched N of M sections", chips del trace agrupadas con
  tooltip de chunk_ids y sufijo "·N chunks", sección de bloqueados dedupeada, narrativa y
  summary-bar con conteos doc-level; Compare agrupa igual. Verificado con Playwright en vivo
  (Single: 6 cards únicas, 10 blocked docs, 89% budget; Compare: naive 16/7151t vs full 6/2013t,
  0 errores JS).
- **Métricas regeneradas y publicadas** (tabla antes/después en README): pe-deal full P@5
  0.3333→0.3000, docs 11.83→6.67, tokens 1448→2017, budget util ~71%→98%; saas 0.2500 igual;
  recall 1.0 y violaciones 0% en ambos. Trade-off honesto documentado: menos docs con contenido
  real. Naive ahora empaqueta ~7000 tokens (baseline más visiblemente peligroso). Queries de
  contenido profundo: 2/3 aciertan vía chunk tardío (covenant doc_012, media contact doc_004);
  la de doc_010 pierde contra el draft casi-duplicado doc_014 — contado en README y en un test.

### Números publicados actualizados (todos medidos)

pe-deal: naive 50% viol / P@5 0.2667 / 16 docs / 7151 t → full 0% / 0.3000 / 6.67 / 2017.
saas-internal: naive 58% / 0.2667 / 14 / 6592 → full 0% / 0.2500 / 5.83 / 2022.
Imagen Docker 980 MB (−49%). Suite 421/0 en ~2.4 s.

### Archivos tocados

Nuevos: `src/embedder.py`, `src/chunker.py`, `tests/test_embedder.py`, `tests/test_chunker.py`,
`tests/test_chunking_pipeline.py`, `plansToPortfolio/detailsToComplete.md`.
Modificados: `src/indexer.py`, `src/retriever.py`, `src/models.py`, `src/pipeline.py`,
`src/stages/{permission_filter,freshness_scorer,budget_packer,trace_builder}.py`, `src/main.py`,
`src/ask.py`, `src/evaluator.py`, `requirements.txt`, `Dockerfile`, `.github/workflows/ci.yml`,
`frontend/app.js`, `frontend/styles.css`, `README.md`, `CLAUDE.md`, `docs/architecture.md`,
`tests/{test_retriever,test_indexer,test_stages,test_ask,test_workspace_cli}.py`,
`artifacts/{pe-deal,saas-internal}/*` (regenerados — el dueño los versiona),
`plansToPortfolio/{README,fase-5-retrieval-depth}.md`.

### Mensaje de commit sugerido

`F5: ONNX embedder (fastembed) + real chunking — 421 tests, evals regenerated, image 1.92GB→980MB`

### Pendientes que abre esta sesión (agregados a detailsToComplete.md)

- Los goldens de Ask (`corpora/pe-deal/ask_goldens.json`) y el snapshot
  `evals/results/ask-2026-07-06-pe-deal.json` se midieron PRE-chunking; siguen siendo mediciones
  válidas de esa fecha, pero si el dueño quiere números Ask post-chunking: corrida keyed de
  `--ask` / `--ask-goldens` (~USD 0.05).
- Etapa C (reranker) opcional; D2 revisar con el cold start real post-ONNX en Render.
