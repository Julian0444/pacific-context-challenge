# Fase 4 — Ask mode: cerrar el loop RAG con citas auditables

> Hoy QueryTrace arma el contexto pero nunca lo usa — no hay una sola llamada a un LLM en el
> proyecto. Esta fase agrega `POST /ask`: la misma pregunta como *analyst* y como *partner* produce
> **respuestas diferentes**, con citas `[doc_id]` verificables y el decision trace probando qué vio
> (y qué nunca vio) el modelo. Es el diferenciador más grande del roadmap.

**Depende de:** Fase 0 y **Fase P** (las reglas de sesión y redacción del trace de P gobiernan
`/ask` — ver 4.1.3 — y el tour del minuto 2 es su payoff); Fase 2 recomendada para que Ask sea por
workspace · **Esfuerzo:** 2–3 sesiones · **⚠️ Decisión D3:** requiere `ANTHROPIC_API_KEY` en el
deploy; costo ~centavos por query de demo con Haiku.

**Señal de entrevista:** integración LLM real con grounding, citas validadas mecánicamente, evals de
fidelidad propios, control de costos. El pitch sube de "hice retrieval" a "hice un sistema RAG
auditable end-to-end".

---

## 4.1 Backend — `src/ask.py` (nuevo módulo, misma filosofía de stages)

1. **`build_prompt(query, included_docs) -> (system, user)`** — función pura, testeable sin red:
   - System: "Answer ONLY from the provided context. After each claim, cite the source as
     [doc_id]. If the context is insufficient, say so explicitly — do not use outside knowledge."
   - User: la query + bloques de contexto etiquetados:
     `<doc id="doc_003" title="..." date="..." type="...">{content}</doc>`
     (el mismo contenido que empaqueta el budget packer — el prompt ES el contexto auditado).
2. **Cliente Claude:** SDK `anthropic` (nueva dep). Modelo por env `ASK_MODEL`, default Haiku
   (`claude-haiku-4-5-20251001` — **verificar id vigente y precios contra la referencia de la API al
   implementar**, no confiar en este plan). `max_tokens≈600`, `temperature=0.2`. v1 sin streaming
   (JSON simple + spinner); streaming SSE queda como stretch anotado.
3. **`POST /ask`** — request igual a `/query` (`query, role, top_k, policy_name, workspace`):
   - Reglas de Fase P: con sesión, el rol se deriva de la cookie (body `role` contradictorio → 400)
     y el trace de la response se redacta según el viewer; sin sesión (guest-lab), rol del body.
   - Corre `run_pipeline()` (cero lógica duplicada) → si no hay key → 403 tipo feature-disabled.
   - Llama al modelo con el contexto empaquetado.
   - **Extracción y validación de citas:** regex `\[doc_\d+\]` sobre la respuesta → cada cita se
     marca `valid` (∈ included) o `invalid`. Métrica mecánica, sin LLM-judge.
   - Response: `{answer, citations: [{doc_id, valid}], grounded_doc_count, model, usage:{input_tokens,
     output_tokens}, decision_trace, context}` — el trace viaja SIEMPRE con la respuesta.
4. **Feature flag (patrón ya existente de `ingest_enabled`):** `/health` expone
   `ask_enabled: bool` (= hay API key). Sin key todo lo demás funciona igual.
5. **Guardrails de demo pública:**
   - **Cache** por `(workspace, query normalizada, role, policy)` con TTL (~1 h) — repetir la demo
     no re-paga tokens.
   - **Rate limit** in-process simple: contador por ventana de 60 s global + por IP
     (`X-Forwarded-For` detrás del proxy de Render) → 429 con mensaje amable. Límites por env
     (`ASK_MAX_PER_MINUTE`, default 6).
   - `ASK_MAX_CONTEXT_TOKENS` de recorte defensivo (el budget packer ya limita a 2048 — doble
     cinturón).
   - Presupuesto estimado documentado: 12 evals × ~2 k tokens input con Haiku ≈ centavos; una demo
     de entrevista completa < USD 0.10.

## 4.2 Frontend

1. En Single mode, junto a **Run**: botón **"Ask AI"** (visible solo si `ask_enabled`).
2. **Panel de respuesta** arriba de los result cards: el texto con las citas `[doc_003]` renderizadas
   como chips clickeables → scroll + highlight del card correspondiente. Citas inválidas (raras) en
   rojo con tooltip "cited a document that was not in context".
3. **Badge de grounding:** "Grounded in N docs · M blocked docs never reached the model" — la frase
   que convierte el RBAC en algo visceral.
4. Nota de uso discreta (tokens in/out) al pie del panel — transparencia de costos.
5. Estado sin key: el botón no existe (mismo patrón que Upload oculto).

## 4.3 La demo asesina (guardarla como fixtures)

Elegir 2–3 pares de preguntas donde la respuesta **cambia según el rol** (p. ej. "What is the IC
recommendation?" — partner ve el memo final [doc_010], analyst recibe "the provided context does not
include an IC recommendation") y guardarlos como snapshots en `evals/ask_goldens.json` + capturas en
el README. Ese lado-a-lado es la imagen que un entrevistador recuerda — y es exactamente el
minuto 2 del tour de Fase P (julia bloqueada vs victoria con citas), que queda upgradeado gratis.

## 4.4 Evals de fidelidad

Extender `src/evaluator.py` con `--ask` (opt-in, gasta tokens):

- Corre las 12 queries con Ask → **citation validity rate** (citas válidas / totales — objetivo
  100 %), **groundedness proxy** (respuestas que citan ≥1 doc vs respuestas-rechazo), y por query si
  los `expected_doc_ids` aparecen citados.
- Snapshot fechado en `evals/results/ask-YYYY-MM-DD.json`; la tabla del README suma la fila
  "Citation validity".
- En CI **no** se corre con red/key: el smoke usa el cliente mockeado.

## 4.5 Tests (sin red, cliente mockeado)

- `build_prompt`: incluye todos los included con sus ids, nunca incluye blocked (test que inyecta un
  trace con blocked y asserta que sus contenidos NO están en el prompt — es el test de seguridad
  clave de la fase).
- Validador de citas: válidas/ inválidas/ duplicadas/ sin citas.
- `/ask` con mock: shape de response, cache hit (segundo call no llama al cliente), rate limit 429,
  sin key → 403 y `ask_enabled: false` en health.
- Manejo de errores del proveedor: timeout/500 del API → 502 propio con mensaje claro, sin stack.

## 4.6 Riesgos

- **Costo runaway en demo pública** → rate limit + cache + Haiku + max_tokens; kill-switch = sacar
  la env var (el modo desaparece de la UI).
- **Prompt injection desde documentos** (un doc ingestado podría decir "ignore instructions"):
  mitigación honesta para el README — los docs van en bloques etiquetados y el system prompt manda;
  para el alcance demo se documenta como known limitation, no se resuelve.
- **Modelo/id desactualizado**: verificar contra la doc de la API al implementar (regla: ids y
  precios nunca hardcodeados desde este plan).

---

## Definition of Done — Fase 4

- [x] `/ask` con citas validadas, trace adjunto, cache, rate limit y flag por env *(2026-07-06 — gate order: flag 403 → sesión/workspace/rol → cache → rate limit 429 → pipeline → modelo 502; redacción per-viewer incluso sirviendo desde cache)*
- [x] Prompt builder testeado incl. "blocked nunca entra al prompt" *(unit con pipeline real + test en el borde de la API capturando el prompt enviado al provider — 37 tests nuevos, suite 333/0)*
- [x] UI: botón Ask, panel con citas clickeables, badge de grounding, oculto sin key *(E2E Playwright 19/19: sin key oculto, con key visible solo en Single, chips válidas scrollean+highlightean, inválidas en rojo, 502 amable sin traceback, julia product-mode con withheld strip)*
- [x] 2–3 goldens analyst-vs-partner guardados + captura lado-a-lado en README *(2026-07-06: los 3 goldens MEDIDOS con la key del dueño — IC recommendation: analyst "cannot find" (cita doc_005/doc_015) vs partner "$340M proceed" (doc_010/doc_014); valuation: analyst/vp citan el rumor doc_015 $500M; customer concentration: analyst sin acceso vs vp cita doc_012/doc_008. Snapshots en `corpora/pe-deal/ask_goldens.json`; el contraste quedó narrado en el README — la captura de pantalla lado-a-lado sigue siendo opcional del dueño)*
- [x] `evaluator --ask` con citation validity publicada; CI verde sin necesitar key *(2026-07-06: corrida keyed sobre el benchmark pe-deal con claude-haiku-4-5 — **citation validity 100%, groundedness 100%, expected-cited 100%**, 26,612 in / 2,909 out ≈ USD 0.04; snapshot en `evals/results/ask-2026-07-06-pe-deal.json`; número publicado en la sección Ask del README. CI sin key ✓ — corre con el push del dueño)*
- [ ] Deploy con key activa y límites probados (429 reproducible) *(requiere push/deploy manual del dueño + cargar la `ANTHROPIC_API_KEY` en el hosting — la key nunca pasa por Claude ni por el repo; `render.yaml` ya declara la env var con `sync: false`)*

### Desvíos documentados (ejecución 2026-07-06)

- **Goldens por workspace, no `evals/ask_goldens.json`:** Fase 2 movió todo lo corpus-específico a `corpora/<slug>/`; los goldens son del corpus pe-deal → viven en `corpora/pe-deal/ask_goldens.json` (spec con `snapshots: null` hasta la primera corrida keyed). Los snapshots de `--ask` sí van a `evals/results/ask-YYYY-MM-DD-<slug>.json` como decía el plan.
- **Id de modelo verificado al implementar (regla del plan):** el id vigente es el alias `claude-haiku-4-5` (sin sufijo de fecha), $1/$5 por MTok — no el `claude-haiku-4-5-20251001` que citaba el plan como placeholder.
- **Cache key incluye `top_k`** además de (workspace, query normalizada, role, policy): distinto top_k ⇒ distinto contexto ⇒ respuesta distinta.
- **`AskResponse` incluye `total_tokens`** (espeja `QueryResponse`) para que el frontend reutilice `renderSingleResult()` sin bifurcar.
- **`/ask` no escribe en el session-audit** — la doc de MET-A define el audit como log de `/query`; extenderlo a `/ask` queda anotado como follow-up opcional, no se cambió en silencio.
