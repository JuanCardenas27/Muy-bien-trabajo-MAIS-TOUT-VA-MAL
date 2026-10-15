# AGENTS.md — protocolo para agentes que construyen Frances Classroom

Lee en este orden: este archivo → `docs/superpowers/specs/2026-10-14-frances-classroom-design.md` → `docs/superpowers/plans/2026-10-14-00-master-plan.md` (contratos y Global Constraints) → el plan del subsistema de tu tarea.

## Tomar una tarea

1. Elige una tarea de `docs/superpowers/plans/tasks.yaml` con `human: false` cuyas `deps` estén todas fusionadas en `main` y que nadie tenga reclamada (no hay issue con la etiqueta `claimed` ni PR abierto con su ID).
2. Reclámala: asígnate su issue `[<ID>] <título>` y ponle la etiqueta `claimed`. El issue lo crea `scripts/sync_issues.py`.
3. Trabaja en un worktree propio: `git worktree add ../wt-<ID> -b task/<ID>-<slug> origin/main`.
4. Un PR por tarea, con título `[<ID>] <título>`. Antes de pedir revisión puede ser draft.
5. Si en 48 h no hay commits, el reclamo caduca y otro agente puede tomar la tarea.

## Reglas duras

- TDD: primero el test, verlo fallar, implementar, verlo pasar. Sigue los pasos del plan en orden.
- Solo tocas las rutas `owns` de tu tarea. Lees lo demás, no lo modificas.
- Los contratos (`src/frances/models/`, DDL en `src/frances/db/migrations/`, interfaces del plan maestro) no se cambian dentro de una tarea normal. Si uno no te alcanza: abre un issue `[CHG-<n>] <cambio>` con la propuesta y la lista de consumidores afectados, y detente. Un humano o el conductor lo aprueba; la tarea CHG actualiza contrato y consumidores en un solo PR.
- Nunca hay datos reales del Classroom en este repo, ni en tests, ni en fixtures, ni en logs. Todo fixture sale de `tests/fixtures/make_fixtures.py`.
- Nunca se commitea un secreto. Las variables de entorno sensibles están listadas en el plan maestro; se leen solo en `frances.config`.
- Sin red en los tests (`--disable-socket`). Lo que necesita red o modelos pesados va marcado `@pytest.mark.heavy`.
- Las dependencias van con versión exacta (`uv add pkg==X.Y.Z`; `npm install --save-exact`). Antes de agregar una, revisa la regla de licencias de Global Constraints.
- No se desactivan hooks, lint ni checks de tipos para que algo pase.

## Revisión

Cada PR lo revisa un agente fresco, que no implementó la tarea, con esta lista:

1. ¿El PR implementa exactamente los pasos de la tarea y nada fuera de `owns`?
2. ¿Los nombres y tipos coinciden con el bloque **Interfaces** del plan y con el plan maestro?
3. ¿Se cumplen las Global Constraints?
4. Si la tarea tiene un ítem de Review Focus, ¿existe su test y prueba lo que dice?
5. ¿La Definition of Done está completa?

Veredicto: `APPROVE` o `REQUEST_CHANGES` con una lista numerada. Después de dos rechazos seguidos, la tarea vuelve a la cola con las notas del revisor. Solo un humano fusiona a `main`.

## Comandos

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
npm --prefix web ci
npm --prefix web run lint && npm --prefix web run typecheck && npm --prefix web test
uv run frances schema export contracts/ && npm --prefix web run gen:types   # después de tocar modelos (solo tareas CHG/FND-02)
uv run python scripts/tasks_check.py --waves                                 # validar el grafo y ver las tareas listas
```

## Tareas humanas

Las tareas con `human: true` (SPK-02, SPK-04, SPK-05, SPK-06, LIVE-01, LIVE-02) las ejecuta el dueño del proyecto. Un agente puede preparar el material (guías, scripts, plantillas), pero no inventa sus resultados. Cada una deja un ADR o un checklist firmado en `docs/decisions/`.
