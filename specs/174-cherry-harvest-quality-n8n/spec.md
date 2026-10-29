# PDF de calidad de cosecha de cerezas a n8n
# Path: specs/174-cherry-harvest-quality-n8n/spec.md
date: 2026-10-29

## What

Trabajo autónomo que, cada hora de 08:00 a 20:00 hora de Chile, todos
los días, baja el PDF de Looker «Control de Calidad Cosecha-Cerezas»,
deja solo las hojas con datos y lo envía a n8n solo si el contenido es
distinto del último envío.

Looker no se usa por correo: ese envío sale una sola vez al día. Las
URLs cortas no devuelven el PDF. El archivo sale de Descargar informe,
dentro de una sesión de Google.

## Acceptance criteria

- [x] Carpeta aparte `automations/harvest_quality/`, en inglés, fuera de ChatAI.
- [x] `CLAUDE.md` y `AGENTS.md` en esa carpeta, en español, con la misma frontera.
- [x] `config/n8n.yaml` (`production_url`, `test_url`, `file_field` data, `force_field` forzar, `force_value` 1) y `config/job.yaml` (timezone `America/Santiago`, hours 8 a 20, `proceso` `calidad-cosecha`, `report_url` del informe, `empty_marker` "No hay datos").
- [x] Comando `run`: cron, URL de producción. Sin `forzar` de 08:00 a 16:00. Con `forzar=1` de 17:00 a 20:00. Si la hora de Chile no está entre 08:00 y 20:00, termina sin fila.
- [x] Comando `now`: prueba en producción, URL de producción, con `forzar=1`, sin mirar el reloj. Envía aunque la huella ya se haya mandado. También vía `workflow_dispatch`.
- [x] El cron de GitHub es `0 0,11-23 * * *` UTC. `schedule.py` deja pasar solo 08:00–20:00 en `America/Santiago`.
- [x] Abre `https://datastudio.google.com/s/imKk2KuwenU` con sesión de Google guardada (secreto, no va al git). Fecha = hoy en Santiago. Descarga el PDF de todas las páginas.
- [x] Quita hojas cuyo texto contiene "No hay datos". Si no queda ninguna, no hay POST y la fila queda `sin_datos`.
- [x] La huella es el hash del texto de las hojas que quedan, sin la línea de última actualización. Si coincide con el último `enviado`, la fila queda `sin_cambios` y no hay POST.
- [x] Cada revisión inserta una fila en `intranet.proceso_estado` (`id`, `proceso`, `huella`, `enviado`, `motivo`, `revisado_en`, `enviado_en`). No se pisa el historial.
- [x] POST multipart, archivo en el campo `data`. `now` agrega `forzar=1`.
- [x] Si la sesión no entra o n8n rechaza el archivo, termina sin marcar `enviado`.
- [x] No importa `chatai`, `core` ni `tarjas_empresa`. Postgres solo para `intranet.proceso_estado`. No abre BigQuery. Dependencias solo en `automations/harvest_quality/requirements.txt`. No se copia en `chatai/Dockerfile`.
- [x] `.github/workflows/deploy.yml` ignora `automations/**`.
- [x] `harvest_quality.yml` corre solo en `schedule` (comando `run`) y `workflow_dispatch` (comando `now`). El cron no dispara `now`.

## Context

- La carpeta `automations/harvest_quality/` puede crecer sin tocar la app FastAPI.
- La imagen de Cloud Run solo copia `chatai/`, `core/` y `mcp_server/bigquery_client.py` (`chatai/Dockerfile`). Este trabajo queda fuera de esa imagen.
- `.github/workflows/deploy.yml` ignora `automations/**`. Un cambio solo de esta carpeta no redespliega Cloud Run. Si el mismo commit toca `sql/` o la app, el deploy sigue corriendo.
- n8n recibe POST y responde de inmediato. No hay autenticación. El archivo va en el campo `data`. El campo opcional `forzar=1` salta la ventana 08:00–16:59 hora de Chile que n8n aplica por su cuenta. Path de producción: `calidad-cosecha-7f3a9c2e41b8`. Path de prueba: `webhook-test`.
  - producción: `https://gestionempresasdonar.app.n8n.cloud/webhook/calidad-cosecha-7f3a9c2e41b8`
  - prueba: `https://gestionempresasdonar.app.n8n.cloud/webhook-test/calidad-cosecha-7f3a9c2e41b8`
- Las corridas con horario no envían `forzar` y usan la URL de producción. `now` también usa la URL de producción y envía `forzar=1`, aunque la huella ya se haya mandado. La URL de prueba queda en `config/n8n.yaml` y no la usa ningún comando.
- El secreto de la sesión de Google se llama `HARVEST_QUALITY_SESSION`. No se commitea. Se renueva a mano cuando vence.
- Regla de hoja vacía verificada el 2026-10-29: las páginas que dicen «No hay datos» están vacías. Ese día las útiles fueron Resumen y las cuadrillas 1, 2, 5, 6, 7, 8, 9 y 10. La regla es el marcador, no esa lista fija.
- Este informe no es tarjas. No se aplica 1,45 ni 1,50.
- El cron `0 0,11-23 * * *` UTC cubre los dos desfases de `America/Santiago`. `schedule.py` deja pasar solo las 08:00–20:00 en Santiago, con 25 minutos de gracia por si el runner parte tarde. La hora que no coincide termina sin descarga y sin fila. Desde las 17:00 el POST lleva `forzar=1`.
- La tabla es `intranet.proceso_estado` (`sql/intranet/03_proceso_estado.sql`). Sirve a más de un proceso. Este job usa `proceso = calidad-cosecha`. Cada hora inserta. La comparación es la última fila de ese proceso con `enviado` verdadero. Un martes a las 08:00 con la misma huella del lunes a las 16:00 no envía. Un domingo sin monitoreos inserta `sin_datos` y no envía.
- Postgres de este job es solo esa tabla. El secreto es `DATABASE_URL`, el mismo del cron de centros de costo.

## Decisions

- Horario final: 08:00 a 20:00 inclusive, todos los días. Desde las 17:00 se manda `forzar=1`.
- Estado en Postgres, no en un txt del runner ni en un commit por hora.
- La huella ignora la línea de última actualización de Looker.

## Implemented

- `sql/intranet/03_proceso_estado.sql`
- `automations/harvest_quality/` (comandos `run` y `now`, config, filtro de hojas, huella, traza)
- `.github/workflows/harvest_quality.yml`
- `paths-ignore` de `automations/**` en `.github/workflows/deploy.yml`

## Routes

## Tests

- `automations/harvest_quality/tests/test_decision.py` cubre la decisión, la huella, el reloj y el descarte de la hoja que dice «No hay datos». No toca la base ni n8n.

## Manual QA

- `intranet.proceso_estado` ya está creada en la base.
- Falta el secreto `HARVEST_QUALITY_SESSION` en GitHub. Sin esa sesión el cron no puede bajar el PDF.
