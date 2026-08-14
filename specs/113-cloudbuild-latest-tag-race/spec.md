# Pipeline de Cloud Build duplicado sobrescribe deploys de GitHub Actions
# Path: specs/113-cloudbuild-latest-tag-race/spec.md
issue: #113 · branch: 113-cloudbuild-latest-tag-race · date: 2026-08-14

## What
El deploy pipeline legado de Cloud Build (`cloudbuild.yaml`, trigger `chatai-main-deploy`) sigue
activo en paralelo al pipeline correcto de GitHub Actions (`.github/workflows/deploy.yml`).
Ambos se disparan en cada push a `main`. El de Cloud Build despliega por tag mutable `:latest`
sin hacer `docker push` explícito antes del deploy, así que bajo builds concurrentes puede
desplegar la imagen de OTRO commit — como pasó hoy, sobrescribiendo silenciosamente el deploy
correcto del fix de PR #111 con la imagen sin el fix de PR #110.

## Acceptance
- [x] El deploy a Cloud Run queda determinístico: solo un pipeline despliega, y lo hace pinneado
      a un digest/SHA inmutable — no a `:latest`.
- [x] `cloudbuild.yaml` deja de tener un step de deploy que compite con GitHub Actions.
- [ ] (Infra, fuera del repo) Deshabilitar o eliminar el trigger de Cloud Build
      `chatai-main-deploy` para que no siga corriendo builds redundantes en cada push.
- [ ] (Infra, fuera del repo) Producción re-apuntada a la revisión que sí contiene el fix.

## Context
- `cloudbuild.yaml` (raíz del repo) — pipeline legado: tests → `docker build` (solo local a la
  VM de Cloud Build, sin `docker push` explícito) → `gcloud run deploy --image=...:latest`.
  El push real de la imagen ocurre recién al final, vía el campo top-level `images:`, que Cloud
  Build empuja **después de que todos los steps —incluido el deploy— ya corrieron**. Por lo
  tanto el propio step de deploy de una build nunca despliega lo que esa build construyó: lee
  cualquier cosa que `:latest` tenga en Artifact Registry en ese instante.
- `.github/workflows/deploy.yml` — pipeline correcto, agregado después (commit `12a6ef3`) pero
  sin remover el de Cloud Build. Tagea con `:latest` **y** `${{ github.sha }}`, hace
  `docker push` explícito de ambos, despliega con `--image=...:${{ github.sha }}` (inmutable).
- Trigger de Cloud Build `chatai-main-deploy` (`gcloud builds triggers list`) — dispara
  `cloudbuild.yaml` en cada push a `main`, en paralelo a GitHub Actions. No está definido en el
  repo (se creó vía consola/gcloud), así que no se puede deshabilitar con un commit.

## Decisions
- No se toca `chatai/backend/controllers/tarjas_controller.py` — el fix de PR #111 (footer row
  con `style="width:..."` en cada celda) ya está correctamente mergeado en `main` en el commit
  `c1aa7fe`. El bug reportado como "sigue roto en producción" no es un bug de código: es que
  producción está sirviendo una imagen construida desde un commit ANTERIOR al fix (`2cd8eb4`,
  PR #110), por la condición de carrera entre pipelines.
- Se elige remover el step de deploy de `cloudbuild.yaml` (dejándolo solo con tests + build, útil
  como *smoke build* opcional) en vez de "arreglarlo" (push explícito + deploy por digest),
  porque mantener dos pipelines de deploy — incluso ambos "correctos" — sigue siendo doble
  superficie de mantenimiento y una fuente de confusión futura (¿cuál corrió? ¿cuál ganó?).
  GitHub Actions ya cubre tests + build + push + deploy pinneado por SHA.
- Deshabilitar/eliminar el trigger `chatai-main-deploy` y la mitigación inmediata en producción
  (re-apuntar tráfico a la revisión con el fix, o forzar un nuevo deploy) son acciones de
  infraestructura fuera del repo — se dejan pendientes de aprobación explícita antes de
  ejecutarlas (ver reporte de la sesión).

## Implemented
### CI
- `cloudbuild.yaml` — se elimina el step `cloud-run-deploy` y la sección `images:` (ya no
  publica ni despliega imágenes; queda como pipeline de tests + build de verificación).

## Routes
Sin cambios de API — este es un fix de infraestructura de CI/CD.

## Tests
No aplica pytest — no hay lógica de aplicación modificada. Verificación es de configuración
(ver Manual QA).

## Manual QA
1. `cat cloudbuild.yaml` — confirmar que ya no contiene ningún step `gcloud run deploy` ni la
   clave `images:` a nivel raíz.
2. (Infra) Tras deshabilitar el trigger `chatai-main-deploy`: hacer un push de prueba a `main` y
   confirmar en `gcloud builds list` que solo corre el workflow de GitHub Actions, y en
   `gcloud run revisions list --service=chatai` que la nueva revisión está pinneada por
   `@sha256:...` correspondiente al `github.sha` del commit — no a un tag `:latest`.
3. (Infra) Confirmar que la revisión activa en `gcloud run services describe chatai` sirve un
   PDF de "Hora ponderada estandarizada a 9 horas" legible (sin columnas superpuestas) para
   confirmar que el fix de PR #111 finalmente está en vivo.

## Deferred
- Deshabilitar/eliminar el trigger de Cloud Build `chatai-main-deploy` (acción de infra, no de
  repo) — pendiente de aprobación.
- Mitigación inmediata de producción (re-servir la revisión correcta) — pendiente de aprobación.
- Migrar `apps/sync_cc.yml`-style scheduled jobs a un patrón similar si en el futuro se agregan
  más triggers de Cloud Build — no aplica hoy, fuera de alcance.
