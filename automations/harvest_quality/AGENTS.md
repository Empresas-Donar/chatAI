# Calidad de cosecha — PDF a n8n

Este trabajo no es parte de ChatAI. Vive solo en `automations/harvest_quality/`.

## Qué hace

Cada hora, de 08:00 a 21:00 hora de Chile, todos los días, abre el informe Looker «Control de Calidad Cosecha-Cerezas», deja solo las hojas con datos y llama a n8n si el contenido cambió respecto del último envío. Si no hay datos, no llama. Si los números son los mismos que el último envío —aunque sea de otro día—, no llama.

## Frontera

- No importa `chatai`, `core` ni `tarjas_empresa`. Este informe no usa 1,45 ni 1,50.
- No abre BigQuery.
- Postgres solo para `intranet.proceso_estado`. No toca tablas de AppSheet ni de la app.
- Dependencias solo en `requirements.txt` de esta carpeta. No van a `chatai/requirements.txt`.
- No se copia en `chatai/Dockerfile`. `deploy.yml` ignora `automations/**` para no redesplegar Cloud Run.
- La sesión de Google es el secreto `HARVEST_QUALITY_SESSION` (JSON de Playwright). No va al git. Se renueva a mano cuando el login vence.
- El control de fecha del informe tiene que ser hoy en Santiago. El job no elige otra fecha.

## Comandos

Desde esta carpeta:

```bash
python -m harvest_quality session
python -m harvest_quality run
python -m harvest_quality now
```

- `session` abre Chrome normal (no incógnito) en el login de Google y guarda `.session/state.json`. Ese archivo es el secreto `HARVEST_QUALITY_SESSION`. No se commitea. El informe se ve sin cuenta; la descarga no.
- `run` es el cron. URL de producción. De 08:00 a 16:00 no manda `forzar`. De 17:00 a 21:00 sí, porque n8n solo acepta hasta las 16:59. Si la hora de Chile no está entre 08:00 y 21:00 (con 25 minutos de gracia), termina sin descargar y sin fila.
- `now` es la prueba en producción. Ignora el reloj, usa la URL de producción y manda `forzar=1`. Envía aunque la huella ya se haya mandado. Si no hay hojas con datos, no hay POST. Si n8n acepta, esa huella queda como último envío y la hora siguiente no la repite.

## Trazabilidad

Tabla `intranet.proceso_estado` (`sql/intranet/03_proceso_estado.sql`). Cada revisión inserta una fila. No se actualiza la anterior.

| Columna | Rol |
|---|---|
| `id` | TEXT, un id por revisión |
| `proceso` | `calidad-cosecha` |
| `huella` | hash del texto de las hojas que quedan. Vacío si no hay datos |
| `enviado` | si el POST salió |
| `motivo` | `sin_datos`, `sin_cambios` o `enviado` |
| `revisado_en` | cuándo corrió esa hora |
| `enviado_en` | cuándo n8n aceptó el archivo. Solo si `enviado` |

La comparación usa la última fila de ese proceso con `enviado` verdadero. La huella ignora la línea «última actualización» de Looker, porque el PDF cambia de bytes aunque los números no.

## Horario

El Cloud Run Job `harvest-quality` está en `southamerica-west1` y no es el servicio `chatai`. La cuenta de GitHub no puede crear Cloud Scheduler, así que el horario lo dispara el workflow **Execute harvest quality job** (`0 0,1,11-23 * * *` UTC). `schedule.py` deja pasar solo las 08:00–21:00 de Chile. Desde las 17:00 manda `forzar=1`. **Harvest quality PDF** → **Run workflow** sigue siendo la prueba `now`.

## Hoja vacía

Se quita la página cuyo texto contiene «No hay datos». Si no queda ninguna, motivo `sin_datos` y no hay POST. La regla es ese texto, no una lista fija de cuadrillas.

## Si falla

Sin sesión, sin PDF o si n8n no acepta el archivo, el proceso termina con error y no escribe `enviado`. No inventa un envío.
