# Fase 6 — Lacre: rediseño institucional de la UI + empaquetado portfolio

> La auditoría de 5 lentes dijo lo mismo cinco veces: el frontend tiene sistema pero susurra, las
> secciones tardías rompen la paleta, y la historia del producto (el trace, el 50%→0%) está
> escondida. Esta fase lo resuelve en una sola dirección estética — **"Lacre": cada respuesta es un
> memorándum de private equity con sellos estampados** — y termina empaquetando el proyecto para que
> venda antes de que nadie lea el README. Historia de entrevista: "convertí el invariante contable
> de mi pipeline en el lenguaje visual del dominio del corpus".

## Context

El dueño quiere el proyecto presentable para portfolio. La auditoría multi-agente (2026-07-12, 5
lentes: identidad visual, primera impresión, UX de resultados, recruiter, pulido/a11y) concluyó que
el frontend NO es genérico (tokens disciplinados, pergamino+ámbar, Bricolage+Plex Mono) pero:

1. **Todo susurra** — micro-tipografía 0.55–0.62rem con contraste ~2.6:1 (`--text-tertiary #9e968e`),
   28 font-sizes sin escala, ningún momento display (nada supera 1.5rem en la primera pantalla).
2. **Deriva de las secciones tardías** — isla Tailwind en Admin (`styles.css:2363-2506`, tokens
   fantasma `--border-subtle`/`--accent-hover`, azul `rgb(59,130,246)` único en la UI), 33 `rgba()`
   literales fuera de `:root`, y un bug real: `styles.css:2816` `color: var(--text, #e8ebf2)` —
   `--text` no existe → el banner de cold-start de Render es ilegible (~1.1:1).
3. **La historia está escondida** — el pitch medido ("naive filtra 50%, full 0%") solo vive en
   `og:description`; el Decision Trace nace colapsado; el README no tiene ni una imagen (TODO de GIF
   desde Fase 1) y tiene números stale (391→421 tests, over-retrieval ×3→×6); marca fragmentada
   (favicon/og navy+menta vs app pergamino+ámbar; repo "pacific-context-challenge").

Decisión del usuario: alcance de **3 niveles** (quick wins + rediseño + portfolio) con la dirección
**C "Lacre institucional"**: papel algodón con grano, Fraunces (serif display) + Source Serif 4
(lectura) + IBM Plex Mono (se conserva), rojo lacre `#8c2b2b` como marca, sellos de goma estampados
como firma visual, dark mode "reading room".

**Dependencias:** ninguna fase pendiente. Toca `frontend/` + README + un retoque backend mínimo
opcional (D.2). **Esfuerzo:** 7–9 sesiones. **Orden interno: A → B → C → D → E → F → G** (A da valor
inmediato y nada de A se tira; B es la fundación de C–F; G va último porque el GIF/capturas deben
mostrar la UI nueva).

## Decisiones de la fase

- **D6.1 — Doble rol del rojo lacre `#8c2b2b`, separado por FORMA:** marca = solo sello circular QT
  y momentos de firma; estado/peligro (blocked, naive) = solo sellos rectangulares. Si un elemento
  rojo no es ni lo uno ni lo otro, no es rojo.
- **D6.2 — Presupuesto de fuentes:** Fraunces + Source Serif 4 + Plex Mono ≈ +100–150 KB. Subsetear
  ejes en la URL de Google Fonts (solo opsz/wght usados) o self-hostear woff2; **medir peso
  antes/después** — el cold start de Render no puede empeorar.
- **D6.3 — Doble tema desde una sola hoja de tokens:** claro "papel algodón" (canónico) + oscuro
  "reading room" vía `@media (prefers-color-scheme: dark)` **y** `:root[data-theme]` con toggle en
  el header (media query como default; el atributo gana en ambas direcciones).
- **D6.4 — Nada del copy Lacre se hardcodea a pe-deal:** membrete, sellos y titulares salen del
  manifest del workspace; `saas-internal` (Nimbus) debe seguir creíble como "registro interno" —
  verificado en cada etapa.

## Reglas de disciplina anti-kitsch (todas las etapas)

Máx. 1 sello por card · grano ≤3% opacidad · rotaciones ≤3° · cero texturas sobre controles
interactivos · Fraunces solo ≥1.15rem (debajo: Source Serif 4 o Plex Mono) · suelo tipográfico duro
0.7rem — prohibido crear un font-size fuera de la escala de 8 tokens.

## Restricciones duras (heredadas del proyecto)

Sin build step ni frameworks · `escapeHTML` en todo string de origen usuario/servidor · nombres de
API intactos (`naive_top_k`/`permission_aware`/`full_policy`) · **los commits los hace el dueño**
(git manual) · todo lo que se ejecute, con `.venv/bin/python`.

## Verificación estándar por etapa (se repite, no se negocia)

Matriz Playwright con el tooling `webapp-testing` del repo: 4 modos × login × 2 workspaces × 2 temas
(desde B) · viewport 375px · `prefers-reduced-motion` · consola sin errores JS · contraste ≥4.5:1
**calculado** (no a ojo) para cada par texto/fondo nuevo · `ruff check src/ tests/` +
`.venv/bin/python -m pytest tests/` como smoke (421/0; si algo falla, se tocó lo que no era).

---

## Etapa A — Quick wins que sobreviven al Lacre (1 sesión)

**Por qué:** de las 12 prioridades consolidadas, 8 dan valor inmediato y ninguna se tira con el
rediseño. Las otras 4 quedan explícitamente **superseded** para no pagar dos veces.

1. **Bug del cold-start banner** — `styles.css:2816`: `color: var(--text, #e8ebf2)` →
   `var(--text-primary)`. Hoy el aviso de Render es ilegible.
2. **Foco de teclado en controles primarios** — los radios de Role/Policy están en `opacity:0` sin
   indicador al tabular (único `:focus-visible` del archivo: `styles.css:3104`, y hace
   `outline:none`). Añadir `input:focus-visible + .role-chip / + .policy-tab { outline: 2px solid
   var(--accent); outline-offset: 2px; }` (~8 líneas). B re-tokeniza el color gratis.
3. **Header móvil** — `styles.css:115-123`: `flex-wrap: wrap` en `.header-inner` + `@media ≤640px`
   que apile el mode-toggle y acorte "Side-by-side"→"Compare". Elimina el overflow <600px.
4. **Contraste provisional** — `--text-tertiary` `#9e968e`→`#6b645d`, `--tag-text`→`#5f5955`
   (2 líneas; B los sustituye por la tinta Lacre `#6d665c` — se hace igual porque cuesta 2 min y las
   sesiones pueden espaciarse).
5. **CSS muerto + huecos de reduced-motion** — fusionar los 3 keyframes de entrada
   (`result-card-in`:683, `card-in`:689, `cardIn`:1902); borrar `admin-spin`:2453 (usar `spin`:318);
   corregir `.admin-submit-btn`→`.admin-btn` en `styles.css:2785`; añadir
   `.skeleton-card::after { animation: none }` al bloque reduced-motion; eliminar el fallback índigo
   de `.card-sections-badge`:762 y las clases huérfanas (`.card-doc-id`, `.compare-card-id`,
   `.evals-id-cell`).
6. **Trace abierto por defecto en Single** — flip del flag en `app.js:1155`
   (`buildTracePanelHTML(trace, false, role)` → `true`). **Ojo (verificado):** `startOpen` está
   acoplado al modo compacto — `app.js:1964` `buildTraceSummary(trace, userRole, startOpen === true)`
   y `app.js:2014` `trace-summary${startOpen ? " trace-summary-compact" : ""}`. Hay que **desacoplar**
   añadiendo un parámetro `compact` separado (Compare pasa `compact=true`; Single `startOpen=true,
   compact=false`), o Single perdería su resumen narrativo completo.
7. **Barras que se llenan** — las transiciones de `width` de `.metric-bar-fill`/`.budget-bar-fill`
   son código muerto (width final inline: `app.js:1245`, `1268`, `~2039`). Renderizar a `width:0` y
   setear el real en `requestAnimationFrame` (~15 líneas). Sobrevive a cualquier piel.
8. **Números stale del README** — `391 passed`→`421` (`README.md:354,395`); `top_k × 3`→`× 6`
   (`README.md:102,137`). 10 minutos que protegen el pitch de rigor.

**Superseded — NO hacer (los cubre el rediseño):** momento display con Bricolage (throwaway —
Fraunces llega en E) · gradiente de atmósfera + sombras (B trae grano y radial) · re-token del Admin
como parche (B lo absorbe con la paleta nueva) · dark mode standalone (va en B) · chips con títulos
(D los convierte en tabla de acta).

Verificación: matriz estándar (aún piel parchment, 1 tema); tab-order visible en Role/Policy; 375px
sin scroll horizontal; barras animándose y estáticas bajo reduced-motion; resumen narrativo completo
visible con el trace abierto.

## Etapa B — Fundación Lacre: tokens, tipografía, grano y doble tema (1.5–2 sesiones)

**Por qué:** todo componente de C–F se construye sobre esta hoja. Regla de secuencia interna: **la
absorción de colores sueltos va antes que el tema oscuro** — si quedan literales fuera de `:root`,
el dark mode sale con agujeros parchment.

1. **Re-tejer `:root` (`styles.css:3-77`)** con la paleta Lacre clara: papel `#f7f2e9`, superficie
   `#efe8db`, hoja `#fffdf8`, hairlines `#d8cfc0`; tinta `#1f1b16`/`#4a443c`/`#6d665c`; acento
   **rojo lacre** `#8c2b2b` (dim `#6e2222`, tint 8%). Semánticos: lacre = naive/blocked; verde
   registro `#2f5d3f` = full/included; ocre ledger `#8a6a1f` = rbac/stale (el ámbar degradado de
   marca a apoyo — resuelve su sobrecarga semántica actual: hoy `#8b6914` es a la vez marca, RBAC,
   score medio y stale); **azul tinta `#33506b` = dropped/budget/freshness** (hue nuevo — separa
   dropped de stale, hoy gemelos `#8b5214`/`#8b6914`).
2. **Escala tipográfica de 8 tokens** (ratio ~1.22): `0.7 / 0.78 / 0.875 / 1 / 1.15 / 1.4 / 1.75 /
   2.2rem` — colapsa los 28 font-sizes sueltos; suelo duro 0.7rem. Tokens de spacing y radios
   `2/4/8px` (el papel casi no se curva).
3. **Swap de fuentes en `index.html:21`:** entra Fraunces (opsz 9..144, wght 340–640, SOFT 0/WONK 0)
   + Source Serif 4 (400/600); Plex Mono se conserva. Sale Bricolage Grotesque. Aplicar D6.2
   (subset/self-host + medición). De paso eliminar `font-weight: 650` (`styles.css:2856,2920` —
   peso no cargado, síntesis del navegador).
4. **Grano y atmósfera:** textura `feTurbulence` como data-URI inline al ≤3% sobre `body` + radial
   cálido sutil. Cero assets externos; cero texturas en controles.
5. **Pasada de absorción (gate de la etapa):** re-tokenizar la isla Admin (`styles.css:2363-2506`) y
   colapsar los ~33 `rgba()` literales a `color-mix(in srgb, var(--token) N%, transparent)` **con
   fallback rgba en la misma declaración** (Safari viejo). **Gate: grep de colores fuera de `:root`
   = 0 antes del punto 6.**
6. **Tema oscuro "reading room":** bloque que redefine solo tokens — papel carbón
   `#191713`/`#26221c`, tinta marfil `#ebe3d4`, lacre iluminado `#c05047`, verde `#5e9b76`, ocre
   `#c9a648`, azul `#7d9cbb` — vía D6.3, con toggle en el header. Recalcular contraste de CADA
   semántico sobre carbón (frágiles: lacre y azul tinta).

Al cerrar B, la app entera viste Lacre "de serie" por herencia de tokens; C–F esculpen componentes.

Verificación: matriz estándar **en ambos temas** (desde aquí, siempre); tabla de contrastes
calculados en las notas del cambio; peso de fuentes antes/después publicado; gate de absorción
documentado (comando grep + resultado).

## Etapa C — Sellos estampados + result cards como folios (1–1.5 sesiones)

**Por qué:** el sello es la firma irrepetible de la dirección — la traducción literal del invariante
`blocked + included + dropped == retrieved` al lenguaje de deal room.

1. **Sistema de sellos** (componente CSS único `.stamp` + modificadores): Plex Mono uppercase, doble
   borde 2px, `rotate(-2°…3°)`, tinta irregular vía máscara feTurbulence data-URI,
   `mix-blend-mode: multiply` sobre el grano. **Receta separada para tema oscuro** (multiply no
   funciona sobre papel carbón: screen/overlay + alfas recalibrados). Variantes: `BLOCKED` (lacre),
   `SUPERSEDED` (ocre), `APPROVED` (verde), `OVER BUDGET` (azul tinta).
2. Sustituir `.stale-badge` (`styles.css:918`) y los mini-cards `.blocked-card` (`styles.css:1033`)
   por sellos + línea de motivo legible ("Requires vp — you are analyst").
3. **Folios:** `.result-card` (`styles.css:661`) pasa a hoja `#fffdf8` con hairline 1px +
   `border-top: double 3px` estilo informe anual; título en Fraunces 1.15rem; excerpt en Source
   Serif 4 0.95rem/1.6; la barra de acento `::before` (`styles.css:696`, hoy sin leyenda) se
   reemplaza por folio mono `EXHIBIT 03`; `card-meta-badge` → `REF: doc_014`. Solo CSS + retoques de
   strings en `singleCardHTML()` (`app.js:1180`) — `groupContextByDoc()` no se toca.
4. Disciplina: el APPROVED no se estampa en cada folio incluido; se reserva para momentos de
   veredicto (Compare/Metrics, Etapa F).

Verificación: matriz estándar; sellos legibles en ambos temas y sin rotación animada bajo
reduced-motion; badge "matched N of M sections" y expand/collapse intactos; escapeHTML en títulos.

## Etapa D — Membrete, acta y panel de bloqueados (1–1.5 sesiones)

**Por qué:** el Decision Trace es la feature que da nombre al producto; pasa de panel técnico a
"Decision Record" — el acta firmada de la operación.

1. **Summary-bar → encabezado de memorando** (`app.js:1100-1136`, template string local): tabla de
   hairlines `PREPARED FOR: analyst · POLICY: Full Pipeline · 6 DOCS · 675 TOKENS (33% of budget)`
   en vez de pills; `export-btn` → "Download filing ⤓". Roles/nombres desde el meta del workspace
   (D6.4).
2. **Trace → acta del comité** (`buildTracePanelHTML()` `app.js:1961-2051` + chips
   `app.js:1973-1999`, CSS `styles.css:1200-1241`): los 4 grupos de chips se convierten en tabla de
   registro con hairlines — TÍTULO · REF · mini-sello de acción · motivo legible. Resuelve "chips =
   ruido" y "tooltips inaccesibles en táctil". Retitulado "Decision Record" (abierto por defecto
   desde A.6). **Retoque backend mínimo (verificado):** `StaleDocument` (`src/models.py:133`) y
   `DroppedByBudget` (`src/models.py:163`) no llevan `title` — añadir `title: Optional[str] = None`
   (patrón existente: campos opcionales → payloads viejos siguen válidos) y poblarlo en
   `src/stages/freshness_scorer.py` / `src/stages/budget_packer.py` (el dato ya viaja:
   `ScoredDocument.title`, `models.py:80`; `FreshnessScoredDocument.title`, `models.py:105`) +
   tests de los stages. Alternativa si se prefiere no tocar backend: el acta muestra TÍTULO solo
   para included/blocked (ya lo llevan) y REF para stale/dropped.
3. **Regresión obligatoria del trace redactado:** sesiones no-admin reciben
   `blocked_by_permission=[]` + `blocked_summary{count, required_roles}` (withheld-strip,
   `app.js:1473-1500`) — el acta debe renderizar desde el count redactado sin filtrar títulos ni en
   DOM ni en tooltips; verificar `groupTraceEntries` (agrupado por doc padre) con docs multi-chunk.
4. **Header con línea de clasificación** — `PRIVATE & CONFIDENTIAL · <workspace name>` en mono
   espaciado bajo hairline doble (nombre desde el manifest, D6.4); `.brand-mark` (`styles.css:132`)
   → sello circular QT en lacre (D6.1: el único lacre "de marca").

Verificación: matriz estándar con **tres sesiones** (guest / julia / patricia) — el acta redactada
de julia no revela títulos bloqueados; el invariante visible cuadra con `decision_trace`; ambos
workspaces (membrete Nimbus creíble); suite pytest si se hace el retoque de modelos.

## Etapa E — Portada: empty state y login como carta (1 sesión)

**Por qué:** los dos highs de primera impresión — el login no comunica qué es el producto y no hay
momento display.

1. **Empty state como portada de memo** (`index.html:155-160`): Fraunces 2.2rem con el dato que hoy
   solo vive en `og:description` — "Naive retrieval leaks 50% of queries. The full pipeline: 0%." —
   sobre las onboard-cards existentes (comportamiento intacto). Titular genérico del producto, no
   del corpus (D6.4).
2. **Login → carta de presentación** (`index.html:53-70`): `.login-box` como carta con membrete y
   sombra de papel; el H1 pasa del disclaimer al pitch en Fraunces; el disclaimer baja a letra
   pequeña bajo las cards; `#persona-cards` como tarjetas de visita (`JULIA · ANALYST ·
   CLEARANCE I`, datos ya presentes en `/personas`); `#guest-link` promovido a botón primario
   ("Read the memo without credentials →").
3. **A11y de arrastre** (misma zona, un solo toque): `aria-label` en `#query-input`; quitar
   `role="listitem"` de los `<button>` de persona (`app.js:378-391`); `aria-live="polite"` en
   `#results-section` (`index.html:154`); `margin: auto` en `.login-box` (hoy el top queda recortado
   en móvil, `styles.css:2825-2841`).

Verificación: matriz estándar; login completo y scrolleable en 375px; flujo guest → lab y persona →
product mode intactos; ambos workspaces con sus personas.

## Etapa F — Compare como dictamen y Metrics como informe anual (1 sesión)

1. **Compare:** cada `.col-header` (`styles.css:1372`) recibe sello-veredicto por columna —
   "LEAKED N DOCS" en lacre para naive (N desde los `*_doc_count` del full, que ya viajan en la
   respuesta), "CLEAN" verde para full. El contraste que vende el producto, visible sin leer
   números. Restyle de `.col-stats` (`styles.css:1464`, labels 0.55rem → escala tokenizada) y
   compact-cards (`buildCompareCardHTML`, `app.js:1404`) como mini-folios.
2. **Metrics:** grid de `.metric-card` (`styles.css:1881`) → tabla financiera de hairlines con
   cifras en Fraunces a `toFixed(2)` (adiós "0.3000", `app.js:1589-1598`); **"Permission Violations
   0%" promovida a placa 2× con sello `CERTIFIED · 0% VIOLATIONS`** (verde, solo cuando es 0; si no,
   placa de advertencia sin sello); celda Budget% de la tabla per-query (`app.js:1614-1655`) con
   mini-barra inline (las transiciones rAF de A.7 la animan). Session Audit hereda la misma tabla.

Verificación: matriz estándar; Compare entre 960–1260px sin clipping; sello-veredicto correcto en
ambos workspaces (números distintos); Metrics con `/evals` reales de los dos corpus.

## Etapa G — Empaquetado portfolio (1 sesión)

**Por qué al final:** el GIF y las capturas deben mostrar la UI Lacre. (Los números stale ya se
corrigieron en A.8.)

1. **favicon.svg + og-card.png regenerados** con el motivo del sello circular lacre — muere la
   tercera identidad navy+menta (`favicon.svg`: `#1a1d27`/`#7dd3a8`) y la marca queda coherente
   pestaña/social/app en ambos temas.
2. **GIF de 20–30s** para `README.md:11` (el TODO de Fase 1): query como julia → sellos BLOCKED →
   Compare con veredictos → Metrics CERTIFIED. Captura automatizada con el tooling Playwright de
   `webapp-testing`; peso <5 MB.
3. **3 screenshots con caption** (Single con acta abierta, Compare, Metrics) en sección propia del
   README.
4. **Pipeline ASCII → Mermaid** (`README.md:97-135`) — GitHub lo renderiza nativo.
5. **GitHub:** og-card como social preview del repo, description y topics (`rag`, `retrieval`,
   `rbac`, `fastapi`, `faiss`, `llm`).

Verificación: README renderizado en GitHub (Mermaid ok, GIF reproduce, imágenes con alt); preview
social validada con un scraper; links vivos.

---

## Riesgos de la fase

- **Kitsch skeumórfico:** sellos+grano+serif vuelca a "menú de restaurante" sin las reglas de
  disciplina — revisión explícita contra ellas antes de cerrar cada etapa.
- **Lacre marca vs peligro:** si D6.1 no se respeta, el usuario lee la propia marca como error.
- **El dark mode duplica la calibración fina** (sellos, grano, alfas): presupuestado en B.6 y C.1;
  no aceptar "se ve bien en claro" como done.
- **chips→acta reescribe render sin tests visuales:** la regresión manual de D.3 (trace redactado +
  agrupado por doc padre) es obligatoria, no opcional.
- **Fuentes:** Fraunces se empasta en pesos altos/tamaños chicos (suelo 1.15rem) y 3 familias pesan
  — D6.2 con medición publicada.
- **Narrativa mono-corpus:** todo copy vía manifest; si algo solo tiene sentido en pe-deal, es un
  bug (D6.4).
- **Acoplamiento startOpen/compact** (A.6): sin el desacople, abrir el trace por defecto degrada el
  resumen narrativo de Single al formato compacto de Compare.

## Definition of Done — Fase 6

- [x] A: 8 quick wins aplicados y verificados (foco visible, sin overflow 375px, banner legible,
      trace abierto con resumen completo, barras animadas, README 421/×6); superseded respetados
      *(2026-07-12: matriz Playwright **54/54** — 4 modos × guest/julia/patricia/alex × 2 workspaces,
      375px sin scroll horizontal y header sin overflow con "Compare" corto, reduced-motion con barras
      estáticas al ancho final y compare-cols visibles, consola limpia, trace abierto con resumen
      narrativo completo (no compacto) vía desacople `startOpen`/`compact` en `buildTracePanelHTML`;
      contrastes CALCULADOS: banner cold-start 1.05:1→13.83:1, `--text-tertiary` 2.59:1→5.17:1 (page)
      /4.77 (surface)/5.82 (card), `--tag-text` 5.81:1 — todos ≥4.5:1; ruff limpio + pytest 421/0.
      Extras encontrados al verificar: (1) hueco real de reduced-motion — `.compare-col`/`.compare-card`
      nacían `opacity:0` y el bloque RM les quitaba la animación sin restaurar opacidad → columnas
      invisibles; resuelto moviendo el estado inicial al keyframe único `card-in` con fill `backwards`
      (de paso elimina el flash visible→invisible de los delays escalonados); (2) `.role-chip` con
      `transition: all` retrasaba el anillo de foco (outline-width 0→2px animado) — scopeada a
      border-color/color/background/box-shadow. README: 391→421 en L354/L395, ×3→×6 en L102/L137
      mencionando chunk inflation. Barras: render a `width:0` + `data-w` y doble rAF (`animateBars()`),
      cubre metric/budget/mini bars en Single y Compare)*
- [x] B: `:root` Lacre completo (paleta + escala 8 pasos + spacing/radios); gate de absorción
      cumplido (cero colores fuera de `:root`); doble tema con toggle; contrastes calculados y
      publicados; peso de fuentes medido antes/después
      *(2026-07-13: **paleta** — papel `#f7f2e9/#efe8db/#fffdf8`, hairlines `#d8cfc0`, tinta
      `#1f1b16/#4a443c/#6d665c`; `--accent` = TINTA (D6.1: el lacre queda reservado a sello de marca
      y sellos de peligro; los controles escriben en tinta); hues base `--lacre #8c2b2b / --verde
      #2f5d3f / --ocre #7a5e1c / --azul #33506b` con semánticos por var() — el ocre del plan
      (`#8a6a1f`) medía 4.14:1 sobre surface y se oscureció a `#7a5e1c` (5.00:1). **Escala 8 tokens**
      `--fs-2xs…--fs-3xl` (0.7→2.2), 155 font-sizes colapsados por script determinista, 0 literales
      restantes; radios 2/4/8 + `--space-1..6`. **Fuentes**: Fraunces var (opsz 9..144, wght
      340..640) + Source Serif 4 (400/600 estáticas) + Plex Mono; Bricolage fuera (grep = 0 refs);
      pesos woff2 latin MEDIDOS: 104 KB → 145 KB (+41 KB, dentro del presupuesto D6.2 de +100–150);
      650/700 → 600 (rangos cargados). **Grano**: feTurbulence data-URI opacidad 0.028 (≤3%) +
      radial ocre 5.5% como `--grain`/`--atmosphere` sobre body/login — nunca sobre controles.
      **Gate de absorción**: scanner brace-aware (scratchpad/gate_check.py, regex
      `#hex|rgba?()|hsla?()` fuera de los bloques de tokens) = **0 literales** (antes 41 en ~33
      declaraciones); isla Admin re-tokenizada (azul/verde/lacre para estados, job dots en azul),
      fantasmas `--border-subtle`/`--accent-hover` eliminados. **Tema oscuro** "reading room" vía
      `@media prefers-color-scheme` + `:root[data-theme]` (atributo gana en ambas direcciones,
      boot script anti-FOUC en `<head>`, toggle ◐ en header con persistencia localStorage);
      contrastes DARK recalculados por semántico: lacre iluminado subido `#c05047→#dc8177` (3.58→
      4.95:1 en tint 12%) y verde `#5e9b76→#6fab86` (4.20→5.18:1) porque los candidatos del plan
      fallaban AA; ivory `#ebe3d4` 13–14:1, ocre `#c9a648` 5.85:1, azul `#7d9cbb` 4.89:1 — todos
      los pares texto ≥4.5:1 en ambos temas. **Matriz Playwright 45/46 + header-fix re-check**:
      4 modos × 2 workspaces × 2 temas, toggle persiste y `data-theme=light` vence a media query
      dark, 375px sin scroll en ambos temas, reduced-motion ok, consola limpia; el único FAIL fue
      un falso negativo del harness (`document.fonts.check()` devuelve true para familias no
      registradas — Bricolage verificado fuera por grep). ruff limpio + pytest 421/0)*
- [x] C: sistema `.stamp` con receta clara/oscura; cards como folios; disciplina anti-kitsch
      auditada
      *(2026-07-13: componente único `.stamp` — mono uppercase 0.7rem, doble anillo (borde 2px +
      `::before` inset 1px), rotaciones -2°/1.5°/-1.2°/2° (≤3° verificado leyendo la matriz
      computada), tinta irregular vía máscara feTurbulence alpha-only (`--stamp-ink`), receta por
      tema en tokens: `--stamp-blend: multiply`/α0.9 claro y `screen`/α0.95 oscuro (multiply
      desaparece sobre carbón — verificado computado en ambos temas); variantes
      blocked/superseded/approved/overbudget (approved y overbudget definidos, reservados para F
      según C.4). `.stale-badge` → sello SUPERSEDED + línea de motivo legible (texto autosuficiente,
      sello `aria-hidden`); `.blocked-card` → sello BLOCKED absoluto arriba-derecha + REF + motivo.
      Folios: `border-top: 3px double` tinta, radius solo abajo, título Fraunces `--fs-lg`, excerpt
      Source Serif `--fs-md`/1.6, barra `::before` sin leyenda reemplazada por `EXHIBIT NN`
      (`.card-rank`→`.card-folio`), badges `REF: doc_NNN`; `groupContextByDoc()` intocado, solo
      strings en `singleCardHTML()`/`buildBlockedSectionHTML()`. Matriz Playwright **33/33**:
      2 temas × pe-deal + saas-internal (runbook v1 con sello — copy genérico, D6.4 ok), folio/REF/
      doble filete/máscara/blend por tema, máx 1 sello por card, badge "matched N of M" y
      expand/collapse intactos, 375px sin scroll con blocked abierto, sellos estáticos bajo
      reduced-motion, consola limpia. Anti-kitsch: grano 2.8% ≤3%, cero texturas sobre controles
      (stamp es `pointer-events:none`), Fraunces solo ≥1.15rem, suelo 0.7 intacto)*
- [x] D: memo header + Decision Record en tabla (con títulos vía retoque de modelos o fallback REF);
      regresión del trace redactado y de `groupTraceEntries` pasada; sello circular de marca
      *(2026-07-13: **backend D.2** — `title: Optional[str]` en `StaleDocument`/`DroppedByBudget`
      poblado desde `doc.title` en freshness_scorer/budget_packer + 4 tests de stages (payloads
      viejos siguen válidos); suite **425/0** + ruff limpio. **D.1** summary-bar → membrete de memo:
      tabla de campos hairline PREPARED FOR · POLICY · DOCUMENTS · TOKENS (· % of budget) · BLOCKED ·
      STALE con doble filete superior, export → "Download filing ⤓"; la clase `.summary-bar` se
      conserva y la regresión UI-B (banner de controles divergentes) pasó explícitamente. **D.2**
      acta "Decision Record" (`buildDecisionRecordHTML`): una fila por doc por ACCIÓN — TITLE · REF ·
      marca plana `.stamp-flat` (Included verde/Demoted ocre/Dropped azul/Blocked lacre) · motivo
      legible INLINE (muere la dependencia de tooltips táctiles); multi-chunk agregado vía
      `groupTraceEntries` con "· N sections"; Compare conserva chips compactos ("Decision Trace") —
      la tabla de 4 columnas no cabe en columnas de 350px, F las restyla. **D.3 regresión redactada
      VERIFICADA FUERTE**: títulos bloqueados enumerados vía trace de invitado y afirmado CERO
      apariciones en DOM/innerHTML/title= de julia; el acta redactada muestra UNA fila count-only
      ("N withheld · requires vp/partner — titles withheld server-side") sin título ni REF real.
      **D.4** línea de clasificación `PRIVATE & CONFIDENTIAL · <nombre del manifest>` bajo doble
      hairline (Nimbus creíble verificado) + `.brand-mark` → sello circular QT en lacre (anillo
      doble, máscara de tinta, rotación -2° — el ÚNICO lacre de marca, D6.1); scroll-padding 68→96.
      Matriz Playwright **36/36**: guest/julia/patricia × 2 workspaces × 2 temas × 375px, invariante
      visible cuadrado contra `decision_trace` (Included/Blocked/Demoted/Dropped rows ==
      `*_doc_count`), consola limpia. 2 falsos negativos de harness corregidos (innerText respeta
      text-transform: uppercase))*
- [x] E: portada con pitch en Fraunces; login como carta con guest primario; fixes aria/móvil
      *(2026-07-13: **portada** — kicker mono "Context assembly, on the record" + display Fraunces
      `--fs-3xl` (2.2rem, verificado computado 35.2px; ≤640px baja a 2xl) con el dato medido que
      vivía solo en og:description — "Naive retrieval leaks restricted documents on 50% of queries.
      The full pipeline: 0%." con el 0% en verde registro; titular genérico de producto (D6.4), la
      descripción por-corpus sigue viniendo del manifest; onboard-cards intactas (comportamiento
      verificado clickeando el preset). **Login como carta**: `.login-box` = hoja con doble filete +
      hairline + sombra de papel + `margin:auto` (fix del top recortado en móvil, verificado
      scrolleable completo a 375×700); H1 pasa del disclaimer al pitch en Fraunces 2xl; el
      disclaimer baja a letra pequeña mono bajo las cards; personas como tarjetas de visita —
      `NOMBRE / ROL · CLEARANCE I-III` (rango romano desde ROLE_RANKS del meta, corpus-agnóstico,
      Nimbus verificado con employee/exec) + "sees N of M docs" + credenciales; `#guest-link`
      promovido a botón primario en tinta "Read the memo without credentials →" (flujo guest → lab
      y persona → product mode verificados intactos). **A11y**: `aria-label` en `#query-input`,
      `role=listitem/list` eliminados de personas, `aria-live="polite"` en `#results-section`.
      Matriz Playwright **27/27** (2 workspaces, tema oscuro en login saas, 375px sin scroll
      horizontal, consola limpia; 2 falsos negativos de harness corregidos — cards de Compare
      ocultas contadas por el selector global y "Sofía" con acento). `text-wrap: balance` en la
      línea de clearance para el corte limpio)*
- [x] F: sellos-veredicto en Compare; Metrics como informe con placa CERTIFIED condicional y barras
      inline
      *(2026-07-13: **Compare** — sello LEAKED N DOCS (lacre, rotado, tinta) en el col-header de
      naive con N = `blocked_doc_count` del full (afirmado igual al stat BLOCKED de la columna full
      en vivo) y CLEAN (verde) en full; rbac sin veredicto; cuando nada se filtra (partner/exec) el
      naive queda sin sello — honesto — y full mantiene CLEAN; compare-cards como mini-folios
      (doble filete suave + `REF:`, muere la barra `::before` y su `--card-accent`); export del
      banner → "Download filing". **Metrics** — placa CERTIFIED 2× (doble filete verde, 0% en
      Fraunces 1.75rem, sello `.stamp-approved` rotado SOLO cuando rate==0; placa de advertencia en
      lacre sin sello en el else), grid de metric-cards reemplazado por estado financiero de
      hairlines (9 filas Metric/Value/Note, cifras Fraunces `--fs-lg` a toFixed(2) — adiós 0.3000 —
      verificado formato en vivo), celda Budget de la tabla per-query con mini-barra inline azul
      animada por el rAF de A.7 (data-w == width final afirmado) y Session Audit hereda la misma
      celda; CSS muerto de `.metric-card/.metrics-grid` purgado incl. bloque reduced-motion y media
      queries. Matriz Playwright **42/42**: 2 corpus con números DISTINTOS (pe-deal 10 vs saas 8 —
      cross-ws afirmado), 960/1100/1260px sin clipping ni scroll horizontal, /evals reales de ambos
      corpus con CERTIFIED, tema oscuro con veredictos visibles, 375px ok, consola limpia)*
- [x] G: favicon + og-card lacre; GIF en README; 3 screenshots; Mermaid; social preview + topics
      *(2026-07-13: **favicon.svg** = sello circular lacre con media query dark embebida (papel/carbón,
      lacre #8c2b2b/#dc8177) — muere el navy+menta; **og-card.png** regenerada 2400×1260 (~1.0 MB,
      HTML autocontenido renderizado con Playwright: sello + titular Fraunces con el 0% en verde +
      sellos BLOCKED/DEMOTED/CLEAN + pie de clasificación) — identidad única pestaña/social/app;
      misma ruta `/app/og-card.png`, los og:meta de index.html no cambian. **GIF** 20s
      `docs/media/demo-tour.gif` (2.37 MB < 5 MB, 880px, 20 frames con duración por escena —
      pipeline determinista de frames + Pillow porque el ffmpeg de Playwright no trae encoder GIF ni
      muxer image2): carta de login → cover → Permission Wall en Single (folios + memo) → sellos
      BLOCKED → acta Decision Record → veredictos LEAKED/CLEAN en Compare → placa CERTIFIED. Nota:
      el guión usa guest-analyst en vez de julia — misma clearance, pero el lab enseña los sellos y
      Compare/Metrics que el product-mode de julia oculta (la vista redactada de julia queda contada
      en el tour de 3 min del README). **README**: TODO de Fase 1 reemplazado por el GIF con alt;
      sección "The product, in three views" con las 3 capturas + captions (Single con acta, Compare
      con veredictos, Metrics CERTIFIED, docs/media/*.png a 2×); pipeline ASCII → **Mermaid**
      flowchart (validado renderizando con mermaid@10 real: "ok"); links locales del README todos
      vivos (verificados). **Pendiente del dueño (acciones en github.com/Render tras push+deploy)**:
      subir `frontend/og-card.png` como Social preview del repo en Settings, poner description
      ("Auditable RAG gateway: RBAC + freshness + token budget con Decision Record por query") y
      topics `rag, retrieval, rbac, fastapi, faiss, llm`, y validar el scrape social del deploy
      (opengraph.xyz) — no ejecutable desde local)*
- [x] Global: matriz Playwright completa (4 modos × 3 sesiones × 2 workspaces × 2 temas × 375px ×
      reduced-motion) sin errores de consola; `ruff check` + pytest intactos (421/0); ambos
      workspaces creíbles con el copy nuevo
      *(2026-07-13: matriz global consolidada del estado final **42/42** — guest×2ws×2temas con
      barrido Single(memo+folios+acta)/Compare(3 cols+chips)/Metrics(placa+estado de 9 filas),
      julia en 2 temas (product mode, CERO fugas de títulos/ids bloqueados contra ground truth,
      strip + fila redactada), patricia (radios bloqueados en Single, Upload operativo), alex en
      saas (membrete Nimbus creíble), 375px en los 4 estados sin scroll horizontal, reduced-motion
      (barras estáticas, columnas visibles), toggle de tema persistente, consola limpia. ruff limpio
      + pytest **425/0** (el objetivo decía 421; los 4 tests nuevos de D.2 suben el total). Los
      scripts por etapa quedaron en el scratchpad de la sesión; los de A/B afirman intencionalmente
      estados intermedios (metric-cards) que F reemplazó — la matriz global es la vigente)*

**Fuera de alcance (señalado, no desarrollado):** tests visuales automatizados (snapshot testing)
para blindar el rediseño a futuro — sería una fase aparte.
