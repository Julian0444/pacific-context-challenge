# Fase 1 — Deploy sólido

> El link del portfolio carga rápido, se ve bien al compartirlo, y no depende de que tu laptop esté
> prendida. Deploy desde Docker, con flags correctos y checklist de humo post-deploy.

**Depende de:** Fase 0 (Dockerfile, pins arreglados) · **Esfuerzo:** ½–1 sesión ·
**Resultado observable:** URL pública estable en el README, preview card linda en LinkedIn/Slack,
`/health` monitoreado.

> **Recordatorio (Regla 4 del README):** en esta fase Claude solo prepara archivos y config en el
> working tree (Dockerfile ya existe; OG tags, `render.yaml`, GIF, etc.) y los verifica localmente.
> **Ningún deploy ocurre hasta que el dueño pushea** — Render solo reacciona a pushes del dueño, y
> los pasos que tocan el dashboard de Render (cambiar a Docker, env vars, rama de deploy) los
> ejecuta el dueño con Claude indicando exactamente qué tocar. La checklist de humo (1.5) corre
> recién después de ese deploy manual.

---

## ⚠️ Decisión D1 — dónde hostear (contexto técnico)

**Vercel completo queda descartado** para la API con el stack actual — no es config, es física:

- Funciones Python de Vercel: límite **250 MB descomprimido**. Solo torch cpu ≈ 190 MB; con
  transformers + sentence-transformers + faiss + modelo (~90 MB) se supera 3–4×.
- Filesystem **read-only** (solo `/tmp`): `/ingest` escribe `corpus/` y `artifacts/`; imposible.
- Estado en memoria de proceso (session audit, caches) no sobrevive instancias serverless.

(El swap a ONNX de la Fase 5 achica las deps ~10×, pero el estado y las escrituras siguen sin
encajar en serverless. Vercel para la API solo tendría sentido tras un rediseño a vector store +
estado externos — fuera de alcance.)

**Opciones reales:**

| Opción | Pros | Contras |
|---|---|---|
| **A. Render + Docker (recomendada)** | Ya está deployado ahí; cero migración; custom domain gratis; deploy automático desde el repo | Free tier duerme a los 15 min → cold start 45–60 s (ver D2) |
| **B. Hugging Face Spaces (Docker SDK)** | Gratis, 16 GB RAM; estar en HF es señal de AI engineer en sí; buen espejo del deploy principal | URL `*.hf.space`; duerme a las 48 h de inactividad (free); sin custom domain |
| **C. Híbrido: frontend en Vercel + API en Render** | Te da el link `*.vercel.app` si te importa la estética | Suma CORS + dos deploys para mantener; gana poco |

**Recomendación:** A como principal (+ B como espejo si sobra tiempo — es ~20 min extra con el
mismo Dockerfile). C solo si el dominio Vercel es un requisito personal.

## ⚠️ Decisión D2 — cold start del free tier

Un reclutador que espera 60 s se va. Opciones:

1. **Render Starter (USD 7/mes)** — instancia siempre viva. Recomendado mientras dure la búsqueda
   laboral; se cancela después.
2. Aceptar el cold start pero **avisarlo**: mensaje "waking up the free-tier server (~45 s)…" en el
   frontend cuando `/health` tarda (mejor que un spinner mudo).
3. Ping de keep-alive cada 10 min (UptimeRobot free). Funciona, es práctica común, pero va contra el
   espíritu del free tier — decisión personal.
4. Fase 5 (ONNX) reduce el arranque de la app a segundos; el spin-up del contenedor de Render sigue
   existiendo pero el total baja mucho.

---

## 1.1 Deploy en Render desde Docker

1. Cambiar el servicio de Render de buildpack a **Docker** (usa el Dockerfile de Fase 0). El build
   pre-hornea el modelo → el arranque ya no descarga nada.
   **Rama de deploy:** durante el roadmap, apuntar el Auto-Deploy de Render a la rama de trabajo
   `feat/ToDeploy` (así cada push del dueño se ve deployado de verdad). El deploy "oficial" desde
   `main` recién existe cuando el dueño hace el merge final — en ese momento se re-apunta el
   servicio a `main` (o se mantienen dos servicios: preview en la rama, oficial en main).
   **Nota de control:** "Auto-Deploy" de Render solo significa que un push del dueño dispara el
   deploy — nadie más puede dispararlo. Si el dueño prefiere doble control (que ni siquiera sus
   pushes deployen solos), Render permite `Auto-Deploy: No` y deployar con el botón "Manual
   Deploy" cuando él decida. Ambas opciones son compatibles con el roadmap; elegir al configurar.
2. Env vars: `ALLOW_INGEST=false` (deploy read-only; se revisa en **Fase P**, cuando Upload queda
   detrás de la sesión admin y el deploy público puede habilitarlo de verdad).
3. Health check path: `/health`.
4. Opcional pero pro: **`render.yaml`** (Blueprint) en el repo — infra as code, un archivo de 15
   líneas que define servicio, env vars y health check. Buen talking point.
5. Verificar que los artifacts versionados en el repo (`artifacts/*.{index,json}`) llegan a la
   imagen (no están en `.dockerignore`).

## 1.2 Presentación del link (esto es lo que "se ve profesional")

En `frontend/index.html`:

1. **OG tags + Twitter card**: `og:title` ("QueryTrace — Auditable RAG gateway"), `og:description`
   (una frase con el pitch), `og:image` → `frontend/og-card.png` (imagen estática 1200×630 con
   nombre + una captura del Compare mode), `meta description`.
2. **Favicon** propio (el "QT" del brand mark como SVG/PNG).
3. Title ya está bien (`QueryTrace — Context Policy Lab`).

En el README:

4. **GIF hero de ~15 s** del Compare mode (grabar con Kap/QuickTime → gif optimizado <3 MB):
   la misma query como analyst mostrando 3 columnas con los bloqueos. Es el asset de marketing más
   rentable de todo el proyecto.
5. Link vivo arriba de todo + nota de cold start si quedó free tier.

## 1.3 Monitoreo mínimo

- UptimeRobot (free) contra `/health` → si el deploy se cae, enterarse antes que un reclutador.
- Opcional: badge de uptime en el README.

## 1.4 (Solo si D1 = C) Frontend en Vercel

- `frontend/` como proyecto estático en Vercel (cero build).
- `app.js`: hoy `API_BASE` asume same-origin fuera de localhost (`frontend/app.js:6-10`) → agregar
  override: `const API_BASE = window.QUERYTRACE_API ?? (heurística actual)` + un
  `<script>window.QUERYTRACE_API="https://<render-host>"</script>` solo en el deploy de Vercel.
- CORS en `src/main.py:34-39`: restringir `allow_origins` a `[vercel-domain, localhost]` y
  `allow_methods=["GET", "POST"]` (hoy `*`/`*`).

## 1.5 Checklist de humo post-deploy

```
curl https://<host>/health                          → {"status":"ok","ingest_enabled":false}
curl -X POST https://<host>/query -d '{"query":"ARR growth","role":"analyst"}' → 200 con trace
https://<host>/app/                                  → UI carga, sin errores de consola
Compare mode                                        → 3 columnas, flags "blocked in full"
Metrics mode                                        → 12 queries, violaciones 0%
Upload tab                                          → oculto (ingest_enabled=false)
Pegar el link en LinkedIn (modo preview)            → card con imagen y descripción
Lighthouse rápido                                   → sin rojos graves de accesibilidad
Recorrida en viewport móvil (~390px)                → header, Compare (scroll horizontal digno),
                                                      cards y trace legibles; sin overflow roto
Pasada rápida solo-teclado                          → tabs, radios, toggles y trace alcanzables
                                                      con foco visible
```

---

## Definition of Done — Fase 1

- [ ] D1 y D2 decididas y anotadas en `plansToPortfolio/README.md`
- [ ] Deploy desde Docker con `ALLOW_INGEST=false` y health check configurado *(requiere push + config de Render del dueño)*
- [ ] OG tags + favicon + og-card.png; preview card verificada *(la verificación de la card requiere el deploy)*
- [ ] GIF hero en el README + link vivo
- [ ] Checklist de humo completa y pasada *(corre contra el deploy manual del dueño)*
- [ ] Monitoreo de uptime activo
