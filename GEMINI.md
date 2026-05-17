# Contexto del Proyecto — AppSheet Migration + Odoo BigQuery

Este archivo provee contexto completo para responder preguntas de negocio combinando datos de AppSheet (PostgreSQL) y Odoo (BigQuery).

---

## Cliente: KONTROLAG SPA

- **RUT:** 77235191-7
- **Rubro:** Servicios agrícolas (supervisión de cuadrillas, instalaciones) para empresas de la zona central de Chile
- **Estacionalidad:** 70 empleados en peak (febrero), ~10 fuera de temporada
- **Facturación concentrada:** diciembre–mayo (temporada de fruta)
- **Empresa relacionada:** Agricola Donar Dos SpA es cliente directo de KONTROLAG (grupo Donar)

---

## Fuente 1: AppSheet → PostgreSQL

**Esquema:** `appsheet`  
**Conexión:** variables de entorno en `.env` (no hardcodear credenciales)

### App `contratistas_isla_maipo`

Gestión de mano de obra agrícola en predios Zuñiga, Isla de Maipo y Talagante.

#### Tablas principales

**`contratistas`** — empresas contratistas con condiciones pactadas
- `Id_Supervisor` (PK, TEXT)
- `Campo` — predio (Zuñiga, Isla de Maipo, Talagante)
- `Supervisor` — nombre del supervisor
- `Empresa_Contratista` — razón social
- `Valor_Jornada` — pago diario por trabajador
- `Valor_Hora_Extra`
- `%Jornada_Bono`, `%Trato` — porcentajes de bonificación
- `Fijo_Jornada`, `Bono_Extra`

**`trabajadores`** — nómina por contratista
- `Id_Trabajador` (PK, TEXT)
- `Contratista` (FK → contratistas)
- nombre, RUT, estado

**`tratos`** — contratos de labor por campo/CC/período
- `Id_Tratos` (PK, TEXT)
- `Campo`, `Centro de Costo` (CC)
- `Labor` (FK → labor)
- `Fecha Inicio Trato`, `Fecha Termino Trato`
- `Valor del Trato` — precio unitario por unidad producida

**`registro`** — movimientos diarios por trabajador
- `Id_Registro` (PK, TEXT)
- `Fecha`, `Campo`, `CC`, `Labor`, `Contratista`, `Trabajador`
- `Jornada`, `Horas Extras`, `Bonificación`

**`registro_trato`** — unidades de trato por registro
- vincula registro ↔ tratos, registra `Unidades`

**`pagos`** — liquidación diaria completa
- `ID_Resumen` (PK, TEXT)
- `Campo`, `Fecha`, `Mes`, `Contratista`, `CC`, `Labor`, `Trabajador`, `Empresa`
- `Jornada`, `Trato`, `Unidades Trato`
- `Valor Jornada`, `Valor Trato`
- `Total Trabajador`, `Total Contratista`, `Total a Pagar`
- `Cultivo`, `Tipo de pago` (A Trato / Jornada)
- `Día Hábil`

**`labor`** — catálogo de labores agrícolas
- `Id_Labor` (PK), `Labor` (nombre)

**`cultivos`** / **`cultivos_detalle`** — cultivo por campo y CC

### App `tarjas`

Cuadrillas en campo, con integración directa a Odoo.

- `tarjas_reporte_odoo` (VIEW) — mapea pagos diarios a líneas de pedido de compra Odoo:
  - `"Vendedor"` = contratista
  - `"Lineas del pedido/Producto/Nombre"` = labor
  - `"Lineas del pedido/Cantidad"` = jornadas
  - `"Lineas del pedido/Precio un."` = total unitario
  - `"order_line/product_id"` = código labor en Odoo
  - `"order_line/analytic_distribution"` = distribución por CC en JSON

### App `medicion_pozos`

Registros de niveles de pozos de agua. En proceso de migración.

---

## Fuente 2: Odoo → BigQuery

**GCP Project:** `ace-scarab-484515-v1`  
**Dataset:** `odoo_data`  
**Service Account:** `odoo-bigquery@ace-scarab-484515-v1.iam.gserviceaccount.com`  
**Clave JSON local:** `/Users/bedomax/startups/donar/bigquery-odoo-key.json`  
**gcloud account:** `gestion@empresasdonar.cl`

> Las tablas sin sufijo `_staging_*` están vacías. Siempre usar las staging.

### Conexión Python

```python
from google.cloud import bigquery
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json"
)
client = bigquery.Client(project="ace-scarab-484515-v1", credentials=credentials)
```

### Tabla: `Cuentas_por_cobrar` (109 filas)

Facturas emitidas — `account.move` de Odoo.

| Campo | Significado |
|---|---|
| `name` | Número de factura (e.g. `FAC 000135`) |
| `invoice_partner_display_name` | Nombre del cliente |
| `invoice_date` | Fecha emisión |
| `invoice_date_due` | Fecha vencimiento |
| `amount_untaxed` | Monto neto |
| `amount_tax` | IVA |
| `amount_total` | Total con IVA |
| `amount_residual` | Saldo pendiente |
| `payment_state` | `not_paid` / `partial` / `paid` |
| `state` | `posted` / `draft` / `cancel` |
| `l10n_cl_sii_send_ident` | RUT receptor |
| `x_studio_estado_aprobacin` | Campo custom Odoo Studio |

### Tabla: `Remuneraciones` (1.199 filas)

Liquidaciones de sueldo — `hr.payslip` de Odoo.

| Campo | Significado |
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

### Tabla: `Reporte_Analítico_staging_1778157508` (50.000 filas)

Líneas contables por centro de costo.

| Campo | Significado |
|---|---|
| `account_id` | Cuenta contable |
| `analytic_account_id` | Centro de costo / proyecto |
| `partner_id` | Cliente o proveedor |
| `date` | Fecha del movimiento |
| `debit` / `credit` | Debe / Haber |
| `balance` | Saldo neto |
| `move_id` | Referencia al asiento contable |

### Tabla: `Ordenes_de_aplicación_staging_1778157654` (1.441 filas)

Órdenes de aplicación agrícola.

| Campo | Significado |
|---|---|
| `name` | Código de la orden |
| `product_id` | Producto/insumo aplicado |
| `picking_id` | Guía de despacho asociada |
| `partner_id` | Cliente destinatario |
| `date` | Fecha de la orden |
| `product_qty` | Cantidad |
| `state` | Estado de la orden |

---

## Cruces clave entre fuentes

| Pregunta de negocio | Join |
|---|---|
| Costo mano de obra por CC vs lo contabilizado | `pagos."CC"` ↔ `Reporte_Analítico.analytic_account_id` |
| Costo laboral mensual vs remuneraciones Odoo | `pagos."Mes"` ↔ `Remuneraciones.date_from` |
| Lo facturado al cliente vs lo que costó producirlo | `Cuentas_por_cobrar.invoice_partner_display_name` ↔ `pagos."Empresa"` |
| Órdenes de aplicación vs tratos ejecutados | `Ordenes_de_aplicación.partner_id` ↔ `contratistas."Campo"` |
| Rentabilidad por contratista | `pagos."Total a Pagar"` agrupado por `"Contratista"` vs facturas |

### Campo AppSheet → Empresa en Odoo

| Campo | Empresa |
|---|---|
| Isla de Maipo | Agricola Donar Dos SpA |
| Zuñiga | Agricola Donar Dos SpA |
| Talagante | Verificar en `Cuentas_por_cobrar` |

---

## Hallazgos financieros (al 07/05/2026)

- **Facturación total histórica:** $858.7 MM — solo 24% cobrado; $650 MM pendiente
- **Deuda crítica (+90 días):** $171.6 MM
  - Exportadora Rancagua: $198.8 MM vencidos (~128 días)
  - Agricola Curico: $107.7 MM vencidos (~145 días)
  - Agricola Donar Dos SpA: $50.2 MM vencidos (~129 días)
- **Costo laboral 2025:** ~$2.200 MM acumulado; facturación llegó rezagada en dic 2025
- **Ratio saludable:** abril 2026 fue el primer mes con 72% costo laboral / facturación neta

---

## Convenciones importantes

- Nombres de columnas en **español exacto** — no renombrar (AppSheet es case-sensitive)
- PKs siempre `TEXT` — AppSheet genera sus propios IDs string
- Nunca migrar columnas `_RowNumber` ni `Related_*`
- Usar `ON CONFLICT` (UPSERT) siempre
- Dinero y porcentajes: `NUMERIC`, nunca `TEXT`
- Limpieza obligatoria: `$18.000` → `18000`, `45,00%` → `0.45`, fechas → `YYYY-MM-DD`
