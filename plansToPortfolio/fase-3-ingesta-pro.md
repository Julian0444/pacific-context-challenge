# Fase 3 — Ingesta pro: del form de demo al ciclo de vida del dato

> La ingesta deja de ser "un PDF por vez con spinner de 10 segundos" y pasa a ser: multi-formato,
> asíncrona con progreso real, incremental (O(1) por documento), deduplicada, y con un camino CLI
> para traer un corpus entero propio. (La auth ya viene resuelta por la sesión admin de Fase P.)

**Depende de:** Fase 0 (fixes de fecha/event-loop/atomicidad), Fase P (sesión admin — gatea
`/ingest` y los endpoints de jobs) y Fase 2 (workspaces — la ingesta escribe en un workspace) ·
**Esfuerzo:** 2–3 sesiones · **Resultado observable:** subís 5 archivos
mezclados (.pdf/.md/.docx), ves estados de progreso reales, el segundo upload del mismo archivo da
409, y `python -m src.workspace create` levanta un corpus tuyo completo.

**Señal de entrevista:** pensamiento de producción sobre el ciclo de vida del dato — validación en
capas, jobs asíncronos con el trade-off explícito de "threads vs Celery", costo de indexado O(1) vs
O(N) medido, e idempotencia.

Las etapas son incrementales y cada una es deployable por separado.

---

## Etapa A — Quick wins de robustez (½ sesión)

1. **Magic bytes:** además del content-type (spoofeable), verificar la firma real del archivo:
   `%PDF-` para PDF, UTF-8 decodificable para .txt/.md, firma ZIP `PK` para .docx → 415 si no
   matchea la extensión declarada.
2. **Tamaño antes de leer:** hoy `src/main.py:317` hace `file.read()` completo a memoria y recién
   después `src/ingest.py:166` chequea los 10 MB. Fix: chequear `Content-Length` primero (413
   temprano) y leer en chunks con tope `MAX_PDF_BYTES + 1` — un body de 2 GB nunca llega a RAM.
3. **Dedup por contenido:** `sha256` del texto extraído normalizado, guardado como `content_hash`
   en la entrada de metadata. Si ya existe en el workspace → **409** con el `doc_id` existente en el
   detail. Idempotencia real: subir dos veces lo mismo no duplica el corpus.
4. **Multi-formato:** `extract_text(file_bytes, filename) -> str` como dispatcher:
   - `.pdf` → pdfplumber (actual)
   - `.txt` → decode UTF-8 (fallback latin-1)
   - `.md` → texto plano, strip de frontmatter YAML si existe
   - `.docx` → `python-docx` (nueva dep en requirements)
   El mínimo de 50 chars extraídos aplica a todos. El form del frontend acepta los 4 tipos.
5. **Auth: ya resuelta por Fase P** (reemplaza el `INGEST_API_KEY` que planeaba esta fase —
   la sesión admin es más natural de producto que un header de API key). Lo único que esta etapa
   agrega: los endpoints nuevos (`GET /ingest/jobs/*`, futuro DELETE) heredan la misma regla
   "solo sesión admin", con sus tests.

Tests: por formato (happy + corrupto), magic bytes vs extensión mentirosa, oversize por
Content-Length y por stream, dedup 409, endpoints de ingest/jobs sin sesión admin → 401/403.

## Etapa B — Ingesta asíncrona con jobs (1 sesión)

Hoy (post-Fase 0) el reindex corre en el threadpool pero el request queda colgado 5–10 s igual.

1. **`src/jobs.py` (nuevo):** `JobStore` in-process — dict + lock, `Job{id, workspace, state,
   created_at, updated_at, error, result}`, estados: `queued → extracting → embedding → indexing →
   done | failed`. Retención: últimos 50 jobs.
2. **Ejecutor:** `ThreadPoolExecutor(max_workers=1)` — un solo worker **serializa** los reindex
   (reemplaza al `_INGEST_LOCK` como mecanismo de serialización; el lock queda para la sección
   crítica de metadata). Inyectable: los tests usan un ejecutor inline síncrono
   (`run_inline=True`) para no dormir ni poll-ear.
3. **API:** `POST /ingest` valida lo barato en el request (campos, formato, tamaño, auth, dedup) →
   encola → **202 `{job_id}`**. `GET /ingest/jobs/{job_id}` → estado + resultado
   (`IngestResponse` cuando `done`, error tipado cuando `failed`). 404 si expiró.
4. **Frontend:** polling de 1 s al job; barra de progreso con los 4 estados con label humano
   ("Extrayendo texto… / Generando embeddings… / Actualizando índices…"); submit deshabilitado
   mientras hay job activo del usuario.
5. **Trade-off documentado en el código y README** (el talking point): threads in-process es la
   elección correcta para una instancia única de demo; el upgrade path a multi-instancia es una
   cola externa (Celery/RQ/SQS) y se explicita por qué no se pagó ese costo hoy.
6. **Rollback:** si el job falla después de escribir el `.txt` pero antes de reindexar, el job
   limpia el archivo y la entrada de metadata (hoy quedan huérfanos — hallazgo de la auditoría).

Tests: transición de estados, job failed con rollback verificado (no queda .txt ni entrada),
202 + fetch del job, serialización (dos POST → el segundo queda `queued` hasta que termina el
primero, con ejecutor real en un test lento marcado).

## Etapa C — Indexado incremental: O(N) → O(1) (½–1 sesión)

Hoy cada upload re-embeddea el corpus completo (`indexer.build_and_save()` desde
`src/ingest.py:208`). Con `IndexFlatIP` el add incremental es trivial.

1. **`indexer.add_document(workspace, entry, text)`:** embeddea **solo el doc nuevo** →
   `index.add(vec)` sobre el índice cargado → append del payload a `index_documents.json` → BM25 se
   re-tokeniza completo (es Python puro y barato, ~ms) → escritura atómica de los tres artifacts
   (helper de Fase 0).
2. Fallback automático a `build_and_save()` si el índice no existe o hay drift detectado
   (len(payloads) != index.ntotal → rebuild defensivo + warning).
3. Ediciones/borrados siguen siendo full rebuild (documentado; `IndexFlatIP` no soporta remove
   barato sin IDMap — anotar `IndexIDMap` como upgrade path).
4. **Medir y publicar:** tiempo de ingest por documento antes/después
   (esperable: ~5–10 s → <1 s). El número real va al README — es el mejor bullet de infra de la fase.

Tests: add incremental deja el índice consistente (query encuentra el doc nuevo; ntotal == len
payloads == len bm25), fallback a rebuild, drift detectado.

## Etapa D — Bring-your-own-corpus por CLI (½–1 sesión)

El pitch "aplicable a cualquiera" hecho comando (la versión UI con ZIP puede venir después):

```bash
python -m src.workspace create mi-empresa \
    --from-dir ~/docs-de-prueba \
    --roles roles.json \            # opcional; default: viewer(1) < editor(2) < admin(3)
    --name "Mi Empresa KB"
python -m src.workspace list
```

1. Recorre el directorio (pdf/txt/md/docx), extrae con el dispatcher de la Etapa A, genera
   `metadata.json` con defaults sensatos (min_role = rol más bajo, date = mtime del archivo,
   doc_type = "document", title = filename humanizado), crea `workspace.json`, indexa, e imprime el
   resumen + cómo probarlo (`uvicorn ...` → seleccionar el workspace en la UI).
2. Reusa 100 % el código de ingest/indexer — la CLI es un loop fino sobre lo existente; si algo no
   se puede reusar limpio, es olor de que la Etapa A/C dejó lógica en el handler HTTP.
3. Validaciones: directorio vacío, archivos ilegibles (skip con warning y resumen final), slug
   duplicado.

Tests: creación end-to-end desde un tmp_path con 3 formatos mezclados; workspace resultante
responde `/query` con roles default.

## Etapa E — Metadata asistida por LLM (opcional, después de Fase 4)

Cuando exista la integración con Claude (Fase 4): `POST /ingest/suggest` recibe el archivo, extrae
texto y pide a Claude título/doc_type/tags/fecha sugeridos → la UI pre-llena el form y el humano
confirma. Env-gated igual que Ask mode. Convierte el form de 7 campos en "subí y confirmá".
No bloquea nada de esta fase — se lista como stretch para no perderla de vista.

---

## Definition of Done — Fase 3

- [x] 4 formatos con magic bytes + tamaño chequeado antes de leer + dedup 409; jobs gateados por sesión admin (Fase P) *(2026-07-06: `extract_text` dispatcher + `check_magic_bytes` + Content-Length/chunked 413 + `content_hash` → 409; `GET /ingest/jobs*` exige sesión admin del workspace; no hay DELETE aún — sigue sin path de borrado, anotado como límite)*
- [x] `POST /ingest` → 202 + job trackeable; UI con progreso real; rollback en failure testeado *(2026-07-06: `src/jobs.py` con worker único; estados queued→extracting→embedding→indexing→done|failed; E2E API: 202 en 224 ms con /health en 3–10 ms durante el job; Playwright 6/6 sobre la UI de progreso; rollback testeado a nivel unit y endpoint)*
- [x] Ingest incremental con tiempo medido antes/después publicado en README *(2026-07-06: `indexer.add_document` O(1) con fallback por drift; medido warm-model M-series: 16 docs 0.04s→0.009s, 160 docs 0.22s→0.010s (~21×); publicado en README/architecture/CLAUDE)*
- [x] `python -m src.workspace create --from-dir` funcional end-to-end con tests *(2026-07-06: `src/workspace.py` create/list; 11 tests sandboxeados + corrida real verificada con /query y /meta; dedup y archivos ilegibles se saltean con warning; skeleton se limpia si nada es ingestable)*
- [x] Decisión threads-vs-cola documentada en código y README (Known Limitations actualizado) *(2026-07-06: docstring de `src/jobs.py` + bullet "In-process job queue" en Known Limitations)*
- [ ] Upload habilitado en el deploy público (sesión admin de Fase P) y probado end-to-end *(requiere push/deploy + cambio de env var del dueño)*

**Desvíos registrados (2026-07-06):**
- El check de content-type del handler se eliminó en vez de extenderse: es spoofeable e inconsistente entre browsers para .md/.docx; la extensión declarada + magic bytes son el contrato (documentado en CLAUDE.md).
- El test de serialización "dos POST → el segundo queued" se implementó a nivel `jobs.submit()` (determinístico, <0.2s) en vez de con dos POSTs reales; la serialización del worker único queda igualmente cubierta.
- BM25 en el add incremental: se appendea la fila tokenizada del doc nuevo en vez de re-tokenizar el corpus completo — equivalente (las filas existentes no cambian con un doc nuevo) y O(1).
- La dedup corre dos veces por diseño: en `prepare_ingest` (409 sincrónico en el request) y re-check autoritativo bajo lock en `finalize_ingest` (carrera prepare→turno del job).
- Etapa E (metadata sugerida por LLM) queda como stretch declarado, no ejecutada.
