# Fase P — Modo producto: login, personas y permisos vividos

> QueryTrace deja de ser solo un laboratorio: un empleador entra con una cuenta demo, choca contra
> el muro de permisos como analyst, obtiene la respuesta como vp y gobierna el corpus como admin.
> El pipeline no cambia — cambia **quién sos** cuando lo usás.

**Depende de:** Fase 0 (Fase 1 recomendada para publicarlo apenas cierre) · **Esfuerzo:** 1–1.5
sesiones · **Resultado observable:** pantalla de login con personas clickeables, rol derivado de la
sesión en el servidor, Upload exclusivo del admin, y el tour de 3 minutos en el README.

**Decisiones ya tomadas (debate de producto, acordadas el 2026-07-04):**

1. **Guest-lab queda:** el laboratorio actual sigue accesible sin login ("Explore the Lab") — no se
   esconde la mejor demo técnica detrás de una pantalla.
2. **Disclosure de bloqueados = knob, default conteo:** en modo producto el usuario ve
   "N documents withheld · requires vp+", sin títulos (los títulos filtran información); el detalle
   completo vive en la consola admin y en el lab.
3. **Personas con nombre**, no cuentas secas — el audit log se lee como producto real.
4. **Fase P va antes de los workspaces (F2)**, con personas del corpus PE actual; F2 suma las del
   mundo SaaS.

**Señal de entrevista:** "moví el claim de rol de client-asserted a server-derived" · redacción del
trace en el borde de la API según quién mira · "la revelación del bloqueo también es una política" ·
auth demo-grade con upgrade path declarado (OIDC).

**Referencia visual:** artifact "QueryTrace como producto — debate y propuesta" (secciones 02 y 04:
pantalla de login y vista dual empleado/admin).

---

## P.1 Modelo de usuarios (`corpus/users.json`)

```json
{
  "users": [
    {"username": "julia",    "name": "Julia Ferreyra",  "role": "analyst", "is_admin": false, "password_sha256": "…"},
    {"username": "victoria", "name": "Victoria Sosa",   "role": "vp",      "is_admin": false, "password_sha256": "…"},
    {"username": "patricia", "name": "Patricia Alonso", "role": "partner", "is_admin": true,  "password_sha256": "…"}
  ]
}
```

- `role` = acceso a datos (los rangos existentes de `roles.json`); `is_admin` = capacidad de
  plataforma (Upload, consola, audit con nombres). **Son ejes distintos a propósito** — en el corpus
  PE la partner es también admin (los partners dirigen el fondo), así el login queda en 3 tarjetas
  sin inventar una cuarta cuenta artificial.
- Passwords hasheadas (SHA-256) por prolijidad, pero **publicadas en texto plano en el README y en
  la propia pantalla de login** — cuentas ficticias, datos ficticios, fricción cero. Deliberado y
  documentado.
- Migración en F2: `users.json` pasa a vivir por workspace (`corpora/<slug>/users.json`), con las
  personas SaaS (sofia/employee, marcos/manager, alex/exec+admin).

## P.2 Sesión (`src/auth.py`, nuevo)

1. `POST /login {username, password}` → verifica contra `users.json` → **cookie firmada**
   (HMAC-SHA256 con `SECRET_KEY` de entorno; payload: username, role, is_admin, exp). Stateless:
   sin session store — correcto para instancia única y sobrevive restarts.
2. `GET /me` → identidad actual o 401. `POST /logout` → borra la cookie.
3. Rate limit de login in-process (p. ej. 10 intentos/min por IP) → 429.
4. Sin registro, sin reset, sin OIDC — **known limitation declarada** en el README con el upgrade
   path nombrado (OIDC/Okta; grupos del IdP → roles).
5. `SECRET_KEY` como env var en el deploy; en dev local, default con warning ruidoso en logs.

Tests: login ok / password mala / usuario inexistente; `GET /me` con y sin cookie; **tampering**
(cookie alterada → 401, nunca 500); rate limit 429.

## P.3 Rol server-side — el upgrade de seguridad de la fase

Hoy `/query` y `/compare` aceptan `role` en el body: cualquiera con curl pregunta como partner.

- **Con sesión:** el rol sale de la cookie. Un `role` en el body que contradiga la sesión → **400
  explícito** (error temprano > ignorar en silencio).
- **Sin sesión (guest/lab):** comportamiento actual — el rol viene del body y el laboratorio sigue
  funcionando exactamente igual. Cero breakage de la suite existente.
- En modo producto la policy queda fija en `full_policy` — el selector de policies es un
  instrumento del lab; un empleado real no elige "sin filtros".
- **El test clave de la fase:** sesión de `julia` (analyst) que postea `role: "partner"` → 400; sin
  el campo → filtrado como analyst con los docs de partner en blocked. Verificado contra la API
  cruda, no contra la UI.

## P.4 Redacción del trace según el viewer (server-side, no cosmética)

Si la UI oculta títulos pero la API los manda, `curl` los revela — el knob tiene que aplicarse en el
borde de la API.

1. `redact_trace_for_viewer(trace, viewer)`: para sesión no-admin, `blocked_by_permission` se reduce
   a `{count, required_roles}` (sin doc_id, title ni doc_type). `demoted_as_stale` y
   `dropped_by_budget` quedan íntegros (no revelan contenido prohibido).
2. Config `BLOCKED_DISCLOSURE = "count" | "titles"` (env/config simple ahora; pasa a
   `workspace.json` en F2). Default **count**. Admin y guest-lab reciben el trace completo.
3. Frontend producto: strip "🔒 N documents withheld · requires vp+" con popover **"Why?"** →
   "your role: analyst (1) < required: vp (2)".
4. Tests: el JSON crudo de una sesión analyst **no contiene** los doc_ids bloqueados (assert sobre
   la response, no sobre el DOM); admin sí los recibe; knob en `titles` los muestra.

## P.5 Capacidades por sesión

| Superficie | Guest (lab) | Analyst/VP (producto) | Admin |
|---|---|---|---|
| Query (+ Ask cuando exista F4) | ✅ rol a elección | ✅ rol de la sesión | ✅ |
| Policy selector | ✅ | — (fijo `full_policy`) | ✅ (consola) |
| Side-by-side ("View as…") | ✅ | — | ✅ |
| Metrics / Evals | ✅ | — | ✅ |
| Session audit | ✅ anónimo | — | ✅ con usuarios |
| Upload | — | — | ✅ |

- `/ingest` exige sesión admin — **esto reemplaza el `INGEST_API_KEY` que planeaba la Fase 3**.
  `ALLOW_INGEST` se conserva como kill-switch de entorno (defensa en profundidad), pero con la
  sesión admin el deploy público puede habilitar Upload de verdad.
- Session audit: cada entrada gana `user` (username, o `null` para guest) — el audit del admin se
  lee "julia (analyst) asked …". `/session-audit` con detalle de usuarios queda para admin; el lab
  sigue viendo la versión anónima.

## P.6 UI

1. **Pantalla de login:** 3 tarjetas de persona (avatar de iniciales, nombre, rol,
   "sees N of 16 docs" calculado, credenciales visibles, tap para entrar) + link
   **"Explore the Lab without signing in →"** igual de visible.
2. Header con avatar + nombre + logout durante la sesión; los mode-buttons se filtran según la
   tabla P.5.
3. Los flujos existentes del lab (onboarding cards, compare, stale banner) no se tocan — solo se
   les suma la puerta de entrada.

## P.7 Tour de 3 minutos (README, arriba de todo)

| Min | Cuenta | Acción | Qué demuestra |
|---|---|---|---|
| 1 | `julia / demo-analyst` | Pregunta por el financial model → rechazo con "N withheld · requires vp+" | El muro se siente, no se explica |
| 2 | `victoria / demo-vp` | La misma pregunta → respuesta real (v2 arriba, v1 demoted como superseded) | Misma app, otra identidad, otra verdad |
| 3 | `patricia / demo-admin` | Sube un PDF y abre el audit: ahí está el intento bloqueado de julia con su trace | Gobernar, preguntar, auditar — ciclo cerrado |

Tabla de credenciales en el README + en la pantalla de login. (Con F4, el minuto 2 gana citas
`[doc_008]` clickeables — el tour ya queda escrito para ese upgrade.)

## Riesgos

- **Fricción:** jamás forzar login para ver el lab — el guest path va primero en la pantalla.
- **Cookie firmada casera mal hecha:** usar `itsdangerous` o `hmac` estándar + tests de tampering.
- **Compat:** toda la suite existente corre por el guest path sin sesión → cero breakage esperado;
  los tests nuevos cubren el path con sesión.

---

## Definition of Done — Fase P

- [x] `POST /login` / `GET /me` / `POST /logout` con cookie firmada, rate limit y test de tampering (`src/auth.py` + `tests/test_auth.py`; tampering → 401, nunca 500)
- [x] Rol server-derived: test "sesión analyst + body `role: partner` → 400" verde (`test_session_role_conflict_400`)
- [x] Trace redactado server-side para no-admin (assert sobre JSON crudo en `test_non_admin_raw_json_has_no_blocked_doc_ids`), knob `BLOCKED_DISCLOSURE` default `count`
- [x] Upload solo con sesión admin (401 guest / 403 no-admin); `ALLOW_INGEST` documentado como kill-switch en README y CLAUDE.md
- [x] Session audit con atribución de usuario (`user` en cada entrada; viewer no-admin la ve anónima)
- [x] Login con 3 personas clickeables + guest-lab visible; header con identidad + Sign out
- [x] Tour de 3 minutos con credenciales en el README (arriba de todo)
- [x] Suite completa verde: **238 passed, 0 skipped** (37 tests nuevos de sesión; guest path intacto) + E2E Playwright del flujo completo (login → julia withheld sin leak de doc_ids en el DOM → patricia admin) — verificado 2026-07-05

**Nota de cierre (2026-07-05):** ejecutada íntegramente en local. `GET /personas` expone las cards del login (incl. `docs_visible` y `password_hint` — deliberado). El extra del plan "popover Why?" quedó implementado en el strip de withheld. Todo pendiente de commit/push del dueño.
