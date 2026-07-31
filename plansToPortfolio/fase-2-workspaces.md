# Fase 2 — Workspaces: de corpus ficticio único a motor multi-dominio

> El pipeline no cambia; lo que cambia es que el corpus, los roles y los tipos de documento dejan de
> estar hardcodeados. QueryTrace pasa de "demo de una financiera ficticia" a "traé tu organización".

**Depende de:** Fase 0, Fase 1 y **Fase P** (la sesión y las personas ya existen — esta fase las
multiplica por workspace) · **Esfuerzo:** 2–3 sesiones · **Resultado observable:** selector de
workspace en la UI con **dos corpus** (PE deal + SaaS interno), personas y roles dinámicos por
workspace, y aislamiento entre workspaces testeado.

**Por qué importa para el portfolio:** demuestra diseño config-driven, pensamiento multi-tenant y
modelado de datos — y duplica el demo gratis. La mayor parte del backend ya es data-driven
(roles vienen de `roles.json`, el filtro compara rangos); esta fase mata los hardcodes restantes.

---

## 2.1 Estructura de datos

```
corpora/
  pe-deal/                      ← el corpus actual, migrado tal cual
    workspace.json              ← manifiesto (nuevo)
    users.json                  ← personas demo del workspace (migra de corpus/users.json — Fase P)
    documents/*.txt
    metadata.json
    roles.json
    evals.json                  ← evals/test_queries.json actual
  saas-internal/                ← corpus nuevo (2.4)
    ...igual estructura
artifacts/
  pe-deal/{querytrace.index, index_documents.json, bm25_corpus.json}
  saas-internal/...
```

**`workspace.json` (manifiesto):** todo lo que hoy está hardcodeado en código o frontend:

```json
{
  "slug": "pe-deal",
  "name": "Atlas Capital — PE Deal Room",
  "description": "A private equity fund evaluating a fintech acquisition.",
  "doc_types": ["board_memo", "deal_memo", "financial_model", "..."],
  "blocked_disclosure": "count",
  "scenarios": [
    {"title": "Permission Wall", "hint": "Analyst query hits 10 blocked docs",
     "query": "What is Meridian's ARR growth rate...", "role": "analyst", "mode": "single"}
  ],
  "example_queries": [...]
}
```

- Migración: `corpus/` → `corpora/pe-deal/` y `evals/test_queries.json` →
  `corpora/pe-deal/evals.json` (mover preservando historial es una operación de git — **la ejecuta
  el dueño**; Claude indica el mapeo exacto de rutas). Sin shim de compatibilidad de paths internos
  (los paths viven en código propio), pero la **API mantiene compat**: requests sin `workspace`
  usan el default.

## 2.2 Backend

1. **`src/workspaces.py` (nuevo):** resolver central.
   - `list_workspaces() -> list[WorkspaceInfo]` (escanea `corpora/*/workspace.json`).
   - `get_workspace(slug) -> Workspace` con paths (`documents_dir`, `metadata_path`, `roles_path`,
     `evals_path`, `artifacts_dir`), manifiesto, `roles`, `metadata` — cacheado por slug con lock.
   - Validación de slug (`^[a-z0-9-]{1,40}$`) — es input de usuario y entra en paths: **nunca**
     concatenar sin validar (anti path-traversal) + test dedicado.
   - `DEFAULT_WORKSPACE = "pe-deal"` (env-overrideable).
2. **`src/indexer.py`:** `build_and_save(workspace)` — paths por workspace; CLI
   `python -m src.indexer [--workspace pe-deal]` (default: todos).
3. **`src/retriever.py`:** los singletons pasan a dicts por slug (`_bm25: dict[str, BM25Okapi]`,
   el modelo sigue global — es corpus-independiente); `retrieve(query, top_k, workspace)`;
   `invalidate_caches(workspace)`.
4. **`src/main.py`:** `workspace: str = DEFAULT` en `QueryRequest`/`CompareRequest` (y en el form de
   `/ingest`); roles/metadata dejan de ser globales de módulo → se piden al resolver por request.
   Endpoints nuevos:
   - `GET /workspaces` → lista con slug, name, description, doc_count.
   - `GET /workspaces/{slug}/meta` → roles (nombre, rank, descripción, **docs accesibles contados
     desde metadata** — reemplaza el hardcode del frontend), doc_types, scenarios, example_queries.
5. **`src/ingest.py`:** matar los frozensets hardcodeados `VALID_MIN_ROLES` / `VALID_DOC_TYPES`
   (`src/ingest.py:33-40`) → validar contra `workspace.roles` y `workspace.manifest["doc_types"]`.
6. **`src/evaluator.py`:** `--workspace` flag; `/evals?workspace=` con cache por slug.
7. **Session audit:** cada entrada lleva `workspace` (además del `user` que agregó Fase P).
8. **Fase P por workspace:** `users.json` migra a `corpora/<slug>/users.json`; la pantalla de login
   muestra las personas del workspace elegido (servidas por `/meta`, sin hashes); el knob
   `blocked_disclosure` pasa del env de Fase P al `workspace.json`. Una sesión pertenece a UN
   workspace — usarla contra otro → 403.

## 2.3 Frontend

1. **Workspace picker** en el header (dropdown poblado por `GET /workspaces`); al cambiar:
   fetch de `/meta`, re-render de todo lo dependiente, reset de resultados.
2. **Roles dinámicos:** los radios hardcodeados (`frontend/index.html:56-69`) y
   `ROLE_DESCRIPTIONS` (`frontend/app.js:41-45`) se generan desde `/meta`
   ("Sees N of M docs" calculado, no tipeado). Ojo alcance post-Fase P: los radios de rol viven en
   el **guest-lab y la consola admin ("View as…")**; en modo producto el rol viene de la sesión y
   no hay selector.
3. **Onboarding cards y example buttons** se generan desde `manifest.scenarios` /
   `example_queries` — hoy son HTML hardcodeado del corpus PE.
4. El estado stale-banner y los presets siguen funcionando igual (solo cambia el origen de datos).

## 2.4 Segundo corpus: "SaaS interno" (✅ Decisión D4 resuelta 2026-07-04)

Confirmado: empresa SaaS ficticia **"Nimbus Analytics"** — el entrevistador vive ese escenario:
"el empleado no puede ver las bandas salariales" se entiende en 2 segundos.

- **Roles:** `employee (1) < manager (2) < exec (3)`.
- **Personas (`users.json` del workspace):** Sofía Reyes (`sofia`, employee), Marcos Vidal
  (`marcos`, manager), Alex Kim (`alex`, exec + `is_admin` — se presenta como "Platform Admin").
- **~14 documentos** (~500–900 palabras c/u, generados como los del corpus PE), por ejemplo:
  - employee: onboarding de ingeniería, security policy, oncall runbook **v1 (superseded)**,
    oncall runbook v2, postmortem de outage de DB, guía de perf review, sales playbook.
  - manager: bandas salariales **2023 (superseded)**, bandas 2024, hiring plan, resumen SOC-2.
  - exec: board deck Q1, memo de layoff planning, roadmap **draft (superseded)** → roadmap final.
- **3 pares superseded** (runbook, comp bands, roadmap) — replican la mecánica de stale detection.
- **12 eval queries** con `expected_doc_ids` + `forbidden_doc_ids` espejando la estructura del
  corpus PE (queries de permiso, de staleness, de contenido).
- Indexar y dejar los **artifacts de ambos workspaces generados y listos para que el dueño los
  versione** (mismo criterio actual: el server bootea sin correr el indexado).

## 2.5 Tests (los que importan de verdad)

- **Aislamiento:** una query en `saas-internal` jamás devuelve docs de `pe-deal` (y viceversa) —
  en included, blocked, stale y dropped. Es EL test de multi-tenancy.
- Slug inválido / traversal (`../`, mayúsculas, vacío) → 400/404, nunca toca el filesystem.
- **Sesión cruzada:** una cookie de `pe-deal` (p. ej. `julia`) usada contra `saas-internal` → 403,
  nunca un mapeo silencioso de roles entre workspaces.
- Compat: requests sin `workspace` → default `pe-deal`, respuestas idénticas a pre-fase.
- `/meta` cuenta bien los docs por rol; ingest valida contra roles/doc_types del workspace correcto.
- Evaluator corre por workspace; el A/B naive-vs-full de Fase 0 funciona en ambos.

## 2.6 Riesgos

- **Toca casi todos los módulos** → hacerlo en 4 tandas chicas de trabajo: (1) resolver + indexer/retriever,
  (2) API param + endpoints meta, (3) frontend dinámico, (4) corpus nuevo + evals.
- El corpus nuevo es escritura creativa (½ sesión sola): usar el corpus PE como template de tono y
  densidad de datos; cada doc necesita hechos concretos consultables (números, nombres, fechas) para
  que las evals tengan expected_doc_ids no ambiguos.
- README/CLAUDE.md: actualizar rutas (`corpus/` → `corpora/<slug>/`) y la sección de corpus.

---

## Definition of Done — Fase 2

- [x] `corpora/pe-deal/` migrado; API retro-compatible (suite vieja verde sin tocar requests) *(2026-07-06; compat verificada con test explícito implicit-vs-explicit workspace)*
- [x] `GET /workspaces` + `/workspaces/{slug}/meta`; frontend 100 % libre de roles/counts hardcodeados *(2026-07-06; "Sees N of M docs" computado server-side; radios/escenarios/ejemplos/personas/placeholder/selects de Upload renderizados desde /meta)*
- [x] Segundo corpus completo: 14 docs, 3 pares superseded, 12 evals, artifacts generados (los versiona el dueño) *(2026-07-06; "Nimbus Analytics", employee/manager/exec, artifacts en `artifacts/saas-internal/`. Nota: docs ~250 palabras c/u — la densidad real del corpus PE, no las ~500-900 que estimaba este plan; el criterio aplicado fue "como los del corpus PE")*
- [x] Personas por workspace (login muestra las del workspace elegido); test de sesión cruzada → 403 *(2026-07-06; sofia/marcos/alex; julia→saas 403 y sofia→pe 403 testeados; cookies pre-F2 sin workspace resuelven al default)*
- [x] Test de aislamiento entre workspaces verde; test de slug malicioso verde *(2026-07-06; aislamiento afirmado por títulos/contenido — los doc_ids son namespaces por workspace y colisionan por diseño; slugs validados con regex antes de tocar filesystem + test de que la validación corre antes de cualquier I/O)*
- [x] Evaluator + /evals por workspace; métricas de ambos en el README *(2026-07-06; medido: pe-deal naive 50%→0%, saas-internal naive 58%→0%, ambos recall 1.0)*
- [ ] Demo deployado mostrando el picker con los dos mundos *(requiere push/deploy manual del dueño; Claude deja todo verificado en local — E2E Playwright 23/23 + 17/17 checks)*
