# QueryTrace — Roadmap de implementacion

**Proyecto:** QueryTrace Context Policy Lab  
**Objetivo:** Llevar el proyecto a nivel top para la internship en Pacific  
**Tiempo estimado total:** 3-4 dias  
**Regla de oro:** El backend ya es excelente. Todo el esfuerzo va a hacer que la UI cuente esa historia tan bien como el codigo la implementa.

---

## BLOQUE 1: MUST — Lo que transforma el proyecto

Estas son las mejoras sin las cuales el proyecto no transmite su valor real. Son las primeras en implementarse porque tienen el mayor ratio impacto/esfuerzo y porque varias son prerequisitos de las demas.

---

### IDEA 1 — Nombres humanos para las policies + warning en naive

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2-3 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`  
**Dependencias:** Ninguna. Es autocontenida.

**Descripcion detallada:**

Hoy las tres politicas se muestran con nombres internos de desarrollador: `naive_top_k`, `permission_aware`, `full_policy`. En la UI aparecen como "NAIVE", "RBAC", "FULL". Estos nombres no le dicen nada a un usuario no tecnico, y son exactamente el tipo de detalle que alguien con criterio de producto no dejaria pasar.

La mejora tiene tres partes:

1. **Renombrar las etiquetas visibles** en el objeto `POLICY_META` de `app.js` (linea 8-27):
   - `naive_top_k` → label: `"No Filters"`, desc: `"Raw retrieval only — no permissions, no freshness, no token budget. The dangerous baseline."`
   - `permission_aware` → label: `"Permissions Only"`, desc: `"Role-based access control active. Token budget enforced. No freshness scoring."`
   - `full_policy` → label: `"Full Pipeline"`, desc: `"Permissions + freshness scoring + token budget. Production-grade context assembly."`

2. **Agregar una descripcion inline visible** debajo del selector de politicas en modo Single, que cambie segun la politica seleccionada. Al hacer clic en cada radio button, aparece un texto corto explicando que hace esa politica.

3. **Agregar un warning visual** cuando el usuario selecciona "No Filters" (naive). Un banner sutil pero visible que diga algo como: *"Warning: this policy skips all access controls. Restricted documents will appear in results regardless of your role."* Esto es especialmente poderoso para la demo porque hace explicito el riesgo, que es exactamente la tesis del proyecto.

Los nombres internos (`naive_top_k`, etc.) se mantienen en el codigo backend y en las llamadas a la API — solo cambian las etiquetas visuales. En el Compare mode, los headers de columna tambien deben usar los nuevos nombres.

**Por que importa para Pacific:** Ellos buscan "great taste" explicitamente en su job posting. `naive_top_k` es un nombre de variable, no un nombre de producto. Este cambio cuesta 2 horas y transmite inmediatamente que pensas como product engineer, no solo como backend developer.

---

#### PROMPT PARA IMPLEMENTAR IDEA 1

```
Necesito mejorar los nombres de las politicas en la UI de QueryTrace. No toques el backend ni los nombres internos de la API — esto es solo cambio visual en frontend.

Archivos a modificar:
- frontend/app.js
- frontend/index.html  
- frontend/styles.css

Cambios requeridos:

1. En app.js, actualiza el objeto POLICY_META (linea 8-27) con nuevos labels y descripciones:
   - naive_top_k: label "No Filters", desc "Raw retrieval — no permissions, no freshness, no budget. Dangerous baseline."
   - permission_aware: label "Permissions Only", desc "Role-based access control + token budget. No freshness scoring."
   - full_policy: label "Full Pipeline", desc "Permissions + freshness + token budget. Production-grade."

2. En index.html, en los labels del selector de politicas (lineas 74-85), cambia los textos visibles:
   - "naive" → "No Filters"
   - "rbac" → "Permissions Only" 
   - "full" → "Full Pipeline"

3. Agrega debajo del div .policy-options (dentro de #single-policy-selector) un elemento <p> con clase "policy-description" que muestre la descripcion de la politica seleccionada actualmente. En app.js, agrega un event listener a los radios de policy para actualizar ese texto cuando cambian.

4. Cuando la politica seleccionada es "naive_top_k" (No Filters), muestra un warning banner sutil debajo de la descripcion. Usa clase "policy-warning" con fondo amarillo/ambar suave, un icono de warning (⚠), y texto: "This policy skips all access controls. Restricted documents will appear in results regardless of role." El warning se oculta cuando se selecciona otra politica.

5. Actualiza los estilos CSS necesarios para:
   - .policy-description: texto gris claro, font-size pequeno, margin-top minimo
   - .policy-warning: fondo ambar suave, borde izquierdo ambar, padding compacto, font-size pequeno
   - Transiciones suaves al cambiar entre descripciones

6. En Compare mode (las columnas), los headers ya usan POLICY_META.label — esos se actualizaran automaticamente. Verifica que los column headers y badges muestren los nuevos nombres correctamente.

IMPORTANTE: No cambies los values de los radio buttons, ni los nombres que se envian al backend (policy_name sigue siendo "naive_top_k", "permission_aware", "full_policy"). Solo cambian las etiquetas visibles.

Mantene el design language existente del proyecto (colores tierra, tipografia Bricolage Grotesque / IBM Plex Mono, estilo warm/elegante).
```

---

### IDEA 2 — Enriquecer DocumentChunk con metadata (titulo, tipo, fecha)

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 1-2 horas  
**Archivos involucrados:** `src/models.py`, `src/stages/budget_packer.py`, `src/main.py`  
**Dependencias:** Ninguna. Es prerequisito para ideas 3, 9 y 10.

**Descripcion detallada:**

Este es un cambio CRITICO de backend que desbloquea varias mejoras de frontend. Hoy el modelo `DocumentChunk` (lo que el frontend recibe en cada respuesta de `/query` y `/compare`) tiene solo estos campos:

```python
class DocumentChunk(BaseModel):
    doc_id: str
    content: str
    score: float
    freshness_score: Optional[float] = None
    tags: List[str] = Field(default_factory=list)
```

Pero el pipeline internamente tiene MUCHA mas metadata disponible. `FreshnessScoredDocument` (el input del budget packer) tiene: `title`, `date`, `min_role`, `sensitivity`, `short_summary`, `superseded_by`, `is_stale`. Toda esa informacion existe y fluye por el pipeline, pero se pierde en la conversion final a `DocumentChunk`.

El cambio es agregar campos opcionales a `DocumentChunk` y a `IncludedDocument`, y pasar la metadata a traves de la cadena:

1. Agregar a `IncludedDocument`: `title`, `doc_type`, `date`, `superseded_by`, `sensitivity`
2. En `budget_packer.py`, pasar esos campos al crear cada `IncludedDocument`
3. Agregar a `DocumentChunk`: `title`, `doc_type`, `date`, `superseded_by`
4. En `main.py`, pasar esos campos al crear cada `DocumentChunk`

Todos los campos nuevos son `Optional` con default `None` para mantener backward compatibility. Ningun test existente se rompe porque los campos son opcionales.

**Por que importa:** Sin este cambio, el frontend no puede mostrar titulos, tipos de documento, fechas, ni badges de stale en las cards. Es la base sobre la que se construyen las ideas 3, 9 y 10. Es un cambio minimo en el backend pero habilita mejoras enormes en el frontend.

---

#### PROMPT PARA IMPLEMENTAR IDEA 2

```
Necesito enriquecer los modelos DocumentChunk e IncludedDocument para que el frontend reciba metadata adicional (titulo, tipo de documento, fecha, superseded_by) que hoy existe en el pipeline pero se pierde en la conversion final.

Archivos a modificar:
- src/models.py
- src/stages/budget_packer.py
- src/main.py

Cambios en src/models.py:

1. En IncludedDocument (linea ~125), agregar estos campos opcionales:
   title: Optional[str] = None
   doc_type: Optional[str] = None
   date: Optional[str] = None
   superseded_by: Optional[str] = None

2. En DocumentChunk (linea ~212), agregar estos campos opcionales:
   title: Optional[str] = None
   doc_type: Optional[str] = None  
   date: Optional[str] = None
   superseded_by: Optional[str] = None

Cambios en src/stages/budget_packer.py:

3. En la funcion pack_budget(), donde se crea IncludedDocument (linea ~85), agregar los campos nuevos extrayendolos del FreshnessScoredDocument:
   title=doc.title,
   doc_type=getattr(doc, 'sensitivity', None),  # temporalmente, pero ver nota abajo
   date=doc.date,
   superseded_by=doc.superseded_by,

NOTA: FreshnessScoredDocument no tiene un campo "type" directo, pero tiene "sensitivity". El campo "type" (public_filing, deal_memo, etc.) no existe en FreshnessScoredDocument. Para resolver esto:
- Agrega un campo opcional `doc_type: Optional[str] = None` a ScoredDocument y FreshnessScoredDocument en models.py
- En retriever.py funcion _build_results() (linea ~141), pasa el campo "type" del payload como "doc_type" en el dict de resultado
- Esto hara que fluya a traves de todo el pipeline: retriever → ScoredDocument → FreshnessScoredDocument → IncludedDocument → DocumentChunk

Cambios en src/main.py:

4. En la funcion query() (linea ~70), donde se crea DocumentChunk, agregar los campos nuevos:
   title=inc.title,
   doc_type=inc.doc_type,
   date=inc.date,
   superseded_by=inc.superseded_by,

5. Hacer lo mismo en la funcion compare() (linea ~122) que tiene la misma conversion.

IMPORTANTE:
- Todos los campos nuevos son Optional con default None para mantener backward compatibility
- No se debe romper ningun test existente
- Correr python3 -m pytest tests/ -v despues de los cambios para verificar
- El campo se llama doc_type (no type) para evitar conflicto con la keyword de Python
```

---

### IDEA 3 — Rediseno de cards: titulos, tipo, fecha, expand

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 4-5 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/styles.css`  
**Dependencias:** Requiere IDEA 2 completada.

**Descripcion detallada:**

Hoy las cards de documentos en modo Single se ven asi:

```
┌─────────────────────────────────────────────────┐
│ doc_001                                    #1   │
│                                                 │
│ MERIDIAN TECHNOLOGIES, INC. FORM 10-K —         │
│ FISCAL YEAR ENDED DECEMBER 31, 2023 EXCERPT:    │
│ BUSINESS OVERVIEW AND SELECTED FINANCIAL DATA   │
│ BUSINESS OVERVIEW Meridian Technologies, Inc...  │
│                                                 │
│ RELEVANCE ████████ 1.00   FRESHNESS ██████ 0.91│
│ [meridian] [public] [financials] [arr] [nrr]   │
└─────────────────────────────────────────────────┘
```

El titulo del documento (que es muy informativo) esta mezclado con el contenido en el bloque de texto. El `doc_id` es el encabezado principal. No se ve el tipo de documento, la fecha, ni hay forma de leer el contenido completo.

El rediseno propuesto:

```
┌─────────────────────────────────────────────────┐
│ Meridian Technologies — Form 10-K FY2023   #1   │
│ doc_001 · Public Filing · Mar 2024              │
│─────────────────────────────────────────────────│
│ Meridian Technologies, Inc. is a B2B fintech    │
│ platform headquartered in Austin, Texas. The... │
│                          [Show full document ▾] │
│─────────────────────────────────────────────────│
│ RELEVANCE ████████ 1.00   FRESHNESS ██████ 0.91│
│ [meridian] [public] [financials] [arr] [nrr]   │
└─────────────────────────────────────────────────┘
```

Cambios clave:
1. **Titulo real como header principal** — extraido del campo `title` del DocumentChunk (que viene del metadata)
2. **Linea de metadata** — doc_id como badge discreto + tipo de documento formateado (Public Filing, Research Note, Deal Memo, etc.) + fecha formateada (Mar 2024, Jan 2024, etc.)
3. **Contenido mas corto por defecto** — solo 2-3 lineas (~200 chars) en vez de 480
4. **Boton expand/collapse** — "Show full document ▾" / "Hide ▴" que muestra el contenido completo
5. **Mismo cambio en las cards compactas del Compare mode** — version mas condensada pero con titulo visible

Para la funcion de expand/collapse, se necesita un event listener en cada card. Se puede usar un data attribute con el contenido completo y toggle CSS.

Las cards del Compare mode (`buildCompareCardHTML`) necesitan una version mas compacta del mismo rediseno: titulo en una linea, metadata en otra, snippet cortisimo, sin expand (porque las columnas son angostas).

**Por que importa para Pacific:** Dylan Field (CEO de Figma) es inversor de Pacific. Ellos valoran "great taste". Una card que muestra "doc_001" como titulo y un muro de texto grita "developer tool". Una card que muestra "Meridian Technologies — Form 10-K FY2023 · Public Filing · Mar 2024" grita "producto pensado para usuarios".

---

#### PROMPT PARA IMPLEMENTAR IDEA 3

```
Necesito redisenar las cards de documentos en la UI de QueryTrace para mostrar metadata util (titulo, tipo, fecha) y agregar expand/collapse del contenido completo.

PREREQUISITO: La idea 2 (enriquecer DocumentChunk) ya debe estar implementada. El frontend ahora recibe chunk.title, chunk.doc_type, chunk.date, chunk.superseded_by ademas de los campos existentes.

Archivos a modificar:
- frontend/app.js (funciones singleCardHTML y buildCompareCardHTML)
- frontend/styles.css

Cambios en singleCardHTML (app.js, linea ~310):

1. Reestructurar el card-header para mostrar:
   - Titulo del documento como encabezado principal (chunk.title || chunk.doc_id como fallback)
   - Ranking (#1, #2, etc.) a la derecha
   
2. Agregar una linea de metadata debajo del titulo:
   - doc_id como badge discreto con fondo gris claro (estilo monospace)
   - Tipo de documento formateado legible: mapear chunk.doc_type de valores internos a etiquetas humanas:
     * "public_filing" → "Public Filing"
     * "research_note" → "Research Note"  
     * "press_release" → "Press Release"
     * "sector_overview" → "Sector Overview"
     * "deal_memo" → "Deal Memo"
     * "financial_model" → "Financial Model"
     * "internal_email" → "Internal Email"
     * "board_memo" → "Board Memo"
     * "lp_update" → "LP Update"
     * "internal_analysis" → "Internal Analysis"
   - Fecha formateada corta (formatear chunk.date de "2024-03-01" a "Mar 2024")
   - Separar los tres elementos con " · "

3. Reducir el contenido preview de 480 a 200 caracteres por defecto.

4. Agregar un boton expand/collapse debajo del contenido:
   - Texto: "Show full document ▾" cuando esta colapsado, "Hide ▴" cuando esta expandido
   - Al hacer clic, alterna entre el snippet corto (200 chars) y el contenido completo (chunk.content entero)
   - Usar un data attribute o variable para almacenar el contenido completo
   - Animacion suave con CSS transition en max-height

5. Mantener las barras de Relevance y Freshness, los tags, y los colores existentes sin cambios.

Cambios en buildCompareCardHTML (app.js, linea ~472):

6. Version compacta del mismo rediseno para las columnas de Compare:
   - Titulo del documento como encabezado principal (truncado a ~60 chars si es necesario)
   - doc_id como badge discreto + tipo + fecha en una linea
   - Snippet de contenido mas corto (~120 chars)
   - SIN boton expand (las columnas son angostas)
   - Mantener las mini barras de score y freshness existentes
   - Mantener la etiqueta "blocked in full" cuando aplique

Cambios en styles.css:

7. Nuevos estilos para:
   - .card-title: font-weight 600, tamano un poco mas grande, color texto principal
   - .card-meta: font-size pequeno, color gris, font-family monospace para el doc_id badge
   - .card-meta-badge: fondo gris claro, border-radius, padding horizontal
   - .card-meta-type: texto normal
   - .card-meta-date: texto gris
   - .card-expand-btn: boton discreto, sin fondo, color acento, cursor pointer, alineado a la derecha
   - .card-content cuando expanded: max-height none o auto, con transicion
   - .card-content cuando collapsed: max-height ~4em con overflow hidden

Crear un helper JS para formatear tipos de documento y fechas. Ejemplo:
function formatDocType(raw) { return (raw || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }
function formatDate(dateStr) { if (!dateStr) return ''; const d = new Date(dateStr); return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }); }

Wireup del expand/collapse: despues de renderizar las cards, agregar event listeners a todos los botones .card-expand-btn para hacer toggle de una clase "expanded" en la card, y alternar el texto del boton.

Mantene el design language existente: colores tierra, tipografia Bricolage Grotesque / IBM Plex Mono, estilo warm/elegante. Respetar los estilos CSS existentes — extender, no reemplazar.
```

---

### IDEA 4 — Explicabilidad humana del Decision Trace

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 3-4 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/styles.css`  
**Dependencias:** Ninguna (no depende del backend enriquecido).

**Descripcion detallada:**

Hoy el Decision Trace es un panel tecnico con chips de IDs, barras de budget, y numeros promedios. Es poderoso para un ingeniero, pero crudo para cualquier otra persona. El resumen actual del toggle es: "7 blocked · 1 stale · 0 dropped" — informativo pero no explicativo.

La mejora es agregar un **parrafo de resumen en lenguaje natural** al inicio del trace body (arriba de los chips), generado puramente en el frontend a partir de los datos del trace. No requiere cambios en el backend.

El resumen se construye concatenando frases condicionales segun la data:

```
"5 documents were included in the assembled context (571 tokens, 28% of budget).
7 documents were blocked because the analyst role does not have access to VP-level
and Partner-level materials. 1 document (doc_002) was demoted because it was superseded
by a newer version (doc_003) — its freshness score was penalized by 50%.
No documents were dropped by the token budget."
```

La logica para generar este resumen:

1. **Included:** `"N documents were included in the assembled context (X tokens, Y% of budget)."`
2. **Blocked:** Si blocked_count > 0, generar una frase que diga cuantos fueron bloqueados y por que. Extraer los required_roles unicos de los blocked items para decir "VP-level and Partner-level materials" en vez de solo un numero.
3. **Stale:** Si stale_count > 0, listar cada documento stale con su superseded_by. Ejemplo: `"doc_002 was demoted because it was superseded by doc_003"`.
4. **Dropped:** Si dropped_count > 0, listar cuantos y por que (exceeded token budget). Si es 0, decir `"No documents were dropped by the token budget."`.

El resumen va dentro del `.trace-body`, como primer hijo, dentro de un `<div class="trace-summary">` con estilo de parrafo legible (no monospace, no chips — texto corrido).

Ademas, agregar **micro-tooltips** a las metricas del trace:
- `avg score` → tooltip: "Average relevance score of included documents"
- `avg freshness` → tooltip: "Average freshness score (0 = oldest, 1 = newest in corpus)"
- `ttft` → tooltip: "Time-to-First-Token estimate — how fast the context would be ready for an LLM"
- Budget bar → tooltip: "Percentage of the 2048-token budget used"

**Por que importa para Pacific:** Pacific vende a instituciones financieras. Los que compran son compliance officers y managing directors, no ingenieros. Un sistema que puede explicar EN PALABRAS por que bloqueo un documento es algo que Pacific puede usar como argumento de venta. Esta mejora demuestra que pensas en la audiencia final, no solo en el pipeline.

---

#### PROMPT PARA IMPLEMENTAR IDEA 4

```
Necesito agregar un resumen en lenguaje natural al panel de Decision Trace en la UI de QueryTrace. Hoy el trace muestra chips tecnicos con IDs. La mejora es agregar un parrafo explicativo arriba de los chips que traduzca los datos a una narrativa humana.

Archivos a modificar:
- frontend/app.js (funcion buildTracePanelHTML, linea ~630)
- frontend/styles.css

Cambios en buildTracePanelHTML (app.js):

1. Al inicio del .trace-body (despues de la linea que genera el div trace-body, antes de los trace-row), insertar un <div class="trace-summary"> con un parrafo generado dinamicamente.

2. Crear una funcion helper buildTraceSummary(trace) que genere el texto del resumen. La logica:

   a) INCLUDED: "N documents were included in context (X tokens, Y% of budget)."
      - N = trace.included.length
      - X = trace.total_tokens
      - Y = budgetPct (ya calculado)
   
   b) BLOCKED: Si m.blocked_count > 0:
      - Extraer la lista de required_roles unicos de trace.blocked_by_permission
      - Extraer el user_role del primer blocked item (todos tienen el mismo)
      - Generar: "N documents were blocked — your role (ROLE) cannot access REQUIRED_ROLES-level materials."
      - Ejemplo: "7 documents were blocked — your role (analyst) cannot access vp-level and partner-level materials."
      Si m.blocked_count === 0: omitir esta frase.
   
   c) STALE: Si trace.demoted_as_stale.length > 0:
      - Para cada stale doc: "DOC_ID was demoted (superseded by SUPERSEDED_BY, freshness penalized by PENALTY×)."
      - Unir con " " entre cada uno.
      Si no hay stale: omitir.
   
   d) DROPPED: Si m.dropped_count > 0:
      - "N documents passed all filters but were dropped because they exceeded the token budget."
      Si m.dropped_count === 0: "No documents were dropped by budget."

   Concatenar las frases a-d en un solo parrafo.

3. Agregar tooltips (title attribute) a las metricas existentes en .trace-numbers (linea ~703-706):
   - "avg score" span: title="Average relevance score of included documents (0-1)"
   - "avg freshness" span: title="Average freshness score — 1.0 = newest document in corpus"  
   - "ttft" span: title="Time-to-First-Token proxy — estimated latency before an LLM starts generating"
   - Budget label: title="Percentage of the 2048-token budget used by assembled context"

Cambios en styles.css:

4. Agregar estilos para:
   - .trace-summary: padding 12px 16px, background ligeramente diferente del trace body (un tono mas claro), border-bottom sutil, font-size 0.875rem, line-height 1.6, color texto principal (no gris — debe ser legible)
   - Dentro del trace-summary, los roles y doc IDs mencionados en el texto podrian ir en <strong> para resaltarlos visualmente

IMPORTANTE: 
- Este resumen se muestra TANTO en modo Single como en Compare (la funcion buildTracePanelHTML se usa en ambos)
- El resumen en Compare debe ser mas conciso ya que el espacio es menor
- Si startOpen es true (Compare mode), el resumen es lo primero que ve el usuario — debe ser claro y compacto
- Mantener el design language existente (colores tierra, tipografia Bricolage Grotesque)
- No tocar los chips tecnicos existentes — el resumen va ARRIBA de ellos como una capa adicional
```

---

### IDEA 5 — Seccion visible de documentos bloqueados

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 3 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/styles.css`  
**Dependencias:** Mejor despues de IDEA 2 (para tener titulo/tipo), pero funciona sin ella (solo mostraria doc_id y required_role).

**Descripcion detallada:**

Hoy cuando el sistema bloquea 7 documentos porque el rol del usuario no tiene acceso, esa informacion solo esta disponible si el usuario abre el Decision Trace y mira los chips rojos. Es facil perderlo.

La mejora es agregar una **seccion colapsable dedicada** entre las cards de resultados y el Decision Trace, que muestre los documentos bloqueados de forma prominente:

```
┌─────────────────────────────────────────────────┐
│ 🔒 7 documents blocked by permissions    [▾]    │
├─────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────┐   │
│ │ doc_006 · Deal Memo · Requires VP         │   │
│ │ Atlas Capital — Project Clearwater DD     │   │
│ └───────────────────────────────────────────┘   │
│ ┌───────────────────────────────────────────┐   │
│ │ doc_010 · Board Memo · Requires Partner   │   │
│ │ Atlas Capital — IC Memo: Acquisition      │   │
│ └───────────────────────────────────────────┘   │
│ ... (5 more)                                    │
└─────────────────────────────────────────────────┘
```

Puntos clave:
- La seccion empieza **colapsada** — solo muestra el header "N documents blocked by permissions" con un toggle
- Al expandir, muestra una mini-card por cada documento bloqueado con: doc_id, tipo (si disponible), razon formateada ("Requires VP access — your role is Analyst"), y titulo (si disponible via la IDEA 2)
- **NO se muestra el contenido** del documento bloqueado (seria incoherente mostrar contenido que el rol no puede ver)
- Estilo visual: fondo con tinte rojo/rosado suave, borde izquierdo rojo, iconografia de candado
- Si no hay bloqueados (partner tiene acceso total), la seccion no aparece

Los datos necesarios ya existen en `data.decision_trace.blocked_by_permission`, que contiene `doc_id`, `reason`, `required_role`, y `user_role`. Si la IDEA 2 esta implementada, se podria cruzar con los datos de included para mostrar titulo y tipo, pero esos campos no estan en BlockedDocument. La alternativa es agregar titulo y tipo a BlockedDocument en el backend (cambio minimo: 2 campos opcionales en models.py + pasarlos en permission_filter.py).

**Por que importa para Pacific:** Esto es compliance-thinking puro. En finanzas, no solo importa que el sistema bloquee informacion restringida — importa que el usuario SEPA que algo fue bloqueado y POR QUE. Esta transparencia es exactamente lo que Pacific necesita demostrar a sus clientes. Que tu proyecto lo haga de forma visible y elegante muestra que entendes el dominio.

---

#### PROMPT PARA IMPLEMENTAR IDEA 5

```
Necesito agregar una seccion visible de documentos bloqueados por permisos en modo Single de QueryTrace. Hoy esa info solo esta en el Decision Trace (chips). La mejora es una seccion colapsable prominente que muestre POR QUE cada documento fue bloqueado.

Archivos a modificar:
- frontend/app.js (funcion renderSingleResult)
- frontend/styles.css
- (Opcional pero recomendado) src/models.py y src/stages/permission_filter.py — para enriquecer BlockedDocument con title y doc_type

Cambio opcional en backend (recomendado):

1. En src/models.py, agregar campos opcionales a BlockedDocument:
   title: Optional[str] = None
   doc_type: Optional[str] = None

2. En src/stages/permission_filter.py, funcion filter_permissions(), al crear BlockedDocument (lineas ~51-57 y ~63-70), agregar:
   title=doc.title,
   doc_type=getattr(doc, 'doc_type', None),
   (estos campos existen en ScoredDocument si la IDEA 2 fue implementada)

Cambios en frontend/app.js:

3. En renderSingleResult() (linea ~246), despues de generar cardsHTML y antes de traceHTML, agregar una seccion de blocked documents:

   - Leer trace.blocked_by_permission (ya disponible en data.decision_trace)
   - Si la lista tiene items (length > 0), generar HTML para una seccion colapsable:
     * Header: icono candado + "N documents blocked by permissions" + toggle button
     * Body (oculto por defecto): lista de mini-cards, una por documento bloqueado
     * Cada mini-card muestra:
       - doc_id como badge
       - title (si disponible) como texto principal
       - doc_type formateado (si disponible)
       - Razon legible: formatear como "Requires [required_role] access — your role is [user_role]"
   - Si la lista esta vacia, no renderizar nada

4. Crear una funcion buildBlockedSectionHTML(blocked) que genere este HTML.

5. Agregar wireup del toggle expand/collapse para la seccion (similar al trace panel toggle).

6. Insertar el HTML entre cardsHTML y traceHTML en la linea:
   resultsSection.innerHTML = summaryHTML + cardsHTML + blockedSectionHTML + traceHTML;

Cambios en styles.css:

7. Estilos para:
   - .blocked-section: margin-top 1rem, border-radius, overflow hidden
   - .blocked-header: fondo con tinte rosado/rojo suave (ej: rgba(180,60,60,0.08)), padding, display flex, justify-content space-between, cursor pointer, border-left 3px solid var(--trace-blocked)
   - .blocked-header-text: font-weight 500, con icono de candado
   - .blocked-body: oculto por defecto (max-height 0, overflow hidden), con transicion
   - .blocked-section.open .blocked-body: max-height auto
   - .blocked-card: fondo blanco, border sutil, padding compacto, margin-bottom 4px
   - .blocked-card-reason: font-size pequeno, color rojo/naranja oscuro
   - .blocked-card-title: font-weight normal, color texto principal

Mantener design language existente. La seccion de blocked se ve como parte natural de los resultados — no debe sentirse como un error o un warning alarmista, sino como informacion de compliance profesional.
```

---

### IDEA 6 — Narrativa en el dashboard de Evals

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 3 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`  
**Dependencias:** Ninguna.

**Descripcion detallada:**

El dashboard de Evals hoy muestra 10 tarjetas de metricas y una tabla de 8 queries. Los numeros estan bien pero no dicen nada a alguien que no sepa que es Precision@5 o budget_utilization. Falta una capa narrativa que traduzca los numeros a una historia.

Tres cambios:

1. **Banner narrativo arriba de las metricas** — un parrafo que resuma los highlights mas importantes en lenguaje humano. Se genera en el frontend a partir de los datos del aggregate:

   ```
   "Zero permission violations across 8 test queries — the context layer never leaked 
   restricted documents. 100% recall — every expected document was found. Average budget 
   utilization: 53%, meaning the system assembles efficient context without waste."
   ```

   Este banner es lo primero que ve el usuario en la tab de Evals. Es el "headline" del dashboard.

2. **Micro-explicaciones debajo de cada tarjeta de metrica** — un texto gris de una linea que explique que mide:
   - Precision@5: "Accuracy of the top 5 results"
   - Recall: "Coverage of expected documents"
   - Permission Violations: "% of queries with leaked restricted docs"
   - Avg Context Docs: "Documents per assembled context"
   - Avg Total Tokens: "Token consumption per query"
   - Avg Freshness: "Document recency score (1 = newest)"
   - Avg Blocked: "Documents excluded per query by RBAC"
   - Avg Stale: "Superseded documents flagged per query"
   - Avg Dropped: "Documents cut by token budget"
   - Avg Budget Util: "How much of the token budget was used"

3. **Mostrar el texto de la query en la tabla** — hoy la columna "Query" solo muestra el ID (q001, q002...). Cambiar para mostrar el texto real de la query (truncado a ~50 chars) con el ID como tooltip o subtitulo. Los datos de la query ya vienen del backend en el campo `query` de cada item de per_query.

**Por que importa para Pacific:** Annika pidio evals EXPLICITAMENTE en su email ("We're looking for interesting ideas related to search, context management, TTFT, permissions, agentic workflows, evals"). Tenerlos es tabla stakes. Pero hacerlos legibles para un no-ingeniero es lo que diferencia un buen proyecto de un proyecto top. El banner narrativo es el equivalente a un "executive summary" — algo que alguien de Pacific lee en 5 segundos y dice "ah ok, el sistema es seguro y funciona".

---

#### PROMPT PARA IMPLEMENTAR IDEA 6

```
Necesito mejorar el dashboard de Evals de QueryTrace agregando una capa narrativa que traduzca los numeros a una historia legible para no ingenieros.

Archivos a modificar:
- frontend/app.js (funcion renderEvals, linea ~546)
- frontend/styles.css

Cambios en renderEvals (app.js):

1. BANNER NARRATIVO: Antes de las metric cards, insertar un <div class="evals-narrative"> con un parrafo generado dinamicamente. Crear una funcion buildEvalsNarrative(agg) que genere el texto:

   Logica del texto:
   - Si permission_violation_rate === 0: "Zero permission violations across N test queries — the context layer never leaked restricted documents."
   - Si permission_violation_rate > 0: "Warning: X% of queries had permission violations."
   - Si avg_recall >= 0.95: "N% recall — nearly every expected document was found."
   - Si avg_recall === 1.0: "100% recall — every expected document was found."
   - Siempre incluir: "Average budget utilization: X%, meaning the system assembles [efficient/moderate/heavy] context packs." (efficient si <60%, moderate si 60-80%, heavy si >80%)
   
   Concatenar las frases en un unico parrafo.

2. MICRO-EXPLICACIONES EN TARJETAS: Modificar el array `cards` (linea ~550) para incluir un campo `hint` con explicacion de cada metrica. Actualizar el template de cada card para mostrar el hint debajo del valor:

   Agregar hints:
   - Precision@5: "Accuracy of the top 5 results"
   - Recall: "Coverage of expected documents"
   - Permission Violations: "Restricted docs leaked to context"
   - Avg Context Docs: "Documents per assembled context"
   - Avg Total Tokens: "Token consumption per query"
   - Avg Freshness: "Document recency (1 = newest)"
   - Avg Blocked: "Docs excluded per query by RBAC"
   - Avg Stale: "Superseded docs flagged per query"
   - Avg Dropped: "Docs cut by token budget"
   - Avg Budget Util: "Token budget utilization"

   Template actualizado de cada card:
   <div class="metric-card">
     <span class="metric-card-label">LABEL</span>
     <span class="metric-card-value">VALUE</span>
     <span class="metric-card-hint">HINT</span>
   </div>

3. QUERY TEXT EN TABLA: En el bodyRows map (linea ~589), cambiar la celda de Query ID para mostrar el texto real truncado:
   - Reemplazar: ${escapeHTML(q.id)}
   - Con: ${escapeHTML(q.id)} como badge pequeno + texto de query truncado a 50 chars
   - El campo q.query ya viene del backend en cada item de per_query
   - Ejemplo: <td><span class="evals-qid">${q.id}</span> ${escapeHTML((q.query || '').slice(0, 50))}...</td>

Cambios en styles.css:

4. Estilos para:
   - .evals-narrative: padding 20px 24px, background ligeramente diferente (un tono mas calido/destacado), border-radius, margin-bottom 1.5rem, font-size 1rem, line-height 1.7, color texto principal. Destacar numeros clave con <strong>
   - .metric-card-hint: font-size 0.7rem, color gris claro, margin-top 4px, text-transform uppercase, letter-spacing 0.5px
   - .evals-qid: font-family monospace, font-size 0.75rem, background gris claro, padding 2px 6px, border-radius 3px, margin-right 6px
   - La columna Query de la tabla necesita ser mas ancha para acomodar el texto. Ajustar widths si es necesario.

Mantener design language existente. El banner narrativo debe sentirse como un "executive summary" — profesional, claro, no alarmista.
```

---

### IDEA 7 — Badge de stale en cards + badge de tipo/fecha

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2 horas  
**Archivos involucrados:** `frontend/app.js`, `frontend/styles.css`  
**Dependencias:** Requiere IDEA 2 (para superseded_by en DocumentChunk). El badge de tipo/fecha esta incluido en IDEA 3, pero si se implementan por separado, este es el lugar.

**Descripcion detallada:**

Cuando un documento incluido en los resultados es una version vieja que fue reemplazada por una mas nueva (como doc_002 reemplazado por doc_003, o doc_007 reemplazado por doc_008), hoy la unica forma de saberlo es mirando el score de freshness (que es bajo) o abriendo el Decision Trace.

La mejora es agregar un **badge visual prominente** directamente en la card del documento que diga:

```
⚠ Superseded by doc_003 — freshness penalized 50%
```

La logica es simple: si `chunk.superseded_by` no es null (despues de IDEA 2), mostrar el badge. Tambien se puede cruzar con `trace.demoted_as_stale` para obtener el penalty_applied.

El badge tiene estilo visual de advertencia suave (fondo amarillo/ambar, icono de reloj o warning) y va justo debajo del header de la card o entre el contenido y las metricas.

Si IDEA 2 no esta implementada, la alternativa es recorrer `data.decision_trace.demoted_as_stale` y construir un Set de doc_ids stale, luego en cada card verificar si el doc_id esta en ese Set. En ese caso el badge no podria decir "Superseded by doc_003" (porque no tendria el campo), pero podria decir "This document has been superseded by a newer version".

**Por que importa para Pacific:** La deteccion de documentos obsoletos es una de las features diferenciadoras de tu pipeline. Pero si el usuario no la ve en la card, no sabe que existe. Hacerla visible transforma freshness de "metrica interna del pipeline" a "feature de producto que protege al usuario de usar informacion desactualizada".

---

#### PROMPT PARA IMPLEMENTAR IDEA 7

```
Necesito agregar un badge visual de "stale/superseded" en las cards de documentos de QueryTrace cuando un documento fue reemplazado por una version mas nueva.

Archivos a modificar:
- frontend/app.js (funciones singleCardHTML y buildCompareCardHTML)
- frontend/styles.css

Estrategia: Hay dos formas de detectar si un documento es stale:
A) Si IDEA 2 fue implementada: chunk.superseded_by no es null → mostrar "Superseded by [superseded_by]"
B) Si IDEA 2 NO fue implementada: cruzar chunk.doc_id contra trace.demoted_as_stale

Implementar ambas con fallback: usar chunk.superseded_by si existe, sino cruzar con el trace.

Cambios en app.js:

1. En renderSingleResult(), antes de generar cardsHTML, construir un Map de stale info:
   const staleMap = new Map();
   if (trace?.demoted_as_stale) {
     trace.demoted_as_stale.forEach(s => staleMap.set(s.doc_id, s));
   }

2. Pasar staleMap a singleCardHTML como parametro adicional.

3. En singleCardHTML(), verificar si el documento es stale:
   const staleInfo = staleMap?.get(chunk.doc_id);
   const isSuperseded = chunk.superseded_by || staleInfo;
   
   Si isSuperseded, generar un badge HTML:
   const staleHTML = isSuperseded ? `
     <div class="stale-badge">
       <span class="stale-icon">⚠</span>
       <span class="stale-text">
         Superseded by <strong>${escapeHTML(chunk.superseded_by || staleInfo?.superseded_by)}</strong>
         — freshness penalized ${staleInfo?.penalty_applied || 0.5}×
       </span>
     </div>` : '';
   
   Insertar staleHTML justo despues del card-header y antes del card-content.

4. Hacer lo mismo en buildCompareCardHTML() pero version mas compacta:
   Solo mostrar: "⚠ Superseded" como badge corto (sin el detalle de penalty porque el espacio es limitado).

Cambios en styles.css:

5. Estilos para:
   - .stale-badge: display flex, align-items center, gap 6px, padding 6px 12px, background rgba(180, 130, 20, 0.08), border-left 3px solid var(--trace-stale, #b88c14), border-radius 4px, margin 8px 0, font-size 0.8rem
   - .stale-icon: font-size 1rem
   - .stale-text: color texto oscuro, line-height 1.3
   - .stale-text strong: font-weight 600, font-family monospace
   - En Compare cards: .compare-stale-badge version mas compacta, font-size 0.7rem, padding 3px 8px

IMPORTANTE: El badge solo aparece en documentos que estan en los resultados pero fueron marcados como stale. No aparece en todos los documentos.
```

---

### IDEA 8 — Ingesta de PDFs admin-lite

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 8-12 horas (la mas grande)  
**Archivos involucrados:** Backend: `src/main.py`, `src/indexer.py`, `src/models.py`. Frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`. Nuevo: posiblemente `src/ingest.py`.  
**Dependencias:** Funciona independiente, pero es mejor hacerla al final cuando el resto de la UI esta pulida.

**Descripcion detallada:**

Esta es la feature transformadora. Pacific es literalmente una empresa de ingesta de documentos empresariales. Su producto core toma los datos privados de una empresa y los hace buscables para IA. Si tu proyecto solo funciona con un corpus fijo que vos hardcodeaste, es una demo cerrada. Si ademas puede ingerir documentos nuevos y que pasen por el pipeline real (permisos, freshness, budget, trace), deja de ser demo y empieza a sentirse herramienta real.

**Alcance minimo viable (lo que hay que construir):**

**Backend:**
1. Nuevo endpoint `POST /ingest` que acepta un PDF como multipart/form-data + campos de metadata (title, date, min_role, tags como JSON string, y opcionalmente doc_type, sensitivity, superseded_by)
2. Logica de ingesta:
   - Generar un doc_id unico (ej: `doc_013`, incrementando desde el ultimo)
   - Extraer texto del PDF usando PyPDF2 o pdfplumber (pdfplumber es mejor para texto limpio)
   - Guardar el texto extraido como `.txt` en `corpus/documents/` con un nombre sanitizado
   - Construir el entry de metadata y hacer append a `metadata.json`
   - Llamar a `build_and_save()` del indexer para reconstruir los indices FAISS y BM25
   - Recargar los singletons del retriever (invalidar `_model` y `_bm25` caches, o forzar re-load)
   - Retornar un response con el doc_id asignado y confirmacion
3. Dependencia nueva: `pdfplumber` o usar `PyPDF2` que ya esta instalado
4. Manejo de errores: PDF corrupto, campos faltantes, titulo duplicado, etc.

**Frontend:**
1. Un tab "Admin" o una seccion dedicada accesible desde el header (como cuarto modo junto a Single/Compare/Evals, o un boton separado)
2. Un formulario con:
   - Input file (accept=".pdf")
   - Input text: Title (obligatorio)
   - Input date: Date (obligatorio, date picker)
   - Select: min_role (analyst/vp/partner — obligatorio)
   - Select: doc_type (public_filing, research_note, deal_memo, etc.)
   - Input text: Tags (comma-separated)
   - Select: sensitivity (low/medium/high/confidential)
   - Boton "Upload & Index"
3. Estado de loading con mensaje "Uploading PDF and rebuilding index..." (el reindex tarda unos segundos)
4. Mensaje de exito: "Document ingested successfully as doc_013. It is now searchable across all modes."
5. Opcionalmente: lista de los documentos actuales en el corpus como tabla simple

**Lo que NO se incluye:**
- No hay OCR (el PDF debe tener texto seleccionable)
- No hay multi-upload
- No hay edicion ni borrado de documentos
- No hay autenticacion (el tab "Admin" esta abierto)
- No hay validacion de contenido duplicado

**Por que importa para Pacific:** Es la diferencia entre "demostro que entiende el problema" y "construyo algo que funciona como herramienta real". Pacific ingiere documentos de empresas financieras todos los dias. Mostrar que tu sistema puede hacer eso (aunque sea en forma minima) demuestra que pensas end-to-end: no solo el retrieval y el pipeline, sino el ciclo completo desde la ingesta hasta la busqueda.

---

#### PROMPT PARA IMPLEMENTAR IDEA 8

```
Necesito implementar un sistema de ingesta de PDFs para QueryTrace. Un panel "Admin" donde se sube un PDF con metadata, el backend extrae el texto, lo agrega al corpus, reindexa, y el documento pasa a ser buscable en todos los modos.

Esta es una feature grande. Voy a dividirla en pasos.

PASO 1: Backend — endpoint de ingesta

Archivos a crear/modificar:
- src/ingest.py (nuevo)
- src/main.py
- requirements.txt (agregar pdfplumber si no esta, o usar PyPDF2 que ya existe)

En src/ingest.py, crear:

1. Funcion extract_text_from_pdf(file_bytes: bytes) -> str:
   - Usar PyPDF2 para extraer texto de todas las paginas
   - Concatenar con newlines
   - Limpiar whitespace excesivo
   - Retornar el texto

2. Funcion generate_next_doc_id(metadata_path: str) -> str:
   - Leer metadata.json
   - Encontrar el doc_id mas alto (ej: doc_012)
   - Retornar el siguiente (doc_013)

3. Funcion sanitize_filename(title: str) -> str:
   - Convertir titulo a filename valido (lowercase, reemplazar espacios con _, remover caracteres especiales, max 60 chars)
   - Agregar .txt al final

4. Funcion ingest_document(pdf_bytes, title, date, min_role, doc_type, sensitivity, tags, superseded_by=None) -> dict:
   - Extraer texto del PDF
   - Generar doc_id
   - Generar filename
   - Guardar el texto como .txt en corpus/documents/
   - Construir entry de metadata
   - Leer metadata.json, hacer append del nuevo entry, guardar metadata.json
   - Llamar indexer.build_and_save() para reconstruir FAISS y BM25
   - Retornar el entry creado

En src/main.py, agregar:

5. Endpoint POST /ingest:
   - Acepta multipart/form-data
   - Parametros: file (UploadFile), title (str), date (str), min_role (str), doc_type (str, default "other"), sensitivity (str, default "medium"), tags (str, JSON array como string)
   - Validar: file es PDF, title no vacio, date formato valido, min_role es uno valido
   - Llamar ingest_document()
   - Invalidar caches del retriever: importar y resetear _model=None, _bm25=None de retriever.py (o mejor: crear una funcion reload_retriever_caches() en retriever.py)
   - Invalidar _evals_cache = None para que se recalculen las evals
   - Recargar _metadata global
   - Retornar {"status": "ok", "doc_id": "doc_013", "title": "...", "tokens_extracted": N}
   - Manejo de errores: PDF vacio, texto no extraible, etc.

6. En retriever.py, agregar funcion publica:
   def invalidate_caches():
       global _model, _bm25
       _bm25 = None  # _model no necesita invalidarse, solo BM25 y el index

   Y tambien invalidar el index cacheado. Revisar si load_persisted_index() cachea algo o lee de disco cada vez. Si cachea, agregar invalidacion.

PASO 2: Frontend — tab Admin

Archivos a modificar:
- frontend/index.html
- frontend/app.js
- frontend/styles.css

En index.html:

7. Agregar un cuarto boton en el mode-toggle:
   <button class="mode-btn" data-mode="admin" aria-pressed="false">Admin</button>

8. Agregar una nueva seccion hidden:
   <section id="admin-section" class="admin-section" hidden>
     <div class="admin-header">
       <h2>Document Ingestion</h2>
       <p>Upload a PDF document to add it to the searchable corpus.</p>
     </div>
     <div id="admin-content">
       <!-- Form injected or static -->
     </div>
   </section>

En app.js:

9. Agregar "admin" al mode switch logic en switchMode():
   - Ocultar search-section en modo admin (igual que evals)
   - Mostrar admin-section
   - No mostrar single-policy-selector

10. Crear el formulario de upload dentro de admin-section (puede ser HTML estatico en index.html o generado por JS). Campos:
    - File input (accept=".pdf") — obligatorio
    - Title (text) — obligatorio
    - Date (date picker) — obligatorio
    - min_role (select: analyst/vp/partner) — obligatorio  
    - doc_type (select con opciones: public_filing, research_note, press_release, sector_overview, deal_memo, financial_model, internal_email, board_memo, lp_update, internal_analysis) — obligatorio
    - Sensitivity (select: low/medium/high/confidential) — default medium
    - Tags (text, comma-separated) — opcional
    - Boton "Upload & Index"

11. Crear funcion async uploadDocument() que:
    - Construya un FormData con el file y los campos
    - Haga POST a /ingest
    - Muestre spinner/loading: "Extracting text and rebuilding search index..."
    - En exito: muestre mensaje verde con doc_id asignado
    - En error: muestre el error

12. Opcionalmente: debajo del formulario, mostrar una tabla simple con los documentos actuales del corpus (se puede hacer un GET /corpus o simplemente hardcodear que muestre la lista de evals despues de un upload exitoso).

Estilos CSS:

13. Estilos para el admin form:
    - .admin-section: mismo padding que las otras secciones
    - .admin-form: max-width 600px, margin auto, display grid, gap 16px
    - Labels y inputs con el estilo del proyecto (colores tierra, bordes suaves)
    - Boton de upload con el estilo del boton "Run" existente
    - .admin-success: fondo verde suave, borde verde, padding, border-radius
    - .admin-error: fondo rojo suave, borde rojo
    - .admin-loading: spinner similar al de evals

IMPORTANTE:
- El reindex puede tardar 5-15 segundos. El frontend debe mostrar un loading state claro.
- Despues de un upload exitoso, si el usuario va a Single o Compare y busca, el documento nuevo debe aparecer.
- No implementar auth. El tab "Admin" esta abierto. Esto es una demo, no produccion.
- No implementar delete ni edit de documentos.
- Agregar pdfplumber a requirements.txt si se usa, o usar PyPDF2 que ya esta como dependencia.
```

---

## BLOQUE 2: SHOULD — Lo que sube de nivel

---

### IDEA 9 — Persona switcher con contexto de rol

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2 horas  
**Archivos involucrados:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`  
**Dependencias:** Ninguna.

**Descripcion detallada:**

Los tres radio buttons de rol (Analyst / VP / Partner) son funcionales pero frios. No le dicen al usuario que significa elegir cada rol ni que puede esperar antes de buscar.

La mejora es agregar un **texto descriptivo** que aparece debajo del selector de rol y cambia segun la seleccion actual:

- **Analyst seleccionado:** "Entry-level deal team member. Access to public filings, research notes, and press releases. Cannot view internal memos, financial models, or board materials. Access level: 1 of 3."
- **VP seleccionado:** "Vice President. Access to internal deal memos, financial models, and communications. Cannot view IC memos or LP updates. Access level: 2 of 3."
- **Partner seleccionado:** "Partner-level. Full corpus access — all 12 documents visible, including board materials and LP communications. Access level: 3 of 3."

Adicionalmente, se puede mostrar un indicador visual de cuantos documentos puede ver cada rol: "5 of 12 documents accessible" / "10 of 12" / "12 of 12" usando los datos reales del corpus.

Este texto ayuda al usuario a entender QUE VA A PASAR antes de hacer clic en Run. Si es un analyst, ya sabe que muchas cosas van a estar bloqueadas. Si es un partner, sabe que ve todo.

**Por que importa para Pacific:** Los permisos son el corazon de la tesis del proyecto. Hacer que el usuario entienda el alcance de su rol ANTES de buscar es product thinking aplicado. No es solo funcionalidad — es comunicacion.

---

#### PROMPT PARA IMPLEMENTAR IDEA 9

```
Necesito agregar una descripcion contextual debajo del selector de rol en QueryTrace que cambie segun el rol seleccionado, explicandole al usuario que puede ver con ese rol.

Archivos a modificar:
- frontend/index.html
- frontend/app.js
- frontend/styles.css

Cambios en index.html:

1. Debajo del div .role-options (dentro del .selector-group de roles, linea ~67), agregar:
   <p class="role-description" id="role-description"></p>

Cambios en app.js:

2. Crear un objeto con las descripciones de cada rol:
   const ROLE_DESCRIPTIONS = {
     analyst: "Entry-level deal team. Access to public filings, research notes, and press releases. <strong>5 of 12</strong> documents accessible.",
     vp: "Vice President. Access to internal deal memos, financial models, and communications. <strong>10 of 12</strong> documents accessible.",
     partner: "Full corpus access — all documents visible, including board materials and LP communications. <strong>12 of 12</strong> documents accessible."
   };

3. Crear una funcion updateRoleDescription() que lea el radio seleccionado y actualice el contenido de #role-description con innerHTML del texto correspondiente.

4. Llamar updateRoleDescription() al cargar la pagina (para mostrar la descripcion del analyst que esta seleccionado por defecto).

5. Agregar event listeners a los radio buttons de rol para llamar updateRoleDescription() cada vez que cambian.

Cambios en styles.css:

6. Estilos para:
   - .role-description: font-size 0.8rem, color var(--text-secondary), line-height 1.5, margin-top 6px, max-width 500px, transition opacity 0.2s
   - .role-description strong: font-weight 600, color var(--text-primary)

Mantener design language existente. El texto debe ser discreto pero legible — no debe competir visualmente con el buscador.
```

---

### IDEA 10 — Empty state que guie al usuario nuevo

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2 horas  
**Archivos involucrados:** `frontend/index.html`, `frontend/styles.css`  
**Dependencias:** Ninguna.

**Descripcion detallada:**

Cuando un evaluador de Pacific abre tu app por primera vez, ve esto:

```
[icono hexagonal]
Permission-Aware Context Gateway

QueryTrace retrieves documents from the Atlas Capital / Meridian Technologies corpus,
filters by role, penalises stale docs, and enforces token budgets —
with every decision visible in the Decision Trace.

Try Analyst wall ↔ to see 7 documents blocked by RBAC across three policies.
```

Es correcto pero no guia. El texto es denso, tecnico, y no le dice al usuario QUE HACER primero para llegar al "wow moment".

El rediseno propone un empty state que funcione como onboarding rapido:

1. **Headline clara:** "See how context assembly changes with different permissions, freshness, and budget controls."

2. **Tres scenario cards clickeables** que llevan directamente a los escenarios mas impactantes:
   - Card 1: "Permission Wall" — "See 7 documents blocked when an analyst searches" — click ejecuta Analyst wall en Compare
   - Card 2: "Stale Detection" — "See how outdated documents get demoted by freshness scoring" — click ejecuta VP deal view en Compare
   - Card 3: "Full Access" — "See what a partner with full access gets vs restricted roles" — click ejecuta Partner view en Compare

3. **Frase de cierre:** "Or type your own query above and choose a role to explore."

Las cards deben tener estilo visual atractivo, con el dot de color del rol (verde/azul/dorado), y al hacer clic disparan el mismo evento que los botones de escenario existentes.

**Por que importa para Pacific:** Primera impresion. Un evaluador tiene ~10 segundos para decidir si tu proyecto vale la pena. Si aterrizan en un empty state que los lleva directamente al "wow" (ver 7 documentos bloqueados lado a lado), ya gano.

---

#### PROMPT PARA IMPLEMENTAR IDEA 10

```
Necesito redisenar el empty state de QueryTrace para que funcione como un onboarding rapido que guie al usuario al "wow moment" del proyecto.

Archivos a modificar:
- frontend/index.html (seccion #empty-state, linea ~121-136)
- frontend/app.js (para wireup de clicks en las scenario cards)
- frontend/styles.css

Cambios en index.html:

1. Reemplazar todo el contenido del div #empty-state (linea 121-136) con un nuevo diseno:

   - Headline: <h2>"How different policies change context assembly"</h2>
   - Subtitulo: <p>"QueryTrace assembles document context for AI search — with role-based permissions, freshness scoring, and token budgets. Every decision is traceable."</p>
   
   - Tres scenario cards en un grid horizontal:
   
     Card 1 (class="onboard-card onboard-analyst"):
       Dot color analyst + titulo "Permission Wall"
       Descripcion: "Search as an analyst and see 7 documents blocked by RBAC. Compare across three policy levels."
       data-query, data-role, data-mode attributes iguales al boton "Analyst wall" existente
   
     Card 2 (class="onboard-card onboard-vp"):
       Dot color VP + titulo "Stale Detection"  
       Descripcion: "Search as a VP and see how outdated financial models get demoted by freshness scoring."
       data attributes iguales al boton "VP deal view"
   
     Card 3 (class="onboard-card onboard-partner"):
       Dot color partner + titulo "Full Access"
       Descripcion: "Search as a partner with unrestricted access. See the full pipeline with zero blocks."
       data attributes iguales al boton "Partner view"
   
   - Frase de cierre: <p class="onboard-hint">"Or type your own query above and choose a role to explore."</p>

Cambios en app.js:

2. Agregar event listeners a los .onboard-card elements que funcionen igual que los .example-btn existentes:
   - Leer data-query, data-role, data-mode del card
   - Setear el input value, seleccionar el rol radio, hacer switchMode si necesario, y ejecutar la query
   - Reutilizar la misma logica del handler de .example-btn (linea ~108-134)

Cambios en styles.css:

3. Estilos para:
   - #empty-state: text-align center, padding vertical generoso
   - .onboard-grid: display grid, grid-template-columns repeat(3, 1fr), gap 16px, max-width 800px, margin 2rem auto
   - .onboard-card: cursor pointer, padding 20px, border-radius 8px, border 1px solid var(--border), background white, text-align left, transition all 0.2s, hover: shadow sutil + border-color acento
   - .onboard-card-title: font-weight 600, font-size 1rem, margin-bottom 8px, display flex, align-items center, gap 8px
   - .onboard-card-desc: font-size 0.85rem, color var(--text-secondary), line-height 1.5
   - .onboard-dot: width 8px, height 8px, border-radius 50% (colores iguales a los dots existentes de analyst/vp/partner)
   - .onboard-hint: margin-top 1.5rem, color var(--text-secondary), font-size 0.85rem

Mantener design language existente. Las cards deben sentirse como invitaciones a explorar, no como botones genericos.
```

---

## BLOQUE 3: NICE TO HAVE

---

### IDEA 11 — Deploy read-only

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2-4 horas  
**Dependencias:** Todo lo anterior terminado y estable.

**Descripcion:** Desplegar la version actual a Railway, Render, o Fly.io para que Pacific pueda abrir un link sin clonar el repo. La version desplegada seria read-only (sin upload de PDFs, porque la escritura a disco es compleja en hosts cloud). El frontend se sirve desde FastAPI con StaticFiles.

**Advertencia:** Si el upload de PDFs esta implementado, la version desplegada NO lo incluiria (o se desactivaria con una variable de entorno). La razon es que los hosts cloud tienen filesystems efimeros — los archivos se pierden en cada redeploy.

---

#### PROMPT PARA IMPLEMENTAR IDEA 11

```
Necesito desplegar QueryTrace como aplicacion read-only en Railway (o Render/Fly.io como alternativa).

Pasos:

1. Agregar servicio de archivos estaticos en src/main.py para servir el frontend:
   from fastapi.staticfiles import StaticFiles
   app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
   (Agregar al final, despues de todas las rutas API, para no bloquear los endpoints)

2. Crear un Procfile o railway.json/render.yaml segun el host:
   Web command: uvicorn src.main:app --host 0.0.0.0 --port $PORT

3. Asegurar que requirements.txt tiene todas las dependencias.

4. Asegurar que los artifacts/ esten committed al repo (querytrace.index, index_documents.json, bm25_corpus.json) para que el deploy funcione sin necesidad de correr el indexer.

5. En app.js, cambiar API_BASE para que funcione tanto en local como en produccion:
   const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

6. Si el endpoint /ingest existe, desactivarlo en produccion con una variable de entorno:
   import os
   ALLOW_INGEST = os.getenv("ALLOW_INGEST", "false").lower() == "true"
   Y en el endpoint: if not ALLOW_INGEST: raise HTTPException(403, "Ingestion disabled in this deployment")

7. Testear localmente con: uvicorn src.main:app --host 0.0.0.0 --port 8000
   Y abrir http://localhost:8000/app/ para verificar que el frontend carga.

IMPORTANTE: NO hacer push de archivos sensibles. Verificar que .gitignore no excluya los artifacts necesarios.
```

---

### IDEA 12 — Exportar resultados

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 1-2 horas  

**Descripcion:** Boton "Export JSON" en Single y Compare que descarga el resultado completo (incluyendo Decision Trace) como archivo .json. Util para auditorias y documentacion.

---

#### PROMPT PARA IMPLEMENTAR IDEA 12

```
Agregar un boton "Export" en los modos Single y Compare de QueryTrace que descargue el resultado completo como JSON.

En app.js:

1. Crear funcion downloadJSON(data, filename):
   const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
   const url = URL.createObjectURL(blob);
   const a = document.createElement('a');
   a.href = url; a.download = filename; a.click();
   URL.revokeObjectURL(url);

2. En renderSingleResult(), al final del summaryHTML, agregar un boton:
   <button class="export-btn" id="export-single">Export JSON</button>
   Y en el wireup, agregar click handler que llame downloadJSON(data, `querytrace_${role}_${policy}.json`)

3. En renderCompare(), agregar un boton similar en el compare-banner:
   <button class="export-btn" id="export-compare">Export JSON</button>
   Handler: downloadJSON(data, `querytrace_compare_${data.role}.json`)

4. Estilo: .export-btn discreto, alineado a la derecha, icono de download, hover sutil.
```

---

### IDEA 13 — Micro-animaciones y polish

**Estado:** `[ ]` Pendiente  
**Tiempo estimado:** 2-3 horas  

**Descripcion:** Mejorar transiciones entre modos, suavizar aparicion de cards, mejorar hover states, y pulir loading states para que la app se sienta mas "producto terminado".

---

#### PROMPT PARA IMPLEMENTAR IDEA 13

```
Mejorar las micro-interacciones y transiciones de la UI de QueryTrace para que se sienta mas producto y menos prototipo.

Solo cambios CSS y minimos de JS. No cambiar funcionalidad.

1. Transicion de modos: al cambiar entre Single/Compare/Evals, las secciones aparecen con fade-in suave (opacity 0→1, 200ms ease-out) en vez de aparecer instantaneamente.

2. Cards de documentos: mejorar la animacion de entrada actual (ya tienen animation-delay). Agregar un slide-up sutil (translateY 8px → 0) ademas del delay existente.

3. Hover en cards: agregar sombra sutil al hacer hover, transicion suave de box-shadow y transform (translateY -1px).

4. Boton Run: transicion de color mas suave. Estado loading: pulso sutil en el spinner.

5. Trace panel: transicion smooth al abrir/cerrar (max-height con transicion, no display toggle abrupto).

6. Compare columns: entrada escalonada ya existe, mejorar con slide-from-bottom sutil.

7. Metric cards en Evals: agregar un hover lift sutil (translateY -2px + shadow).

Todo debe ser sutil — no queremos que parezca una landing page animada, sino una herramienta profesional con polish.
```

---

## PRIORIDAD DE IMPLEMENTACION

| # | Idea | Bloque | Tiempo | Dep. |
|---|------|--------|--------|------|
| 1 | Nombres humanos policies + warning | MUST | 2-3h | — |
| 2 | Enriquecer DocumentChunk (backend) | MUST | 1-2h | — |
| 3 | Rediseno cards (titulo, tipo, expand) | MUST | 4-5h | #2 |
| 4 | Explicabilidad humana del trace | MUST | 3-4h | — |
| 5 | Seccion blocked documents visible | MUST | 3h | — (mejor con #2) |
| 6 | Narrativa en Evals + query text | MUST | 3h | — |
| 7 | Badge stale + tipo/fecha en cards | MUST | 2h | #2 |
| 8 | Ingesta PDFs admin-lite | MUST | 8-12h | — |
| 9 | Persona switcher con contexto | SHOULD | 2h | — |
| 10 | Empty state guiado | SHOULD | 2h | — |
| 11 | Deploy read-only | NICE | 2-4h | Todo estable |
| 12 | Export JSON | NICE | 1-2h | — |
| 13 | Micro-animaciones | NICE | 2-3h | — |

### Plan dia a dia sugerido

**Dia 1 (UX foundation):** Ideas 1, 2, 9, 10 → ~7 horas  
**Dia 2 (Cards + trace):** Ideas 3, 4, 7 → ~9 horas  
**Dia 3 (Blocked + evals + PDF start):** Ideas 5, 6, empezar 8 → ~9 horas  
**Dia 4 (PDF finish + polish + deploy):** Terminar 8, ideas 13, 11 → ~8 horas  

---

*Generado para el proyecto QueryTrace — Pacific Software Engineering Intern Application*
