# Producción de Frances Classroom

Esta carpeta es la **configuración de despliegue** del repo de producción. El
código y esta configuración viven en git; los datos del Classroom, el estado y
los audios viven en un bucket **R2 privado** (`frances-data`). Nada del curso
entra al repo ni a los logs, que son públicos (D1).

## Cómo funciona (D1, R-30)

- El repo de producción es **público y del dueño de la cuenta**: en un repo de
  cuenta personal solo el dueño puede gestionar secretos (R-30). Los workflows
  de producción solo corren ahí, porque el job lleva
  `if: vars.FRANCES_PROD == 'true'`.
- Los secretos viven **solo** en el environment `production`, limitado a la
  rama `main`. Ningún workflow de producción se dispara con `push` ni con un
  PR: solo con `schedule` o `workflow_dispatch`. Tampoco se usan
  `pull_request_target` ni runners self-hosted (R-30, D12).
- `daily.yml` corre todos los días: toma un lease de escritor único en R2,
  baja el estado, restaura SQLite, corre `frances run-daily`, vuelca el estado,
  decide si hace falta publicar (huella R-25), cifra y publica el bundle, sube
  lo nuevo y libera el lease. `reconcile.yml` corre los domingos para detectar
  borrados en el Classroom.
- La huella del último deploy se guarda en `data/state/last_deploy_sha`
  (R-25): el daily publica solo si cambió la huella, si el resumen marca
  cambios o si se lanzó a mano con `force_deploy = true`.
- Si falla la autenticación de Google (exit 3) no se publica nada: el sitio
  anterior sigue sirviendo y los steps de bundle/deploy se saltan. Un exit 2
  (parcial) deja el job en verde con un aviso y se reintenta al día siguiente.
- El Worker de Cloudflare solo expone `site/bundle.json` y `site/d/*.bin`; el
  bucket no tiene acceso público ni `r2.dev` (R-30). La app descifra el bundle
  en el navegador con la passphrase.
- GitHub apaga los cron de un repo público tras 60 días sin actividad (D11).
  El step `Keepalive` de `daily.yml` los reactiva por API en cada corrida.

## Archivos

| Archivo | Qué es |
|---|---|
| `frances.toml` | Configuración (`Settings`): cursos, tarjetas, audio, traductor y bundle. Sin secretos. |
| `voices.yaml` | Ajustes sobre las 17 voces por defecto (13 builtin + 4 sintéticas). `voices: []` = sin cambios. |
| `README.md` | Este documento. |

`frances.toml` y `voices.yaml` se copian al directorio de datos antes de cada
corrida (`cp deploy/frances.toml deploy/voices.yaml data/`).

`salt` de `[bundle]` es **obligatorio** y lo genera LIVE-02
(`secrets.token_bytes(16)` en b64url). No es un secreto —también viaja en
`bundle.json`— pero sin él `frances bundle` falla. Cambiarlo invalida las
passphrases anteriores.

## Secretos del environment `production`

Todos se cargan en **Settings → Environments → production → Add secret**. La
tabla no repite valores: los secretos nunca se escriben en el repo.

| Secreto | Obligatorio | De dónde sale |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Sí | Cliente OAuth de Google Cloud (tipo Web application) del proyecto de LIVE-01. |
| `GOOGLE_CLIENT_SECRET` | Sí | Se genera junto al cliente OAuth (LIVE-01). |
| `GOOGLE_REFRESH_TOKEN` | Sí | OAuth Playground con ese mismo cliente; se pega a mano (R-23, LIVE-01). |
| `AZURE_SPEECH_KEY` | Sí | Recurso Azure Speech F0 del proyecto de SPK-04. |
| `AZURE_SPEECH_REGION` | Sí | Región de ese recurso Speech (por ejemplo `eastus`). |
| `AZURE_TRANSLATOR_KEY` | Sí | Recurso Azure Translator F0 `frances-translator` (LIVE-02). |
| `AZURE_TRANSLATOR_REGION` | Sí | Región del traductor (`global` en el plan F0). |
| `FRANCES_PASSPHRASE` | Sí | La eliges tú: 24+ caracteres y 5+ palabras aleatorias, guardada en el gestor de contraseñas. Abre el bundle en la app. |
| `R2_ACCOUNT_ID` | Sí | Dashboard de R2 → Account ID (LIVE-02). |
| `R2_ACCESS_KEY_ID` | Sí | Token de R2 con Object Read & Write limitado a `frances-data` (LIVE-02). |
| `R2_SECRET_ACCESS_KEY` | Sí | Se muestra una sola vez al crear el token de R2 (LIVE-02). |
| `R2_BUCKET` | Sí | `frances-data` (LIVE-02). |
| `CLOUDFLARE_API_TOKEN` | Sí | Token «Edit Cloudflare Workers» para que `worker-deploy.yml` despliegue el Worker (LIVE-02). |
| `CLOUDFLARE_ACCOUNT_ID` | Sí | Dashboard de Cloudflare → Account ID (LIVE-02). |
| `LLM_BASE_URL` | No | Endpoint compatible con OpenAI (SPK-06, ADR-006). Sin él se usa el generador determinista. |
| `LLM_API_KEY` | No | Clave del proveedor LLM elegido. |
| `LLM_MODEL` | No | Id del modelo del proveedor LLM. |

`GITHUB_TOKEN` lo inyecta Actions automáticamente (lo usan `report-failure` y
`Keepalive`); no se guarda como secreto. Los tres `LLM_*` son opcionales: si
faltan, las tarjetas se generan con el respaldo determinista o con `llm = off`.

## Variables del repositorio

Se cargan en **Settings → Secrets and variables → Actions → Variables** (no son
secretas):

| Variable | Valor | Para qué |
|---|---|---|
| `FRANCES_PROD` | `true` | Habilita los jobs de producción. En el repo de desarrollo no existe o es `false`, y los workflows no corren. |
| `FRANCES_PAGES_ORIGIN` | `https://<usuario>.github.io` | Origen permitido por el Worker (`worker-deploy.yml`). |
| `FRANCES_DATA_URL` | `https://frances-data.<subdominio>.workers.dev/` | URL del Worker que lee la app; debe terminar en `/` (OPS-06). |

## Horarios (hora de Bogotá, UTC−5)

| Workflow | Cron (UTC) | Hora de Bogotá | Qué hace |
|---|---|---|---|
| `daily` | `17 10 * * *` | Todos los días 05:17 | Pipeline diario, bundle y publicación. |
| `reconcile` | `0 11 * * 0` | Domingos 06:00 | Reconciliación completa para detectar borrados. |

Los dos comparten `concurrency: frances-prod` sin cancelación: si uno está
corriendo, el otro espera. El daily pide el lease de escritor único con
`--ttl 7200 --wait 1800`; el reconcile, `--ttl 3600 --wait 1800`.

## Cómo actualizar el código

1. Revisa y fusiona el cambio en el repo de desarrollo; `main` debe estar en
   verde (`python`, `web`, `contracts`, `e2e`, `worker`).
2. Sincroniza el repo de producción con `main` (merge o «Sync fork»), sin
   tocar los secretos ni las variables.
3. Opcional: Actions → `daily` → **Run workflow** con `force_deploy = true`
   para publicar aunque la huella no haya cambiado.
4. Los datos no se migran a mano: el daily baja el estado de R2, corre
   `frances restore` y al final `frances r2 push`. Un cambio incompatible del
   formato de datos va en una tarea CHG, no en un push manual.

## Puesta en marcha

Los pasos humanos (bucket, tokens, secretos y variables) están en **LIVE-02**:
[`docs/superpowers/plans/2026-10-14-07-ops-golive.md`](../docs/superpowers/plans/2026-10-14-07-ops-golive.md#task-live-02-bucket-r2-worker-secretos-del-environment-y-variables).
Después de LIVE-02, la primera corrida se lanza a mano con `force_deploy =
true` (LIVE-03).
