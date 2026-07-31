# QueryTrace — Glosario de métricas y variables

Este glosario cubre todas las métricas, etiquetas y conceptos visibles en la interfaz de QueryTrace. Todas estas métricas evalúan **cómo se ensambla el contexto antes de pasárselo al LLM** — no evalúan si la respuesta final del LLM "suena bien."

---

## Lectura rápida

- **Recall** = no perdimos lo importante. Cada documento que debía aparecer, apareció.
- **Permission Violations** = no se filtró ningún documento prohibido al contexto.
- **Budget / Freshness / Blocked** explican *por qué* el contexto quedó armado así.

---

## Inventario de etiquetas actuales

Fuente: `frontend/app.js`, `frontend/index.html` — descubierto desde `POLICY_META`, `buildTracePanelHTML()`, `renderSingleResult()`, `renderCompare()`, `renderEvals()`, `renderSessionAudit()`, array de tarjetas de métricas, y template de summary bar.

### Políticas

| Etiqueta UI | Clave backend | Descripción |
|-------------|---------------|-------------|
| No Filters | `naive_top_k` | Retrieval sin controles — sin permisos, sin frescura, sin presupuesto. Existe como línea base peligrosa para comparación. |
| Permissions Only | `permission_aware` | Control de acceso por rol (RBAC) + presupuesto de tokens. Sin scoring de frescura. |
| Full Pipeline | `full_policy` | Permisos + frescura + presupuesto de tokens. Modo producción. |

### Roles

| Etiqueta UI | Rango | Acceso |
|-------------|-------|--------|
| Analyst | 1 | 6 de 16 docs — filings públicos, research notes, press release, sector overview, noticias públicas. |
| VP | 2 | 12 de 16 docs — agrega memos de deal, modelos financieros, análisis de diligencia, memos internos. |
| Partner | 3 | 16 de 16 docs — corpus completo incluyendo IC memo, LP update, y diligencia legal. |

### Modos

| Etiqueta UI | Clave interna | Función |
|-------------|---------------|---------|
| Query | `single` | Consulta con una política. Resultado detallado con tarjetas, sección de bloqueados, y Decision Trace. |
| Side-by-side | `compare` | Misma consulta, tres políticas en paralelo. Tres columnas comparativas. |
| Metrics | `evals` | Benchmark (q001–q012) + Session Audit (q013+). |
| Upload | `admin` | Ingesta de PDFs. Puede estar deshabilitado en deploys públicos. |

---

## Métricas detalladas

### Precision@5 / P@5

| | |
|---|---|
| **Etiqueta UI** | `Precision@5` (tarjetas de Metrics), `P@5` (columna de tabla benchmark) |
| **Dónde aparece** | Metrics tab — tarjetas agregadas y tabla por query |
| **Qué mide** | De los 5 documentos de mayor score devueltos por el pipeline, ¿cuántos eran los "esperados" según la definición del test? |
| **Valor alto** | Más de los documentos esperados aparecen en las primeras 5 posiciones. |
| **Valor bajo** | El sistema incluyó documentos relevantes adicionales que no estaban en la lista "esperada". En un corpus de 16 documentos con queries amplias, esto es esperable. |
| **Caveat** | **No significa que la respuesta sea "33% correcta."** Mide si los documentos pre-definidos como esperados cayeron dentro del top 5 del contexto. Un valor de 0.33 con Recall=1.0 significa que todos los esperados aparecieron, pero no necesariamente en las primeras 5 posiciones. No aparece en Session Audit (queries en vivo no tienen `expected_doc_ids`). |

---

### Recall

| | |
|---|---|
| **Etiqueta UI** | `Recall` (tarjeta de Metrics y columna de tabla benchmark) |
| **Dónde aparece** | Metrics tab — tarjetas agregadas y tabla por query |
| **Qué mide** | De todos los documentos que *deberían* haber aparecido en el contexto (según la definición del test), ¿cuántos realmente aparecieron? |
| **Valor alto (1.0)** | Nunca se perdió un documento esperado. El sistema encontró todo lo que debía encontrar. |
| **Valor bajo** | Algún documento esperado no llegó al contexto final — podría haber sido filtrado por permisos, descartado por presupuesto, o no recuperado por el retriever. |
| **Caveat** | Mide cobertura del contexto ensamblado, no calidad de una respuesta en texto. No aparece en Session Audit (queries en vivo no tienen `expected_doc_ids`). |

---

### Permission Violations / Violations

| | |
|---|---|
| **Etiqueta UI** | `Permission Violations` (tarjeta de Metrics), `Violations` (columna de tabla benchmark) |
| **Dónde aparece** | Metrics tab — tarjetas agregadas y tabla por query. El banner narrativo también lo menciona. |
| **Qué mide** | Porcentaje de queries donde un documento restringido apareció en el contexto final cuando no debería haberlo hecho. |
| **Valor 0.0% / "none"** | El sistema nunca dejó pasar un documento prohibido. Esto es lo correcto. |
| **Valor > 0%** | Un documento restringido se coló al contexto — falla de seguridad. |
| **Caveat** | Solo se calcula contra los 12 queries de benchmark que tienen `forbidden_doc_ids` definidos. Las queries en vivo en Session Audit no miden violations porque no tienen listas de documentos prohibidos. |

---

### Relevance / score / avg score

| | |
|---|---|
| **Etiqueta UI** | `Relevance` (barra en tarjetas de Query mode), `score` (tooltip en chips de Decision Trace), `avg score` (strip de métricas del trace) |
| **Dónde aparece** | Query mode — barras de resultado. Side-by-side — mini barras. Decision Trace — tooltips de chips incluidos y strip de métricas. |
| **Qué mide** | Qué tan relevante es un documento para tu consulta. Valor de 0 a 1. Combina búsqueda semántica (FAISS) y léxica (BM25) fusionadas por Reciprocal Rank Fusion (RRF) y normalizadas. |
| **Valor alto (→ 1.0)** | El documento es altamente relevante para la consulta. |
| **Valor bajo** | Menos relevante *comparado con los otros documentos del corpus para esta query*. No significa irrelevante en absoluto. |
| **Caveat** | Los scores son relativos al corpus y a la query. Un score de 0.20 no significa "malo" — significa "menos relevante que los otros documentos *en este corpus* para esta consulta". En un corpus de 16 documentos, incluso el menos relevante puede tener scores razonables. |

---

### Freshness / Avg Freshness / N/A — skipped by policy

| | |
|---|---|
| **Etiqueta UI** | `Freshness` (barra en tarjetas, columna en tablas benchmark y Session Audit), `Avg Freshness` (tarjeta de Metrics), `avg freshness` (strip de métricas del trace), `N/A — skipped by policy` (en tarjetas cuando la política no evalúa frescura) |
| **Dónde aparece** | Query mode — barra en tarjetas de resultado. Side-by-side — mini barra. Metrics — tarjeta agregada y tablas. Decision Trace — strip de métricas. |
| **Qué mide** | Qué tan reciente es un documento respecto al más nuevo del corpus. Valor de 0 a 1 (1.0 = el documento más nuevo). Los documentos supersedidos reciben una penalización adicional de 0.5×. |
| **Valor alto (→ 1.0)** | El documento es reciente comparado con el corpus. |
| **Valor bajo** | El documento es antiguo o fue supersedido. |
| **N/A** | Aparece cuando la política es **No Filters** o **Permissions Only**, porque esas políticas no ejecutan el scoring de frescura. Solo **Full Pipeline** calcula frescura. |
| **Caveat** | Es relativa al corpus, no al calendario real. Un score de 0.91 no significa "91% fresco" — significa "muy cerca de la fecha del documento más nuevo del corpus." |

---

### Tokens / Avg Total Tokens

| | |
|---|---|
| **Etiqueta UI** | `tokens` (summary bar en Query mode, stats strip en Side-by-side, columna en tablas), `Avg Total Tokens` (tarjeta de Metrics) |
| **Dónde aparece** | Query mode — summary bar. Side-by-side — stats strip por columna. Metrics — tarjeta agregada y tablas. Session Audit — columna. |
| **Qué mide** | Total de tokens consumidos por los documentos incluidos en el contexto ensamblado. |
| **Valor alto** | Más contenido en el contexto. Puede acercarse al límite del presupuesto (2048 tokens por defecto). |
| **Valor bajo** | Menos contenido pasó al contexto — sea por pocos documentos relevantes o por bloqueos de permisos. |
| **Caveat** | No es un conteo de tokens de un LLM real — es la estimación del pipeline basada en tokenización del texto. |

---

### Docs / Avg Context Docs / Included

| | |
|---|---|
| **Etiqueta UI** | `docs` (summary bar en Query mode), `included` (stats strip en Side-by-side), `Docs` (columna en tablas), `Avg Context Docs` (tarjeta de Metrics), `✓ Included` (sección en Decision Trace), `Included` (chips en Session Audit detail) |
| **Dónde aparece** | Todas las vistas. |
| **Qué mide** | Cuántos documentos pasaron todas las etapas del pipeline y fueron empaquetados en el contexto final. |
| **Valor alto** | Más documentos en el contexto — más fuentes de información para el LLM. |
| **Valor bajo** | Pocos documentos superaron los filtros — puede ser por bloqueos de permisos, restricciones de presupuesto, o baja relevancia. |

---

### Blocked / Avg Blocked / 🔒 Blocked

| | |
|---|---|
| **Etiqueta UI** | `blocked` (summary bar y stats strip), `Blocked` (columna en tablas), `Avg Blocked` (tarjeta de Metrics), `🔒 Blocked` (sección en Decision Trace), `🔒 N documents blocked by permissions` (sección expandible en Query mode), `Blocked` (chips en Session Audit detail) |
| **Dónde aparece** | Todas las vistas excepto con la política No Filters (que no filtra permisos). |
| **Qué mide** | Documentos que el retriever encontró como relevantes pero que fueron excluidos del contexto porque el rol del usuario no tiene acceso. |
| **Valor alto** | El usuario tiene un rol bajo (ej: analyst) y hay muchos documentos de acceso superior. Esto es lo esperado. |
| **Valor 0** | El usuario tiene acceso a todo (partner) o la política es No Filters. |
| **Caveat** | Un documento bloqueado es una decisión de seguridad correcta, no un error. En la sección expandible de Query mode, cada bloqueo incluye la razón: "Requires VP role — you are analyst." |

---

### Stale / Avg Stale / ⏱ Stale / ⚠ Superseded

| | |
|---|---|
| **Etiqueta UI** | `stale` (summary bar y stats strip), `Stale` (columna en tablas), `Avg Stale` (tarjeta de Metrics), `⏱ Stale` (sección en Decision Trace), `⚠ Superseded by doc_XXX — freshness penalized 0.5×` (badge en tarjetas de Query), `⚠ Superseded` (badge compacto en Side-by-side), `Stale` (chips en Session Audit detail) |
| **Dónde aparece** | Query mode — badges en tarjetas y chips en trace. Side-by-side — badges compactos. Metrics — tarjeta y tablas. Session Audit — columna y chips de detalle. |
| **Qué mide** | Documentos que fueron reemplazados por una versión más nueva (superseded). En el corpus actual hay tres pares: doc_002→doc_003 (research note), doc_007→doc_008 (financial model), doc_014→doc_010 (IC draft → final). |
| **Valor > 0** | El pipeline detectó documentos obsoletos y los demotó con penalización 0.5× en frescura. Los documentos stale **no se eliminan** — siguen en el contexto pero con menor peso. |
| **Valor 0** | No hay documentos supersedidos en los resultados, o la política no ejecuta scoring de frescura (No Filters, Permissions Only). |
| **Caveat** | **Stale no significa eliminado.** El documento supersedido sigue en el contexto pero con un penalty de 0.5× en su score de frescura, para que el LLM lo pese menos. Solo Full Pipeline detecta documentos stale. |

---

### Dropped / Avg Dropped / ✂ Dropped

| | |
|---|---|
| **Etiqueta UI** | `dropped` (stats strip en Side-by-side), `Dropped` (columna en tablas), `Avg Dropped` (tarjeta de Metrics), `✂ Dropped` (sección en Decision Trace), `Dropped` (chips en Session Audit detail) |
| **Dónde aparece** | Side-by-side — stats strip. Metrics — tarjeta y tablas. Decision Trace — sección con chips grises. Session Audit — columna y chips de detalle. |
| **Qué mide** | Documentos que pasaron los filtros de permisos y frescura, pero no cupieron en el presupuesto de tokens (2048 por defecto). |
| **Valor > 0** | El presupuesto se llenó antes de empaquetar todos los documentos elegibles. Los documentos de menor score son los que se descartan. |
| **Valor 0** | Todos los documentos elegibles cupieron en el presupuesto. |
| **Caveat** | Un documento "dropped" no es irrelevante ni bloqueado — pasó todos los filtros anteriores pero no cabe en el contexto. Es una decisión de priorización, no de seguridad. Solo se aplica con políticas que tienen presupuesto activo (Permissions Only, Full Pipeline). |

---

### Budget / Avg Budget Util / Budget utilization

| | |
|---|---|
| **Etiqueta UI** | `Budget` (barra en Decision Trace, columna en tablas), `Avg Budget Util` (tarjeta de Metrics) |
| **Dónde aparece** | Decision Trace — barra de progreso con tooltip "Percentage of the 2048-token budget used by assembled context." Metrics — tarjeta agregada. Tablas benchmark y Session Audit — columna. |
| **Qué mide** | Porcentaje del presupuesto de tokens (2048 por defecto) utilizado por los documentos empaquetados en el contexto final. |
| **Valor alto (>80%)** | Contexto pesado ("heavy") — casi todo el presupuesto está en uso. |
| **Valor medio (60–80%)** | Uso moderado ("moderate"). |
| **Valor bajo (<60%)** | Uso eficiente ("efficient") — hay margen de presupuesto sin usar. |
| **Caveat** | El banner narrativo de Metrics clasifica la utilización en tres niveles: efficient (<60%), moderate (60–80%), heavy (>80%). Estos son descriptivos, no normativos — no hay un valor "correcto." |

---

### TTFT / ttft / TTFT proxy

| | |
|---|---|
| **Etiqueta UI** | `ttft` (stats strip en Side-by-side), `ttft Xms` (strip de métricas en Decision Trace) |
| **Dónde aparece** | Side-by-side — stats strip por columna. Decision Trace — strip de métricas (tooltip: "Time-to-First-Token proxy — estimated latency before an LLM starts generating"). |
| **Qué mide** | Estimación del tiempo que tardaría un LLM en empezar a generar una respuesta con este contexto. Calculado a partir del tamaño del contexto y tiempos del pipeline. |
| **Valor bajo** | Menos latencia estimada antes de que el LLM empiece a responder. |
| **Valor alto** | Más latencia estimada — contexto más grande o pipeline más lento. |
| **Caveat** | **Es un proxy, no una medición real.** El proyecto no llama a un LLM real. El valor es una estimación basada en el conteo de tokens y tiempos de pipeline. No lo uses como benchmark de rendimiento. |

---

### blocked in full

| | |
|---|---|
| **Etiqueta UI** | `blocked in full` (etiqueta roja en tarjetas de Side-by-side, columna No Filters) |
| **Dónde aparece** | Side-by-side — columna No Filters solamente. |
| **Qué mide** | Este documento aparece sin filtrar en la columna No Filters, pero *sería* bloqueado bajo Full Pipeline para este rol. Es una anotación de contraste, no un estado del pipeline. |
| **Caveat** | Solo aparece en la columna No Filters como ayuda visual. Muestra el "leak" que ocurriría sin controles de acceso. |

---

### Decision Trace

| | |
|---|---|
| **Etiqueta UI** | `Decision Trace` (panel expandible al fondo de cada resultado) |
| **Dónde aparece** | Query mode — panel colapsable. Side-by-side — panel abierto por defecto en cada columna. |
| **Qué contiene** | Resumen narrativo en lenguaje natural + cuatro secciones de chips (✓ Included, 🔒 Blocked, ⏱ Stale, ✂ Dropped) + barra de Budget + strip de métricas (avg score, avg freshness, ttft). |
| **Para qué sirve** | Auditoría completa de cada decisión del pipeline. Cada chip tiene tooltip con detalle (score, tokens, rol requerido, doc supersedido). |

---

## Benchmark vs Session Audit

### Benchmark (q001–q012)

| | |
|---|---|
| **Qué son** | 12 queries de test predefinidas en `evals/test_queries.json`. |
| **Cómo se ejecutan** | Automáticamente al abrir la pestaña Metrics por primera vez. Cacheadas después. |
| **Política** | Siempre `full_policy`. |
| **Métricas disponibles** | P@5, Recall, Violations, Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget. |
| **IDs** | q001 a q012. |

### Session Audit (q013+)

| | |
|---|---|
| **Qué son** | Queries en vivo ejecutadas en modo Query durante la sesión actual del servidor. |
| **Cómo se ejecutan** | El usuario las corre manualmente. Se registran automáticamente. |
| **Política** | La que el usuario haya elegido (No Filters, Permissions Only, o Full Pipeline). |
| **Métricas disponibles** | Docs, Tokens, Freshness, Blocked, Stale, Dropped, Budget. **No** P@5, Recall, ni Violations (no hay `expected_doc_ids` ni `forbidden_doc_ids`). |
| **IDs** | q013 en adelante (auto-incrementan). |

---

## Persistencia del Session Audit

- El log de Session Audit vive **en memoria del servidor** — no hay persistencia a disco.
- Es **compartido** entre todos los visitantes de la misma instancia del servidor.
- **No ingreses información sensible o personal** — las queries son visibles para cualquiera que abra la pestaña Metrics.
- El log se **resetea** cuando el proceso del servidor se reinicia o se redespliega. En Render u otros hosting efímeros, cada deploy borra el log.
- Las queries de benchmark (q001–q012) no se ven afectadas por el reset porque se recalculan desde el archivo de test estático.
- Solo las llamadas `POST /query` se registran. Side-by-side (`/compare`) y Metrics (`/evals`) **no** generan entradas de auditoría.
