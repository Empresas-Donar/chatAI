# Calidad de cosecha — PDF a n8n

Este trabajo no es parte de ChatAI. Vive solo en `automations/harvest_quality/`.

## Qué hace

Cada hora, de 08:00 a 16:00 hora de Chile, todos los días, abre el informe Looker «Control de Calidad Cosecha-Cerezas», deja solo las hojas con datos y llama a n8n si el contenido cambió respecto del último envío. Si no hay datos, no llama. Si los números son los mismos que el último envío —aunque sea de otro día—, no llama.

## Frontera

- No importa `chatai`, `core` ni `tarjas_empresa`. Este informe no usa 1,45 ni 1,50.
- No abre BigQuery.
- Postgres solo para `intranet.proceso_estado`. No toca tablas de AppSheet ni de la app.
- Dependencias solo en `requirements.txt` de esta carpeta. No van a `chatai/requirements.txt`.
- No se copia en `chatai/Dockerfile`. `deploy.yml` ignora `automations/**` para no redesplegar Cloud Run.
- La sesión de Google es el secreto `HARVEST_QUALITY_SESSION` (JSON de Playwright). No va al git. Se renueva a mano cuando el login vence.
- El control de fecha del informe tiene que ser hoy en Santiago. El job no elige otra fecha. El contenedor y Chromium usan `America/Santiago`, porque «Hoy» en Looker sigue el reloj del navegador. En UTC, después de las 21:00 de Chile ya es el día siguiente.

## Comandos

Desde esta carpeta:

```bash
python -m harvest_quality session
python -m harvest_quality run
python -m harvest_quality now
python -m harvest_quality run isla
python -m harvest_quality now isla
```

- `session` abre Chrome normal (no incógnito) en el login de Google y guarda `.session/state.json`. Ese archivo es el secreto `HARVEST_QUALITY_SESSION`. No se commitea. El informe se ve sin cuenta; la descarga no.
- `run` es el cron. URL de producción. De 08:00 a 16:00 no manda `forzar`, porque esa franja entra en la ventana de n8n (hasta las 16:59). Si la hora de Chile no está entre 08:00 y 16:00 (con 25 minutos de gracia), termina sin descargar y sin fila.
- `now` es la prueba en producción. Ignora el reloj, usa la URL de producción y manda `forzar=1`. Envía aunque la huella ya se haya mandado. Si no hay hojas con datos, no hay POST. Si n8n acepta, esa huella queda como último envío y la hora siguiente no la repite.

## Trazabilidad

Tabla `intranet.proceso_estado` (`sql/intranet/03_proceso_estado.sql`). Cada revisión inserta una fila. No se actualiza la anterior.

| Columna | Rol |
|---|---|
| `id` | TEXT, un id por revisión |
| `proceso` | `calidad-cosecha` en el informe original. `calidad-cosecha-isla` en Isla de Maipo. Cada uno compara solo contra su último envío |
| `huella` | hash del texto de las hojas que quedan. Vacío si no hay datos |
| `enviado` | si el POST salió |
| `motivo` | `sin_datos`, `sin_cambios` o `enviado` |
| `revisado_en` | cuándo corrió esa hora |
| `enviado_en` | cuándo n8n aceptó el archivo. Solo si `enviado` |

La comparación usa la última fila de ese proceso con `enviado` verdadero. La huella ignora la línea «última actualización» de Looker, porque el PDF cambia de bytes aunque los números no.

## Horario

El horario es el Cloud Scheduler `harvest-quality-hourly` en `southamerica-east1`, proyecto `integraciones-484915`, creado con la configuración gcloud `donar` (`gestion@empresasdonar.cl`). Corre `0 8-16 * * *` en `America/Santiago` y llama al Cloud Run Job `harvest-quality` en `southamerica-west1`. No es el servicio `chatai`. GitHub solo despliega la imagen; no crea ni actualiza ese horario. `schedule.py` deja pasar solo las 08:00–16:00. Esas horas no mandan `forzar`. **Run workflow** sigue sirviendo para `now`.

## Otro campo

Un predio nuevo es un archivo `config/reports/<campo>.yaml`: su URL de Looker, su `proceso`, su webhook y su `pdf_name`. El comando es `python -m harvest_quality run <campo>`. El deploy crea el Cloud Run Job `harvest-quality-<campo>` cuando ese yaml tiene un webhook. La huella queda en `intranet.proceso_estado` bajo ese `proceso`, así que no se mezcla con otro campo.

El horario de cada campo es un Cloud Scheduler propio en la cuenta Donar, el mismo cron `0 8-16 * * *`. GitHub no lo crea. El informe original sigue siendo `harvest-quality` sin perfil.

## Isla de Maipo

El mismo proceso, otro informe: «Control de Calidad Cosecha-Cerezas Isla de Maipo». Perfil `isla` (`config/reports/isla.yaml`). Misma sesión de Google, mismo reloj y la misma regla de hojas vacías. La huella no se mezcla con el informe original.

El POST va a `https://gestionempresasdonar.app.n8n.cloud/webhook/a36c5908-03f6-4d86-bf9f-e79b3ba15ccd`. El enlace `/workflow/Demvw9lpEtE5Vvn1` es solo el editor. El deploy crea el Cloud Run Job `harvest-quality-isla` con el comando `python -m harvest_quality run isla`. El horario es otro Cloud Scheduler en la cuenta Donar. GitHub no lo crea.

## Hoja vacía

Se quita la hoja que dice «No hay datos» o «No data» y no tiene filas de cosechero. El título de la columna no cuenta. Si hay filas y además un recuadro vacío, la hoja se queda. Si no queda ninguna, motivo `sin_datos` y no hay POST.

## Si falla

Si Looker no entrega el PDF, lo intenta de nuevo hasta 5 veces. Sin sesión no reintenta. Si n8n no acepta el archivo, el proceso termina con error y no escribe `enviado`. No inventa un envío.
