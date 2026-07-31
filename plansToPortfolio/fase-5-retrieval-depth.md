# Fase 5 — Retrieval depth: ONNX, chunking y (stretch) reranker

> Tres mejoras profundas del núcleo de retrieval, cada una con su historia de entrevista:
> (A) migrar el embedder a ONNX **probando con el eval harness propio que las métricas no cambian**,
> (B) chunking real que arregla el truncado silencioso de 256 tokens, y (C) un reranker opcional
> como stage extra. Es la fase opcional — pero A y B son las dos mejoras técnicas más citables del
> roadmap.

**Depende de:** Fase 0 (evals A/B como red de seguridad); mejor después de 2–4 para no re-embeddear
dos veces · **Esfuerzo:** 2–4 sesiones · **⚠️ Decisión D5:** el chunking cambia todas las métricas
publicadas → hay que regenerar evals y README en la misma tanda de cambios.

**Orden interno recomendado: A → B → C.** A abarata todo lo que sigue (re-embeddear con ONNX es más
rápido y liviano) y no cambia la semántica; B sí la cambia; C es stretch.

---

## Etapa A — Swap del embedder a ONNX con `fastembed` (1 sesión)

**Por qué:** hoy el stack de embeddings arrastra torch + transformers + sentence-transformers
(~500 MB de deps, el grueso del cold start y de la imagen Docker). `fastembed` (ONNX Runtime) corre
**el mismo modelo** `all-MiniLM-L6-v2` en ~50 MB, con arranque de segundos.

**La historia de entrevista es el método, no la lib:** "migré el runtime de inferencia y usé mi
propio eval harness para demostrar que la calidad de retrieval no se movió" — eval-driven
engineering, exactamente lo que un equipo de AI quiere escuchar.

1. `src/embedder.py` (nuevo): interfaz mínima `embed(texts: list[str]) -> np.ndarray` (normalizada,
   float32, 384 dims) — hoy la implementa fastembed; el resto del código deja de importar
   sentence-transformers directamente (`src/indexer.py:61-66`, `src/retriever.py:50-56`).
2. Requirements: fuera `sentence-transformers`, `transformers`, `torch` (¡y el marker por plataforma
   de la Fase 0 muere con ellos!); entra `fastembed`. Verificar al implementar qué variante ONNX del
   modelo usa fastembed (fp32 vs int8) y fijarla explícitamente.
3. **Re-embeddear y regenerar los artifacts** de todos los workspaces, listos para que el dueño
   los versione (los vectores ONNX no son bit-idénticos a los de torch).
4. **Gate de aceptación con el evaluator (la clave de la etapa):** correr `--compare` por workspace
   antes y después. Aceptar si: recall se mantiene 1.0, violaciones 0 %, y P@5 dentro de ±0.02 del
   techo. Si algún ranking flipea en un near-tie, documentar el delta honestamente junto con el
   cambio.
5. Actualizar Dockerfile (el pre-download del modelo cambia; imagen esperada ~1.2 GB → ~300 MB,
   **medir y publicar ambos números**), CI (más rápido, cache más chico) y README (tech stack).
6. Bonus que habilita: el cold start de Render free deja de ser doloroso (revisar la decisión D2).

Tests: el harness existente ES el test (por eso A va primero: sin tocar semántica, si la suite +
evals pasan, el swap es correcto). Sumar un unit del contrato del embedder (shape, norma ~1.0,
determinismo).

## Etapa B — Chunking real (1–2 sesiones)

**Problema actual (dos mitades):** (1) `src/indexer.py:65` embeddea el documento completo pero
MiniLM **trunca a ~256 tokens** — la señal semántica solo "ve" el inicio de cada doc (BM25 disimula
la pérdida porque sí usa el texto completo). (2) El budget packer empaqueta excerpts fijos de 500
chars (`indexer.py:77`), así que el "contexto" servido es un teaser, no contenido real.

**Diseño:**

1. `src/chunker.py`: split por párrafos → merge greedy hasta ~350 tokens (tiktoken) con overlap
   ~15 %; `chunk_id = f"{doc_id}#c{i:02d}"`, offsets de char, `chunk_index`, `parent doc_id`.
2. **Indexado:** una fila FAISS/BM25 por chunk; el payload lleva la metadata del doc padre
   (min_role, date, superseded_by heredados) + el **texto completo del chunk** como contenido
   empaquetable (reemplaza al excerpt de 500 chars).
3. **Stages:** permission y freshness ya operan por metadata de doc — funcionan sin cambios
   conceptuales (el chunk lleva `doc_id`); el budget packer empaqueta chunks (contenido real).
4. **Resolución del hallazgo H4 de la auditoría (semántica de `top_k`), acá y explícita:** con
   chunks el problema se agrava (32+ candidatos). Definición propuesta: `top_k` = **máximo de
   documentos únicos** en el contexto final; el budget de tokens sigue siendo el segundo límite.
   Documentar la definición en README y docstring del packer.
5. **UI:** agrupar chunks por doc en el card (mejor chunk visible + "matched 3 sections"); el trace
   muestra chunk_ids dentro del bucket del doc.
6. **Evals:** `expected_doc_ids` siguen a nivel doc → `assembled_ids` se deduplica a docs padre
   antes de computar P@5/recall (comparabilidad antes/después). Regenerar TODAS las métricas y
   publicar la tabla **antes vs después** — el cambio de comportamiento es contenido, no vergüenza:
   con truncado a 256 resuelto, queries sobre contenido profundo de docs largos deberían mejorar
   (verificarlo con 2–3 queries nuevas que apunten al final de documentos largos; si no mejora,
   contarlo igual — honestidad ante todo).

Tests: chunker (bordes: doc corto = 1 chunk, doc largo, overlap correcto, ids estables), herencia de
metadata, invariante del trace con chunks (¡la contabilidad ahora cuenta chunks — decidir y testear
si `retrieved_count` cuenta chunks o docs!), dedup de evals, top_k como cap de docs únicos.

**Riesgo principal:** es el cambio más invasivo del roadmap — toca indexer, retriever, packer,
trace, UI y evals. Tratarlo como un bloque de trabajo aislado, con el A/B de métricas como gate
antes de darlo por integrado (el aislamiento en branches, si se usa, lo maneja el dueño).

## Etapa C — Reranker cross-encoder (stretch, ½–1 sesión)

Solo si A y B quedaron sólidas y sobra energía:

1. Stage opcional `rerank` post-RRF: cross-encoder chico (variante ONNX de
   `ms-marco-MiniLM-L-6`) re-puntúa los top-N fusionados antes del permission filter.
2. Nuevo preset `full_policy_rerank` (los presets existentes no cambian — comparabilidad).
3. Publicar el A/B honesto: P@5 / latencia p50 con y sin reranker. En un corpus de 16 docs
   probablemente el delta sea chico — **ese resultado también es publicable** ("medí que a esta
   escala no paga; el stage queda como opt-in") y demuestra criterio, que vale más que la feature.

## Extra liviano de la fase (si sobra tiempo)

- **Latencia p50/p95 por stage** en `/evals` y Metrics UI (reemplaza el `ttft_proxy_ms` promedio
  por percentiles — lenguaje de infra).

---

## Definition of Done — Fase 5

- [x] A: deps sin torch; evals pre/post iguales (o delta documentado); tamaños de imagen y tiempos
      de arranque medidos y publicados; artifacts regenerados (listos para versionar)
      *(2026-07-11: `src/embedder.py` (fastembed 0.7.4, fp32 ONNX de qdrant/all-MiniLM-L6-v2-onnx);
      torch/sentence-transformers desinstalados y fuera de requirements; gate pasado — pe-deal
      idéntico (P@5 0.3333, recall 1.0, viol 0%), saas-internal P@5 full 0.2667→0.2500 (−0.017,
      dentro de ±0.02; causa: tokenizer ONNX trunca a 512 vs 256 de torch — documentado en README);
      imagen Docker 1.92 GB→980 MB medida con build real + smoke (/health 0.5 s, /query 0.39 s,
      /app/ 200); suite 396/0 en 2.2 s; artifacts de ambos workspaces regenerados; CI cachea
      ~/.cache/fastembed; test de ranking near-tie reescrito sobre el mecanismo BM25)*
- [x] B: chunking integrado con tabla de métricas antes/después en el README; H4 resuelto y
      documentado; invariante del trace redefinido y testeado para chunks
      *(2026-07-11: `src/chunker.py` (~350 tokens, overlap 15%, fallbacks oración/ventana de
      tokens, ids `doc_NNN#cNN`, offsets exactos, 12 tests); una fila FAISS/BM25 por chunk con
      metadata heredada; H4: `top_k` = cap de docs únicos en el packer (naive sin cap), documentado
      en README/architecture/docstring; invariante del trace cuenta chunks + `*_doc_count`
      derivados en TraceMetrics; evaluator dedupea a docs padre (comparabilidad pre/post);
      `build_prompt` de Ask agrupa chunks por doc (citas siguen doc-level); UI agrupa cards por
      doc con badge "matched N of M sections", chips con chunk_ids, bloqueados dedupeados —
      verificado Playwright en vivo (Single + Compare, 0 errores JS); over-retrieval 3×→6× por
      inflación de chunks; métricas regeneradas y publicadas con tabla antes/después: pe-deal
      P@5 full 0.3333→0.3000 (honesto: menos docs con contenido real, budget util 71%→98%),
      recall 1.0 y violaciones 0% en ambos corpus; queries de contenido profundo verificadas
      (2 de 3 aciertan vía chunk tardío; la tercera pierde contra el draft casi-duplicado —
      contado honestamente); suite 421/0)*
- [ ] C (si se hace): preset `full_policy_rerank` + A/B publicado con conclusión honesta
      *(2026-07-11: NO se hizo — el plan la define como stretch "solo si sobra energía"; A+B
      agotaron la sesión. Queda declarada como roadmap en README Known Limitations y en
      detailsToComplete.md)*
- [x] CLAUDE.md y architecture.md actualizados (pipeline con chunks / nuevo embedder)
      *(2026-07-11: ambos + README quickstart/tech-stack/evaluation/known-limitations)*
