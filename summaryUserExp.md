# QueryTrace: Resumen completo de experiencia de usuario

---

## 1. Que es QueryTrace y para que sirve

QueryTrace es una herramienta de laboratorio que simula como un sistema de busqueda empresarial con inteligencia artificial ensambla el contexto que luego le pasaria a un modelo de lenguaje (LLM) para responder preguntas.

**No es un chatbot.** No responde preguntas. No genera texto con IA. Lo que hace es mostrar *que documentos elegiria el sistema* para armar el paquete de contexto que un LLM usaria como fuente de verdad, y *por que eligio esos y no otros*.

El escenario simulado es el siguiente: una firma de capital privado llamada **Atlas Capital Partners** esta evaluando la adquisicion de una empresa fintech llamada **Meridian Technologies** (proyecto interno: "Project Clearwater"). El corpus de documentos contiene 12 archivos reales que cualquier firma de inversiones tendria en un deal asi:

| Tipo de documento | Ejemplo | Quien puede verlo |
|---|---|---|
| Filings publicos (10-K) | Reporte anual de Meridian FY2023 | Todos (Analyst, VP, Partner) |
| Notas de research | Cobertura de Summit Financial Research | Todos |
| Press releases | Comunicado de la Serie C de Meridian | Todos |
| Overview de sector | Vision interna de Atlas sobre fintech | Todos |
| Memos de due diligence | Hallazgos de Phase 1 de Atlas | Solo VP y Partner |
| Modelos financieros | Modelo v1.0 y v2.0 del deal | Solo VP y Partner |
| Emails internos | Riesgos de integracion | Solo VP y Partner |
| Analisis de concentracion de clientes | ARR breakdown por cliente | Solo VP y Partner |
| Memo del Investment Committee | Recomendacion formal del IC | Solo Partner |
| Update para LPs | Carta trimestral a inversores | Solo Partner |

El punto central es: **no todos los usuarios deberian ver todos los documentos**. Un analista junior no tiene por que ver el memo del Investment Committee. Un VP no tiene por que ver la carta a los LPs. El sistema tiene que respetar eso.

---

## 2. Los tres roles: quien sos cuando usas la app

Cuando abris QueryTrace, lo primero que elegis es **tu rol**. Hay tres:

### Analyst (Rango 1 - el mas bajo)
- Puede ver: filings publicos, research notes, press releases, y el sector overview.
- **No puede ver**: memos internos, modelos financieros, emails, analisis de clientes, memo del IC, ni updates para LPs.
- Es el rol mas restrictivo. De los 12 documentos, solo tiene acceso a **5**.

### VP (Rango 2 - intermedio)
- Puede ver todo lo del analyst **mas**: memos de due diligence, modelos financieros, emails internos, y analisis de concentracion.
- **No puede ver**: memo del IC ni updates para LPs (esos son solo para partners).
- De los 12 documentos, tiene acceso a **10**.

### Partner (Rango 3 - acceso total)
- Ve absolutamente todo. Los 12 documentos.
- Es el unico que puede ver el memo del Investment Committee y la carta a los LPs.

**Lo que ves en la UI:** En la barra de controles hay tres botones (Analyst, VP, Partner). Al seleccionar uno, le estas diciendo al sistema "simulemos que soy esta persona" y todas las busquedas que hagas respetaran los permisos de ese rol.

**Para que sirve esto al usuario:** Para entender y demostrar que el sistema de busqueda no filtra documentos a ciegas, sino que respeta las jerarquias de acceso. Si sos un analista y buscas algo, el sistema te muestra solo lo que tu rol permite ver, y ademas te dice cuantos documentos *fueron bloqueados* y por que.

---

## 3. Las tres politicas: como se ensambla el contexto

Ademas del rol, podes elegir una **politica de ensamblado** (solo visible en modo Single). Esto controla *que etapas del pipeline se aplican* a los documentos recuperados:

### naive (naive_top_k)
- **Que hace:** Busca documentos y los devuelve tal cual, sin ningun filtro.
- **No filtra por permisos.** Un analyst veria documentos confidenciales del IC.
- **No evalua frescura.** Un documento viejo y desactualizado aparece igual que uno nuevo.
- **No aplica presupuesto de tokens.** Mete todo lo que encuentra sin limite.
- **Para que existe:** Es el "baseline peligroso". Existe para que el usuario pueda comparar y ver lo que pasa cuando un sistema NO tiene controles. Es la version "todo vale" para demostrar por contraste por que las otras politicas importan.

### rbac (permission_aware)
- **Que hace:** Busca documentos y luego filtra por permisos del rol.
- **Si filtra por permisos.** Los documentos que tu rol no puede ver se bloquean.
- **No evalua frescura.** Los documentos viejos no se penalizan.
- **Si aplica presupuesto de tokens.** Hay un limite maximo de tokens que pueden entrar al contexto.
- **Para que existe:** Muestra el efecto de agregar solo la capa de seguridad (RBAC = Role-Based Access Control). Es el punto medio.

### full (full_policy)
- **Que hace:** Aplica todas las etapas del pipeline.
- **Si filtra por permisos.** Documentos restringidos se bloquean.
- **Si evalua frescura.** Documentos mas nuevos tienen mejor score. Documentos que fueron reemplazados por una version mas nueva (como un modelo financiero v1 reemplazado por v2) reciben una penalizacion del 50%.
- **Si aplica presupuesto de tokens.** Hay un limite (2048 tokens por defecto) y si no cabe todo, los documentos menos relevantes se descartan.
- **Para que existe:** Es la politica "de produccion". Representa como deberia funcionar un sistema real en una empresa.

**Lo que ves en la UI:** En modo Single, hay tres botones (naive, rbac, full). La politica seleccionada se aplica cuando haces clic en "Run". En modo Compare no se muestra este selector porque el sistema automaticamente ejecuta las tres politicas en paralelo.

---

## 4. Los tres modos de la interfaz

### 4.1 Modo Single - "Buscar con una politica"

**Que ves:** Un buscador, un selector de rol, un selector de politica, y cuando ejecutas una consulta, una lista de documentos como tarjetas (cards).

**Que hace:**
1. Escribis una pregunta en lenguaje natural (ejemplo: "What is Meridian's ARR growth rate?")
2. Elegis un rol (Analyst, VP, Partner)
3. Elegis una politica (naive, rbac, full)
4. Haces clic en "Run"
5. El sistema busca los documentos mas relevantes, aplica la politica seleccionada, y te muestra los resultados

**Que te muestra para cada documento:**
- **doc_id**: Identificador del documento (ej: doc_001)
- **Posicion en el ranking**: #1, #2, etc.
- **Extracto del contenido**: Los primeros ~480 caracteres del documento
- **Barra de Relevance**: Un valor de 0 a 1 que indica que tan relevante es el documento para tu consulta. 1.00 = perfectamente relevante. Es un score combinado de busqueda semantica y lexica (BM25).
- **Barra de Freshness**: Un valor de 0 a 1 que indica que tan reciente/vigente es el documento relativo al documento mas nuevo del corpus. Si la politica es naive, aparece "N/A" porque esa politica no evalua frescura.
- **Tags**: Etiquetas descriptivas del documento (ej: "meridian", "public", "financials", "arr")

**Barra de resumen superior:**
- Cantidad de documentos incluidos
- Total de tokens consumidos
- Rol utilizado
- Politica aplicada
- Documentos bloqueados por permisos
- Documentos marcados como "stale" (obsoletos/reemplazados)

**Panel de Decision Trace (colapsable):**
Al final de los resultados hay un panel que se puede expandir llamado "Decision Trace". Este es el corazon de la transparencia del sistema. Muestra:

- **Included**: Chips verdes con los IDs de los documentos que entraron al contexto final. Al pasar el mouse ves el score y la cantidad de tokens.
- **Blocked**: Chips rojos con los IDs de los documentos bloqueados por permisos. Muestra que rol se necesita para accederlos.
- **Stale**: Chips amarillos con los IDs de documentos que tienen una version mas nueva. Muestra a cual documento fueron reemplazados (ej: "doc_002 -> doc_003").
- **Dropped**: Chips grises con los IDs de documentos que pasaron todos los filtros pero no cupieron en el presupuesto de tokens.
- **Budget**: Una barra de progreso mostrando que porcentaje del presupuesto de tokens se uso.
- **Metricas**: Score promedio, freshness promedio, y una estimacion de Time-to-First-Token (TTFT) en milisegundos.

**Para que le sirve al usuario:**
- Para entender *exactamente* que documentos entraron al contexto y por que.
- Para ver el impacto de cambiar la politica: si cambias de "full" a "naive", vas a ver documentos bloqueados que ahora aparecen, documentos stale que ya no se penalizan, etc.
- Para verificar que el sistema de permisos funciona correctamente.

**Coherencia de controles y resultados (UI-B):**
Si cambias el rol o la politica despues de haber ejecutado una consulta, los controles nuevos quedan seleccionados pero los resultados siguen siendo los de la corrida anterior. Para que no parezca que la UI miente, aparece un banner discreto arriba de los resultados ("Controls changed — press Run to refresh these results.") y las tarjetas viejas se atenuan al 60% de opacidad. El banner y la atenuacion desaparecen cuando apretas **Run** (o cuando volves a dejar los controles como estaban al momento del ultimo render). Los botones de ejemplo de la fila "Single" (ARR growth / DD risks / IC memo) son **presets deterministas**: siempre corren con politica **Full Pipeline** y sincronizan el radio de politica, asi la demo se comporta igual sin importar que politica tuvieras seleccionada antes.

---

### 4.2 Modo Compare - "La misma consulta con tres politicas"

**Que ves:** Tres columnas lado a lado, una por cada politica (NAIVE, RBAC, FULL).

**Que hace:**
1. Escribis una pregunta y elegis un rol
2. Haces clic en "Run"
3. El sistema ejecuta la misma consulta tres veces, una con cada politica
4. Te muestra los resultados en tres columnas para que compares

**Que te muestra en cada columna:**
- **Header coloreado**: Con el nombre de la politica y su descripcion corta
- **Stats strip**: Una fila con 6 metricas rapidas:
  - `included`: cuantos documentos quedaron en el contexto final
  - `tokens`: total de tokens usados
  - `blocked`: cuantos documentos fueron bloqueados por permisos
  - `stale`: cuantos documentos estan marcados como obsoletos
  - `dropped`: cuantos documentos fueron descartados por presupuesto
  - `ttft`: estimacion del Time-to-First-Token en milisegundos

- **Cards de documentos**: Version compacta de cada documento con score de relevancia y freshness
- **Annotation "blocked in full"**: En la columna de NAIVE, si un documento aparece ahi pero estaria bloqueado en la politica FULL, se le agrega una etiqueta roja que dice "blocked in full". Esto es para que veas visualmente la "filtracion" que el modo naive permite.
- **Decision Trace por columna**: Cada columna tiene su propio trace expandido (en Compare empieza abierto por defecto).

**Escenarios pre-armados (Compare shortcuts):**
Debajo del buscador hay tres botones de acceso rapido para el modo Compare:

1. **"Analyst wall"**: Ejecuta una consulta sobre ARR como analyst. Demuestra que naive le muestra 12 documentos pero RBAC/FULL le bloquean 7. Es el caso mas dramatico de "mira lo que pasa sin permisos".

2. **"VP deal view"**: Ejecuta una consulta sobre modelos financieros como VP. Muestra como el VP ve los modelos pero tiene 2 documentos bloqueados (los de partner) y 2 documentos stale (las versiones v1 reemplazadas).

3. **"Partner view"**: Ejecuta una consulta sobre el IC memo como partner. Muestra que el partner no tiene nada bloqueado, pero si tiene documentos stale.

**Para que le sirve al usuario:**
- Es la funcionalidad mas poderosa para entender **por que las politicas importan**. 
- Ver tres columnas lado a lado hace inmediatamente visible la diferencia entre "sin filtros", "con permisos", y "pipeline completo".
- Los annotations de "blocked in full" en la columna naive son especialmente utiles porque muestran exactamente que documentos "se filtran" si tuvieras la politica completa.
- Es ideal para hacer demos y explicar a alguien no tecnico por que un sistema de contexto necesita capas de seguridad.

---

### 4.3 Modo Evals - "Dashboard de evaluacion"

**Que ves:** Un dashboard con 10 tarjetas de metricas agregadas y una tabla con 8 filas (una por query de test).

**Que hace:**
1. Al hacer clic en la pestaña "Evals", el sistema ejecuta automaticamente 8 consultas predefinidas a traves del pipeline completo (full_policy).
2. Calcula metricas de calidad de retrieval y seguridad.
3. Muestra los resultados.

**Las 10 metricas agregadas (tarjetas superiores):**

| Metrica | Que significa para el usuario |
|---|---|
| **Precision@5** | De los primeros 5 documentos que el sistema devuelve, que porcentaje son realmente los correctos. 0.30 = 30% de acierto en el top 5. |
| **Recall** | De todos los documentos que deberian aparecer, que porcentaje efectivamente aparecio. 1.0000 = nunca se perdio un documento esperado. |
| **Permission Violations** | Porcentaje de queries donde un documento restringido aparecio en el contexto final. 0.0% = perfecto, nunca hubo una filtracion de permisos. |
| **Avg Context Docs** | Promedio de documentos incluidos por consulta. |
| **Avg Total Tokens** | Promedio de tokens consumidos por consulta. |
| **Avg Freshness** | Promedio del score de frescura de los documentos incluidos. |
| **Avg Blocked** | Promedio de documentos bloqueados por permisos por consulta. |
| **Avg Stale** | Promedio de documentos marcados como obsoletos por consulta. |
| **Avg Dropped** | Promedio de documentos descartados por presupuesto por consulta. |
| **Avg Budget Util** | Promedio de utilizacion del presupuesto de tokens (52.6% = se usa poco mas de la mitad del presupuesto disponible). |

**La tabla por query (8 filas):**
Cada fila es una consulta de test diferente. Las columnas son:
- **Query**: ID de la consulta (q001-q008)
- **Role**: El rol usado para esa consulta
- **P@5**: Precision en el top 5 para esa consulta especifica
- **Recall**: Recall para esa consulta
- **Docs**: Cuantos documentos se incluyeron
- **Tokens**: Cuantos tokens se usaron
- **Freshness**: Score promedio de frescura
- **Blocked**: Cuantos documentos se bloquearon (resaltado en rojo si >0)
- **Stale**: Cuantos documentos estan obsoletos (resaltado en amarillo si >0)
- **Dropped**: Cuantos documentos se descartaron por presupuesto
- **Budget**: Porcentaje de utilizacion del presupuesto
- **Violations**: Si hubo alguna filtracion de permisos ("none" = todo correcto)

**Para que le sirve al usuario:**
- Es la prueba cuantitativa de que el sistema funciona. No es una demo subjetiva, son numeros.
- El dato mas importante para el usuario de negocio es que **Permission Violations = 0.0%** y **Recall = 1.0000**. Eso significa: "nunca filtramos un documento restringido" y "nunca nos perdemos un documento relevante".
- La Precision@5 de 0.30 es baja, pero hay que entender por que: el sistema devuelve mas documentos de los estrictamente "esperados" porque incluye contexto adicional relevante. No es necesariamente un problema, sino una consecuencia de que el corpus es chico y muchos documentos son parcialmente relevantes para varias queries.

---

## 5. Como funciona realmente el buscador

### Que tipo de busqueda hace

El buscador combina **dos metodos de busqueda** que se fusionan:

1. **Busqueda semantica (FAISS + sentence-transformers):** Convierte tu pregunta en un vector numerico y busca documentos con significado similar. Buena para preguntas conceptuales como "cuales son los riesgos de la adquisicion?" porque entiende el significado, no solo las palabras.

2. **Busqueda lexica (BM25):** Busca coincidencias exactas de palabras. Buena para terminos especificos como "MRDN" (ticker de Meridian) o "Section 13D" que la busqueda semantica puede no captar.

Los dos rankings se fusionan usando **Reciprocal Rank Fusion (RRF)**, un metodo estandar que combina ambos rankings en uno solo. El score final va de 0 a 1 (normalizado).

### Que devuelve

No devuelve una "respuesta" a tu pregunta. Devuelve una **lista de documentos rankeados** con sus extractos (`excerpt`), scores, y metadata. Son los documentos que un LLM *usaria* para responder tu pregunta si estuvieras en un sistema RAG (Retrieval-Augmented Generation).

### Sobre que busca

Busca sobre los **12 documentos del corpus**. Estos son documentos simulados pero realistas de un caso de M&A (fusiones y adquisiciones) en fintech. La busqueda se realiza sobre el texto completo de cada documento (el campo `excerpt` que contiene el texto entero del archivo).

### Limitaciones del buscador

1. **No busca dentro de los documentos con precision quirurgica.** No es un buscador de texto plano tipo Ctrl+F. Si buscas "4.1M deferred revenue adjustment" probablemente encuentre el email interno que menciona eso (doc_009), pero lo devuelve como un resultado *completo* del documento, no te resalta la linea exacta donde aparece.

2. **El corpus es fijo y pequeño (12 documentos).** No se pueden agregar documentos desde la interfaz. Para cambiar el corpus hay que editar los archivos en la carpeta `corpus/documents/`, actualizar `metadata.json`, y reconstruir el indice con `python3 -m src.indexer`.

3. **Los scores de relevancia son relativos, no absolutos.** Un score de 0.20 no significa "poco relevante en general", sino "menos relevante que los otros documentos *dentro de este corpus* para esta query". En un corpus de 12 documentos, incluso los menos relevantes pueden tener scores decentes.

4. **No hay filtrado por texto exacto de tags o tipo de documento.** El usuario no puede filtrar por "solo research notes" o "solo documentos con tag 'arr'". Todo pasa por la busqueda en lenguaje natural.

5. **No hay paginacion.** El sistema devuelve los top-K documentos (por defecto 8 candidatos, luego filtrados por politica) y no hay forma de pedir "los siguientes 8".

6. **El buscador no tiene autocompletado, sugerencias, ni historial.** Es un campo de texto plano.

---

## 6. Que informacion ve el usuario en cada pantalla y para que le sirve

### En modo Single

| Elemento | Que le dice al usuario |
|---|---|
| Cards de documentos | "Estos son los documentos que el sistema eligio para responder tu pregunta" |
| Barra de relevancia | "Este documento es mas/menos relevante que los otros para tu consulta" |
| Barra de freshness | "Este documento es mas/menos reciente comparado con el mas nuevo del corpus" |
| Tags | "De que temas trata este documento" |
| Summary bar (docs/tokens/blocked/stale) | "Resumen rapido de que paso con tu consulta" |
| Decision Trace | "Queres saber exactamente por que el sistema tomo cada decision? Abri este panel" |

### En modo Compare

| Elemento | Que le dice al usuario |
|---|---|
| Tres columnas lado a lado | "Asi se ve la misma consulta con tres niveles de proteccion diferentes" |
| Stats strip por columna | "Comparacion rapida: cuantos documentos, tokens, bloqueos en cada politica" |
| Etiqueta "blocked in full" | "Este documento aparece en naive pero se bloquearia con la politica completa - cuidado, esto es una filtracion" |
| Decision Trace por columna | "El detalle completo de cada decision, politica por politica" |

### En modo Evals

| Elemento | Que le dice al usuario |
|---|---|
| Permission Violations = 0% | "El sistema nunca filtro un documento restringido. Los permisos funcionan." |
| Recall = 1.0 | "El sistema nunca perdio un documento que deberia haber incluido." |
| Precision@5 | "De los 5 primeros resultados, este porcentaje eran los correctos." |
| Tabla por query | "Para cada tipo de consulta de prueba, asi se comporto el sistema." |

---

## 7. Clasificacion: que es para el usuario final y que es para evaluacion/demo

### Funcionalidades para el usuario final

1. **Modo Single con politica "full"**: Es la experiencia principal. Buscar documentos relevantes respetando permisos, frescura y presupuesto de tokens. El Decision Trace es util para auditar las decisiones.

2. **Cards de documentos con extractos y scores**: Le dicen al usuario que documentos encontro el sistema y con que confianza.

3. **Tags en las cards**: Ayudan a identificar rapidamente de que trata cada documento.

4. **Selector de rol**: Util si un usuario quiere verificar que veria alguien de otro nivel de acceso (ej: un partner verificando que ven los analysts).

### Funcionalidades para comparar politicas/sistemas

5. **Modo Compare**: Es una herramienta de comparacion, no de uso diario. Sirve para demostrar y validar que las politicas funcionan como se espera. Ideal para presentaciones, auditorias internas, y validacion con stakeholders.

6. **Escenarios pre-armados (Analyst wall, VP deal view, Partner view)**: Son atajos para demos rapidas. Muestran los casos mas dramaticos y educativos.

7. **Selector de politica en modo Single (naive/rbac/full)**: Permite al usuario cambiar manualmente entre politicas para ver la diferencia. Es mas una herramienta de exploracion que de uso productivo.

8. **Etiquetas "blocked in full" en la columna naive del Compare**: Una ayuda visual para entender la filtracion.

### Funcionalidades internas de metricas/evaluacion

9. **Modo Evals**: Es una herramienta de benchmarking. Demuestra con numeros que el pipeline funciona. Util para ingenieros, QA, y documentacion tecnica.

10. **Metricas detalladas (budget utilization, TTFT proxy, avg score, avg freshness)**: Son datos internos del pipeline. Un usuario de negocio no necesita saber que la "budget utilization" es 52.6% ni que el TTFT proxy es 8ms. Pero un ingeniero si.

11. **Precision@5 y Recall**: Son metricas estandar de information retrieval. Tienen significado tecnico preciso. Un usuario no tecnico probablemente no las entienda sin contexto.

---

## 8. Analisis de las capturas

### Captura 1 y 4: Modo Single (Analyst + full policy)

Se ve la consulta "What is Meridian's ARR growth rate and net revenue retention?" ejecutada con rol Analyst y politica FULL.

**Lo que esta bien:**
- La summary bar muestra claramente: 5 docs, 571 tokens, analyst role, FULL policy, 7 blocked, 1 stale.
- Los 7 bloqueados tienen sentido: son los 7 documentos que un analyst no puede ver (doc_006 a doc_012 menos los publicos).
- El 1 stale es doc_002 (la research note vieja de Q3 2023 que fue reemplazada por doc_003).
- doc_001 (el 10-K con datos de ARR) aparece primero con relevancia 1.00 y freshness 0.91 - correcto, es el documento mas relevante.
- doc_003 (la research note actualizada) aparece segundo con relevancia 0.54 - correcto, es la revision de estimaciones.

**Lo que puede confundir:**
- El usuario ve "7 blocked" pero no sabe cuales son a menos que abra el Decision Trace.
- Los tags (meridian, public, financials, etc.) son informativos pero no hay forma de hacer clic en ellos para filtrar.
- El extracto del contenido esta cortado a 480 caracteres sin indicacion visual de que hay mas.

### Captura 2: Modo Evals

Se ven las 10 tarjetas de metricas y la tabla de 8 queries.

**Lo que esta bien:**
- Permission Violations en 0.0% esta resaltado en verde - transmite inmediatamente que los permisos son seguros.
- La tabla muestra patron claro: las queries de analyst (q001-q003) tienen 7 blocked, las de VP (q004-q005, q007) tienen 2 blocked, las de partner (q006, q008) tienen 0 blocked. Esto es consistente con la jerarquia de roles.
- Todas las queries tienen recall 1.00 y violations "none".

**Lo que puede confundir:**
- Precision@5 de 0.30 puede parecer baja y alarmar a alguien que no entiende el contexto. En un corpus de 12 docs con queries amplias, es esperable.
- "Avg Context Docs = 8.6" y "Avg Budget Util = 52.6%" no dicen mucho al usuario de negocio.
- Los colores de las tarjetas (rojo para blocked, amarillo para stale) son informativos pero sin explicacion de que es "bueno" o "malo".

### Captura 3: Modo Compare (Analyst, ARR query)

Se ven las tres columnas NAIVE, RBAC, FULL con los Decision Traces expandidos.

**Lo que esta bien:**
- La diferencia visual es impactante: NAIVE tiene 0 blocked, RBAC tiene 2 blocked, FULL tiene 2 blocked + 2 stale. Se ve inmediatamente el valor de cada capa.
- En la columna NAIVE, los Decision Trace chips muestran doc_010 y doc_011 incluidos sin restriccion - estos son documentos de nivel partner que un analyst no deberia ver.
- Los Blocked chips en RBAC y FULL muestran claramente "doc_010 -partner" y "doc_011 -partner".
- Los Stale chips en FULL muestran "doc_007 -> doc_008" y "doc_002 -> doc_003", indicando que versiones nuevas reemplazaron a las viejas.

**Lo que puede confundir:**
- La barra de "Budget" con 75%, 63%, 63% no tiene contexto de que es "bueno". El usuario no sabe si deberia apuntar a 100% o si 63% esta bien.
- Los "avg score 0.40/0.42" y "avg freshness 0.00/0.79" no tienen benchmark. El 0.00 en freshness de NAIVE y RBAC es porque no calculan freshness, pero el usuario podria pensar que es un error.
- TTFT de 38ms vs 8ms: la primera politica (NAIVE) es mas lenta que las otras porque no filtra nada y procesa mas documentos, pero el usuario no tiene forma de saber si 38ms es rapido o lento sin contexto.

### Capturas 5 y 6: Barra de controles

Se ven los controles superiores: buscador, rol selector, politica selector, y botones de escenarios.

**Lo que esta bien:**
- Los controles son claros y compactos.
- Los botones de escenarios tienen tooltips descriptivos que explican que va a pasar.
- La separacion "SINGLE" vs "COMPARE" para los botones de escenario es clara.

**Lo que puede confundir:**
- El selector de politica (naive/rbac/full) desaparece en modo Compare sin explicacion. El usuario podria pensar que algo se rompio.
- Los botones de escenario cambian automaticamente de modo (de Single a Compare o viceversa) lo cual puede ser desorientador si el usuario no lo espera.
- No hay indicacion visual de cual escenario esta seleccionado actualmente despues de hacer clic.

---

## 9. Resumen: que valor recibe el usuario

### Si sos un decisor de negocio o stakeholder:
- **Compare mode + los tres escenarios pre-armados** son lo mas valioso. En segundos ves la diferencia entre "sin controles", "con permisos", y "pipeline completo".
- **Permission Violations = 0%** en Evals es el dato que importa: el sistema es seguro.
- Las etiquetas "blocked in full" en la columna naive te muestran exactamente lo que se filtraria.

### Si sos un ingeniero o evaluador tecnico:
- **Evals mode** te da las metricas duras: precision, recall, budget utilization.
- **Decision Trace** en cualquier modo te muestra cada decision del pipeline como datos estructurados.
- Los scores, freshness, y token counts te permiten validar que cada etapa del pipeline funciona correctamente.

### Si sos un usuario final haciendo busquedas:
- **Single mode con full policy** es tu modo de uso. Escribis una pregunta, elegis tu rol, y ves los documentos relevantes que el sistema te daria como contexto.
- Las cards con extractos, tags, y scores te ayudan a evaluar rapidamente si los resultados son utiles.
- El Decision Trace te da transparencia total si necesitas auditar por que cierto documento fue incluido o excluido.

---

## 10. Limitaciones y ambiguedades de UX actuales

1. **No se explica que es cada metrica.** El usuario ve "Precision@5 = 0.30" pero no hay tooltip, leyenda, o explicacion contextual de que significa. Lo mismo con TTFT, budget utilization, avg freshness, etc.

2. **Los scores no tienen referencia.** Un score de relevancia de 0.54 no dice nada sin contexto. El usuario no sabe si eso es "bueno" o "malo".

3. **El Decision Trace es poderoso pero denso.** Tiene mucha informacion valiosa, pero un usuario no tecnico puede sentirse abrumado. No hay un "resumen en lenguaje humano" de por que el sistema tomo las decisiones que tomo.

4. **El selector de politica puede confundir en Single mode.** Un usuario casual podria elegir "naive" sin saber que esta desactivando todos los controles de seguridad. No hay warning o explicacion de lo que implica cada politica.

5. **El modo Evals no tiene contexto para las queries.** La tabla muestra "q001", "q002", etc., pero no muestra el texto completo de la consulta. El usuario tiene que adivinar de que se trata cada una (a menos que lea el tooltip o la columna "Query" que solo muestra el ID).

6. **No hay forma de ver el contenido completo de un documento.** Las cards muestran un extracto cortado y no hay forma de expandirlas para leer el documento entero.

7. **El estado vacio ("Permission-Aware Context Gateway") es informativo pero no guia al usuario.** Sugiere "Try Analyst wall" pero no explica que es eso para alguien que no conoce el sistema.

8. **En modo Compare, la columna NAIVE muestra freshness como "N/A" lo cual es correcto tecnicamente** (la politica no calcula freshness), pero visualmente parece un error o dato faltante.

9. **No hay forma de exportar resultados.** Si el usuario quiere guardar una comparacion o un trace para reportarlo, tiene que hacer screenshot manual.

10. **La interfaz esta solo en ingles.** Dado que el escenario es financiero y los documentos estan en ingles, esto es coherente, pero podria ser una barrera para usuarios hispanohablantes.

---

## 11. Resumen ejecutivo

QueryTrace no es un buscador comun. Es un **laboratorio de transparencia** para sistemas de busqueda empresarial con IA. Su valor esta en hacer visible lo invisible: por que un sistema de IA eligio ciertos documentos y no otros para armar el contexto de una respuesta.

Tiene tres capas de valor:

1. **Capa de busqueda (Single mode):** Demuestra que la busqueda hibrida (semantica + lexica) funciona, que los permisos se respetan, que los documentos viejos se penalizan, y que hay un presupuesto de tokens controlado.

2. **Capa de comparacion (Compare mode):** Demuestra visualmente que pasa cuando quitamos capas de proteccion. Es la herramienta de storytelling del proyecto: "mira lo que pasa sin permisos, mira lo que pasa sin freshness, mira lo que pasa con todo activado".

3. **Capa de evaluacion (Evals mode):** Demuestra con numeros que el sistema es seguro (0% violations), exhaustivo (100% recall), y eficiente (budget controlado).

El proyecto esta pensado como herramienta de demostracion y validacion tecnica para Pacific, no como producto final para usuarios. Su fortaleza esta en la transparencia y la rigurosidad del pipeline. Las mejoras de UX deberian enfocarse en hacer esa transparencia mas accesible sin sacrificar la profundidad tecnica.

---

*Archivos clave referenciados:*
- Frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- API: `src/main.py` (endpoints `/query`, `/compare`, `/evals`)
- Pipeline: `src/pipeline.py`
- Busqueda: `src/retriever.py` (hibrida FAISS + BM25)
- Etapas: `src/stages/permission_filter.py`, `src/stages/freshness_scorer.py`, `src/stages/budget_packer.py`
- Politicas: `src/policies.py`
- Modelos: `src/models.py`
- Evaluador: `src/evaluator.py`
- Corpus: `corpus/metadata.json`, `corpus/roles.json`, `corpus/documents/`
- Queries de test: `evals/test_queries.json`
