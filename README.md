# Migrador AppSheet → PostgreSQL

Herramienta interna para migrar aplicaciones AppSheet a una base de datos PostgreSQL.

El flujo es: exportar CSVs desde AppSheet → subirlos a la herramienta web → validar estructura y datos → sincronizar con PostgreSQL → reconectar AppSheet a la nueva base de datos.

---

## Cómo funciona

```
AppSheet (con backend en Google Sheets)
        │
        │  Exportar CSVs
        ▼
Herramienta Web  (https://appsheet-migrator-nx63mrnslq-tl.a.run.app)
        │
        │  1. Subir CSVs e ingresar nombre de la app
        │  2. Detección automática de tipos de columna
        │  3. Vista previa y validación
        │  4. Prueba en seco (opcional)
        │  5. Confirmar y sincronizar
        ▼
PostgreSQL  →  esquema: appsheet
               tablas: appsheet.<nombre_app>_<tabla>
        │
        │  Conectar AppSheet → PostgreSQL
        │  Ejecutar "Regenerar estructura"
        ▼
AppSheet ahora lee desde PostgreSQL
```

---

## Apps registradas

| App | Estado | Notas |
|---|---|---|
| `contratistas_isla_maipo` | Migrada | Migración completa con scripts por tabla en `apps/` |
| `tarjas` | Migrada | Migrada con la herramienta web como primera prueba en producción |
| `medicion_pozos` | Pendiente | — |

Convención de nombres: `appsheet.<nombre_app>_<nombre_tabla>`

### tarjas

Primera migración real en producción, realizada con la herramienta web. Las tablas viven bajo el prefijo `appsheet.tarjas_*` en la base de datos `donar_prod`.

Se creó una vista de reporte en [sql/tarjas/01_views_reporte.sql](sql/tarjas/01_views_reporte.sql):

```
appsheet.tarjas_reporte
```

Consolida los pagos semanales de `appsheet.tarjas_pagos` agrupados por contratista, campo, fecha y tipo de pago (`trato` vs `al día`). Reemplaza los reportes dinámicos que AppSheet generaba desde Google Sheets.

---

## Acceso a la herramienta

La herramienta está desplegada en Google Cloud y se accede desde cualquier browser:

**URL:** `https://appsheet-migrator-nx63mrnslq-tl.a.run.app`

Al abrir la URL el browser muestra un popup de login. Ingresar las credenciales y listo — no se requiere instalar nada ni correr comandos.

| Campo | Valor |
|---|---|
| Usuario | `gestion` |
| Contraseña | _(guardada en Cloud Run como `AUTH_PASSWORD` — consultar al administrador del proyecto)_ |

---

## Migrar una nueva app

### Paso 1 — Exportar CSVs desde AppSheet

Exportar cada tabla como CSV. Mantener los nombres de archivo originales — el nombre del archivo se convierte en el nombre de la tabla.

> Antes de correr cualquier migración, tomar capturas de pantalla de la definición de columnas de cada tabla en AppSheet. Los nombres de columna en AppSheet son la fuente de verdad.

### Paso 2 — Subir y validar

1. Abrir [https://appsheet-migrator-nx63mrnslq-tl.a.run.app](https://appsheet-migrator-nx63mrnslq-tl.a.run.app)
2. Ingresar el **nombre de la app** (ej. `medicion_pozos`) — se usa como prefijo de las tablas
3. Seleccionar todos los CSVs de la app
4. Hacer clic en **Subir y Analizar**

La herramienta va a:
- Detectar el tipo PostgreSQL de cada columna automáticamente
- Marcar columnas con muchos valores vacíos, IDs duplicados o tipos mezclados
- Mostrar una vista previa de las primeras 20 filas por tabla

### Paso 3 — Prueba en seco

Hacer clic en **Prueba en seco** para validar todo el proceso sin escribir nada en la base de datos. Confirma que los CSVs son legibles y que el conteo de filas es correcto.

### Paso 4 — Sincronizar

Hacer clic en **Confirmar y Sincronizar**. La herramienta va a:
- Crear el esquema `appsheet` si no existe
- Crear cada tabla con los tipos detectados (`CREATE TABLE IF NOT EXISTS`)
- Insertar filas con `ON CONFLICT DO NOTHING` — seguro para volver a correr
- Mostrar los logs en tiempo real en el browser
- En caso de error, revertir solo la tabla afectada — las demás no se ven afectadas

### Paso 5 — Conectar AppSheet a PostgreSQL

1. En AppSheet ir a **Datos → Agregar fuente de datos → Base de datos en la nube**
2. Ingresar los datos de conexión PostgreSQL
3. Hacer clic en **Regenerar estructura** para que AppSheet relea los tipos de columna
4. Probar todas las vistas y acciones en modo **Vista previa** antes de publicar

---

## Reglas de nombres de columna

AppSheet distingue mayúsculas y minúsculas. Los nombres de columna deben coincidir exactamente con el origen — sin excepciones.

| Regla | Ejemplo |
|---|---|
| No renombrar columnas | `Id_Supervisor` se queda como `Id_Supervisor` |
| Preservar tildes | `Bonificación` se queda como `Bonificación` |
| Preservar prefijo `%` | `%Jornada_Bono` se queda como `%Jornada_Bono` |
| Preservar espacios | `Centro de Costo` se queda como `Centro de Costo` |
| Siempre con comillas dobles en SQL | `"Bonificación"`, `"%Jornada_Bono"` |

**Columnas que nunca se migran:**

| Columna | Motivo |
|---|---|
| `_RowNumber` | Columna virtual de Google Sheets — no existe en PostgreSQL |
| `Related_*` | AppSheet genera estas columnas de referencia inversa automáticamente |

---

## Detección de tipos

| Condición | Tipo PostgreSQL |
|---|---|
| Más del 30% de valores vacíos | `TEXT` |
| Todo `true/false/yes/no/si/sí/1/0` | `BOOLEAN` |
| Todo con formato `YYYY-MM-DD` | `DATE` |
| Todo con formato `YYYY-MM-DD HH:MM...` | `TIMESTAMP` |
| Solo números enteros | `INTEGER` |
| Números con decimales | `NUMERIC(12,2)` |
| Mezclado o no reconocido | `TEXT` |

Las claves primarias siempre son `TEXT NOT NULL PRIMARY KEY` — AppSheet genera sus propios IDs en formato texto.

---

## Infraestructura (Google Cloud)

| Recurso | Detalle |
|---|---|
| **Cloud Run** | `appsheet-migrator`, región `southamerica-west1` |
| **Cloud SQL** | `db-donar` (PostgreSQL 16), base de datos `donar_prod` |
| **Artifact Registry** | `integraciones`, imagen `appsheet-migrator:latest` |
| **Proyecto** | `integraciones-484915` |

El servicio escala a cero cuando no está en uso — sin costo cuando está inactivo.

### Actualizar el servidor tras cambios en el código

```bash
cd web_migrator/

# 1. Reconstruir y subir la imagen
gcloud builds submit \
  --tag southamerica-west1-docker.pkg.dev/integraciones-484915/integraciones/appsheet-migrator:latest \
  --project=integraciones-484915

# 2. Desplegar la nueva revisión
gcloud run deploy appsheet-migrator \
  --image=southamerica-west1-docker.pkg.dev/integraciones-484915/integraciones/appsheet-migrator:latest \
  --region=southamerica-west1 \
  --project=integraciones-484915
```

### Variables de entorno

Se configuran en Cloud Run desde la consola de Google Cloud o con `--set-env-vars`.

| Variable | Descripción |
|---|---|
| `DB_HOST` | Ruta del socket de Cloud SQL (`/cloudsql/...`) |
| `DB_PORT` | `5432` |
| `DB_NAME` | `donar_prod` |
| `DB_USER` | Usuario de la base de datos |
| `DB_PASSWORD` | Contraseña de la base de datos |
| `AUTH_USER` | Usuario para el login de la herramienta |
| `AUTH_PASSWORD` | Contraseña para el login de la herramienta |

---

## Desarrollo local

### 1. Instalar dependencias

```bash
cd web_migrator/
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar credenciales

```bash
cp web_migrator/.env.example web_migrator/.env
# Editar .env con los valores reales — nunca subir este archivo al repositorio
```

### 3. Iniciar el servidor

```bash
cd web_migrator/
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Abrir [http://localhost:8000](http://localhost:8000).

Para detener: `Ctrl+C`. Si el puerto está ocupado: `lsof -ti :8000 | xargs kill -9`

---

## Seguridad

- **Nunca subir `.env`** al repositorio — contiene credenciales de la base de datos. Está en `.gitignore`.
- Usar `.env.example` como plantilla segura para compartir con el equipo.
- La URL de producción está protegida con usuario y contraseña — las credenciales se guardan como variables de entorno en Cloud Run, nunca en el código.
- La base de datos se conecta por socket interno de Cloud SQL (sin exponer IP pública).
- Los CSVs subidos se guardan temporalmente en `uploads/` y se eliminan automáticamente después de una sincronización exitosa.

---

## Estructura del proyecto

```
Appsheet_migration/
├── web_migrator/                   # Herramienta web principal (FastAPI)
│   ├── backend/
│   │   ├── main.py                 # Rutas FastAPI + streaming de logs
│   │   ├── auth.py                 # Autenticación Basic Auth
│   │   ├── csv_parser.py           # CSV → análisis de tablas y vista previa
│   │   ├── type_inference.py       # Detección de tipos + advertencias
│   │   ├── schema_builder.py       # Generación de DDL (CREATE SCHEMA/TABLE)
│   │   └── sync_service.py         # Sincronización con PostgreSQL y transacciones
│   ├── frontend/
│   │   ├── templates/index.html    # Interfaz de una sola página (ES/EN)
│   │   └── static/
│   │       ├── app.js              # Lógica de la UI + cliente SSE
│   │       ├── i18n.js             # Traducciones ES/EN
│   │       └── styles.css
│   ├── uploads/                    # CSVs temporales (se eliminan tras la sync)
│   ├── .env                        # ⚠ Nunca subir — contiene credenciales
│   ├── .env.example                # Plantilla segura para compartir
│   └── requirements.txt
│
├── apps/                           # Scripts de migración por app (legado)
├── sql/                            # Definición de esquemas SQL por app
├── data/                           # CSVs originales y procesados por app
├── core/                           # Utilidades compartidas (db, cleaners, loader)
└── logs/                           # Logs de migración
```

---

## Problemas frecuentes

**La sesión expiró después de recargar la página**
La herramienta recupera la sesión automáticamente desde el disco. Si sigue fallando, volver a subir los CSVs — la sesión se reconstruye en segundos.

**AppSheet no reconoce el tipo de una columna al conectarse**
La columna probablemente fue detectada como `TEXT` en vez del tipo correcto. Revisar el paso de validación — la herramienta muestra los tipos detectados antes de sincronizar. Corregir el CSV origen y volver a correr.
