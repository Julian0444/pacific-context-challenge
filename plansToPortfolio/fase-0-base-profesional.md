# Fase 0 — Base profesional

> Un clon limpio instala, testea y corre en cualquier máquina; los bugs conocidos están arreglados;
> el repo público no tiene ruido; hay CI verde, Docker y un README 100 % honesto.

**Depende de:** nada · **Esfuerzo:** 1–2 sesiones · **Resultado observable:** badge de CI verde,
`docker run` funcionando, suite `184 passed / 0 skipped`, README sin ningún número falso.

Todos los hallazgos citados abajo fueron **verificados en la auditoría del 2026-07-02** (venv limpio
real, suite ejecutada, evaluator corrido en dos stacks). No son hipótesis.

---

## 0.1 Reproducibilidad (CRÍTICO — hoy un clon limpio no instala en Mac)

**Problema verificado:** `requirements.txt:7` pinea `torch==2.2.2+cpu`. Los wheels `+cpu` del index
de PyTorch existen solo para Linux/Windows → `pip install -r requirements.txt` **falla en cualquier
macOS** con `No matching distribution found`. Render (Linux) funciona; por eso el deploy vive y el
clon local muere. Además `pytest` y `httpx` no están en ningún requirements → el paso "correr tests"
del README es imposible en un clon limpio (verificado: `No module named pytest`).

**Tareas:**

1. En `requirements.txt`, reemplazar la línea `torch==2.2.2+cpu` por:
   ```
   torch==2.2.2+cpu; sys_platform == "linux"
   torch==2.2.2; sys_platform != "linux"
   ```
   (Fix verificado en venv limpio: instala torch 2.2.2 / transformers 4.46.3 /
   sentence-transformers 3.3.1 / numpy 1.26.4 / faiss-cpu 1.8.x en Python 3.9 arm64, y el
   evaluator da números idénticos al entorno de desarrollo.)
2. Crear `requirements-dev.txt`:
   ```
   -r requirements.txt
   pytest
   httpx
   ruff
   ```
3. **No subir `transformers` más allá de ~4.46 mientras torch esté en 2.2.x** — transformers ≥4.50
   usa APIs de torch ≥2.4 (`torch.library.register_fake`). Dejar esta regla como comentario en
   `requirements.txt`.
4. README: agregar prerequisito **Python 3.9–3.11** (probado: 3.9 local, 3.11 Render vía
   `.python-version`), el paso de venv explícito, `pip install -r requirements-dev.txt` antes de
   los tests, y una nota de que la primera corrida descarga el modelo MiniLM (~90 MB) y el encoding
   BPE de tiktoken (necesita internet una vez).

**Criterio de aceptación:** en un venv nuevo (fuera del repo):
`pip install -r requirements-dev.txt` → `python -m pytest tests/ -q` verde →
`python -m src.evaluator` reproduce las métricas → `uvicorn src.main:app` responde `/health`.

---

## 0.2 Bug fixes de correctness

### a) Fecha validada solo por regex → 500 permanente (HIGH, bug real)

`src/ingest.py:44` (`DATE_RE = ^\d{4}-\d{2}-\d{2}$`) acepta `"2024-99-99"`. Esa fecha se escribe en
`corpus/metadata.json` y el próximo `/query` con freshness revienta en
`datetime.strptime` (`src/freshness.py:35`) → **500 para todo el corpus** hasta editar el JSON a mano
(el `reference_date = max(all_dates)` también puede tomar la fecha inválida).

- En `_validate_inputs` (`src/ingest.py:109`): tras el regex, `datetime.strptime(date, "%Y-%m-%d")`
  dentro de try/except → `IngestError("date must be a real calendar date...", 400)`.
- Tests nuevos: `test_ingest_rejects_impossible_date` (`"2024-99-99"` → 400) y
  `test_ingest_accepts_leap_day` (`"2024-02-29"` → pasa validación).

### b) `/ingest` bloquea el event loop (HIGH)

`src/main.py:278` declara `async def ingest(...)` pero llama trabajo síncrono pesado
(pdfplumber + reindex completo, 5–10 s) **sobre el event loop** → durante un upload ni `/health`
responde.

- Cambiar a `def ingest(...)` (FastAPI lo despacha al threadpool). El `await file.read()`
  (`src/main.py:317`) pasa a `file.file.read()`.
- Test: no hay assert directo simple del threadpool; verificar manualmente con un upload real +
  `curl /health` concurrente, y dejar comentario en el handler explicando por qué es `def`.
  (La solución definitiva — jobs asíncronos — llega en Fase 3; esto elimina el freeze ya.)

### c) Escrituras no atómicas de artifacts y metadata (HIGH)

`src/indexer.py:83-91` (`faiss.write_index` + `json.dump` directo al path final) y
`src/ingest.py:202-206` (`metadata.json` reescrito in-place). Como `retrieve()` relee del disco en
cada request (`src/retriever.py:198`), un query concurrente durante un reindex puede leer un archivo
a medio escribir o un index nuevo con payloads viejos. Un crash a mitad de escritura de
`metadata.json` deja el server sin bootear.

- Helper `_atomic_write_json(path, obj)` y patrón `write → .tmp` + `os.replace(tmp, final)` para:
  `querytrace.index` (faiss escribe al tmp path y se renombra), `index_documents.json`,
  `bm25_corpus.json`, `corpus/metadata.json`.
- Orden de escritura que minimiza la ventana de inconsistencia: payloads+bm25 primero, index último
  (o documentar la ventana residual como known limitation de single-file-pair).
- Tests: unit del helper (tmp no queda huérfano en error; el archivo final nunca está a medias).

### d) El invariante mapea a 400 en vez de 500 (HIGH)

`src/stages/trace_builder.py:54-60` lanza `ValueError` si `blocked+included+dropped != retrieved`,
y `src/main.py:122-123` captura `ValueError → HTTPException(400)`. Un error **interno** de
contabilidad se reportaría como "bad request" del usuario.

- Nueva excepción `TraceAccountingError(RuntimeError)` en `trace_builder.py`; el handler de
  `/query` y `/compare` no la captura → 500 (correcto). El `except ValueError` queda solo para
  errores de input reales (`resolve_policy`).
- Test: `build_trace` con cuentas desbalanceadas lanza `TraceAccountingError` y
  `not isinstance(exc, ValueError)`.

### e) Validación de entrada de la API (MEDIUM)

`src/models.py` — `QueryRequest.top_k` sin bounds: verificado que `top_k=-1` devuelve **200** con la
lista recortada silenciosamente (`[:-1]` en el retriever). `query` sin límites de longitud.

- `top_k: int = Field(default=5, ge=1, le=50)` en `QueryRequest` y `CompareRequest`;
  `query: str = Field(min_length=1, max_length=2000)`.
- Tests: `top_k=-1` → 422, `top_k=0` → 422, query vacía → 422.

---

## 0.3 Dead code fuera → suite sin skips

Verificado: `src/context_assembler.py` (completo), `apply_freshness` (`src/freshness.py:44-70`) y
`filter_by_role` (`src/policies.py:65-79`) solo los referencian tests marcados
`skip("legacy: replaced by stages/...")` — los "14 skipped".

- Borrar: `src/context_assembler.py`, `tests/test_context_assembler.py`, la función
  `apply_freshness` + su bloque legacy en `tests/test_freshness.py`, la función `filter_by_role` +
  su bloque legacy en `tests/test_policies.py`. (`compute_freshness` y `load_roles` **se quedan** —
  son código vivo.)
- Quitar `tiktoken` import huérfano si queda alguno; `semantic_retrieve` se queda (uso real en
  tests/CLI/comparación).
- Resultado esperado: **184 passed, 0 skipped** (los 14 skips eran exactamente estos legacy).
- Actualizar CLAUDE.md y README donde mencionan los módulos borrados y los "14 skipped".

## 0.4 Micro-fixes de tests

- `tests/test_main.py:61` — `test_query_invalid_role_returns_422` asserta 400: renombrar a
  `..._returns_400`.
- `tests/test_main.py:48-58` — `test_query_partner_can_see_all` no asserta nada de partner:
  agregar `assert "doc_010" in doc_ids` (IC memo, partner-only).

---

## 0.5 Honestidad de docs + eval A/B (el headline metric)

**Números verificados hoy:** suite real = **184 passed** (README dice 175 en `README.md:176` y
`:211`). Métricas del evaluator: P@5 0.3333, recall 1.0, violaciones 0 %, budget 71 %, blocked 4.17,
stale 2.08 — todas correctas en el README.

1. README 175 → 184 (dos lugares); si 0.3 borró los skips, quitar "(deprecated)".
2. **Reframe de P@5:** el 0.3333 es exactamente el **techo teórico** — los expected sets tienen 1–3
   docs, máximo promedio alcanzable = 4.0/12 = 0.3333, y las 12 queries lo alcanzan. Reescribir la
   fila de la tabla: "P@5 0.33 (= techo teórico: el 100 % de los documentos esperados aparece en el
   top-5 en las 12 queries)". Nota al pie: `precision_at_k` clampea k al tamaño del resultado
   (ya documentado en el docstring de `src/evaluator.py:45-57`, falta en README).
3. `docs/pacific_demo_guide.md:3` referencia `demo.md` y `script_en.md` que **no existen** → borrar
   esas referencias.
4. **Eval comparativo naive vs full** (nueva feature chica, ~30 líneas):
   - `run_evals(queries, k, top_k, policy_name="default")` — pasar `policy_name` al `QueryRequest`.
   - CLI `python -m src.evaluator --compare` → corre `naive_top_k` y `full_policy`, imprime tabla
     lado a lado: violation rate, blocked, docs promedio, P@5.
   - **Medir el número real** de violation rate del baseline naive (no publicar estimaciones) y
     ponerlo en el README: "violaciones: X % (naive) → 0 % (full)". Ese delta es el pitch del
     proyecto.
   - Tests: `run_evals` con `naive_top_k` reporta violaciones > 0; con `full_policy` = 0.

---

## 0.6 Limpieza del repo público

Ruido detectado (tracked): `test-results/.last-run.json`, `summaryUserExp.md` (34 KB en el root),
`docs/` con 3.250 líneas (HANDOFF de 101 KB, 19 planes históricos, duplicados ES/EN).

**Nota (decisión 2026-07-04):** las skills de Claude Code (`.claude/skills/`, `.agents/skills/` y
`skills-lock.json`) **se conservan deliberadamente en el repo** — son tooling activo para trabajar
este roadmap, no ruido. No se eliminan ni se gitignorean.

1. Dejar de trackear `test-results/` (**operación de git — la ejecuta el dueño**; Claude solo la
   indica) + entrada `test-results/` en `.gitignore` (la decisión sobre `plansToPortfolio/` está
   en el punto 5).
2. **`frente_3_querytrace.md` (untracked, guion personal de entrevista): mover fuera del repo YA y
   agregar a `.gitignore` para que jamás entre al historial** (el dueño maneja git).
3. `summaryUserExp.md` → `docs/` o fuera del repo.
4. `docs/` consolidado: quedan `docs/architecture.md` (destilado de `backendSummary.md`, EN) y
   `docs/demo-guide.md` (de `pacific_demo_guide.md`, sin links rotos). `HANDOFF.md`,
   `backendSummarySpanish.md`, `glosario_metricas.md`, `metrics_glossary.md` y `docs/plans/*` →
   `docs/archive/` (o fuera del repo; decisión estética del dueño).
5. **Decisión sobre `plansToPortfolio/` (este directorio):** o se gitignorea (material de trabajo
   privado) o forma parte del repo público como bitácora de roadmap. Ambas son defendibles; decidir
   antes del release público (la operación de git resultante la hace el dueño).
6. `LICENSE` MIT en el root (hoy no hay — sin licencia nadie puede usar el código legalmente).

---

## 0.7 CI — GitHub Actions

`.github/workflows/ci.yml`:

- Trigger: **push a cualquier rama** + pull requests — así la rama de trabajo `feat/ToDeploy`
  recibe CI en cada push del dueño. `main` no participa del roadmap: solo recibe el merge final
  cuando el dueño da por bueno el resultado.
- Python 3.11 (matchea `.python-version` de Render). Opcional: matrix con 3.9 para validar el rango.
- Pasos: checkout → setup-python con cache pip → `pip install -r requirements-dev.txt` →
  `ruff check src/ tests/` → `pytest -q` → `python -m src.evaluator --compare` como smoke
  (asserta violaciones full = 0).
- **Cache de modelos**: `actions/cache` sobre `~/.cache/huggingface` (keyed por nombre de modelo) y
  `TIKTOKEN_CACHE_DIR` — sin esto cada run baja ~90 MB.
- Badge en el README.

Config de `ruff` mínima en `pyproject.toml` (line-length, target-version); arreglar lo que marque
(esperable: imports sin usar tras el 0.3).

---

## 0.8 Dockerfile

- Base `python:3.11-slim`; `pip install -r requirements.txt` (con el fix de pins, en Linux resuelve
  `torch==2.2.2+cpu` — imagen CPU, no CUDA).
- **Pre-descargar en build** el modelo y el encoding para matar el cold start:
  ```dockerfile
  RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
  RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
  ```
- `CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}` (Render inyecta `PORT`).
- `.dockerignore`: `.venv`, `.git`, `docs/`, `plansToPortfolio/`, `tests/`, `.claude`, `.agents`
  (las skills quedan en el repo, pero no hacen falta dentro de la imagen).
- Usuario non-root, `HEALTHCHECK` contra `/health`.
- Verificación: `docker build -t querytrace . && docker run -p 8000:8000 -e ALLOW_INGEST=false querytrace`
  → `/health`, `/query`, `/app/` responden.

---

## 0.9 README final de la fase

Estructura objetivo: hero (una frase + link al deploy + GIF placeholder hasta Fase 1) → badges
(CI, Python, license) → "Why this exists" → quickstart 3 pasos → pipeline diagram (ya existe) →
tabla de métricas con el A/B naive vs full → **Known Limitations** (sección nueva, promovida desde
CLAUDE.md: sin RBAC real en ingest — se resuelve en Fase P con la sesión admin —, reindex síncrono,
estado single-process, truncado semántico a ~256 tokens del embedder, CORS abierto por el flujo
`file://`, disco efímero en Render) → roadmap (link a `plansToPortfolio/` si queda en el repo
público).

---

## Definition of Done — Fase 0

- [x] Venv limpio: install + tests + evaluator + server OK con los comandos del README — **verificado en Mac (2026-07-05)**; CI Linux queda pendiente del primer push del dueño
- [x] Suite: **201 passed, 0 skipped, 0 failed** (el objetivo decía 184; los 17 tests nuevos de 0.2/0.5 suben el total medido a 201)
- [x] Los 5 bugs (0.2 a–e) arreglados con test cada uno (0.2b además verificado en vivo: /health respondió en 1–13 ms durante un ingest real de 4.9 s)
- [x] `--compare` implementado y número real naive vs full en README: **50% → 0% violation rate** (medido 2026-07-05)
- [x] README sin ningún claim no verificado; links rotos eliminados (P@5 reframeado como techo teórico con footnote)
- [x] Repo sin tmp/docs personales tracked — pendientes 2 operaciones de git del dueño (untrack `test-results/`; ver resumen de sesión); LICENSE MIT presente. ⚠ Ver D6 en README: el working tree tiene las skills borradas + gitignoreadas, contradiciendo la nota de conservarlas.
- [x] `docker run` funcional (verificado 2026-07-05: /health, /query, /app/ OK; /ingest→403 con ALLOW_INGEST=false). CI escrito con badge; **"CI verde" se confirma con el primer push del dueño**

**Nota de ejecución (2026-07-05):** el pin `torch==2.2.2+cpu; sys_platform == "linux"` del punto 0.1 falló en Docker sobre Apple Silicon (linux/arm64 no tiene wheels +cpu de 2.2.x). Marker final: `+cpu` solo para `linux and x86_64`; el resto usa el wheel normal de PyPI. Render (x86_64) no cambia.
