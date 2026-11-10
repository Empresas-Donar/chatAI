# PDF de calidad de cosecha de Isla de Maipo a n8n
# Path: specs/180-cosecha-isla-n8n/spec.md
date: 2026-11-06

## What

El mismo trabajo que `specs/174-cherry-harvest-quality-n8n`, para el
informe Looker «Control de Calidad Cosecha-Cerezas Isla de Maipo».
Cada hora de 08:00 a 16:00 hora de Chile, igual que Zúñiga, baja el PDF, deja solo las
hojas con filas de cosechero y lo envía a su propio flujo de n8n si
el contenido cambió.

## Acceptance criteria

- [x] Perfil `isla` en `automations/harvest_quality/config/reports/isla.yaml`. El comando sin perfil sigue siendo el informe original.
- [x] Informe `https://datastudio.google.com/reporting/90e3af30-e527-41a9-96c8-8b1157dacffb`. Misma sesión `HARVEST_QUALITY_SESSION`. Misma zona `America/Santiago`.
- [x] `proceso` `calidad-cosecha-isla` en `intranet.proceso_estado`. No compara contra la huella del otro predio.
- [x] Misma regla de hoja vacía: «No hay datos» o «No data» sin filas se quita. El título «Cosechero» no salva la hoja.
- [x] `production_url` es `https://gestionempresasdonar.app.n8n.cloud/webhook/a36c5908-03f6-4d86-bf9f-e79b3ba15ccd`, el webhook de producción del flujo `Demvw9lpEtE5Vvn1`. El campo del archivo es `data` y `forzar=1` solo fuera de 08:00–16:00 o en `now`.
- [x] Cloud Run Job `harvest-quality-isla` con la misma imagen y el comando `python -m harvest_quality run isla`. El deploy crea un job `harvest-quality-<campo>` por cada archivo de `config/reports/` que tenga webhook.
- [x] Cloud Scheduler `harvest-quality-isla-hourly`, `0 8-16 * * *`, `America/Santiago`, cuenta Donar. El mismo horario que Zúñiga. Esas horas no mandan `forzar`. GitHub no lo crea.

## Context

- El informe tiene Resumen y cuadrillas 1 a 16, igual que el otro. El 2026-11-06 el resumen decía «No hay datos».
- `https://gestionempresasdonar.app.n8n.cloud/workflow/Demvw9lpEtE5Vvn1` abre el editor y pide clave. No acepta el PDF.
- No es tarjas. No se aplica 1,45 ni 1,50.

## Tests

- `tests/test_decision.py` cubre que `isla` es otro proceso y otro informe, y que una URL de editor no se acepta como webhook.
