# QueryTrace — Guía de Demo

Esta guía existe para un propósito específico: **que puedas abrir la app, seguir un guión, y convencer a un empleador en menos de 5 minutos**. No explica arquitectura, no habla de FAISS ni BM25 al frente, y no describe capacidades abstractas. Describe **lo que se ve en la pantalla, lo que hacés con el mouse, y qué decís en voz alta mientras lo hacés**.

---

## 1. Resumen ejecutivo (lo que dirías en 30 segundos)

> "QueryTrace simula cómo un sistema de búsqueda empresarial con IA ensambla el contexto que le pasaría a un LLM para responder. El corpus es un caso de M&A realista: un fondo de capital privado evaluando adquirir una fintech. Hay doce documentos y tres roles — un analista no debería ver el memo del Investment Committee, un VP no debería ver la carta a los LPs. La app muestra en vivo qué documentos entran al contexto, cuáles se bloquean, y **por qué**, todo auditable. No es un chatbot; es la capa invisible que decide qué ve el LLM *antes* de que el LLM hable."

Con eso ya comunicaste tres cosas: **dominio realista, permisos, trazabilidad**. El resto de la demo es evidencia visual.

---

## 2. Cómo explicar la UI (sin tecnicismos al principio)

La app tiene **una sola ventana con cuatro pestañas** arriba a la derecha: **Single, Compare, Evals, Admin**. En todas las pestañas hay los mismos controles a la izquierda — una barra de búsqueda, un selector de rol (Analyst / VP / Partner), y en Single también un selector de política (No Filters / Permissions Only / Full Pipeline).

Explicalo así, en orden:

1. **"Elegís un rol."** Es decirle al sistema "simulemos que soy un analyst junior, o un VP, o un partner". Cada rol tiene distintos permisos de acceso al corpus.
2. **"Escribís una pregunta en lenguaje natural."** Por ejemplo: *"What is Meridian's ARR growth rate?"*
3. **"Elegís cómo querés que se ensamble el contexto."** En Single hay tres políticas; cada una activa o desactiva capas del pipeline. En Compare no hay selector porque el sistema corre las tres a la vez.
4. **"Mirás los resultados."** No son respuestas — son los documentos que el sistema *le pasaría* a un LLM, con su relevancia, frescura, y una barra de auditoría llamada Decision Trace.

Ese es el mental model que tiene que tener tu audiencia antes de que toques una sola pestaña.

### La fila de botones de ejemplo

Debajo del buscador hay **dos filas de botones pre-armados** (dedupadas en UI-C: ya no repiten las historias de las tarjetas de onboarding):

- Fila "Single" → `DD risks` (VP) y `IC memo` (partner). Atajos a consultas distintas de las de onboarding, sin cambio de modo.
- Fila "Compare" → `Stale detection →` (partner, query IC + LP update). Este botón **sí** cambia a Compare — el glifo `↔`/`→` es afordancia explícita.

### El "empty state" (Single, por defecto)

Al abrir la app sin haber hecho nada, en el centro aparecen **tres tarjetas de onboarding**: **Permission Wall** (analyst), **VP Deal View** (VP) y **Stale Detection** (partner). **UI-C las rediseñó**: cada tarjeta ahora tiene dos botones — **`Run in Single`** (primario) corre la consulta en modo Single con `full_policy`, **sin cambiar de modo**, y **`Open in Compare →`** (secundario) sí salta a Compare. Esto elimina el "teleport silencioso" anterior: el cambio de modo queda siempre explícito.

### Compare — empty state propio (UI-C)

Si el usuario entra a Compare sin haber corrido ninguna consulta, ahora ve **tres tarjetas de preview** que reflejan las mismas historias base (Permission Wall / VP Deal View / Stale Detection), cada una con un hint cuantitativo resumido (ej: "Naive surfaces 12 · RBAC + Full block 7"). Las tarjetas de Compare son **un solo click** (toda la tarjeta dispara `/compare`), porque el modo ya es explícito. En la primera corrida el onboarding desaparece y se revela el banner + las tres columnas.

---

## 3. Qué representa cada modo visible (y cuándo mostrarlo)

### Single — "el uso diario"

- **Qué se ve:** barra de resumen (docs / tokens / role / policy / blocked / stale / Export JSON), tarjetas de documentos, una sección colapsable "🔒 N documents blocked by permissions", y un Decision Trace colapsable al fondo.
- **Qué historia contás:** "Así se ve cuando un usuario real consulta la base. Le da los documentos relevantes a los que su rol le da acceso, y le muestra con transparencia qué documentos existían pero fueron bloqueados."
- **Cuándo mostrarlo en la demo:** como **apertura rápida** (un analyst busca algo, ve 5 docs, 7 bloqueados) o como **cierre detallado** (abrir el Decision Trace y señalar el resumen narrativo).
- **Mensaje de negocio:** transparencia — "cada decisión queda documentada; esto es auditable por compliance".
- **Coherencia de estado (UI-B):** cambiar el rol o la política mientras hay un resultado en pantalla muestra un banner discreto arriba ("Controls changed — press Run to refresh these results.") y desatura las tarjetas viejas al 60% hasta que apretás **Run**. Esto evita el "bug visual" de que los controles digan una cosa y los resultados reflejen otra. Los botones de ejemplo de la fila Single (`DD risks` / `IC memo`) y los botones `Run in Single` del empty state son **presets deterministas**: siempre corren con **Full Pipeline**, sin importar qué política estuviera seleccionada antes, y sincronizan el radio de política para que la UI quede coherente con el resultado renderizado.

### Compare — "la pantalla que vende sola"

- **Qué se ve:** tres columnas lado a lado (No Filters, Permissions Only, Full Pipeline), cada una con su propio stats strip (included/tokens/blocked/stale/dropped/ttft), tarjetas compactas de documentos, y Decision Trace abierto por defecto.
- **Qué historia contás:** "Misma consulta, mismo rol, tres niveles de protección. Mirá lo que cambia."
- **Cuándo mostrarlo en la demo:** **siempre al principio**. Es el 80% del impacto visual del proyecto.
- **Mensaje de negocio:** "sin permisos" no es "no pasa nada" — es "un analyst junior acaba de ver el memo del Investment Committee". Las etiquetas "blocked in full" en la columna No Filters muestran **exactamente** qué documentos se filtrarían.

### Evals — "los números duros"

- **Qué se ve:** un banner narrativo arriba ("Zero permission violations across 8 test queries"), 10 tarjetas de métricas agregadas, y una tabla con 8 filas (una por query de test).
- **Qué historia contás:** "Esto no es una demo subjetiva — son métricas de 8 queries corriendo a través del pipeline real. Permission Violations: 0%. Recall: 100%."
- **Cuándo mostrarlo en la demo:** **después del Compare**, para pasar de lo cualitativo a lo cuantitativo.
- **Mensaje de negocio:** "esto podés ponerlo en un reporte a legal o auditoría. No es una promesa, es un test reproducible".

### Admin — "el modo 'cómo se alimenta el sistema'"

- **Qué se ve:** un formulario para subir un PDF con metadata (título, fecha, min_role, tipo, sensibilidad, tags). Un aviso de "Demo only: ephemeral filesystem".
- **Qué historia contás:** "Se puede cargar nuevo contenido en vivo. El backend extrae texto, lo indexa, y ya está disponible."
- **Cuándo mostrarlo en la demo:** **solamente si lo pregunta** la audiencia. Si tu deploy tiene `ALLOW_INGEST=false`, esta pestaña ni aparece — y para demos públicas en Render eso es lo recomendado.
- **Mensaje de negocio:** "el pipeline es extensible", pero no prometas que está listo para producción (no hay auth, no hay delete, reindex completo cada upload).

---

## 4. Demos concretas — literales, copiables

Cada demo te dice: qué escribir, qué rol, qué policy, qué tab, qué señalar, qué decir, y por qué importa.

### Demo A — "El analyst wall" (la demo más fuerte del proyecto)

| Paso | Acción |
|---|---|
| Tab | **Compare** |
| Cómo llegar | Click en **`Open in Compare →`** de la tarjeta "Permission Wall" del empty state. (El shortcut row ya no duplica esta historia: la tarjeta de onboarding es el único acceso directo.) |
| Buscador | `What is Meridian's ARR growth rate and net revenue retention?` |
| Rol | **Analyst** |
| Policy | (Compare corre las tres automáticamente) |

**Qué señalar en la pantalla:**

1. Columna **No Filters**: stats strip muestra un número alto de included y **0 blocked**. Entre las tarjetas hay documentos etiquetados en rojo con **"blocked in full"** — son el memo del IC (doc_011), el LP update (doc_012), memos internos, modelos financieros. *Señalalos con el mouse.*
2. Columna **Permissions Only**: stats strip ahora muestra **7 blocked**. Abrí el Decision Trace — los chips rojos de "Blocked" dicen "doc_006 ·vp", "doc_011 ·partner", etc. Cada chip te dice el rol que hubiera sido necesario.
3. Columna **Full Pipeline**: mismos 7 blocked, **más** chips amarillos de Stale (doc_002 → doc_003). Un documento obsoleto sigue apareciendo pero con penalización 0.5× de frescura.

**Qué decir en voz alta:**

> "Misma pregunta, mismo analyst. En la columna No Filters, el sistema le está pasando al LLM el memo del Investment Committee y la carta a los LPs — cosas que un analista junior jamás debería ver. En la segunda columna, RBAC bloquea 7 documentos y te dice exactamente cuáles y por qué. En la tercera, además detecta que la research note de Q3 fue reemplazada por la de Q4 y le baja la frescura para que el LLM priorice la versión vigente. Todo esto sin que el LLM se entere — pasa *antes* del prompt."

**Por qué importa para la empresa:**

Los LLMs no tienen noción de quién está preguntando. Si mandás un documento confidencial al contexto, el LLM lo va a usar. La seguridad tiene que estar **antes** del prompt, en la capa de contexto. Esta pantalla demuestra que el proyecto resuelve eso.

---

### Demo B — "VP deal view con stale detection"

| Paso | Acción |
|---|---|
| Tab | **Compare** |
| Cómo llegar | Click en **`Open in Compare →`** de la tarjeta "VP Deal View" del empty state. (UI-C quitó el shortcut "VP deal view ↔" de la fila Compare por redundante.) |
| Buscador | `What are the financial model assumptions, revenue projections, and deal valuation for Project Clearwater?` |
| Rol | **VP** |

**Qué señalar:**

- En la columna Full Pipeline, fijate en los **stale chips**: doc_007 → doc_008. Son dos versiones del modelo financiero; el v1 fue reemplazado por el v2. El pipeline completo **sigue incluyendo el v1** pero con penalización 0.5×. El LLM lo ve, pero lo pondera menos.
- Compará el ranking de tarjetas entre Permissions Only y Full Pipeline: en la segunda, las versiones viejas caen en el ranking.

**Qué decir:**

> "Un documento obsoleto es peor que uno bloqueado. Un bloqueado no te afecta la respuesta. Un obsoleto te da una respuesta con datos viejos y el LLM no sabe que son viejos. Este modo demuestra que cuando el sistema tiene dos versiones del mismo modelo, automáticamente prioriza la vigente."

**Por qué importa:** en dominios regulados (finanzas, legal, healthcare) usar la versión equivocada no es un error de UX — es responsabilidad legal.

---

### Demo C — "Stale detection" (antes: "Partner view")

| Paso | Acción |
|---|---|
| Tab | **Compare** |
| Cómo llegar | Click en el shortcut **`Stale detection →`** (fila Compare) o en **`Open in Compare →`** de la tarjeta "Stale Detection" del empty state. UI-C renombró el escenario: la query y el rol (partner) **no cambiaron**; cambió la narrativa. |
| Buscador | `What is the investment committee recommendation and LP update for the Meridian acquisition?` |
| Rol | **Partner** |

**Qué señalar:**

- Los tres stats strips muestran **0 blocked** en todas las políticas (partner tiene acceso completo).
- En la columna **Full Pipeline**, el stats strip muestra **stale=2**: doc_002 (research notes v1, reemplazado por doc_003) y doc_007 (financial model v1, reemplazado por doc_008). Ambos aparecen con el badge "⚠ Superseded".
- Confirmado en backend: `/compare` con esta query + `role=partner` devuelve `stl=2` con `demoted_as_stale: ['doc_007', 'doc_002']` en full_policy, y 0 stale en naive + rbac.

**Qué decir:**

> "El partner tiene acceso total — los permisos no filtran nada. Pero el pipeline sigue detectando que dos documentos fueron reemplazados por versiones más nuevas y los demote 0.5×. No es un tema de acceso: es un tema de higiene del contexto. Permisos y frescura son ortogonales — dos capas que operan en paralelo."

**Por qué importa:** la demo antigua ("Partner view") leía como "partner ve todo, no pasa nada" — narrativamente débil. El reframe a **Stale Detection** enfoca la atención en la capa de frescura, que sigue trabajando incluso cuando RBAC no tiene nada que bloquear.

---

### Demo D — "Single mode con Decision Trace" (la demo técnica)

| Paso | Acción |
|---|---|
| Tab | **Single** |
| Cómo llegar | Click en **`Run in Single`** de la tarjeta "Permission Wall" del empty state (UI-C: la fila Single ya no tiene "ARR growth" — la tarjeta de onboarding cubre esa historia con un botón primario que fuerza rol=Analyst y policy=Full Pipeline). Alternativa: tipear la query, elegir rol, apretar Run. |
| Buscador | `What is Meridian's ARR growth rate and net revenue retention?` |
| Rol | **Analyst** |
| Policy | **Full Pipeline** |

**Qué señalar:**

1. Barra de resumen arriba: **5 docs, ~570 tokens, analyst role, Full Pipeline, 7 blocked, 1 stale**.
2. La primera tarjeta tiene relevancia 1.00 (el 10-K de Meridian — tiene sentido, es la fuente oficial de datos de ARR).
3. Segunda tarjeta: research note con tag "⚠ Superseded by doc_003 — freshness penalized 0.5×".
4. Click en el botón **"🔒 7 documents blocked by permissions"**: se despliega una mini-lista con título, tipo, y la razón ("Requires partner role — you are analyst").
5. Click en **Decision Trace** al fondo. Arriba hay un resumen en lenguaje natural: *"5 documents were included (571 tokens, 28% of budget). 7 documents were blocked — your role (analyst) cannot access vp and partner level materials. doc_002 was demoted (superseded by doc_003, freshness penalized by 0.5×)."*
6. Abajo del resumen hay chips coloreados: verdes (incluidos), rojos (bloqueados), amarillos (stale), grises (dropped por presupuesto).

**Qué decir:**

> "Este es el panel que justifica la palabra 'Trace' en el nombre del proyecto. Cualquier respuesta del sistema se puede descomponer en decisiones auditables: qué entró, qué se bloqueó y por qué, qué se demotó, qué se descartó por presupuesto. No hay magia. Y el resumen arriba está pensado para que un stakeholder no técnico lo lea."

**Por qué importa:** compliance, auditoría, debugging de respuestas malas del LLM. "¿Por qué el LLM dijo X?" → abrí el trace, mirás el contexto.

---

### Demo E — "Evals para cerrar con números"

| Paso | Acción |
|---|---|
| Tab | **Evals** (se carga automáticamente al primer click) |

**Qué señalar:**

1. El **banner narrativo** arriba en verde: *"Zero permission violations across 8 test queries — the context layer never leaked restricted documents. 100% recall — every expected document was found."*
2. Las 10 tarjetas de métricas. Señalá específicamente:
   - **Permission Violations: 0.0%** (en verde) — la métrica que realmente importa.
   - **Recall: 1.0000** — nunca se perdió un documento esperado.
   - **Avg Blocked**: número promedio de documentos bloqueados por query. Es evidencia de que el filtro *está haciendo algo* en la mayoría de las queries.
3. La tabla por query: 8 filas, con rol, métricas y una columna final "Violations" que dice "none" en todas.

**Qué decir:**

> "Este dashboard corre el pipeline completo contra 8 queries de test escritas para cubrir los tres roles. Cero violaciones de permisos en 8 de 8. Recall perfecto. Y cada fila es reproducible — no es una screenshot, es el endpoint `/evals` respondiendo en vivo."

**Por qué importa:** es la evidencia que un CTO o un head of security le pediría a cualquier herramienta de context/retrieval antes de dejarla pasar a producción.

---

## 5. Guión recomendado de 3–5 minutos

Este es el guión que recomiendo para una demo de 4 minutos con margen. Podés recortar al final si te quedás corto.

### 0:00 — 0:30 · Setup (antes de tocar nada)

Estás en el empty state. Tres tarjetas de onboarding al centro.

> "Este es QueryTrace. Es un laboratorio que muestra cómo un sistema empresarial de retrieval le arma el contexto a un LLM, respetando permisos, frescura, y presupuesto de tokens. El corpus es un caso de M&A: Atlas Capital evaluando adquirir Meridian Technologies. Doce documentos, tres roles. Un analyst junior no debería ver el memo del comité, un VP no debería ver la carta a los LPs. Vamos a ver cómo el sistema se comporta."

### 0:30 — 1:45 · Compare Mode con "Permission Wall"

En la tarjeta "Permission Wall" del empty state, hacé click en el botón secundario **`Open in Compare →`**. La app salta explícitamente a Compare y corre la consulta. (UI-C: el click en el cuerpo de la tarjeta **no** cambia de modo; solo el botón "Open in Compare →" lo hace. Esto evita el "teleport silencioso" anterior.)

> "Misma pregunta, mismo analyst, tres niveles de protección. Miren la columna de la izquierda, 'No Filters': el sistema le está pasando el memo del Investment Committee y la carta a los LPs — cosas confidenciales. Estas etiquetas rojas que dicen 'blocked in full' marcan exactamente qué se filtraría con la política completa."

*Señalá con el mouse las tarjetas rojas en la columna de la izquierda.*

> "Columna del medio: permisos activados. Siete documentos bloqueados. Y si abren el Decision Trace, cada bloqueo tiene razón explícita: 'requires partner role'. Columna de la derecha: pipeline completo. Mismos siete bloqueos, más dos documentos marcados como stale — son versiones viejas de research notes y modelos financieros que fueron reemplazadas. El sistema igual los incluye, pero con penalización de frescura para que el LLM los pese menos."

### 1:45 — 2:30 · Decision Trace expandido

Ya está abierto en Compare. Señalá el resumen en lenguaje natural de la columna de la derecha.

> "Esto de arriba es el resumen en prosa: cinco docs incluidos, siete bloqueados, dos obsoletos. Pensado para que un stakeholder no técnico lo lea. Abajo están los chips: verdes incluidos, rojos bloqueados, amarillos stale, grises dropped por presupuesto. Cada decisión es chequeable."

### 2:30 — 3:20 · Evals para cuantificar

Click en la pestaña **Evals**.

> "Hasta acá fue cualitativo. Esto es cuantitativo. Ocho queries de test, cada una corriendo a través del pipeline. La métrica que importa está arriba: **Permission Violations: cero por ciento**. En ocho queries, el sistema nunca dejó pasar un documento restringido. Recall: uno coma cero — nunca perdimos un documento que debía aparecer."

*Si hay tiempo, señalá la tabla y mencioná la columna "Violations" llena de "none".*

### 3:20 — 4:00 · Cierre con Single + Decision Trace

Click en **Single**, después click en **`Run in Single`** de la tarjeta "Permission Wall".

> "Para cerrar: así se ve el uso real de una persona. Un analyst hace una consulta, ve 5 documentos relevantes, una barra le dice que hay 7 bloqueados por permisos. Expando el panel 'documents blocked' y veo los títulos, los tipos, y la razón. Abro el Decision Trace abajo y tengo la traza completa para auditoría. Esto es transparencia nativa, no un feature agregado al final."

### 4:00 — (opcional) · Cierre de negocio

> "El mensaje de negocio es simple: los LLMs no tienen contexto de quién pregunta. Si querés que tu LLM respete permisos, frescura, presupuesto, y dejar traza — esa lógica va antes del prompt, no después. Este proyecto es una demostración concreta de cómo construir esa capa."

---

## 6. Cómo verbalizar las diferencias entre roles, policies y modos

Este es un problema real: **Single, Compare, Evals y Admin se parecen visualmente** (hay cards, barras, colores). Si no explicás las diferencias con claridad, tu audiencia va a pensar "es la misma pantalla repetida".

Anclá cada modo a un **caso de uso humano distinto**, no a una diferencia técnica:

| Modo | "Es como si estuvieras…" |
|---|---|
| Single | haciendo una búsqueda diaria en la base de conocimiento de tu empresa. |
| Compare | un ingeniero o compliance officer validando que los controles funcionan. |
| Evals | preparando un reporte para legal o auditoría con métricas reproducibles. |
| Admin | el bibliotecario cargando un documento nuevo al corpus. |

Lo mismo con roles y policies:

- **Rol ≠ política.** El rol es *quién sos*. La política es *cómo se ensambla el contexto*. Podés tener el mismo rol con distintas políticas (Single) o la misma política con distintos roles (probás Analyst y después Partner en Compare). Mencioná esto explícitamente una vez durante la demo para que no se mezclen.
- **"No Filters" no es un setting — es un contraejemplo.** Existe para mostrar qué pasa sin controles. No es una opción que usarías en producción. El banner amarillo "⚠ This policy skips all access controls" al lado está hecho justamente para que nadie se confunda.

Cuando hagas Compare y tu audiencia vea tres columnas, señalá: **"El rol es el mismo en las tres columnas. Lo único que cambia es cómo se ensambla el contexto. Por eso las diferencias que ves son atribuibles a la política, no al usuario."** Esa frase desambigua todo.

---

## 7. Cómo explicar su relevancia para una empresa

Tenés tres ángulos para venderlo, elegí según la audiencia:

### A. Seguridad / Compliance

> "Los LLMs usan lo que les das. Si el contexto contiene un documento confidencial, el LLM va a usar ese documento. La seguridad no puede estar en el prompt, tiene que estar en la capa de contexto. Esto demuestra exactamente cómo: RBAC aplicado antes del prompt, con evidencia por query de que ningún documento restringido se coló."

### B. Calidad de respuesta / Freshness

> "Un documento bloqueado no te afecta la respuesta. Un documento obsoleto sí — te da una respuesta con datos viejos y el LLM no sabe que son viejos. Este proyecto trata stale y permissions como dos problemas separados, con un score de frescura relativo al documento más nuevo del corpus y penalización 0.5× para versiones reemplazadas."

### C. Auditoría / Debugging

> "Cuando una respuesta del LLM es mala o sospechosa, la pregunta es 'qué había en el contexto'. Este proyecto convierte esa pregunta en un endpoint: `/query` te devuelve la respuesta *y* el Decision Trace completo. Cada documento incluido tiene score, cada bloqueo tiene razón, cada drop tiene explicación. No es una caja negra."

Los tres ángulos comparten el mismo mensaje de fondo: **"hace visible lo invisible"**. El retrieval es típicamente la parte más opaca de un stack RAG; este proyecto la abre.

---

## 8. Fortalezas visuales y partes débiles (honesto)

### Fortalezas — apoyate en estas

1. **Compare mode con tres columnas.** Es imbatible visualmente. Mostrá esto en los primeros 30 segundos.
2. **Las etiquetas "blocked in full"** en la columna No Filters. Muestran *exactamente* qué se filtraría. Una audiencia no técnica lo entiende sin explicación.
3. **La sección "🔒 N documents blocked by permissions"** en Single. Cuando se expande, cada bloqueo tiene título, tipo, y razón humana ("Requires partner role — you are analyst"). Esto es *muy* fuerte para compliance.
4. **El resumen narrativo del Decision Trace.** Arranca con prosa entendible, no con chips técnicos.
5. **El badge de stale ("⚠ Superseded by doc_003 — freshness penalized 0.5×").** Cuenta la historia del pipeline en una sola línea.
6. **Evals con el banner verde "Zero permission violations".** Perfecto para cerrar una demo.
7. **Role descriptions que se actualizan debajo del selector.** Si cambiás de analyst a partner, la descripción cambia. Es un toque de polish que transmite que la UI fue pensada.

### Partes débiles — tené respuesta lista, no las saques vos

1. **Precision@5 = 0.30 en Evals.** Parece bajo. Si te preguntan: *"El corpus tiene 12 documentos y muchas queries son amplias, entonces el 'top 5 esperado' es una vara muy alta. Lo que importa es Recall = 1.0 — nunca perdimos un doc — y Permission Violations = 0%."* No toques el tema vos; si te preguntan, pivotá a recall.
2. **Corpus chico (12 docs).** No hables de escala. Si te preguntan: *"Es un demo; el pipeline no tiene dependencia de tamaño, el retriever está construido sobre FAISS y BM25 que escalan a millones."* (esta es la única vez donde mencionás la arquitectura — y solo si preguntan).
3. **Los excerpts están cortados a 200 caracteres.** Si alguien quiere ver el documento completo, no hay forma desde la UI. Tené un "Show more ▾" a mano para ampliar un poco, pero no prometas full-document view.
4. **No hay highlighting del texto matched dentro del excerpt.** Si te lo piden, decí "es un feature trivial de agregar, pero no es lo que este proyecto está demostrando".
5. **Admin mode y filesystem efímero en Render.** Si deployás con `ALLOW_INGEST=false`, el tab ni aparece y nadie pregunta. Si lo dejás habilitado, el PDF que subas va a desaparecer en el próximo redeploy. Si vas a mostrar Admin en una demo pública, deployá con un Render Disk (persistente) o hacé la demo localmente.
6. **Policy selector desaparece en Compare.** Puede desorientar. Si alguien lo nota, decí "en Compare corremos las tres políticas en paralelo, por eso no hay selector".
7. **TTFT proxy.** El número "ttft 38ms" es una estimación del tiempo que tardaría un LLM en empezar a generar, no una medición real. Si te preguntan, sé honesto: "es un proxy basado en token count; no estamos llamando a un LLM real".
8. **La interfaz está en inglés** (incluso si tu audiencia es hispanohablante). Coherente con el contenido financiero, pero mencionalo si preguntan.

### Partes que NO conviene enfatizar

- **Tags en las cards.** Existen pero no son clickeables. No son filtros. Mencionalos como "metadata descriptiva" y seguí.
- **El TTFT proxy detallado.** Útil para un lector técnico en el trace; no una métrica que sacar a relucir.
- **Comparar avg scores entre políticas.** "avg score 0.40 vs 0.42" no significa nada sin más contexto; no abras esa puerta.
- **Las 10 tarjetas de métricas de Evals completas.** Señalá 3 (Violations, Recall, Avg Blocked) y pasá. Las 7 restantes son ruido para una audiencia de negocio.
- **Precision@5.** Solo si te preguntan, y pivotá rápido.

---

## 9. Checklist pre-demo (lo que verificar 2 minutos antes)

- [ ] El backend está corriendo (`uvicorn src.main:app --reload`) y responde en `/health`.
- [ ] La página `http://localhost:8000/app/` carga sin errores.
- [ ] El empty state aparece (las 3 tarjetas de onboarding al centro).
- [ ] Click en **`Open in Compare →`** de la tarjeta "Permission Wall" y carga Compare en <2 segundos.
- [ ] En Compare, las tres columnas muestran datos, no skeletons.
- [ ] Click en Evals — el banner verde dice "Zero permission violations".
- [ ] Si vas a mostrar Admin: tené un PDF de prueba chico (<5 MB) listo para arrastrar.
- [ ] Si deployaste en Render: confirmá que `ALLOW_INGEST=false` está seteado si no querés que Admin aparezca, o que hay Render Disk montado si sí.
- [ ] Zoom del navegador al 100% o 110% para que las tarjetas de Compare entren sin scroll horizontal.

---

## 10. Cierre

Esta app tiene un solo mensaje. **"El retrieval tiene una capa de políticas antes del LLM, y QueryTrace la hace visible."**

Todo lo demás — las métricas, las tarjetas, el trace, los roles — son evidencia de ese mensaje. Si en algún momento durante la demo te sentís perdido, volvé a esa frase y mostrá Compare mode otra vez. Es la pantalla que más rápido comunica el valor del proyecto.

Y si tu audiencia se queda con **una sola imagen en la cabeza**, que sea la de tres columnas: No Filters con el IC memo visible a un analyst, Permissions Only bloqueando 7 docs, Full Pipeline demorando los stale. Con eso, ya entendieron.
