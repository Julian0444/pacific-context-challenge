# QueryTrace — Roadmap de fases

> Objetivo global: convertir QueryTrace de "lab de contexto con corpus financiero ficticio" en un
> **gateway RAG auditable, multi-dominio, deployado y profesional** que demuestre aptitudes de
> AI Engineer: evals propios, integración LLM con citas, ingesta de producción y reproducibilidad.

Cada fase tiene su plan en este directorio. Las fases son **shippeables por separado**: al final de
cada una el proyecto queda mejor que antes, deployable y con la suite verde.

## Orden y dependencias

```
Fase 0 (base profesional) ──► Fase 1 (deploy sólido) ──► Fase P (modo producto)
                                                               │
                                                               ▼
                                                   Fase 2 (workspaces genéricos)
                                                               │
                                                   ┌───────────┴───────────┐
                                                   ▼                       ▼
                                          Fase 4 (Ask mode / RAG)   Fase 3 (ingesta pro)
                                                   │                       │
                                                   └───────────┬───────────┘
                                                               ▼
                                                   Fase 5 (retrieval depth — opcional)
```

- **Fase 0 es prerequisito de todo** — no se construyen features sobre una base con bugs conocidos.
- **Fase P va inmediatamente después del deploy** (acordado 2026-07-04): el modo producto —
  login con personas, rol server-side, upload solo admin — llega con el corpus PE actual; F2 lo
  multiplica por workspace.
- Fase 3 y Fase 4 son independientes entre sí después de Fase 2; **recomendado F4 primero** — Ask
  es el payoff del minuto 2 del tour de Fase P.
- Fase 2 solo puede saltearse aceptando reescribir Fase 3 (su ingesta, jobs y CLI asumen
  workspaces) y resolviendo en otro lado la migración de `users.json` / `blocked_disclosure` que
  Fase P le delega. No recomendado — es el unlock de "aplicable a cualquiera".

## Estado

| Fase | Plan | Esfuerzo estimado | Estado |
|------|------|-------------------|--------|
| 0 — Base profesional | [fase-0-base-profesional.md](fase-0-base-profesional.md) | 1–2 sesiones | 🔨 En curso (todo hecho y verificado en local; falta solo "CI verde" con el primer push del dueño) |
| 1 — Deploy sólido | [fase-1-deploy.md](fase-1-deploy.md) | ½–1 sesión | 🔨 En curso (partes locales hechas: OG tags, favicon, og-card.png, render.yaml, banner cold-start; faltan GIF hero + pasos de Render del dueño) |
| P — Modo producto (login + personas) | [fase-p-producto.md](fase-p-producto.md) | 1–1.5 sesiones | ✅ Hecha (2026-07-05, local; pendiente de commit del dueño) |
| 2 — Workspaces genéricos | [fase-2-workspaces.md](fase-2-workspaces.md) | 2–3 sesiones | 🔨 En curso (2026-07-06: todo hecho y verificado en local — 6/7 casillas; falta solo "demo deployado" que espera push/deploy del dueño) |
| 3 — Ingesta pro | [fase-3-ingesta-pro.md](fase-3-ingesta-pro.md) | 2–3 sesiones | 🔨 En curso (2026-07-06: Etapas A–D hechas y verificadas en local — 5/6 casillas; falta solo "upload en el deploy público" que espera push/deploy del dueño) |
| 4 — Ask mode (RAG completo) | [fase-4-ask-mode.md](fase-4-ask-mode.md) | 2–3 sesiones | 🔨 En curso (2026-07-06: 5/6 casillas — backend+tests, seguridad del prompt, UI E2E 19/19, goldens MEDIDOS y citation validity 100% publicada (corrida keyed del dueño); falta solo "deploy con key activa + 429 en prod" que espera push/deploy del dueño) |
| 5 — Retrieval depth | [fase-5-retrieval-depth.md](fase-5-retrieval-depth.md) | 2–4 sesiones | ✅ Hecha (2026-07-11: Etapas A (ONNX) + B (chunking) completas y verificadas en local — suite 421/0, evals regeneradas, imagen Docker 1.92 GB→980 MB; Etapa C (reranker) NO se hizo — era stretch opcional, queda como roadmap declarado. Pendiente de commit del dueño) |

"Sesión" = una sesión de trabajo enfocada (~2–4 h con asistencia de Claude).

## Decisiones abiertas (bloquean partes de fases, no el arranque)

| # | Decisión | Afecta | Recomendación | Estado |
|---|----------|--------|---------------|--------|
| D1 | Hosting: Render+Docker / HF Spaces / híbrido Vercel-front | Fase 1 | Render+Docker (ya funciona); HF Spaces como espejo | ⬜ |
| D2 | Cold start en Render free (~45–60 s): pagar Starter (USD 7/mes) vs aceptar vs swap ONNX (Fase 5) | Fase 1 | Starter mientras se busca trabajo; ONNX lo resuelve de raíz después | ⬜ |
| D3 | Ask mode con LLM real (requiere `ANTHROPIC_API_KEY` en el deploy, costo ~centavos/query con Haiku) | Fase 4 | Sí — es el diferenciador más grande del roadmap, y el payoff del tour de Fase P | ⬜ |
| D4 | Dominio del segundo corpus | Fase 2 | — | ✅ Resuelta 2026-07-04: SaaS interno ("Nimbus Analytics", employee/manager/exec) |
| D5 | Chunking real (cambia todas las métricas publicadas → regenerar evals) vs dejarlo como roadmap declarado | Fase 5 | Hacerlo, con tabla antes/después como contenido del README | ✅ Resuelta 2026-07-11: se hace (el dueño pidió completar la Fase 5); métricas se regeneran en la misma tanda |
| D6 | Skills de Claude Code: el working tree las tiene borradas y `.gitignore` incluye `.agents/`/`.claude/`, pero la nota del 2026-07-04 (Fase 0.6) dice conservarlas como tooling. ¿Restaurar y des-gitignorear, o aceptar el borrado y actualizar la nota? | Fase 0 (cierre) | Restaurarlas si el roadmap las sigue usando | ⬜ |

**Resueltas en el debate de producto (2026-07-04)** — detalle en [fase-p-producto.md](fase-p-producto.md):
guest-lab accesible sin login · disclosure de bloqueados con default **conteo** · personas con
nombre · Fase P antes de F2 (personas del corpus PE primero).

## Reglas de ejecución (aplican a todas las fases)

1. **Todo cambio con test.** La suite queda verde al final de cada tarea (`184 passed, 0 skipped` después de Fase 0).
2. **Números publicados = números medidos.** Nada de métricas estimadas en README/docs; si una fase cambia métricas, se regeneran y se actualizan en la misma tanda de cambios.
3. **Python siempre con `.venv/bin/python`** en local (el `python3` del sistema está roto para este repo).
4. **Git es 100 % manual del dueño.** Claude NO ejecuta `git add`, `commit`, `push`, `git mv`, ni crea branches, PRs, tags o releases, ni usa `gh` para mutar nada — solo lecturas (`git status`, `git diff`, `git log`). Al cerrar cada tarea, Claude entrega: (a) la lista de archivos tocados, (b) un mensaje de commit sugerido con prefijo de fase (`F0:`, `F1:`, `FP:`…), y el dueño versiona y pushea cuando decide. Si una tarea requiere una operación de git (dejar de trackear un archivo, mover con historial), Claude la describe y el dueño la ejecuta.
   **Esto cubre también los deploys:** nada llega a GitHub, Render, HF Spaces ni a ningún hosting salvo por un push/acción manual del dueño. Claude nunca dispara un deploy ni toca la config del hosting. Toda casilla de una Definition of Done que requiera CI corriendo o un servicio deployado (checklist de humo, "deploy con key activa", "demo deployado", "CI verde") queda **bloqueada hasta que el dueño pushee/deploye** cuando el proyecto le cierre — Claude deja todo listo, verificado localmente, y esa casilla se tilda recién después.
5. **Todo el roadmap vive en la rama `feat/ToDeploy` — `main` es intocable.** Ningún plan, tarea ni sugerencia de commit apunta a `main`: se trabaja y versiona en la rama aparte, y el merge a `main` es una decisión exclusiva del dueño cuando el resultado final le cierre. Si el nombre de la rama de trabajo cambia, se actualiza esta regla.
6. **El estado vive en estos archivos.** Al terminar una tarea se tilda su casilla en la Definition of Done de la fase; al cerrar una fase se actualiza la tabla de Estado de este README (⬜ Pendiente → 🔨 En curso → ✅ Hecha). Como git es manual, esto es la fuente de verdad del progreso.
7. Este directorio `plansToPortfolio/` es material de trabajo: antes del "release público" del repo se decide si forma parte del repo como bitácora o se excluye (ver Fase 0, tarea 6).

## Cómo ejecutar una fase en una sesión nueva

Prompt de arranque sugerido (copiar y pegar, cambiando la fase):

> Leé `plansToPortfolio/README.md` y `plansToPortfolio/fase-0-base-profesional.md`. Ejecutá la
> Fase 0 tarea por tarea, en orden. Respetá las Reglas de ejecución del README — en particular:
> git es 100 % manual mío (vos no commiteás, no pusheás ni deployás nada), trabajamos en la rama
> `feat/ToDeploy` y `main` no se toca, usá `.venv/bin/python`, y todo número que toque un doc
> tiene que estar medido. Al final de cada tarea: suite verde, resumen de archivos tocados y
> mensaje de commit sugerido. Marcá el progreso en la Definition of Done.

Notas para la sesión ejecutora:

- Antes de la primera tarea de una fase: pasar su fila a 🔨 En curso en la tabla de Estado.
- Los planes citan `archivo:línea` verificados en la auditoría del 2026-07-02 — si el código se
  movió desde entonces, verificar antes de editar (los hallazgos siguen siendo válidos; las líneas
  pueden haber corrido).
- Si durante la ejecución aparece una decisión no cubierta por el plan, anotarla en la tabla de
  Decisiones de este README en vez de improvisar en silencio.
