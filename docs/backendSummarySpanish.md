# QueryTrace — Análisis del Backend

**Fecha:** 2026-04-18
**Alcance:** Sólo backend (`src/`, pipeline, tests). Auditoría de sólo lectura, sin cambios de código.
**Branch:** `codex/must-a-idea1-2`

**Estado de `pytest` recién ejecutado:** `171 passed, 1 failed, 14 skipped`. El test que fallaba era `tests/test_retriever.py::TestResultShape::test_top_k_clamped_to_corpus_size` — al momento de la auditoría hacía hardcode de `len(results) == 12` pero el corpus había driftado a 13 documentos (ver CR-1).

El working tree también tenía drift sin commitear (`corpus/documents/agenda.txt` untracked, `corpus/metadata.json` + `artifacts/*` modificados) por un ingest que no se revirtió.

**Update 2026-04-22 (UI-A):** la contaminación del corpus fue removida. `agenda.txt` / `doc_013` ya no existe, los artifacts se reconstruyeron a 12 vectores, y el test fue refactoreado previamente para leer `corpus_size` dinámicamente desde `metadata.json`. Estado actual de `pytest`: `172 passed, 14 skipped, 0 failed`. CR-1 más abajo es histórico.

**Update 2026-04-25 (UI-E):** el corpus de demo fue expandido intencionalmente a 16 documentos redactados (`doc_013`–`doc_016` ahora son legal diligence, IC draft, artículo público de valuación, y memo de CTO). Los artifacts se reconstruyeron a 16 vectores y el evaluator ahora corre 12 queries corpus-grounded. La contaminación `agenda.txt` de UI-A sigue resuelta; el nuevo `doc_013` es contenido redactado, no el viejo probe Agenda.

---

## Índice visual del análisis

```
┌─────────────────────────────────────────────────────────────────────┐
│                       ESTE DOCUMENTO                                │
├─────────────────────────────────────────────────────────────────────┤
│  1. Resumen ejecutivo del backend                                   │
│  2. Walkthrough del pipeline (con diagrama de flujo)                │
│  3. Mapa módulo a módulo (con grafo de dependencias)                │
│  4. Estado, caching y runtime (con diagrama de concurrencia)        │
│  5. Contratos API (con esquemas de request/response)                │
│  6. Hallazgos por severidad (con distribución visual)               │
│  7. Preguntas abiertas                                              │
│  8. Veredicto final                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Resumen ejecutivo del backend

QueryTrace es un servicio de retrieval mayormente de lectura. Dos caminos críticos:

- **Camino de consulta** (`POST /query`, `POST /compare`, `GET /evals`): texto del usuario + rol → retrieval híbrido (FAISS + BM25 fusionados con RRF) → filtro RBAC → scoring de frescura relativo al corpus → empaquetado greedy con budget de tokens → traza de auditoría. Cómputo puro después del paso del retriever.
- **Camino de mutación** (`POST /ingest`): PDF multipart → texto con pdfplumber → append casi-atómico a metadata bajo un `threading.Lock` → rebuild síncrono de FAISS+BM25 → invalidación de caches in-process.

Todo el estado persistente vive en disco local (`corpus/`, `artifacts/`). Sin base de datos, sin llamadas de red durante una consulta, sin workers en background. El modelo SBERT, el índice FAISS y el objeto BM25 son singletons lazy-loaded por proceso (`src/retriever.py:42-58`). Los roles y metadata se cargan una sola vez al startup (`src/main.py:44-47`) pero `_metadata` es un dict mutable para que ingest pueda actualizarlo in-place.

Una cadena de tipos Pydantic corre end-to-end:

```
  ┌──────────────────┐   extra="ignore"     ┌────────────────────────┐
  │ dict del retriever│ ───────────────────▶│   ScoredDocument       │
  │ (FAISS + BM25)   │                      │ frozen, ignore extras  │
  └──────────────────┘                      └───────────┬────────────┘
                                                        │
                                                        ▼
                                         ┌──────────────────────────────┐
                                         │ FreshnessScoredDocument      │
                                         │ + freshness_score, is_stale  │
                                         └──────────────┬───────────────┘
                                                        │
                                                        ▼
               ┌─────────────────────┬─────────────────┴──────────┬───────────────────┐
               ▼                     ▼                            ▼                   ▼
      ┌────────────────┐  ┌─────────────────┐          ┌──────────────────┐  ┌────────────────┐
      │ BlockedDocument│  │ StaleDocument   │          │ IncludedDocument │  │ DroppedByBudget│
      │ (filter)       │  │ (freshness)     │          │ (budget packer)  │  │ (budget packer)│
      └───────┬────────┘  └────────┬────────┘          └────────┬─────────┘  └────────┬───────┘
              │                    │                            │                     │
              └────────────────────┴──────────┬─────────────────┴─────────────────────┘
                                              ▼
                                    ┌──────────────────────┐
                                    │   DecisionTrace      │
                                    │ + TraceMetrics       │
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │   QueryResponse      │
                                    │  (DocumentChunk[])   │
                                    └──────────────────────┘
```

Los modelos de dominio son `frozen=True, extra="forbid"`; los modelos del borde del API son más laxos.

## 2. Walkthrough del pipeline

**Entrada:** `src/main.py:65 query()` → valida rol → llama `run_pipeline()` (`src/pipeline.py:126`) → mapea resultado a `QueryResponse`.

### Diagrama de flujo del pipeline

```
                         ┌──────────────────┐
                         │  POST /query     │
                         │  {query, role,   │
                         │   top_k, policy} │
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  main.py: query()         │
                    │  validar role → 400 si    │
                    │  unknown                  │
                    └──────────────┬───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │  run_pipeline()           │
                    │  pipeline.py:126          │
                    └──────────────┬───────────┘
                                   │
                  resolve_policy(name, top_k)
                                   │
                                   ▼
          ┌────────────────────────────────────────────┐
          │ Stage 1: retrieve(query, top_k * 3)         │
          │   FAISS cosine  ─┐                          │
          │                  ├── RRF fusion ── norm ──▶ │
          │   BM25 lexical  ─┘                          │
          │                                             │
          │   Output: List[ScoredDocument]              │
          └──────────────────┬──────────────────────────┘
                             │
                             ▼
          ┌────────────────────────────────────────────┐
          │ Stage 2: filter_permissions()               │
          │   access_rank(user) >= rank(doc.min_role)?  │
          └───────┬────────────────────────┬────────────┘
                  │                        │
                  ▼                        ▼
           ┌─────────────┐         ┌─────────────────┐
           │ permitted   │         │ blocked[]       │
           │ (sigue)     │         │ (a la traza)    │
           └──────┬──────┘         └────────┬────────┘
                  │                         │
                  ▼                         │
          ┌────────────────────────────────────────────┐
          │ Stage 3: score_freshness()                  │
          │   exp_decay(age, half_life)                 │
          │   × 0.5 si superseded_by != null            │
          └──────────────────┬──────────────────────────┘
                             │ List[FreshnessScoredDocument]
                             │ + List[StaleDocument]
                             ▼
          ┌────────────────────────────────────────────┐
          │ Stage 4: pack_budget()                      │
          │   rank por 0.5*sim + 0.5*fresh              │
          │   greedy: si total+tk > budget → drop       │
          └───────┬────────────────────────┬────────────┘
                  │                        │
                  ▼                        ▼
           ┌─────────────┐         ┌─────────────────┐
           │ packed[]    │         │ over_budget[]   │
           │ (contexto)  │         │ (a la traza)    │
           └──────┬──────┘         └────────┬────────┘
                  │                         │
                  └────────────┬────────────┘
                               ▼
          ┌────────────────────────────────────────────┐
          │ Stage 5: build_trace()                      │
          │   INVARIANT:                                │
          │   blocked + included + dropped == retrieved │
          │   ⚠ raise ValueError si no coincide (MA-7)  │
          └──────────────────┬──────────────────────────┘
                             │ PipelineResult
                             ▼
                   ┌──────────────────────┐
                   │  QueryResponse       │
                   │  → HTTP 200 JSON     │
                   └──────────────────────┘
```

### Detalle de cada stage

Dentro de `run_pipeline` (`src/pipeline.py:149-195`):

1. **Resolve de política** — `resolve_policy(name, top_k)` (`src/policies.py:36`) busca `POLICY_PRESETS` y sobreescribe `top_k` vía `model_copy`. Lanza `ValueError` si el nombre es desconocido — main.py:76 lo convierte a HTTP 400.
2. **User context** — `roles[request.role]["access_rank"]` + nombre del rol → `UserContext` frozen.
3. **Retrieve** — `_retrieve_stage` llama al retriever inyectado con `retrieve_k = policy.top_k * 3`. El retriever (`src/retriever.py:177`) lee FAISS + BM25 de disco en cada llamada, computa diccionarios de rank 1-based, fusiona con `RRF_score(d) = 1/(60+r_sem) + 1/(60+r_bm25)`, normaliza min-max a [0, 1], ordena, clampa a `top_k`, y construye dicts con todos los campos de metadata del corpus. Los resultados se validan a `ScoredDocument`; los keys extra se descartan silenciosamente (`extra="ignore"`).
4. **Permission filter** — `src/stages/permission_filter.py:26`. Dos branches: `doc.min_role` desconocido en roles → `BlockedDocument(reason="unknown_min_role")`; comparación de rank → permitted o `BlockedDocument(reason="insufficient_role")`. Se salta completamente cuando `policy.skip_permission_filter=True` (naive_top_k).
5. **Freshness** — `src/stages/freshness_scorer.py:30`. Construye `meta_by_id` desde toda la metadata en cada llamada. Reference date = `max(all_dates)`. Para cada doc permitido: busca metadata, decay exponencial (`compute_freshness` en `src/freshness.py:18`), multiplica por `0.5` si está superseded. Metadata ausente → `freshness=0.0`, `is_stale=False`, pero `superseded_by` se preserva del ScoredDocument (inconsistente; hallazgo MA-6). Produce lista `FreshnessScoredDocument` + entradas `StaleDocument`. Si se salta → toda freshness=0.0, ninguno stale.
6. **Budget packer** — `src/stages/budget_packer.py:44`. Ordena por `0.5*score + 0.5*freshness_score`, itera, tokeniza `doc.excerpt` con cl100k_base, empaca greedy. Docs over-budget → `DroppedByBudget`. Devuelve `BudgetResult(packed, over_budget, total_tokens, budget_utilization)`. `enforce_budget=False` empaca todo.
7. **Trace builder** — `src/stages/trace_builder.py:24`. Asevera `blocked+included+dropped == retrieved_count` (lanza `ValueError` si no coincide — ver hallazgo MA-7). Computa avg_score, avg_freshness_score, ensambla `DecisionTrace` completa.

`_unwrap` (`src/pipeline.py:60`) convierte cada `StageErr` a `PipelineError(stage, error)`, que main.py:78 mapea a HTTP 500. Cualquier excepción no-stage de `run_pipeline` burbujea tal cual.

## 3. Mapa de módulos

### Grafo de dependencias

```
                          ┌──────────────┐
                          │   main.py    │  ← FastAPI, endpoints
                          │  (FastAPI)   │     /query /compare /evals
                          └──┬───────┬───┘     /ingest /health /app
                             │       │
                ┌────────────┤       ├────────────────┐
                │            │       │                │
                ▼            ▼       ▼                ▼
         ┌────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐
         │ pipeline.py │ │ingest.py│ │evaluator │ │ models.py    │
         │ (orquesta) │ │ (escribe│ │.py       │ │ (Pydantic)   │
         │            │ │ corpus) │ │ (metrics)│ │              │
         └──┬─────┬───┘ └────┬────┘ └────┬─────┘ └──────────────┘
            │     │          │            │
            ▼     └──────────┼─────────┐  │
      ┌──────────┐           │         │  │
      │stages/   │           ▼         │  │
      │(4 stages)│      ┌──────────┐  │  │
      │          │      │indexer.py│  │  │
      │ permission│      │ (rebuild)│  │  │
      │ freshness │      └────┬─────┘  │  │
      │ budget    │           │        │  │
      │ trace     │           ▼        ▼  ▼
      └─────┬─────┘     ┌─────────────────────┐
            │           │    retriever.py      │
            ▼           │ (FAISS + BM25 + RRF) │
      ┌──────────┐      └──────────┬──────────┘
      │protocols │                 │
      │.py (DI)  │                 ▼
      └──────────┘           ┌──────────────┐
                             │  artifacts/  │
                             │ .index .json │
                             └──────────────┘
```

### Tabla módulo a módulo

| Módulo | Rol | I/O clave |
|---|---|---|
| `src/main.py` | Borde FastAPI. `/query`, `/compare`, `/evals`, `/ingest`, `/health`. Mount estático en `/app` (EOF, línea 260). | Carga `roles.json` + `metadata.json` al import. `/evals` cachea module-global `_evals_cache`. |
| `src/pipeline.py` | Orquestador. Envuelve cada stage en `StageOk/StageErr`, aborta en el primer error. Construye `UserContext`, resuelve política, mide TTFT. | Sin I/O. |
| `src/models.py` | Modelos Pydantic del contrato. `frozen=True, extra="forbid"` en tipos de dominio; los de API usan `extra="forbid"` en request/response pero `DocumentChunk` no declara ninguno (MI-4). | — |
| `src/policies.py` | Dict `POLICY_PRESETS` + `resolve_policy(name, top_k)`. También `load_roles()` y el muerto `filter_by_role()`. | Lee roles.json. |
| `src/retriever.py` | Retrieval híbrido. `retrieve()` (default), `semantic_retrieve()` (comparación). Singletons lazy `_model`, `_bm25`; `invalidate_caches()` resetea `_bm25`. | Lee FAISS + `index_documents.json` + `bm25_corpus.json` en cada llamada a `retrieve()`. FAISS no se cachea in-process. |
| `src/indexer.py` | Rebuild completo: carga docs, embedea con MiniLM-L6-v2, escribe `querytrace.index` + `index_documents.json` + `bm25_corpus.json`. `tokenize_for_bm25()` usado por indexer y retriever. | Escribe tres artifacts a `artifacts/`. |
| `src/ingest.py` | PDF → texto → append metadata → reindex. `_INGEST_LOCK` threading.Lock, validación, sanitizador de filename, generador de doc_id. | Escribe `corpus/documents/<file>.txt`, muta `corpus/metadata.json`, invoca `indexer.build_and_save()`. |
| `src/evaluator.py` | Harness de 12 queries, precision@k + recall + permission_violation_rate. Usa `run_pipeline()` así que las métricas reflejan el contexto ensamblado. | Lee `evals/test_queries.json`. |
| `src/stages/*.py` | Cuatro stages de cómputo puro. Sin I/O, sin globales. Cada una devuelve un dataclass con nombre. | — |
| `src/protocols.py` | `RetrieverProtocol`, `RoleStoreProtocol`, `MetadataStoreProtocol` para inyección de dependencias. | — |
| `src/freshness.py` | Helpers puros. `compute_freshness()` usada por la stage de freshness. `apply_freshness()` está muerta. | — |
| `src/context_assembler.py` | Código muerto — packer pre-refactor. Sólo referenciado por `tests/test_context_assembler.py`. | — |

## 4. Estado, caching y comportamiento en runtime

### Diagrama de concurrencia del ingest (MA-2)

```
Thread A (upload PDF 1)         Thread B (upload PDF 2)      Thread C (query)
    │                                 │                            │
    │  extract_text                   │  extract_text              │
    │  (SIN lock, ~5s)                │  (SIN lock, ~5s)           │
    │                                 │                            │
    ├──▶ acquire _INGEST_LOCK ▓▓▓▓   │                            │
    │   (B espera)                    │                            │
    │                                 │                            │
    │   write metadata.json           │                            ├─▶ retrieve()
    │   build_and_save() 5-10s        │                            │   │
    │     ├─ FAISS.write (no atomic)  │                            │   ├─ FAISS.read
    │     │                           │                            │   │   ⚠ puede leer
    │     │                           │                            │   │   archivo a medio
    │     │                           │                            │   │   escribir → 500
    │     ├─ index_documents.json     │                            │   │
    │     └─ bm25_corpus.json         │                            │   ├─ BM25 singleton
    │                                 │                            │   │   ⚠ aún viejo
    │   release lock ───────────────▶│                            │   │
    │                                 ├──▶ acquire lock ▓▓▓▓▓     │   │
    │                                 │                            │   │
    │   ◀── (aquí main.py llama        │                            │   │
    │       invalidate_caches())       │                            │   │
    │                                 │                            │   ▼
    │   VENTANA DE RACE: main.py liberó el lock, pero aún no ha
    │   llamado invalidate_caches() → C obtiene FAISS nuevo +
    │   BM25 viejo y devuelve ranking incoherente.
    │
    ▼
```

### Puntos clave de estado

- **Singletons locales al proceso**: `_model` (SBERT), `_bm25` (BM25Okapi). `_model` nunca se invalida — es corpus-independent. `_bm25` se invalida sólo con `invalidate_caches()` post-ingest.
- **Lecturas de disco por request**: `retrieve()` llama `load_persisted_index()` cada vez — lee FAISS y el JSON de payloads en cada query. El corpus BM25 sólo en cold-cache.
- **Estado mutable module-global en main.py**: dict `_metadata` + `_evals_cache` opcional. Ingest muta ambos. No es thread-safe entre workers de uvicorn.
- **Alcance del lock**: `_INGEST_LOCK` serializa metadata+reindex dentro de un proceso. Un uvicorn multi-worker lo rompe (MA-2). `invalidate_caches()` corre *fuera* del lock desde `main.py:234`; entre la liberación del lock y la invalidación, un `/query` concurrente puede correr contra FAISS nuevo pero `_bm25` viejo.
- **Cache de evals**: module-level `Optional[dict]`. Se puebla en el primer call a `/evals`. Se limpia por ingest. Si `run_evals` falla, el cache queda None y el próximo call reintenta completo.
- **Frontend estático**: montado en `/app` vía `StaticFiles(html=True)`. Cualquier ruta futura que empiece con `/app/...` será tapada.
- **CORS**: `allow_origins=["*"]`, todos los métodos, todos los headers. Justificado en CLAUDE.md para dev con `file://`; tradeoff de producción (MA-3).
- **Gate de ingest**: env `ALLOW_INGEST` leída por-request. Sin otra auth en `/ingest` incluso cuando está habilitada (CR-2).

## 5. Resumen de contratos API

### Esquema de endpoints

```
┌───────────────────────────────────────────────────────────────────┐
│  GET /health                                                      │
│  ─────────────                                                    │
│  ← { "status": "ok", "ingest_enabled": bool }                     │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /query                                                      │
│  ─────────────                                                    │
│  → { "query": str, "role": "analyst|vp|partner",                  │
│      "top_k": int=5, "policy_name": str="default" }               │
│                                                                   │
│  ← { "query": str,                                                │
│      "context": [ DocumentChunk... ],                             │
│      "total_tokens": int,                                         │
│      "decision_trace": DecisionTrace | null }                     │
│                                                                   │
│  DocumentChunk:                                                   │
│    { doc_id, content, score, freshness_score?, tags,              │
│      title?, doc_type?, date?, superseded_by? }                   │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /compare                                                    │
│  ─────────────                                                    │
│  → { "query", "role", "top_k",                                    │
│      "policies": ["naive_top_k","permission_aware","full_policy"]}│
│                                                                   │
│  ← { "query", "role",                                             │
│      "results": { <policy_name>: QueryResponse, ... } }           │
│                                                                   │
│  400 si policies=[] o policy desconocida.                         │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  GET /evals                                                       │
│  ──────────                                                       │
│  ← { "per_query": [...], "aggregate": {...} }                     │
│                                                                   │
│  Cacheada después del primer call.                                │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  POST /ingest  (multipart/form-data)                              │
│  ─────────────                                                    │
│  → file=PDF, title, date=YYYY-MM-DD, min_role, doc_type,          │
│    sensitivity, tags="a,b,c"                                      │
│                                                                   │
│  ← IngestResponse {                                               │
│      status, doc_id, title, file_name, type, date, min_role,      │
│      sensitivity, tags, total_documents }                         │
│                                                                   │
│  Códigos de error:                                                │
│   403 → ingest deshabilitado (ALLOW_INGEST=false)                 │
│   415 → no es PDF                                                 │
│   400 → validación (title vacío, fecha mala, enum inválido)       │
│   413 → >10 MB                                                    │
│   422 → PDF ilegible o <50 chars de texto                         │
│   500 → error de layout del corpus                                │
└───────────────────────────────────────────────────────────────────┘
```

### Estructura de DecisionTrace

```
DecisionTrace
├── user_context: UserContext
│     ├── role: str
│     └── access_rank: int
├── policy_config: PolicyConfig
│     ├── name, token_budget, top_k, half_life_days
│     └── skip_permission_filter, skip_freshness, skip_budget
├── included: List[IncludedDocument]
├── blocked_by_permission: List[BlockedDocument]
├── demoted_as_stale: List[StaleDocument]
├── dropped_by_budget: List[DroppedByBudget]
├── total_tokens: int
├── ttft_proxy_ms: float
└── metrics: TraceMetrics
      ├── retrieved_count
      ├── blocked_count, stale_count, dropped_count, included_count
      ├── total_tokens, budget_utilization
      └── avg_score, avg_freshness_score
```

### Invariantes

- `retrieved_count == blocked_count + included_count + dropped_count` — forzada en `trace_builder`.
- `result.trace.included == result.context` — verificada por test.

## 6. Hallazgos del backend (modo revisor hostil)

### Distribución por severidad

```
  CRITICAL  ██                           2
  MAJOR     ███████                      7
  MINOR     █████████                    9
  NIT       █████                        5
            ─────────────────────────
            0    5    10   15
```

### Orden sugerido de cierre

```
   ┌────────────┐    ┌────────────┐    ┌────────────┐
   │   CR-1     │──▶ │   CR-2     │──▶ │   MA-2     │
   │ drift tree │    │ auth ingest│    │ lock proc  │
   └────────────┘    └────────────┘    └────────────┘
                                              │
   ┌────────────┐    ┌────────────┐    ┌──────▼─────┐
   │   MA-7     │◀── │   MA-3     │◀── │   MA-1     │
   │ trace 400  │    │ CORS *     │    │ artifacts  │
   └────────────┘    └────────────┘    └────────────┘
          │
          ▼
   (MINOR + NIT pueden esperar)
```

---

### CRITICAL

**CR-1 — [RESUELTO 2026-04-22] Drift del working-tree de un ingest real estaba rompiendo un test**
- *Síntoma original:* `corpus/metadata.json` + `artifacts/*` modificados; `corpus/documents/agenda.txt` untracked.
- *Síntoma original:* `tests/test_retriever.py:67-69` hacía hardcode de `assert len(results) == 12  # corpus has 12 docs`, pero metadata + FAISS tenían 13 entradas (IDs `doc_001…doc_013`).
- Por qué importaba: (a) el test era frágil — cualquier ingest real lo rompía; (b) las afirmaciones "CI en verde" sólo eran ciertas contra un estado de artifacts específico; (c) el demo de ingest muta archivos commiteados sin aislamiento de "sandbox de demo".
- *Fix aplicado (UI-A):* `agenda.txt` removido, metadata recortada a 12 docs, artifacts reconstruidos. El test ya había sido refactoreado previamente para leer `corpus_size` desde `metadata.json`, así que el fix dinámico ya está en su lugar. La tensión efímero-vs-tracked alrededor de `corpus/` queda sin resolver a nivel de diseño.

**CR-2 — Sin auth en `/ingest` cuando está habilitado**
- `src/main.py:177-253`. El único gate es la env var `ALLOW_INGEST`.
- En cualquier deploy de Render con `ALLOW_INGEST != "false"`, cualquier caller de la internet pública puede escribir documentos arbitrarios al corpus, triggerar un reindex de ~5–10s, y cambiar qué devuelven futuros `/query` (incluyendo respuestas a otros usuarios). Sin API key, sin rate limit, sin chequeo de origen, y con CORS `*` así que inundaciones de escritura desde el navegador son posibles.
- Por qué importa: aunque el deploy sea demo-only, "demo" + "URL pública" + "endpoint de mutación" es un stepping-stone clásico para prompt-injection / envenenamiento del corpus en el contexto del LLM downstream. Ingest también es CPU/IO-pesado: vector de denial-of-service trivial (subir N PDFs de 10 MB en serie).

### Resumen visual de las stages afectadas por cada hallazgo MAJOR

```
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ retrieve │──▶│ permiso  │──▶│ freshness│──▶│ budget   │──▶│ trace    │
   └────┬─────┘   └──────────┘   └────┬─────┘   └──────────┘   └────┬─────┘
        │                             │                              │
        ├─ MA-1 (artifacts drift)     ├─ MA-6 (superseded_by raro)   ├─ MA-7 (ValueError→400)
        ├─ MA-4 (top_k×3 en naive)    │
        └─ MA-5 (semantic sin doc_type)
```

### MAJOR

**MA-1 — Divergencia silenciosa entre índice FAISS, JSON de payloads y corpus BM25**
- `src/retriever.py:192-202` carga tres artifacts (`querytrace.index`, `index_documents.json`, `bm25_corpus.json`) sin ningún chequeo cruzado de consistencia. Los tres se construyen en una sola pasada de `indexer.build_and_save()`, pero nada evita escrituras parciales, hand-edits o versiones desfasadas.
- `_bm25_ranks` en `src/retriever.py:107-110` correlaciona índices de filas del argsort de BM25 con `payloads[idx]["id"]`. Si `bm25_corpus.json` se construyó con un orden distinto al de `index_documents.json`, los ranks de BM25 se asignan a los doc IDs equivocados sin error visible.
- Por qué importa: clase de bug "respuesta silenciosamente incorrecta". Muy difícil de detectar porque los tests pueden pasar (los ranks siguen siendo "algún ranking") mientras prod devuelve basura.
- Fix: escribir un manifest (fingerprint de metadata + row count) junto a los artifacts; validar al cargar. O consolidar los tres archivos en un solo `.npz`/pickle.

**MA-2 — El lock de ingest es in-process; el reindex es síncrono y no-atómico**
- `src/ingest.py:45, 177-207`. `_INGEST_LOCK = threading.Lock()` serializa sólo dentro de un proceso Python. Un deploy multi-worker de uvicorn (común en FastAPI producción) tiene un lock por worker → escrituras concurrentes a `metadata.json` carrerean.
- `indexer.build_and_save()` escribe tres archivos secuencialmente (`src/indexer.py:152-166`) sin atomicidad de temp-file + rename. Un `/query` que llama `load_persisted_index()` a mitad de escritura puede ver un `querytrace.index` medio escrito → falla `faiss.read_index` → 500.
- `main.py:234` llama `invalidate_caches()` *después* de liberar el ingest lock. Durante los pocos microsegundos entre la liberación del lock y el reset del cache, `/query` puede golpear FAISS nuevo + singleton BM25 viejo y producir un ranking a partir de payloads desalineados.
- Fix: usar un file lock, escribir a `.tmp` y `os.replace()`, e invalidar los caches dentro del lock.

**MA-3 — `CORSMiddleware(allow_origins=["*"])` en producción**
- `src/main.py:33-38`. El rationale (conveniencia dev para `file://`) no aplica cuando el frontend está montado same-origin en `/app/`.
- Con `*` + `allow_methods=["*"]`, cada endpoint — incluyendo `/ingest` cuando está habilitado — es llamable desde cualquier origen por cualquier navegador. Combinado con CR-2, un script kiddie cross-site puede submittear un formulario de ingest apuntando a tu host desde `evil.example.com`.
- Fix: cuando `ALLOW_INGEST=false`, de todas maneras restringir a orígenes conocidos o al host propio del deploy. Documentar la separación dev/prod en vez de mezclarlas.

**MA-4 — `naive_top_k` devuelve 3× el `top_k` que pidió el usuario**
- `src/pipeline.py:161`: `retrieve_k = policy.top_k * 3` sin importar la política. Para `naive_top_k` (salta permission, salta freshness, salta budget), no hay atrición que compensar — el multiplicador se introdujo para el caso permission-aware.
- Un caller que pide `top_k=5, policy_name="naive_top_k"` obtiene **15** docs en el contexto. Los tests pasan porque `test_naive_top_k_dangerous_baseline` sólo asevera `included_count == retrieved_count`, no que included_count sea igual al top_k pedido.
- Por qué importa: la columna "No Filters" en Compare mode se ve inflada artificialmente vs. "Full Pipeline" — la narrativa de "naive es peligroso" viene en parte del multiplicador, no de los filtros faltantes. Los evals no se ven afectados (el evaluator siempre usa la política `default`), pero las comparaciones a ojo engañan a los viewers.
- Fix: multiplicar sólo cuando `not policy.skip_permission_filter`, o documentar que `top_k` es un knob de stage de retrieval, no de contexto final.

**MA-5 — `semantic_retrieve()` omite `doc_type` de sus dicts de resultado**
- `src/retriever.py:205-241`. El híbrido de producción `_build_results` incluye `"doc_type": p.get("type")` (línea 161), pero `semantic_retrieve` no. Cualquiera que cambie retrievers para ablation (lo que `semantic_retrieve` documenta soportar, línea 207) ve `doc_type=None` fluir por todo el pipeline hasta el frontend.
- `ScoredDocument.model_config = ConfigDict(frozen=True, extra="ignore")` esconde esto — ningún error de validación, sólo nulls.
- Fix: compartir el builder de dicts de resultado entre `retrieve` y `semantic_retrieve`.

**MA-6 — La stage de freshness produce estado inconsistente cuando la búsqueda en metadata falla**
- `src/stages/freshness_scorer.py:56-60`. Cuando `doc_meta is None`, `freshness_score=0.0`, `is_stale=False`, pero `superseded_by = doc.superseded_by` se forwarda del retriever. Un `FreshnessScoredDocument` con `superseded_by="doc_XXX"` y `is_stale=False` fluye downstream — contradictorio.
- Al mismo tiempo no se agrega fila `StaleDocument` para ese doc, así que la traza subcuenta `stale_count`. El badge del UI "⚠ Superseded by …" (driven por `superseded_by`) igual se renderea en la tarjeta, pero la narrativa de la traza diría "0 stale."
- Por qué importa: la divergencia entre retriever (autoritativo para `superseded_by` al momento de ingest) y metadata (autoritativa para todo lo demás) puede pasar cada vez que los dos se desfasen (ver MA-1).
- Fix: tratar metadata ausente como error y bloquear el doc, o confiar sólo en metadata (limpiar `superseded_by` también).

**MA-7 — El chequeo de invariante de `build_trace` lanza `ValueError`, que main.py mapea a HTTP 400**
- `src/stages/trace_builder.py:55-60` lanza `ValueError("Document accounting mismatch: ...")` al violarse el invariante.
- `run_pipeline` NO envuelve `build_trace` en un stage wrapper (`src/pipeline.py:178-189` — se llama directo, sin `_unwrap`). Entonces un mismatch burbujea como `ValueError`.
- `src/main.py:76-77` captura `ValueError` como HTTP 400 "Bad Request" y manda el mensaje del invariante al cliente. Una violación real de invariante del server debería ser 500, y el mensaje interno no debería filtrarse.
- Fix: envolver `build_trace` como las demás stages, o capturar `ValueError` de trace por separado y lanzar 500.

### MINOR

**MI-1 — Rutas de código muerto con riesgo de uso accidental**
- `src/policies.py:65-79` `filter_by_role()` — sin tipar, opera sobre "chunks" dict, duplica lo que hace `permission_filter.py` sobre `ScoredDocument`. Superficie pública (sin prefijo `_`).
- `src/freshness.py:44-70` `apply_freshness()` — misma historia, escribe estado mutable en dicts.
- `src/context_assembler.py` — archivo entero muerto (sólo test_context_assembler.py lo importa).
- Fix: borrar o marcar como deprecated.

**MI-2 — Desempate no uniforme entre los rankings de FAISS y BM25**
- `src/retriever.py:107` usa `np.argsort(-scores, kind="stable")`, FAISS devuelve por score descendente. Para corpora con empates (improbable en este corpus chico), la fusión puede favorecer la regla de desempate de un retriever. OK para prod, vale la pena anotarlo.

**MI-3 — `_normalize_scores` colapsa todos los scores iguales a 1.0**
- `src/retriever.py:140-141`. Un caller comparando top-1 contra top-N no puede distinguir "un doc claramente mejor" de "ninguna señal." Improbable en la práctica pero merece un comentario.

**MI-4 — `DocumentChunk` no tiene `model_config`, implícitamente permitiendo extras**
- `src/models.py:220-231`. Todos los demás modelos de API son `extra="forbid"`. Asymmetric strictness: los campos extra en response nunca fallan validación, así que los typos pasan desapercibidos en los tests.
- Fix: agregar `model_config = ConfigDict(extra="forbid")`.

**MI-5 — `score_freshness` reconstruye `meta_by_id` y `reference_date` en cada call**
- `src/stages/freshness_scorer.py:46-48`. Para el corpus chico de demo esto está bien (µs), pero el pipeline recomputa esto por-request aunque `_metadata` se cargó una vez al startup y sólo muta por ingest. Un cache lazy por revisión de metadata sería un poco más limpio — no es issue de performance hoy.

**MI-6 — `/evals` nunca reintenta una carga que falló**
- `src/main.py:167-174`. Si `run_evals` lanza (metadata corrupta, queries ausentes), la excepción se propaga, `_evals_cache` queda None, y el próximo call re-lanza. El cache es write-through-on-success-only. No es bug, pero significa que una falla transitoria durante el warmup de evals mantiene el endpoint roto hasta que la excepción pare.

**MI-7 — `ingest_document` extrae texto antes de adquirir el lock**
- `src/ingest.py:175` llama `extract_text_from_pdf()` fuera de `_INGEST_LOCK` (línea 177). OK para perf (pdfplumber es lento), pero significa que dos uploads concurrentes cada uno gasta 5–10s extrayendo, luego serializan en el lock para el reindex. Peor caso: dos workers carrereando para computar `generate_next_doc_id()` después de la extracción — el primero gana, el segundo lee metadata de nuevo bajo lock y obtiene `doc_(N+1)`. OK hoy, pero vale la pena anotarlo.

**MI-8 — `compute_freshness` clampa ages negativos a 0**
- `src/freshness.py:40` `age_days = max((ref - doc_date).days, 0)`. Un doc fechado después del reference obtiene score=1.0 (max freshness). El pipeline siempre usa `max(all_dates)` como reference así que es safe — hasta que alguien pase una reference estática e ingeste un doc con fecha futura.

**MI-9 — `version="0.2.0"` de FastAPI**
- `src/main.py:31`. No se ha bumpeado a través de MUST-A hasta NICE-B. Puramente cosmético para OpenAPI / `/docs`.

### NIT

**NI-1 — El orden del dict de resultado de `semantic_retrieve()` no coincide con `_build_results`**
- `src/retriever.py:226-240` omite `doc_type`, tiene orden de keys distinto a `_build_results`. Cosmético pero un hotspot de diff.

**NI-2 — `_BM25_STOPWORDS` está definido inline como frozenset construido desde `.split()`**
- `src/indexer.py:107-113`. Fácil de extender, pero hardcoded y no duplicado en ningún otro lado — si un flujo de query futuro quiere compartir tokenization, va a tener que importar desde indexer (que arrastra FAISS/SBERT). Separar el tokenizer en su propio módulo desacoplaría retrieval de indexing.

**NI-3 — Inconsistencia de naming alrededor de "type" vs "doc_type"**
- Metadata usa `"type"` (ingest.py:192, output del indexer). El retriever expone ambos `type` Y `doc_type` (línea 160-161) llamando `.get("type")`. Los modelos downstream usan `doc_type`. Dos nombres para el mismo campo es frágil.

**NI-4 — `PipelineError.__init__` pre-formatea el stage pero main.py lo re-formatea**
- `src/pipeline.py:57` y `src/main.py:81` ambos embeben el stage name en el detail del 500. Inofensivo; duplicación menor.

**NI-5 — El parsing de env de `_ingest_enabled()` acepta "true"/"True"/"1"/etc. pero sólo documenta "false"/"0"**
- `src/main.py:56`. `"not in {"false", "0"}"` significa que "TRUE", "yes", "", "cualquier cosa" habilitan ingest. El default permisivo es intencional según CLAUDE.md pero la semántica asimétrica (off-sólo-en-exact-match) es sorprendente para ops.

---

## 7. Preguntas abiertas / supuestos

1. **¿El `corpus/` commiteado está pensado para ser mutable en runtime?** CLAUDE.md reconoce el caveat del fs efímero pero no prescribe qué pasa con las mutaciones del source tree en una máquina dev (ver CR-1). Si `corpus/` es canónico, `/ingest` no debería tocarlo; si es sandbox de trabajo, no debería estar commiteado.
2. **¿Se soportan deploys multi-worker de uvicorn?** El Procfile (`uvicorn ... --host 0.0.0.0 --port $PORT`) no setea `--workers`, así que aplica el default de Render (1 worker). Si eso cambia alguna vez, MA-2 se activa.
3. **¿Cuál es el contrato entre `ScoredDocument` (extra="ignore") y el retriever?** El `extra="ignore"` es conveniente para flexibilidad de adaptador pero significa que regresiones en los campos del retriever (falta `doc_type`) son indetectables sin tests explícitos.
4. **¿Se lee `_metadata` a mitad de su mutación en `main.py:237-238`?** `_metadata["documents"] = fresh["documents"]` es un swap atómico de puntero en CPython (GIL), así que los readers ven o el viejo o el nuevo — pero la identidad del dict `_metadata` se preserva, lo que significa que cualquier código que haya tomado referencia a `_metadata["documents"]` antes de ingest ahora tiene una lista stale. No existe tal código hoy; vale la pena anotarlo.
5. **¿La falta de `extra="forbid"` en `DocumentChunk` es deliberada por compatibilidad con el frontend?** El docstring dice "Preserved for frontend compatibility" — quizá clientes viejos agregaban extras. Si es así, merece un comentario.

## 8. Veredicto final

**El core del pipeline es sólido.** La estructura basada en stages, los resultados tipados con dataclasses, la DI basada en Protocols, el chequeo de invariante del trace-builder, y el harness de 172 tests le dan al camino de retrieval profundidad defensiva real. RBAC se aplica en el punto correcto, freshness es corpus-relativa, budget es autoritario. La corrección del happy path está apretada.

**Las debilidades se agrupan en el camino de ingest/reindex y en la higiene de artifacts.** Tres problemas entrelazados: (CR-1) drift del source tree del demo de ingest que rompió un test y nunca se revirtió; (CR-2) mutación sin auth en un endpoint deployado públicamente; (MA-2) lock in-process + reindex no-atómico que no sobrevive a deploys multi-worker ni a lecturas a mitad de escritura. No son teóricos — se materializan en el momento que la app se deploya con `ALLOW_INGEST=true` o con más de un worker.

**Fragilidad secundaria: degradación silenciosa de señal.** `extra="ignore"` en ScoredDocument, el multiplicador 3× de top_k aplicado uniformemente a través de políticas, `semantic_retrieve` dropeando `doc_type`, y el mismatch de freshness/`superseded_by` en MA-6 todos producen output wrong-but-plausible en vez de errores. Son los bugs más difíciles de cazar en un pipeline read-only.

Los tests son **exhaustivos para el happy path y la matriz de policy-presets**, **delgados en drift de artifacts y escenarios de concurrencia**, y **contienen al menos un supuesto stale** (CR-1) que actualmente rompe. El evaluator está bien integrado y es confiable mientras artifacts y metadata estén en sync.

Neto: el camino de query es production-grade para el alcance del demo; el camino de ingest es un feature de demo que se shipped con endpoints de producción. Cerrar CR-1, CR-2, MA-1, MA-2, MA-3 y MA-7 traería todo el backend al mismo bar que el core del retrieval.

---

## Anexo: Línea de tiempo de un request típico

```
 t=0 ms  ┃ cliente envía POST /query
         ┃
 t=~1    ┃ FastAPI parsea JSON, valida QueryRequest
         ┃
 t=~1    ┃ main.py valida role (400 si desconocido)
         ┃
 t=~1    ┃ run_pipeline() → resolve_policy
         ┃
 t=~1    ┃ ┌─────────────────────────────────┐
         ┃ │ _retrieve_stage                 │
 t=~50   ┃ │   SBERT.encode(query) ~20ms     │
         ┃ │   faiss.read_index() ~5ms       │
         ┃ │   faiss.search() ~2ms           │
         ┃ │   BM25.get_scores() ~1ms        │
         ┃ │   RRF fuse + normalize ~1ms     │
         ┃ └─────────────────────────────────┘
         ┃
 t=~51   ┃ filter_permissions (µs)
         ┃
 t=~52   ┃ score_freshness (µs — rebuilds meta_by_id)
         ┃
 t=~55   ┃ pack_budget (~3ms — tiktoken encoding)
         ┃
 t=~55   ┃ build_trace (µs)
         ┃
 t=~56   ┃ main.py mapea a QueryResponse
         ┃
 t=~57   ┃ FastAPI serializa a JSON, responde 200

         (ttft_proxy_ms ~= 50-60ms es lo que verás en trace.ttft_proxy_ms
          después del warmup del modelo SBERT)
```
