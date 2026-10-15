# Decisiones y tareas pendientes del dueño del proyecto

Todo lo que los agentes NO pueden decidir ni hacer por ti. Marca cada casilla cuando esté resuelta y anota la decisión al lado.

Fuentes: spec §4 y §10 (`docs/superpowers/specs/2026-10-14-frances-classroom-design.md`), plan maestro R-30 y las tareas `human: true` de `docs/superpowers/plans/tasks.yaml`.

## 1. Bloqueantes (resolver primero: condicionan la operación y el despliegue)

- [x] **Dónde viven los datos**: decidido 2026-10-14, repo público + bucket privado de Cloudflare R2; la app se sirve por GitHub Pages y el contenido cifrado por un Worker de Cloudflare. → spec D1, D2
- [ ] **Repo de producción**: en un repo de cuenta personal solo el dueño puede guardar secretos, y en el repo actual el dueño es `JuanCardenas27`. Elegir una opción:
  - [ ] Un fork público del repo actual en tu cuenta. Tú guardas los secretos y decides cuándo entra código nuevo (recomendado).
  - [ ] Que `JuanCardenas27` cree el environment y guarde él tus secretos (token de Google, claves de Azure, R2 y LLM, passphrase) en su repo.
  → R-30, LIVE-01
- [ ] **Cuenta de Cloudflare**: crearla y activar R2 (puede pedir un método de pago aunque no pases del nivel gratuito). → LIVE-02
- [ ] **Passphrase del sitio**: elegirla (≥ 24 caracteres; mejor 5 o más palabras al azar) y guardarla en un gestor de contraseñas. Nunca va en git. → spec D2, LIVE-02
- [ ] **Google Cloud + OAuth**: crear el proyecto, habilitar las APIs de Classroom y Drive, publicar la pantalla de consentimiento en **«In production»** (en «Testing» el token caduca a los 7 días) y autorizar con la cuenta UNAL. → SPK-05, LIVE-01
- GitHub Pro ya no es necesario: puedes activar el Student Pack igual, pero no bloquea nada.

## 2. Decisiones de contenido

- [x] **Voces adolescentes e infantiles**: decidido 2026-10-14, sin clonación. Son 4 voces **sintéticas** (chica y chico adolescentes, niña y niño): una voz Edge con el tono subido y el timbre desplazado. Los valores se eligen de oído en SPK-02. → spec D7, D8, R-16
- [ ] **Eloise (`fr-FR-EloiseNeural`)**: escucharla y decidir si sirve como voz infantil gratuita. Catálogos de terceros la listan como «child». → SPK-02
- [x] **LLM**: decidido 2026-10-14, API key propia de un proveedor con API compatible con OpenAI. Falta elegir proveedor y modelo y probarlos (SPK-06). Si no hay clave, las tarjetas salen por reglas. → spec D5, SPK-06

## 3. Aprobar (o cambiar) las decisiones que tomó el diseñador (spec §4)

| # | Decisión | Aprobada |
|---|---|---|
| D1 | Repo público con código; datos en un bucket R2 privado | [x] |
| D2 | App en GitHub Pages; contenido cifrado (AES-256-GCM, PBKDF2 a 600 000 iteraciones) servido por un Worker | [ ] |
| D3 | Pipeline en Python con uv; SQLite persistido como volcado `state/state.sql` en R2, con lease y escritura condicional | [ ] |
| D4 | Revisar a diario la `version` de cada archivo de Drive (detecta PDFs reemplazados) | [ ] |
| D5 | LLM opcional por API compatible con OpenAI y, como respaldo, reglas con spaCy y Azure Translator F0 | [x] |
| D6 | Audio: Denise y Henri fijas + 1 voz rotativa por tarjeta; las de taladro con todas las voces | [ ] |
| D7 | Sin clonación y nada en tu PC: todo corre en GitHub Actions o Cloudflare; tus pasos se hacen en el navegador | [x] |
| D8 | Voces jóvenes sintéticas derivadas de Edge; nunca grabaciones de personas | [x] |
| D9 | App en Vite + React + TypeScript, PWA offline, repaso FSRS, UI en español | [ ] |
| D10 | Clave de Azure Speech dentro del bundle cifrado (F0 no factura; el peor caso es agotar la cuota) | [ ] |
| D11 | Sync diario a las 05:17 de Bogotá; reconciliación los domingos 06:00; los cron se reactivan solos | [ ] |
| D12 | Secretos en el environment `production` limitado a `main`; workflows con secretos sin disparo por PR | [ ] |

## 4. Tareas que ejecutas tú (cada una tiene un checklist con comandos exactos)

| Tarea | Qué | Plan | Hecha |
|---|---|---|---|
| SPK-02 | Lanzar el workflow «spike-voices», escuchar los clips en el navegador y elegir los valores de las voces jóvenes → ADR-002 | `plans/2026-10-14-01-spikes-foundation.md` | [ ] |
| SPK-04 | Crear el environment `production` con la clave de Azure y lanzar el workflow «spike-azure» → 7 JSON y ADR-004 | ídem | [ ] |
| SPK-05 | Probar OAuth con la cuenta UNAL en OAuth Playground y revisar si el admin bloquea apps → ADR-005 | ídem | [ ] |
| SPK-06 | Elegir proveedor LLM (API compatible con OpenAI), crear la clave y correr el probe → ADR-006 | ídem | [ ] |
| LIVE-01 | Fork de producción, proyecto GCP, environment `production` y refresh token con OAuth Playground | `plans/2026-10-14-07-ops-golive.md` | [ ] |
| LIVE-02 | Bucket R2, tokens de Cloudflare, Worker (se despliega desde Actions), Azure Translator F0, secretos y variables | ídem | [ ] |

Todo se hace en el navegador: no hay nada que instalar ni ejecutar en tu PC. Además, el dueño de cada repo (desarrollo y producción) activa Pages con fuente «GitHub Actions» (OPS-06) y configura la branch protection de `main` (checks: `python (3.11)`, `python (3.12)`, `web`, `contracts`, `e2e`, `worker`).
