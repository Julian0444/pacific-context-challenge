# QueryTrace — Guion de video (Español)

**Duración objetivo: 4–5 minutos**
**Formato: Loom con pantalla compartida + cámara**

---

## Antes de grabar

- Servidor corriendo: `python3 -m uvicorn src.main:app --reload`
- Browser abierto en `http://localhost:8000/app/`
- Pantalla limpia — solo el browser, sin tabs extras
- La app arranca en el empty state de Query mode (las tres tarjetas de onboarding visibles)

---

## INTRO — 30 segundos

> *[Cámara encendida, pantalla mostrando el empty state]*

"Hola, soy Julian. Voy a mostrar QueryTrace, un proyecto que construí para resolver un problema real de los sistemas de IA empresariales: **¿qué documentos le pasás a un LLM antes de que responda, y cómo te asegurás de que no le pases algo que el usuario no debería ver?**"

"QueryTrace no es un chatbot. Es la capa que decide qué entra al contexto de un modelo de lenguaje — y hace visible cada decisión."

"El escenario simulado es un caso de M&A: un fondo de capital privado evaluando la adquisición de una fintech. Hay 16 documentos y tres niveles de acceso — analista, VP y partner. Vamos a ver qué pasa."

---

## PARTE 1 — Compare mode, Permission Wall (~90 segundos)

> *[Click en "Open in Compare →" de la tarjeta "Permission Wall"]*

"Empiezo con la pantalla que más rápido muestra el valor del proyecto. Clickeo 'Open in Compare' en la tarjeta Permission Wall."

> *[Se cargan las tres columnas]*

"Esto corre la misma búsqueda — 'What is Meridian's ARR growth rate' — como un analista, a través de tres niveles de protección."

> *[Señalar la columna No Filters con el mouse]*

"A la izquierda, **No Filters**: sin ningún control, el sistema le entregaría al LLM todos los documentos relevantes. Fíjense en estas etiquetas rojas que dicen 'blocked in full' — son el memo del Investment Committee, la carta a los LPs, modelos financieros internos y un memo legal partner-only. Cosas que un analista junior **jamás debería ver**."

> *[Mover a la columna del medio]*

"En el medio, **Permissions Only**: el sistema detecta que 10 documentos requieren nivel VP o partner, y los bloquea. El analista solo ve 6."

> *[Mover a la columna Full Pipeline]*

"A la derecha, **Full Pipeline**: además de los permisos, detecta que un documento fue reemplazado por una versión más nueva y le baja la frescura. Permisos y frescura son dos capas que operan en paralelo."

> *[Señalar un Decision Trace abierto]*

"Cada columna tiene su Decision Trace abierto — el desglose completo de qué entró, qué se bloqueó y por qué. Esto es auditable."

---

## PARTE 2 — Stale Detection (~45 segundos)

> *[Volver al empty state: click en la tab "Query", luego "Side-by-side" para ir a Compare, click en la tarjeta Stale Detection]*

"Ahora veamos qué pasa con un partner — alguien con acceso total."

> *[Se cargan las tres columnas]*

"Cero documentos bloqueados en las tres columnas — el partner puede ver todo. Pero mirá la columna Full Pipeline: detectó que tres documentos fueron **reemplazados** por versiones más nuevas."

> *[Señalar los badges "⚠ Superseded"]*

"Estos documentos siguen apareciendo, pero con una penalización del 50% en frescura. El LLM los ve, pero los pondera menos. No es un tema de acceso — es un tema de **higiene del contexto**. Un documento obsoleto es peor que uno bloqueado, porque el LLM no sabe que los datos son viejos."

---

## PARTE 3 — Query mode + Decision Trace (~60 segundos)

> *[Click en la tab "Query", click en "Run in Single" de la tarjeta Permission Wall]*

"Volvamos a Query mode para ver el detalle fino. Estoy como analista con el pipeline completo."

> *[Señalar la barra de resumen]*

"Arriba: 6 documentos incluidos, aproximadamente 675 tokens — eso es el 33% del presupuesto. 10 bloqueados, 1 demotado como stale."

> *[Señalar una tarjeta de resultado]*

"Cada tarjeta muestra título, tipo de documento, fecha, un extracto, y barras de relevancia y frescura."

> *[Click en "🔒 10 documents blocked by permissions"]*

"Si abro la sección de bloqueados, veo exactamente qué documentos se filtraron y por qué — 'Requires partner role, you are analyst'. Esto es lo que le mostrarías a compliance."

> *[Click en "Decision Trace"]*

"Y el Decision Trace abre con un resumen en lenguaje natural — '6 documents included, 10 blocked, your role cannot access VP and partner level materials'. Abajo, los chips de colores: verde para incluidos, rojo para bloqueados, amarillo para stale."

---

## PARTE 4 — Metrics (~30 segundos)

> *[Click en la tab "Metrics"]*

"Para cerrar con datos duros: el dashboard de Metrics corre el pipeline contra 12 queries de test."

> *[Señalar el banner narrativo verde]*

"Zero permission violations — en 12 queries, el sistema nunca filtró un documento a alguien que no debería verlo. Recall perfecto — nunca perdió un documento esperado."

> *[Señalar las tarjetas de métricas]*

"Permission Violations: 0%. Recall: 1.0. Y cada fila de la tabla de abajo es reproducible — no es una screenshot, es el endpoint `/evals` respondiendo en vivo."

---

## CIERRE — 20 segundos

> *[Volver a Compare mode con una vista de tres columnas]*

"En resumen: QueryTrace resuelve el problema de que un LLM no tiene noción de quién pregunta. La seguridad tiene que estar **antes** del prompt, en la capa de contexto. Este proyecto implementa esa capa con permisos por rol, detección de documentos obsoletos, presupuesto de tokens, y trazabilidad completa."

"Todo el código está en el repo. Gracias por mirar."

> *[Fin]*

---

## Tips para la grabación

1. **No leas el guion palabra por palabra** — internalizá las ideas y hablá natural. El guion es una guía de qué señalar y en qué orden.
2. **Mové el mouse lento** sobre lo que estás explicando — el espectador sigue el cursor.
3. **No hagas zoom** al código ni hables de FAISS o BM25 — eso es para la entrevista técnica, no para el Loom.
4. **Si te trabás, seguí** — Loom permite cortar después. Mejor grabar de corrido y editar que hacer 15 tomas.
5. **El ritmo ideal**: 3 segundos de silencio mientras la pantalla carga, luego hablás sobre lo que se ve. No narres antes de que aparezca.
