# AppSheet → PostgreSQL Migration Toolkit

## Contexto del Proyecto

Framework para migrar múltiples aplicaciones AppSheet a PostgreSQL.

Apps actuales:
- `contratistas_isla_maipo`
- `medicion_pozos`

Convención de tablas: `appsheet.<nombre_app>_<nombre_tabla>`

Ejemplos:
```
appsheet.contratistas_isla_maipo_contratistas
appsheet.medicion_pozos_ingresos
```

---

## Arquitectura

```
core/     → lógica reutilizable (db, cleaners, loader, utils)
apps/     → scripts específicos por app
sql/      → definición de esquemas por app
data/     → CSV raw y procesados por app
logs/     → salidas de migración
```

No mezclar responsabilidades entre capas. La lógica reutilizable siempre va en `core/`.

---

## Language Convention

All code must be written in English:
- File names, variable names, function names, class names
- Comments, docstrings, log messages, git commit messages

Exception: table names, column names, and CSV field names stay in Spanish
as defined by the client (e.g. `id_trabajador`, `contratista`, `fecha_inicio_trato`).
Do not translate these — they must match the AppSheet source exactly.

---

## SQL Generation Rules for AppSheet Compatibility

You are generating SQL for a PostgreSQL database that will be connected directly to AppSheet.

STRICT RULES:

1. Keep column names EXACTLY as they appear in AppSheet.
2. Respect uppercase, lowercase, underscores, and special characters (including `%`).
3. Always wrap column names in double quotes in PostgreSQL.
4. DO NOT rename columns.
5. DO NOT normalize to snake_case.
6. DO NOT refactor names.
7. DO NOT change structure for architectural improvements.
8. DO NOT remove fields unless explicitly instructed.
9. DO NOT migrate virtual columns like `Related_*`.
10. DO NOT migrate `_RowNumber` unless explicitly instructed.

The goal is zero structural changes so AppSheet can connect without breaking formulas, references, or virtual columns.

Generate production-ready SQL strictly following these rules.

---

## Reglas de Desarrollo

1. No hardcodear credenciales — usar variables de entorno (`.env`)
2. Usar funciones reutilizables en `core/`
3. Validar tipos antes de insertar en DB
4. Usar `ON CONFLICT` (UPSERT) siempre — nunca INSERT sin manejo de duplicados
5. Evitar duplicación de código entre apps
6. Mantener funciones pequeñas y testeables
7. Documentar scripts críticos

---

## Limpieza de Datos

Aplicar siempre estas transformaciones antes de insertar:

| Entrada      | Salida         |
|--------------|----------------|
| `$18.000`    | `18000`        |
| `45,00%`     | `0.45`         |
| Fechas       | `YYYY-MM-DD`   |
| Boolean      | `True`/`False` |
| EnumList     | `TEXT[]`       |

---

## AppSheet + PostgreSQL Conventions

**Primary Keys**
- Always `TEXT NOT NULL PRIMARY KEY` — never `SERIAL` or `INTEGER`
- AppSheet generates its own string IDs; the column name must match exactly what AppSheet uses as Row ID

**Columns to NEVER migrate**
- `_RowNumber` — virtual Sheets column, does not exist in PostgreSQL
- `Related_*` — reverse ref virtual columns, AppSheet generates these automatically
- Any AppSheet formula/virtual columns

**Type Mapping**
| AppSheet type | PostgreSQL type |
|---|---|
| Text | `TEXT` |
| Number / Decimal / Price | `NUMERIC` |
| Date | `DATE` |
| DateTime | `TIMESTAMP` |
| Yes/No | `BOOLEAN` |
| EnumList | `TEXT[]` |
| Ref | `TEXT` (FK to the referenced table's PK) |

**Ref columns (relationships)**
- Store as `TEXT` with a real FK constraint
- AppSheet uses these to navigate relationships automatically

**Column names**
- AppSheet is case-sensitive — column names must match exactly what AppSheet expects
- Never rename, add spaces, or change casing

**After connecting AppSheet to PostgreSQL**
- Run "Regenerate Structure" so AppSheet re-scans types
- If a column type is wrong (e.g. date stored as TEXT), AppSheet will not recognize it correctly
- Test all views and actions in preview mode before going live

## Revisión de SQL

Al generar o revisar SQL:

- Validar foreign keys y orden de creación de tablas
- Usar `NUMERIC` para dinero/porcentajes, no `TEXT`
- Nunca migrar columnas virtuales de AppSheet
- Nunca migrar columnas `Related_*`

---

## Flujo de Migración

1. Analizar CSV de entrada
2. Aplicar limpieza automática (`core/cleaners.py`)
3. Insertar con transacción
4. Loggear resultados
5. Validar conteos finales

---

## Orden de Migración (dependencias)

1. empresa
2. labor
3. contratistas
4. trabajadores
5. tratos
6. registro
7. registro_trato
8. resumen
9. pagos
10. usuarios

---

## Futuro

- CLI central: `python migrate.py --app nombre_app`
- Validación automática de esquemas
- Comparador Sheet vs DB
- Migraciones incrementales

---

## Fuente de Datos: Odoo en Google Cloud (BigQuery)

El cliente **KONTROLAG SPA** (RUT 77235191-7) tiene una instancia de Odoo activa que exporta datos a BigQuery.

**GCP Project:** `ace-scarab-484515-v1`
**Dataset:** `odoo_data`
**Service Account:** `odoo-bigquery@ace-scarab-484515-v1.iam.gserviceaccount.com`
**Clave JSON local:** `/Users/bedomax/startups/donar/bigquery-odoo-key.json`

### Tablas disponibles

| Tabla BigQuery | Contenido | Filas aprox. |
|---|---|---|
| `Cuentas_por_cobrar` | Facturas emitidas (account.move) | 109 |
| `Remuneraciones` | Liquidaciones de sueldo (hr.payslip) | 1.199 |
| `Reporte_Analítico_staging_1778157508` | Líneas analíticas contables | 50.000 |
| `Ordenes_de_aplicación_staging_1778157654` | Órdenes de aplicación agrícola | 1.441 |

> Las tablas sin sufijo `_staging_*` están vacías — los datos reales están en las staging con sufijos exactos arriba.

### gcloud

- **Cuenta activa:** `gestion@empresasdonar.cl`
- Autenticar con: `gcloud auth application-default login` o usar la clave JSON del service account

### Conexión BigQuery desde Python

```python
from google.cloud import bigquery
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json"
)
client = bigquery.Client(project="ace-scarab-484515-v1", credentials=credentials)

df = client.query("""
    SELECT * FROM `ace-scarab-484515-v1.odoo_data.Cuentas_por_cobrar`
""").to_dataframe()
```

### Columnas clave — Cuentas_por_cobrar

| Campo Odoo | Significado |
|---|---|
| `name` | Número de factura (e.g. `FAC 000135`) |
| `invoice_partner_display_name` | Nombre del cliente |
| `invoice_date` | Fecha emisión |
| `invoice_date_due` | Fecha vencimiento |
| `amount_untaxed` | Monto neto |
| `amount_tax` | IVA |
| `amount_total` | Total con IVA |
| `amount_residual` | Saldo pendiente de cobro |
| `payment_state` | Estado: `not_paid`, `partial`, `paid` |
| `state` | Estado doc: `posted`, `draft`, `cancel` |
| `l10n_cl_sii_send_ident` | RUT receptor (Chile) |
| `x_studio_estado_aprobacin` | Campo custom Odoo Studio |

### Columnas clave — Remuneraciones

| Campo Odoo | Significado |
|---|---|
| `name` | Nombre liquidación (empleado + mes) |
| `employee_id` | ID empleado |
| `date_from` / `date_to` | Período |
| `gross_wage` | Sueldo bruto |
| `net_wage` | Sueldo líquido |
| `sueldo_base` | Sueldo base contractual |
| `descuentos` | Total descuentos |
| `aportes_patronales` | Costos patronales |
| `haberes` | Total haberes |
| `state` | `done` = liquidación cerrada |

### Columnas clave — Reporte_Analítico_staging_1778157508

| Campo | Significado |
|---|---|
| `account_id` | Cuenta contable |
| `analytic_account_id` | Centro de costo / proyecto |
| `partner_id` | Cliente o proveedor |
| `date` | Fecha del movimiento |
| `debit` / `credit` | Debe / Haber |
| `balance` | Saldo neto |
| `move_id` | Referencia al asiento contable |

### Columnas clave — Ordenes_de_aplicación_staging_1778157654

| Campo | Significado |
|---|---|
| `name` | Código de la orden |
| `product_id` | Producto/insumo aplicado |
| `picking_id` | Guía de despacho asociada |
| `partner_id` | Cliente destinatario |
| `date` | Fecha de la orden |
| `product_qty` | Cantidad |
| `state` | Estado de la orden |

### Contexto del negocio

- KONTROLAG SPA presta servicios agrícolas de supervisión e instalaciones a empresas de la zona central de Chile
- Opera con fuerte estacionalidad: **70 empleados en peak (feb 2025)**, ~10 fuera de temporada
- Facturación concentrada en **diciembre–mayo** (temporada de fruta)
- **Agricola Donar Dos SpA** es cliente directo de KONTROLAG (empresa del grupo Donar)
- Los campos con prefijo `x_studio_` son personalizaciones de Odoo Studio del cliente

### Hallazgos financieros (al 07/05/2026)

- **Facturación total histórica:** $858.7 MM — solo 24% cobrado; $650 MM pendiente
- **Deuda crítica (+90 días):** $171.6 MM
  - Exportadora Rancagua: $198.8 MM vencidos (~128 días)
  - Agricola Curico: $107.7 MM vencidos (~145 días)
  - Agricola Donar Dos SpA: $50.2 MM vencidos (~129 días)
- **Costo laboral 2025:** ~$2.200 MM acumulado — facturación llegó rezagada en dic 2025
- **Ratio saludable:** abril 2026 fue el primer mes con 72% costo laboral / facturación neta

---

## Mapa de Datos y Cruces de Negocio

El sistema combina dos fuentes principales para responder preguntas de negocio:

### Fuente 1: AppSheet → PostgreSQL (esquema `appsheet`)

**App `contratistas_isla_maipo`** — gestión de mano de obra agrícola en predios Zuñiga, Isla de Maipo y Talagante:
- `contratistas` — empresas contratistas con condiciones pactadas (valor jornada, bono, % trato)
- `trabajadores` — nómina por contratista
- `tratos` — contratos de labor por campo / centro de costo / período, con valor unitario
- `registro` / `registro_trato` — movimientos diarios por trabajador (jornadas, horas extra, unidades trato)
- `pagos` — liquidación diaria: total trabajador, total contratista, total a pagar por empresa/CC/labor
- `labor` — catálogo de labores agrícolas
- `cultivos` / `cultivos_detalle` — qué cultivo hay en cada campo y centro de costo

**App `tarjas`** — cuadrillas en campo, integrada con Odoo:
- `tarjas_reporte_odoo` — view que mapea pagos diarios a líneas de pedido de compra Odoo

**App `medicion_pozos`** — registros de pozos de agua (en proceso de migración)

### Fuente 2: Odoo → BigQuery (`odoo_data`, proyecto `ace-scarab-484515-v1`)

| Tabla | Contenido |
|---|---|
| `Cuentas_por_cobrar` | Facturas emitidas a clientes (account.move) |
| `Remuneraciones` | Liquidaciones de sueldo de empleados KONTROLAG |
| `Reporte_Analítico_staging_1778157508` | Líneas contables por centro de costo |
| `Ordenes_de_aplicación_staging_1778157654` | Órdenes de aplicación agrícola |

### Cruces clave entre fuentes

| Pregunta de negocio | Join |
|---|---|
| Costo de mano de obra por CC vs lo contabilizado | `pagos."CC"` ↔ `Reporte_Analítico.analytic_account_id` |
| Costo laboral mensual vs remuneraciones Odoo | `pagos."Mes"` ↔ `Remuneraciones.date_from` |
| Qué se le facturó al cliente vs lo que costó producirlo | `Cuentas_por_cobrar.partner` ↔ `pagos."Empresa"` |
| Órdenes de aplicación vs tratos ejecutados en campo | `Ordenes_de_aplicación.partner_id` ↔ `contratistas."Campo"` |
| Rentabilidad por contratista | `pagos."Total a Pagar"` agrupado por `"Contratista"` vs facturas Odoo |

### Campo → Empresa facturada

| Campo AppSheet | Empresa en Odoo |
|---|---|
| Isla de Maipo | Agricola Donar Dos SpA |
| Zuñiga | Agricola Donar Dos SpA |
| Talagante | (verificar en Cuentas_por_cobrar) |
