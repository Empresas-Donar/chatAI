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

### Tablas disponibles (verificadas 21/05/2026)

| Tabla BigQuery | Modelo Odoo | Filas | Contenido |
|---|---|---|---|
| `Contactos` | res.partner | 5.541 | Clientes, proveedores y empleados — directorio completo |
| `Cuentas_Contables` | account.account | 3.767 | Plan de cuentas contable |
| `Cuentas_por_cobrar` | account.move | 106 | Facturas emitidas a clientes |
| `Diarios_Contables` | account.journal | 203 | Diarios contables (ventas, compras, banco, etc.) |
| `Nomina` | hr.payslip.line | 46.068 | **Líneas detalladas** de liquidaciones (reglas salariales por empleado) |
| `Ordenes_de_aplicacion` | stock.move.line | 1.479 | Órdenes de aplicación agrícola (movimientos de insumos) |
| `Remuneraciones` | hr.payslip | 1.214 | Cabeceras de liquidaciones de sueldo |
| `Reporte_Analitico` | account.move.line | 131.707 | Líneas contables con distribución analítica (centro de costo) |
| `Ubicaciones` | stock.location | 129 | Ubicaciones de bodega/almacén |
| `Variantes_del_producto` | product.product | 6.074 | Variantes de productos/insumos |
| `movimientos_de_stock` | stock.move.line | 17.849 | Movimientos de stock completados (despachos, recepciones) |

> **Nota:** Los nombres de tabla ya no tienen sufijo `_staging_*`. Usar nombres exactos arriba.

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

### Columnas clave — Contactos (res.partner)

| Campo | Significado |
|---|---|
| `id` | ID del partner en Odoo |
| `name` | Nombre completo |
| `vat` | RUT (e.g. `77235191-7`) |
| `is_company` | TRUE = empresa, FALSE = persona |
| `customer_rank` | > 0 = es cliente |
| `supplier_rank` | > 0 = es proveedor |
| `employee` | TRUE = es empleado |
| `email` / `phone` / `mobile` | Datos de contacto |
| `street`, `city`, `state_id` | Dirección |
| `l10n_cl_sii_taxpayer_type` | Tipo contribuyente SII Chile |
| `l10n_cl_activity_description` | Giro comercial |
| `commercial_company_name` | Nombre comercial de la empresa |

### Columnas clave — Cuentas_Contables (account.account)

| Campo | Significado |
|---|---|
| `id` | ID interno |
| `code` | Código de cuenta (e.g. `1101010`) |
| `name` | Nombre de la cuenta (JSON bilingüe `{"es_CL": "..."}`) |
| `account_type` | Tipo: `asset_cash`, `liability_payable`, `expense`, `income`, etc. |
| `internal_group` | Grupo: `asset`, `liability`, `income`, `expense` |
| `reconcile` | TRUE = cuenta reconciliable |
| `company_id` | ID de la empresa propietaria |

### Columnas clave — Cuentas_por_cobrar (account.move)

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

### Columnas clave — Remuneraciones (hr.payslip) — cabeceras

| Campo Odoo | Significado |
|---|---|
| `name` | Nombre liquidación (empleado + mes) |
| `employee_id` | ID empleado (join con `Contactos.id` vía `employee=TRUE`) |
| `date_from` / `date_to` | Período de la liquidación |
| `gross_wage` | Sueldo bruto |
| `net_wage` | Sueldo líquido |
| `sueldo_base` | Sueldo base contractual |
| `descuentos` | Total descuentos |
| `aportes_patronales` | Costos patronales |
| `haberes` | Total haberes |
| `state` | `done` = liquidación cerrada |

### Columnas clave — Nomina (hr.payslip.line) — líneas detalladas

| Campo | Significado |
|---|---|
| `slip_id` | ID liquidación madre (join con `Remuneraciones.id`) |
| `employee_id` | ID empleado |
| `name` | Nombre de la regla (e.g. `BONO TRATO`, `TOTAL DESCUENTOS`, `Salario neto`) |
| `code` | Código regla salarial (e.g. `NET`, `TDE`, `BTRATO`) |
| `category_id` | Categoría (haberes, descuentos, aportes, etc.) |
| `amount` / `total` | Monto de la línea |
| `bl_signed_total` | Monto con signo (negativo para descuentos) |
| `quantity` / `rate` | Cantidad y tasa aplicada |
| `date_from` / `date_to` | Período |
| `contract_id` | ID del contrato de trabajo |
| `x_studio_afp` | AFP del trabajador |
| `x_studio_isapre` | Isapre del trabajador |
| `tipo_auxiliar` | Tipo auxiliar de la línea |

### Columnas clave — Reporte_Analitico (account.move.line)

| Campo | Significado |
|---|---|
| `id` | ID de la línea contable |
| `move_id` | ID del asiento contable |
| `move_name` | Nombre del asiento (e.g. `FAC/2026/01/0001`) |
| `account_id` | ID cuenta contable (join con `Cuentas_Contables.id`) |
| `journal_id` | ID diario contable (join con `Diarios_Contables.id`) |
| `partner_id` | ID cliente/proveedor (join con `Contactos.id`) |
| `date` | Fecha del movimiento |
| `invoice_date` | Fecha de factura (si aplica) |
| `debit` / `credit` | Debe / Haber |
| `balance` | Saldo neto (debit - credit) |
| `analytic_distribution` | JSON con distribución analítica `{"ID_CC": porcentaje}` |
| `parent_state` | Estado: `posted`, `draft`, `cancel` |
| `name` | Descripción de la línea |
| `ref` | Referencia del asiento |
| `product_id` | Producto asociado (si aplica) |
| `quantity` | Cantidad |
| `price_unit` / `price_subtotal` | Precio unitario / subtotal |
| `x_studio_n_de_oc` | N° de OC (custom Studio) |
| `x_studio_documento` | Documento de referencia (custom Studio) |
| `x_studio_estado_aprobacin` | Estado aprobación (custom Studio) |

> **Importante:** La distribución analítica está en `analytic_distribution` como JSON string `{"12345": 100.0}` donde la key es el ID del centro de costo analítico. No existe columna `analytic_account_id` directa.

### Columnas clave — Ordenes_de_aplicacion (stock.move.line)

| Campo | Significado |
|---|---|
| `id` | ID del movimiento |
| `move_id` | ID de la operación de stock padre |
| `picking_id` | ID guía de despacho / transferencia |
| `product_id` | ID producto/insumo (join con `Variantes_del_producto.id`) |
| `product_uom_id` | Unidad de medida |
| `quantity` / `quantity_product_uom` | Cantidad movida |
| `location_id` | Ubicación origen (join con `Ubicaciones.id`) |
| `location_dest_id` | Ubicación destino |
| `date` | Fecha del movimiento |
| `state` | Estado: `done`, `assigned`, `cancel` |
| `reference` | Referencia (e.g. `D1/OUT/00019`) |
| `product_category_name` | Categoría del producto (e.g. `AG / INSUMOS AGRO / AGROQUIMICOS`) |
| `x_studio_empresa` | ID empresa asociada (custom Studio) |
| `x_studio_distribucin_analtica` | Distribución analítica (custom Studio) |
| `x_studio_guia_despacho` | Guía de despacho (custom Studio) |
| `x_studio_dosis_x_hectarea` | Dosis por hectárea aplicada |
| `x_studio_dosis_x_100l` | Dosis por 100L aplicada |
| `x_studio_mojamiento_ha` | Mojamiento por hectárea |
| `x_studio_tipo_de_aplicacin` | Tipo de aplicación agrícola |

### Columnas clave — movimientos_de_stock (stock.move.line — despachos)

Misma estructura que `Ordenes_de_aplicacion`. Se diferencia en que contiene **todos** los movimientos de stock (no solo aplicaciones agrícolas). Campos adicionales relevantes:

| Campo | Significado |
|---|---|
| `lot_id` / `lot_name` | Lote del producto |
| `picked` | TRUE = ya fue retirado físicamente |
| `description_picking` | Descripción del despacho |

### Columnas clave — Variantes_del_producto (product.product)

| Campo | Significado |
|---|---|
| `id` | ID de la variante |
| `product_tmpl_id` | ID del template de producto |
| `default_code` | Código interno / referencia (e.g. `4669`) |
| `barcode` | Código de barras |
| `active` | TRUE = producto activo |

### Columnas clave — Ubicaciones (stock.location)

| Campo | Significado |
|---|---|
| `id` | ID de la ubicación |
| `name` | Nombre corto (e.g. `Consumo`) |
| `complete_name` | Ruta completa (e.g. `WH/Stock/Sector A`) |
| `usage` | Tipo: `internal`, `customer`, `supplier`, `production`, `view` |
| `scrap_location` | TRUE = es ubicación de merma |
| `company_id` | Empresa propietaria |
| `warehouse_id` | Bodega a la que pertenece |

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
| Costo de mano de obra por CC vs lo contabilizado | `pagos."CC"` ↔ clave en JSON `Reporte_Analitico.analytic_distribution` |
| Costo laboral mensual vs remuneraciones Odoo | `pagos."Mes"` ↔ `Remuneraciones.date_from` |
| Detalle de reglas salariales por empleado | `Remuneraciones.id` ↔ `Nomina.slip_id` |
| Qué se le facturó al cliente vs lo que costó producirlo | `Cuentas_por_cobrar.partner_id` ↔ `Contactos.id` |
| Nombre de cuenta contable por ID | `Reporte_Analitico.account_id` ↔ `Cuentas_Contables.id` |
| Nombre de proveedor/cliente en línea contable | `Reporte_Analitico.partner_id` ↔ `Contactos.id` |
| Órdenes de aplicación vs producto usado | `Ordenes_de_aplicacion.product_id` ↔ `Variantes_del_producto.id` |
| Bodega origen/destino de un despacho | `movimientos_de_stock.location_id` ↔ `Ubicaciones.id` |
| Rentabilidad por contratista | `pagos."Total a Pagar"` agrupado por `"Contratista"` vs `Cuentas_por_cobrar` |
| RUT de cliente en factura | `Cuentas_por_cobrar.partner_id` → `Contactos.vat` |

> **Nota `analytic_distribution`:** Es un JSON string. Para extraer el CC: `JSON_EXTRACT_SCALAR(analytic_distribution, '$.ID_CC')` en BigQuery, o parsear con `json.loads()` en Python.

### Campo → Empresa facturada

| Campo AppSheet | Empresa en Odoo |
|---|---|
| Isla de Maipo | Agricola Donar Dos SpA |
| Zuñiga | Agricola Donar Dos SpA |
| Talagante | (verificar en Cuentas_por_cobrar) |
