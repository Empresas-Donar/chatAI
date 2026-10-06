# ChatAI — Plataforma BI y Chat IA para Donar / KONTROLAG

## Qué hace esta aplicación

Este repositorio evolucionó de una herramienta de migración AppSheet → PostgreSQL a una **plataforma de inteligencia de negocio y analítica conversacional** para Empresas Donar y KONTROLAG SPA. Tiene tres funciones principales:

1. **Reportería operativa**: dashboards de tarjas (mano de obra), despachos (stock.picking Odoo), órdenes de compra — reemplazando Looker Studio
2. **Chat IA**: interfaz de lenguaje natural con Gemini 2.5-pro que genera SQL, consulta PostgreSQL + BigQuery y exporta resultados (Excel, PDF, Google Sheets)
3. **Migración AppSheet → PostgreSQL**: herramienta web que recibe CSVs, detecta tipos, valida y carga datos con UPSERT transaccional

---

## Stack Técnico

**Backend:** Python 3.11+, FastAPI 0.111+, Uvicorn
**BD:** PostgreSQL 16 (Cloud SQL GCP) + Google BigQuery (Odoo warehouse)
**LLM:** Google Gemini 2.5-pro via `google-genai` SDK con tool use
**MCP:** FastMCP server expone las tablas BigQuery como herramientas al LLM
**Export:** openpyxl (Excel), xhtml2pdf (PDF), gspread (Google Sheets)
**Auth:** sesiones por cookie firmada (`itsdangerous`) + OAuth2 Google
**Infra:** Cloud Run (`southamerica-west1`), Artifact Registry, Cloud Build

---

## Estructura del Proyecto

```
chatai/
  backend/
    main.py                    — FastAPI app, middleware, routers
    auth.py                    — sesiones cookie + OAuth2 Google
    db.py                      — conexión PostgreSQL
    pg_client.py               — ejecutor SELECT-only para el chat
    chat_cache.py              — cache de respuestas LLM
    controllers/               — capa HTTP (10 módulos)
      chat_controller.py       — interfaz chat IA (streaming SSE)
      tarjas_controller.py     — reportes mano de obra / contratistas
      purchase_orders_controller.py — órdenes compra + sync Odoo
      despacho_controller.py   — guías de despacho
      reports_controller.py    — exportación PDF masiva
      csv_migrator_controller.py — migración AppSheet → PG
      sensors_controller.py    — sensores de riego
      roles_controller.py      — control de acceso
      login_controller.py      — sesiones
      google_auth_controller.py — OAuth2
    services/                  — lógica de negocio (sin HTTP)
      csv_parser.py            — CSV → TableAnalysis (inferencia de tipos)
      schema_builder.py        — genera DDL CREATE TABLE
      sync_service.py          — carga datos con transacciones
    models/
      migration_models.py      — TableAnalysis, SyncResult
    prompt_data/               — templates del system prompt
  frontend/
    templates/                 — 27 templates Jinja2 HTML5
    static/                    — JS y CSS (sin framework, vanilla)
  tests/                       — 14 módulos pytest
  uploads/                     — CSVs temporales (auto-limpiados)

core/                          — utilidades reutilizables (legacy migración)
  type_inference.py            — detección tipos PostgreSQL
  cleaners.py                  — limpieza datos CSV
  loader.py / utils.py

mcp_server/                    — servidor MCP para el chat IA
  main.py                      — 3 tools: list_tables, describe_table, query_bigquery
  bigquery_client.py           — credenciales GCP

sql/
  tarjas/                      — esquema PostgreSQL del sistema de tarjas
    01_views_reporte.sql       — vista tarjas_reporte (consolidada)
    02_views_odoo.sql          — vista tarjas_reporte_odoo (export Odoo)
    03_insert_labores_bonhomia.sql
    04_backfill_id_labor.sql
    05_trigger_id_labor.sql
    06_add_id_labor_to_labores.sql

specs/                         — especificaciones de features (en español)
apps/                          — scripts legacy de migración AppSheet
data/                          — CSVs raw por app
```

---

## Módulos Principales

### Tarjas (mano de obra agrícola)
Controlador más grande (3,637 líneas). Gestiona pagos a contratistas por labor agrícola.

**Vistas disponibles:**
- `tarjas_general` — resumen por contratista/campo/labor
- `tarjas_detalle` — detalle semana a semana
- `tarjas_contratista` — tabla pivot trabajadores (horas, costo/hr)
- `tarjas_jornadas_trabajador` — horas por trabajador por fecha
- `tarjas_notas` — notas de crédito
- Variantes `tractorista` para pagos de maquinaria

**Mapeo de labores (4 niveles de fallback):**
El JOIN `tarjas_pagos → tarjas_labores` usa 4 niveles de tolerancia: id_labor exacto → texto normalizado → prefijo → BONHOMIA. Esto es crítico para la vista `tarjas_reporte_odoo`.

**Tablas PostgreSQL:**
```
appsheet.tarjas_pagos          — registros de pago (origen AppSheet)
appsheet.tarjas_labores        — catálogo de labores con codigo_labor (Odoo)
appsheet.tarjas_cc             — centros de costo con analytic_distribution JSON
appsheet.tarjas_reporte        — VIEW consolidada para reportes
appsheet.tarjas_reporte_odoo   — VIEW formato Odoo (product_id, CC JSON)
```

### Cosecha (escaneo de capachos)

AppSheet de cosecha en campo, distinta de tarjas (pago por labor) y de `despacho_ingreso` (ingreso de fruta en kg). No hay controlador ni vistas. El corte contratista/cuadrillas de Zúñiga está en `sql/cosecha/01_zuniga_cuadrillas.sql`. El prompt del chat todavía no documenta estas tablas.

Hay dos apps, una por predio. Isla tiene 8 tablas; Zúñiga agrega `cuadrillas`:

| Sufijo | Rol |
|---|---|
| `cosecha_isla_de_maipo_*` | Isla de Maipo |
| `cosecha_zuniga_*` | Zúñiga |

Tablas: `escaneo`, `registro`, `qr`, `tratos`, `cuarteles`, `contratistas`, `usuarios`, `bins`. Zúñiga además tiene `cuadrillas` y `cuadrilla_cuartel`.

**Grano:**

- 1 fila de `escaneo` = 1 capacho. El trabajador escanea su QR (`codigo_qr`, formato `cos;` + código) contra un bin. El pago observado es `COUNT(escaneos) × precio_trato_aplicado` (CLP por capacho). `piso_aplicado` es el piso diario garantizado en CLP, copiado del trato vigente.
- `bins` es el número del bin, no una cantidad. No hacer `SUM(bins)`. El catálogo `*_bins` está vacío; el id vive en `escaneo.bins` y `registro.bins`.
- `registro` abre el bin (una fila por bin asignado a cuadrilla y cuartel). `registro.bins` es el mismo identificador, no un conteo.
- `tratos` fija `precio_capacho` y `piso_garantizado_diario` por cuartel y `fecha_inicio_vigencia`. El escaneo congela el precio en `precio_trato_aplicado`.
- `qr` es la credencial del trabajador (`qr_trabajador` = `escaneo.codigo_qr`).
- En Isla de Maipo, `contratistas` es una fila por cuadrilla activa (la columna `cuadrillas` es el número de cuadrilla, no un conteo).
- En Zúñiga, `contratistas` es una fila por contratista y `cosecha_zuniga_cuadrillas` es la hija. `contratistas.cuadrillas` quedó obsoleta y en NULL. Registro, QR y escaneo guardan el nombre del contratista, no el id. El número de cuadrilla es único dentro del contratista y puede repetirse entre contratistas.
- `cuarteles` es el catálogo (`id_cuartel` tipo `C05`, `nombre_cuartel`, `variedad`).
- En Zúñiga, `cosecha_zuniga_cuadrilla_cuartel` une cuadrilla y cuartel. Una cuadrilla tiene N cuarteles y el mismo cuartel puede estar en otra cuadrilla. La pareja no se repite (`sql/cosecha/02_zuniga_cuadrilla_cuartel.sql`).
- `usuarios` es el login AppSheet (`rol`: `Admin` o `Cuadrilla`). La columna `contraseña` tiene secretos en texto plano: no seleccionarla, no loguearla, no incluirla en exports.

**Joins:**

- `escaneo.codigo_qr` = `qr.qr_trabajador` (no `qr.id_qr`).
- `escaneo.cuartel` = `cuarteles.nombre_cuartel` (texto del cuartel).
- `registro.cuartel` = `cuarteles.id_cuartel`. El nombre va en `registro.nombre_cuartel_texto`.

Estos montos no pasan por `tarjas_empresa.py`. No usar × 1.45 ni × 1.50.

**Volúmenes revisados (2026-10-01):**

| Predio | Escaneos | Qué se cosechó |
|---|---|---|
| Isla de Maipo | 2.087 | Cereza Rainier, 27–28 nov 2025 (precio $700, piso $15.000). 3 filas de prueba el 27 may 2026. |
| Zúñiga | 21.386 | Ciruela D'Agen, cuartel `CIRUELOS ADULTOS CC-860`, 22–29 ene 2026. Precio baja 1.300 → 1.000. 386 filas con `bins = 'Manual'` (carga sin QR). |

Isla: 12 cuarteles (cerezo Sweet Aryana, Santina, Glow, Lapins, Rainier, Red Pacific, y ciruela D'Agen). Zúñiga: 16 cuarteles (cerezo, kiwi, ciruelo). El catálogo es más amplio que los días con escaneo.

**Deriva de esquema entre predios** (consultar con el tipo real; no unificar a ciegas):

| Columna | Isla de Maipo | Zúñiga |
|---|---|---|
| `escaneo.bins` | `NUMERIC` | `TEXT` (incluye `'Manual'`) |
| Día sin hora en escaneo | `"Fecha_Solo_Dia"` (comillar; mayúsculas) | `fecha_solo_dia` |
| `registro.fecha_y_hora` | `TEXT` (ISO y `DD/MM/YYYY` mezclados) | `TIMESTAMP` |
| `tratos.fecha_inicio_vigencia` | `TEXT` `DD/MM/YYYY` | `DATE` |
| `tratos.piso_garantizado_diario` | `INTEGER` (15.000) | `BOOLEAN` (siempre false: el piso se perdió en la migración) |
| `qr.cuadrilla` | `NUMERIC` | `TEXT` |
| `contratistas.cuadrillas` | `INTEGER` (número de esa fila) | `NUMERIC`, obsoleta y en NULL |

Isla y el resto de tablas de Zúñiga siguen sin PK, FK ni índices. Excepción: `cosecha_zuniga_contratistas`, `cosecha_zuniga_cuadrillas`, `cosecha_zuniga_cuarteles` y `cosecha_zuniga_cuadrilla_cuartel`. Hay `id_escaneo` y `id_qr` duplicados en filas incompletas (`fecha` nula). `id_fecha` es `YYYYMMDDHHMMSS` cuando viene poblado; en Isla hay al menos un valor corrupto por formato Excel. `registro.unnamed` es el timestamp crudo del navegador AppSheet.

### Chat IA
Interfaz conversacional con streaming SSE. Gemini 2.5-pro decide qué SQL ejecutar, usa MCP para BigQuery y `pg_client` para PostgreSQL. Tiene auto-corrección: si el SQL falla, el LLM reintenta.

**Reglas de integridad del LLM:** no puede inventar datos, siempre debe ejecutar SQL antes de responder, no puede responder preguntas fuera del dominio de negocio.

**Exports:** Excel (openpyxl), PDF (xhtml2pdf), Google Sheets (gspread → Drive del usuario).

**Tablas PostgreSQL:**
```
public.chat_messages           — historial de conversaciones
public.system_prompt           — prompt del sistema (editable por admin)
```

### Purchase Orders / Odoo Sync
Gestiona pedidos de venta (BigQuery `Pedidos_de_Venta`) y sincronización de centros de costo con Odoo. Incluye resolución de códigos duplicados por fuzzy matching.

### Despacho
Dashboard de guías de despacho (BigQuery `Despachos`). Incluye preview de sync de distribución analítica antes del export.

### CSV Migrator
Interfaz web que acepta CSVs de AppSheet, detecta tipos automáticamente (BOOLEAN, DATE, NUMERIC, TEXT), muestra preview, hace dry-run y confirma con UPSERT transaccional. Los logs se transmiten en tiempo real por SSE.

---

## Fuentes de Datos

### PostgreSQL — esquema `appsheet`
Tablas migradas desde AppSheet. Prefijo: `appsheet.<nombre_app>_<tabla>`.

Convención de PKs: `TEXT NOT NULL PRIMARY KEY` (nunca SERIAL — AppSheet genera sus propios IDs).

### BigQuery — `ace-scarab-484515-v1.odoo_data`
16 tablas exportadas desde Odoo. Las principales:

| Tabla | Contenido |
|---|---|
| `Cuentas_por_cobrar` | Facturas a clientes |
| `Remuneraciones` | Liquidaciones de sueldo |
| `Nomina` | Líneas detalladas de liquidaciones |
| `Pedidos_de_Venta` | Pedidos S00XXX |
| `Lineas_del_Pedido_de_Venta` | Líneas por pedido |
| `Despachos` | Guías DTE (stock.picking) |
| `Movimientos_de_Stock` | Movimientos de stock |
| `Ordenes_de_aplicacion` | Aplicaciones agrícolas |
| `Empleados` | Ficha empleados con RUT (`formated_vat`) |
| `Contactos` | Clientes, proveedores, empleados |
| `Reporte_Analitico` | Líneas contables con CC analítico |
| `Producto` / `Variantes_del_producto` | Catálogo de productos/insumos |
| `Ubicaciones` | Bodegas y almacenes |

**Credenciales BigQuery:**
- Service account key local: `/Users/bedomax/startups/donar/bigquery-odoo-key.json`
- Variable de entorno en producción: `BIGQUERY_KEY_B64`
- Cuenta gcloud: `gestion@empresasdonar.cl`

---

## Terminología del Dominio

| Término | Significado |
|---|---|
| **Tarjas** | Registros de trabajo diario en campo |
| **Trato** | Pago a destajo (vs. "al día" = jornal) |
| **Labor** | Tipo de trabajo: "AMARRA", "PODA", "REPLANTE", etc. |
| **Contratista** | Empresa/cuadrillero que provee mano de obra |
| **Nombre_campo** | Predio: "Isla de Maipo", "Bonhomia", "Zuñiga" |
| **Cuartel** | Subdivisión del predio (lote agrícola) |
| **CC** | Centro de Costo (dimensión analítica Odoo) |
| **codigo_labor** | Código de producto Odoo para la labor |
| **Despacho** | Transferencia de stock / guía DTE |
| **Orden de Aplicación** | Aplicación de agroquímico en campo |
| **Capacho** | Canasto de cosecha. En `cosecha_*_escaneo`, una fila = un capacho escaneado |
| **Bin (cosecha)** | Identificador del bin en `escaneo.bins` / `registro.bins`. No es una cantidad |
| **Cuadrilla** | Grupo de cosecha dentro de un contratista (`cuadrilla` / `cuadrillas`) |

---

## Convenciones de Código

**Idioma del código:** inglés (archivos, funciones, variables, comentarios, commits)
**Documentación:** español (specs/, README, markdown)
**Columnas DB:** español exacto del AppSheet original — NO renombrar
**Fechas en UI:** `DD/MM/YYYY` — sin excepciones
**Fechas internas:** ISO 8601 `YYYY-MM-DD` (APIs, DB)

---

## Reglas SQL / PostgreSQL

1. PKs siempre `TEXT NOT NULL PRIMARY KEY`
2. Dinero/porcentajes: `NUMERIC` (nunca TEXT)
3. Siempre `ON CONFLICT ... DO UPDATE` (UPSERT) — nunca INSERT sin manejo de duplicados
4. Envolver nombres de columnas en comillas dobles `"columna"` (AppSheet es case-sensitive)
5. No migrar columnas virtuales AppSheet: `_RowNumber`, `Related_*`
6. Preservar nombres de columnas exactamente como aparecen en AppSheet

---

## Reglas de Cálculo: Costo Empresa (tarjas)

Hay **dos fórmulas distintas** para montos de tarjas — no mezclarlas:

| Fórmula | Dónde usarla | Implementación |
|---|---|---|
| **Costo Empresa** | OC, Detalle, Facturación, Notas, Export Odoo | `total_trabajado × factor` via `tarjas_empresa.total_empresa()` |
| **Pago AppSheet** | Reportes de pago a trabajadores (General, Por persona) | `total_trabajado + total_contratista` (raw AppSheet) |

**Factores Costo Empresa** (`chatai/backend/tarjas_empresa.py`):
- Trato → `× 1.45` (+45 %)
- Al día → `× 1.50` (+50 %)
- Otros (Bono, Tractorista, …) → `× 1.0`

Costo Empresa: Trato × 1.45 (+45 %). Al Día × 1.50 (+50 %). NUNCA invertir. Única fuente: `tarjas_empresa.py`.

**Fuente de verdad única:** `chatai/backend/tarjas_empresa.py` con sus factores fijos (Trato 1.45 / Al Día 1.50) es la única fuente de verdad para montos de Costo Empresa. Toda superficie — OC, Detalle, Facturación, Notas, Export Odoo — debe derivar su precio de esta función. `total_trabajado + total_contratista` y `total_pagar` de AppSheet son datos históricos de referencia, no fuente de verdad. AppSheet `total_contratista` usa los mismos porcentajes; igual no se factura con `total_pagar`.

**Regla absoluta:** El export Odoo xlsx se precifica con `tarjas_empresa.total_empresa()` (mismas líneas que la OC) vía `costo_empresa_odoo_lines()`. La vista `tarjas_reporte_odoo` solo aporta `product_id` y `analytic_distribution`. **Nunca** usar `total_unitario` / `pagar_efectivo` de AppSheet como `price_unit`.

**Reconciliación:** `SUM(order_line/product_qty × order_line/price_unit)` en el export Odoo debe cuadrar con el total del header de la Orden de Compra para el mismo rango de fechas y contratista.

**`analytic_distribution`:** JSON `{"id_cc": porcentaje}`. Reglas:
- Los valores deben sumar exactamente 100.00 por fila
- Nunca exportar valores `null` o vacíos en el JSON (`"410": null` o `"410": ,` son inválidos para Odoo)
- Filtrar filas con distribución inválida con estado `⚠ Incompleta` — no exportarlas

---

## Reglas de Desarrollo

1. No hardcodear credenciales — usar variables de entorno (`.env`)
2. Lógica reutilizable va en `core/` o `services/`
3. Validar tipos antes de insertar en DB
4. Funciones pequeñas y testeables
5. No añadir manejo de errores para escenarios imposibles
6. No abstraer prematuramente — si hay 3 líneas similares, no crear helper

---

## Limpieza de Datos (CSV → PostgreSQL)

| Entrada | Salida |
|---|---|
| `$18.000` | `18000` |
| `45,00%` | `0.45` |
| Fechas | `YYYY-MM-DD` |
| Boolean | `True`/`False` |
| EnumList | `TEXT[]` |

---

## Despliegue

**Cloud Run:** `chatai` en `southamerica-west1`, auto-scaling desde 0
**Build:** `cloudbuild.yaml` → Docker → Artifact Registry `integraciones/chatai:latest`
**Deploy manual:** `gcloud run deploy chatai --region southamerica-west1`

**Variables de entorno:**
```
DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
BIGQUERY_KEY_B64          — clave GCP en base64
SECRET_KEY                — firma de cookies
AUTH_USER / AUTH_PASSWORD — auth de sesión
HTTPS_ONLY                — enforce HTTPS en prod
ALLOWED_ORIGINS           — CORS
```

---

## Testing

Pytest con 14 módulos en `chatai/tests/`. Cada test usa fixtures propios. No hay mocks de BD — los tests de integración usan la DB real (local o test). Estrategia: regresión SQL, validación de formato DD/MM/YYYY, lógica de negocio.

Ejecutar: `cd chatai && pytest tests/ -v`

---

## Fuente BigQuery (contexto para queries)

**GCP Project:** `ace-scarab-484515-v1`
**Dataset:** `odoo_data`
**Service Account:** `odoo-bigquery@ace-scarab-484515-v1.iam.gserviceaccount.com`

### Conexión desde Python

```python
from google.cloud import bigquery
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json"
)
client = bigquery.Client(project="ace-scarab-484515-v1", credentials=credentials)
```

### Cruces clave entre fuentes

| Pregunta | Join |
|---|---|
| Costo mano de obra por CC vs contabilidad | `tarjas_pagos."CC"` ↔ `Reporte_Analitico.analytic_distribution` |
| Costo laboral mensual vs remuneraciones | `tarjas_pagos."Mes"` ↔ `Remuneraciones.date_from` |
| Nombre cuenta contable | `Reporte_Analitico.account_id` ↔ `Cuentas_Contables.id` |
| RUT empleado | `Empleados.formated_vat` (directo) |
| Despacho → pedido de venta | `Despachos.sale_id` ↔ `Pedidos_de_Venta.id` |
| Nombre producto | `Variantes_del_producto.product_tmpl_id` ↔ `Producto.id` |
| CC de línea contable | `JSON_EXTRACT_SCALAR(analytic_distribution, '$.ID_CC')` |

> **Nota:** `analytic_distribution` es un JSON string `{"12345": 100.0}` donde la key es el ID del CC analítico de Odoo.

---

## Hallazgos financieros KONTROLAG (al 07/05/2026)

- **Facturación total histórica:** $858.7 MM — solo 24% cobrado; $650 MM pendiente
- **Deuda crítica (+90 días):** $171.6 MM
- **Costo laboral 2025:** ~$2.200 MM acumulado
- **Ratio saludable:** abril 2026 fue el primer mes con 72% costo laboral / facturación neta
- Peak de empleados: ~70 (feb 2025); fuera de temporada: ~10
