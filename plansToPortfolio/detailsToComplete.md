# detailsToComplete — pendientes que se resuelven al final

Lista consolidada (2026-07-11) de todo lo que quedó abierto en fases "casi cerradas".
Nada de esto bloquea la Fase 5; se resuelve al final, la mayoría con el push/deploy
manual del dueño. Fuente: Definition of Done de cada fase + tabla de Decisiones del README.

## 1. Decisiones del dueño (no requieren código)

| # | Decisión | Afecta | Recomendación vigente |
|---|----------|--------|------------------------|
| D1 | Hosting: Render+Docker / HF Spaces / híbrido | Fase 1 | Render+Docker (ya funciona); HF Spaces como espejo |
| D2 | Cold start Render free (~45–60 s): Starter USD 7/mes vs aceptar vs ONNX | Fase 1 | Starter mientras se busca trabajo — **revisar tras Fase 5-A: con ONNX el cold start deja de doler** |
| D3 | `ANTHROPIC_API_KEY` en el deploy (Ask mode real, ~centavos/query) | Fase 4 | Sí — es el diferenciador más grande |
| D6 | Skills de Claude Code: el working tree las tiene borradas + gitignoreadas, contradiciendo la nota del 2026-07-04 de conservarlas | Fase 0 (cierre) | Restaurarlas si el roadmap las sigue usando. **Resolver ANTES del commit** — el commit consolidaría el borrado |
| — | ¿`plansToPortfolio/` entra al repo como bitácora o se excluye? (README regla 7 / Fase 0 tarea 6) | Release público | Decisión del dueño antes del release |

## 2. Operaciones de git del dueño (Claude no ejecuta git)

- [ ] Untrackear `test-results/` (quedó pendiente del cierre de Fase 0, casilla 6).
- [ ] Commit + push de TODO el trabajo del roadmap a `feat/ToDeploy` (working tree entero sin
      commitear desde HEAD `5b3d58c`). Este push destraba casillas en las fases 0, 2, 3 y 4.
- [ ] Versionar los artifacts regenerados por la Fase 5 (los vectores ONNX no son bit-idénticos
      a los de torch).
- [ ] Merge final a `main` cuando el resultado cierre (decisión exclusiva del dueño).

## 3. Casillas que se tildan con el push/deploy

| Fase | Casilla pendiente | Qué necesita |
|------|-------------------|--------------|
| 0 | "CI verde" | Primer push (workflow ya escrito) |
| 1 | Deploy Docker con `ALLOW_INGEST=false` + health check | Push + config de Render |
| 1 | Preview card OG verificada | URL pública (tags/favicon/og-card.png ya hechos) |
| 1 | GIF hero en README + link vivo | Deploy + grabación del dueño |
| 1 | Checklist de humo pasada | Corre contra el deploy |
| 1 | Monitoreo de uptime activo | Servicio externo (UptimeRobot o similar) apuntando al deploy |
| 2 | Demo deployado con el picker de dos workspaces | Push/deploy (local verificado: Playwright 23/23 + 17/17) |
| 3 | Upload habilitado en el deploy público y probado E2E | Push/deploy + `ALLOW_INGEST` en el hosting |
| 4 | Deploy con key activa + 429 reproducible en prod | Push/deploy + cargar `ANTHROPIC_API_KEY` en el dashboard (`render.yaml` ya la declara con `sync: false`) |

## 4. Opcionales anotados dentro de casillas ya tildadas

- **Fase 3:** no existe path de DELETE/edición de documentos — documentado como límite conocido
  (Known Limitations). Cerrarlo sería trabajo nuevo (upgrade path: `IndexIDMap` en FAISS).
- **Fase 4:** captura de pantalla lado-a-lado analyst-vs-partner para el README — opcional del
  dueño; el contraste ya está narrado en texto con los goldens medidos.

## 5. Post-Fase 5 (ejecutada 2026-07-11 — Etapas A+B hechas, C no)

- [x] Tabla antes/después del chunking publicada en README (regla 2 cumplida en la misma tanda).
- [ ] **D2 revisar con datos**: el cold start doloroso era torch; con ONNX el contenedor local
      responde /health en 0.5 s. Medir en Render free tras el deploy y decidir si Starter sigue
      haciendo falta.
- [ ] **Goldens de Ask pre-chunking**: `corpora/pe-deal/ask_goldens.json` y
      `evals/results/ask-2026-07-06-pe-deal.json` se midieron antes del chunking (siguen siendo
      snapshots válidos y fechados). Opcional del dueño: corrida keyed de
      `python -m src.evaluator --ask` y `--ask-goldens` para números post-chunking (~USD 0.05).
- [ ] **Etapa C (reranker cross-encoder)** — stretch no hecho: preset `full_policy_rerank` +
      A/B honesto de P@5/latencia. Declarada como roadmap en README Known Limitations.
- [ ] Extra liviano no hecho: latencia p50/p95 por stage en `/evals` y Metrics UI.
- [ ] Versionar los artifacts regenerados (28 chunks por workspace) junto con el resto del push.
