# Decisiones y tareas pendientes del dueño del proyecto

Todo lo que los agentes NO pueden decidir ni hacer por ti. Marca cada casilla cuando esté resuelta y anota la decisión al lado.

Fuentes: spec §4 y §10 (`docs/superpowers/specs/2026-10-14-frances-classroom-design.md`) y las tareas `human: true` de `docs/superpowers/plans/tasks.yaml`.

## 1. Bloqueantes (resolver primero: condicionan la operación y el despliegue)

- [ ] **Repos**: aprobar dos repos (el público actual solo con código y uno privado nuevo `frances-data` con los datos), o pedirle a `JuanCardenas27` que vuelva privado el repo actual. Motivo: el repo es público y los logs de Actions de un repo público también lo son. → spec D1
- [ ] **GitHub Pro**: activar el GitHub Student Developer Pack en la cuenta que será dueña de `frances-data`, porque Pages desde un repo privado requiere Pro. Plan B sin Pro: un repo público `frances-site` que solo recibe el sitio cifrado. → spec D2
- [ ] **Passphrase del sitio**: elegirla (≥ 24 caracteres; mejor 5 o más palabras al azar) y guardarla en un gestor de contraseñas. Nunca va en git. → spec D2, LIVE-02
- [ ] **Google Cloud + OAuth**: crear el proyecto, habilitar las APIs de Classroom y Drive, publicar la pantalla de consentimiento en **«In production»** (en «Testing» el token caduca a los 7 días) y autorizar con la cuenta UNAL. → SPK-05, LIVE-01

## 2. Decisiones de contenido

- [ ] **Voces adolescentes e infantiles**: elegir la fuente de las referencias para clonar:
  - [ ] Sintéticas (derivadas de una voz Edge con pitch y formantes ajustados), o
  - [ ] Grabaciones con consentimiento escrito (del tutor si es un menor; plantilla en `docs/decisions/consent-template.md`).
  → spec D8, SPK-02
- [ ] **Eloise (`fr-FR-EloiseNeural`)**: escucharla y decidir si sirve como voz infantil gratuita. Catálogos de terceros la listan como «child». → SPK-02
- [ ] **LLM opcional**: intentar desplegar un modelo pequeño en Azure AI Foundry con Azure for Students. Si no se puede, las tarjetas se generan solo por reglas. → spec D5, SPK-06

## 3. Aprobar (o cambiar) las decisiones que tomó el diseñador (spec §4)

| # | Decisión | Aprobada |
|---|---|---|
| D1 | Repo público con código y repo privado `frances-data` con los datos | [ ] |
| D2 | Pages con contenido cifrado (AES-256-GCM, passphrase con PBKDF2 a 600 000 iteraciones) | [ ] |
| D3 | Pipeline en Python con uv; SQLite persistido como volcado `state/state.sql` en git | [ ] |
| D4 | Revisar a diario la `version` de cada archivo de Drive (detecta PDFs reemplazados) | [ ] |
| D5 | LLM opcional y, como respaldo, reglas con spaCy y Azure Translator F0 | [ ] |
| D6 | Audio: Denise y Henri fijas + 1 voz rotativa por tarjeta; las de taladro con todas las voces | [ ] |
| D7 | Clonación semanal en un runner propio en tu PC (CPU), con QA automática (CER ≤ 0.15) | [ ] |
| D8 | Política de consentimiento de voces; nunca datasets con menores identificables | [ ] |
| D9 | App en Vite + React + TypeScript, PWA offline, repaso FSRS, UI en español | [ ] |
| D10 | Clave de Azure Speech dentro del bundle cifrado (F0 no factura; el peor caso es agotar la cuota) | [ ] |
| D11 | Sync diario a las 05:17 de Bogotá; reconciliación los domingos 06:00; clonación los domingos | [ ] |
| D12 | El código se fija por SHA (`FRANCES_CODE_SHA`); branch protection en `main` | [ ] |

## 4. Tareas que ejecutas tú (cada una tiene un checklist con comandos exactos)

| Tarea | Qué | Plan | Hecha |
|---|---|---|---|
| SPK-02 | Escuchar a Eloise y decidir la fuente de las voces infantiles → ADR-002 | `plans/2026-10-14-01-spikes-foundation.md` | [ ] |
| SPK-04 | Correr `~/Escritorio/Azure/azure_pronunciation_test.py` con los audios TTS y guardar los 7 JSON → ADR-004 | ídem | [ ] |
| SPK-05 | Probar OAuth con la cuenta UNAL y revisar si el admin bloquea apps → ADR-005 | ídem | [ ] |
| SPK-06 | Probar un LLM en Azure AI Foundry → ADR-006 | ídem | [ ] |
| LIVE-01 | Proyecto GCP, cliente OAuth, repo privado vacío y `frances auth init` | `plans/2026-10-14-07-ops-golive.md` | [ ] |
| LIVE-02 | Completar `frances-data`: Pages, secretos, salt, Azure Translator F0 y `FRANCES_CODE_SHA` | ídem | [ ] |
| LIVE-04 | Instalar el runner en tu PC, primer lote de clonación y escuchar 20 clips | ídem | [ ] |

Además, el dueño del repo público (`JuanCardenas27`) debe activar Pages con fuente «GitHub Actions» para el demo (OPS-06) y configurar la branch protection de `main` (checks: `python (3.11)`, `python (3.12)`, `web`, `contracts`, `e2e`, `clone-tests`).
