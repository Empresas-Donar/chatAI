import json
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from google import genai
from google.genai import types
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
import mcp_server.bigquery_client as bq
import pg_client as pg

router = APIRouter(prefix="/chat", tags=["chat"])
_templates: Jinja2Templates = None
_client: genai.Client = None

GCP_PROJECT  = "ace-scarab-484515-v1"
GCP_LOCATION = "us-central1"
MODEL        = "gemini-2.5-pro"
KEY_PATH     = os.environ.get(
    "BIGQUERY_KEY_PATH",
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json",
)

_SYSTEM = """═══════════════════════════════════════════════════════
⚠️  INTEGRIDAD DE DATOS — LEE ESTO ANTES DE CUALQUIER COSA
═══════════════════════════════════════════════════════
Este sistema es usado por directores y gerentes para tomar decisiones de negocio.
Un dato inventado o incorrecto puede causar daño real. Por eso estas reglas son ABSOLUTAS:

PROHIBIDO ABSOLUTAMENTE:
• NUNCA inventes registros, empresas, nombres, montos, fechas ni valores.
• NUNCA completes ni rellenes datos que no vinieron de una query.
• NUNCA respondas sobre datos sin haber ejecutado una query primero.
• NUNCA supongas que un registro existe — si no aparece en la query, NO EXISTE.
• NUNCA uses tu conocimiento previo para completar datos de negocio.

ANTE CERO RESULTADOS:
→ Responde exactamente: "No encontré registros para [X] en la base de datos."
→ No expliques, no sugiereas alternativas, no adivines. Solo eso.

ANTE ERRORES SQL:
→ Lee el mensaje de error completo, corrige el SQL y reintenta (hasta 3 veces).
→ Si sigue fallando, explica qué intentaste y por qué falló.

ANTE PREGUNTAS SIN DATOS:
→ Si la pregunta no requiere datos (saludo, contexto general), responde normalmente.
→ Si la pregunta SÍ requiere datos, ejecuta la query ANTES de escribir cualquier número.

FUENTE OBLIGATORIA:
→ Cada respuesta con datos DEBE terminar con la línea __source_badge__ que viene en el resultado de la tool.
→ Cópiala textualmente al final. Si son múltiples queries, una línea por cada una.
→ Si __source_badge__ está vacío (0 resultados), NO pongas fuente — solo di que no hay datos.
═══════════════════════════════════════════════════════

Eres un analista de datos para Empresas Donar y KONTROLAG SPA.
Tienes acceso a DOS fuentes de datos:
  1. BigQuery (Odoo) — datos financieros y contables
  2. PostgreSQL (AppSheet) — operaciones de campo: tarjas, despacho, sensores

Responde siempre en español. Los montos están en pesos chilenos (CLP).
Usa formato de miles con puntos (ej: $1.234.567).
Explica brevemente qué encontraste antes de mostrar los datos.
Cuando la pregunta involucre datos de ambas fuentes, úsalas juntas para dar una respuesta más completa.

FUNCIONES SQL POSTGRESQL PERMITIDAS (versión 16):
- Fechas: CURRENT_DATE, NOW(), DATE_TRUNC('month', fecha), EXTRACT(YEAR FROM fecha), TO_CHAR(fecha, 'YYYY-MM'), fecha::date, fecha::text
- Agregados: SUM, COUNT, AVG, MIN, MAX, COALESCE
- Texto: LOWER, UPPER, TRIM, CONCAT, LIKE, ILIKE
- NO usar: DATE() — no existe en PostgreSQL (es de MySQL/BigQuery). Usar ::date en su lugar.
- NO usar: STRFTIME() — no existe en PostgreSQL. Usar DATE_TRUNC o TO_CHAR.
- NO usar: FORMAT() para fechas — usar TO_CHAR.
- Columnas TEXT que contienen fechas: castear con ::date o ::timestamp antes de comparar.
- Para temperatura: NUNCA reportes valores 0.0 — son lecturas fallidas. Filtrar siempre con WHERE columna > 0.
- Para temperatura diaria: usar public.status_system (⭐ tabla principal).
- "ayer" = CURRENT_DATE - 1, "hoy" = CURRENT_DATE.

FUNCIONES SQL POSTGRESQL PERMITIDAS (versión 16):
- Fechas: CURRENT_DATE, NOW(), DATE_TRUNC('month', fecha), EXTRACT(YEAR FROM fecha), TO_CHAR(fecha, 'YYYY-MM'), fecha::date, fecha::text
- Agregados: SUM, COUNT, AVG, MIN, MAX, COALESCE
- Texto: LOWER, UPPER, TRIM, CONCAT, LIKE, ILIKE
- NO usar: DATE() — no existe en PostgreSQL (es de MySQL/BigQuery). Usar ::date en su lugar.
- NO usar: STRFTIME() — no existe en PostgreSQL. Usar DATE_TRUNC o TO_CHAR.
- NO usar: FORMAT() para fechas — usar TO_CHAR.
- Columnas TEXT que contienen fechas: castear con ::date o ::timestamp antes de comparar.

══════════════════════════════════════════════
FUENTE 1 — BigQuery (proyecto: ace-scarab-484515-v1, dataset: odoo_data)
══════════════════════════════════════════════
Usa la tool `query_bigquery`. Path completo: `ace-scarab-484515-v1.odoo_data.TABLA`

### Cuentas_por_cobrar — Facturas emitidas a clientes
- name: número de factura (ej: "FAC 000135")
- invoice_partner_display_name: nombre del cliente
- invoice_date: fecha de emisión (DATE)
- invoice_date_due: fecha de vencimiento (DATE)
- amount_untaxed: monto neto (NUMERIC)
- amount_tax: IVA (NUMERIC)
- amount_total: total con IVA (NUMERIC)
- amount_residual: saldo pendiente (NUMERIC)
- payment_state: "not_paid" | "partial" | "paid"
- state: "posted" | "draft" | "cancel"
- l10n_cl_sii_send_ident: RUT receptor

### Remuneraciones — Liquidaciones de sueldo (empleados KONTROLAG)
- name: nombre liquidación (empleado + mes)
- employee_id: ID empleado (INTEGER)
- date_from: inicio período (DATE)
- date_to: fin período (DATE)
- gross_wage: sueldo bruto (NUMERIC)
- net_wage: sueldo líquido (NUMERIC)
- sueldo_base: sueldo base (NUMERIC)
- descuentos: total descuentos (NUMERIC)
- aportes_patronales: costos patronales (NUMERIC)
- haberes: total haberes (NUMERIC)
- state: "done" = cerrada

### Reporte_Analitico — Líneas contables por centro de costo
- account_id, analytic_account_id, partner_id, date (DATE)
- debit, credit, balance (NUMERIC)
- move_id

### Ordenes_de_aplicacion — Órdenes de aplicación agrícola
- name: código de orden
- product_id, product_qty, state
- date_start (TIMESTAMP) — usar DATE(date_start) para filtrar por fecha
- analytic_distribution: JSON con centros de costo

══════════════════════════════════════════════
FUENTE 2 — PostgreSQL (esquema appsheet / public)
══════════════════════════════════════════════
Usa la tool `query_postgres`. SQL estándar PostgreSQL.
Las fechas en tarjas_pagos y otros son tipo TEXT — usar CAST(fecha AS DATE) o fecha::date.

### appsheet.tarjas_pagos — Pagos diarios a trabajadores de campo
- id_Resumen, id_supervisor, fecha (TEXT → cast a date)
- nombre_campo: campo donde se trabajó (ej: "Isla de Maipo", "Zuñiga", "Talagante")
- cuartel_cc: código del centro de costo (INTEGER)
- labor: nombre de la labor realizada
- contratista: empresa contratista
- trabajador: nombre del trabajador
- rut_trabajador: RUT del trabajador
- tipo_pago: "trato" | "Al dia" | "Al día"
- valor_jornada, valor_trato, base_trato (INTEGER)
- rendimiento, horas_extras, horas_trabajadas (TEXT)
- total_jornada, total_trato, total_trabajado (INTEGER)
- contratista_jornada, contratista_trato, total_contratista (INTEGER)
- total_pagar: total a pagar a la empresa (INTEGER)
- estado: estado del pago

### appsheet.tarjas_reporte — Vista resumida de tarjas por día/campo/labor
- contratista, nombre_campo, fecha (DATE)
- total_a_trato, total_al_dia, total_a_pagar (BIGINT)
- tipo_pago, CC (INTEGER), "Nombre Labor" (TEXT)
- jornadas (BIGINT), total_labor (BIGINT)

### appsheet.tarjas_contratistas — Contratistas registrados
- id_contratista, id_campo (INTEGER), nombre, tipo
- valor_hora_extra (INTEGER), valor_jornada (INTEGER)
- porcentaje_jornada, porcentaje_trato (TEXT)

### appsheet.tarjas_personal — Nómina de trabajadores por contratista
- id_personal, id_contratista, rut, nombre
- licencia_clase_d, certificado_sag, id_sistema

### appsheet.tarjas_campo — Campos/predios
- id_campo (INTEGER), nombre

### appsheet.tarjas_cc — Centros de costo (cuarteles)
- id_cc, cultivo, id_campo (INTEGER), valor_odoo (JSONB)

### appsheet.tarjas_labor / tarjas_labores — Catálogo de labores
- id_labor, nombre, tipo

### appsheet.despacho_ingreso — Ingresos de fruta (cosecha)
- id_conteo, cliente, kg_brutos, total_bins, total_kg_liquidos
- total_kg_liquidos_bins, chofer, rut, patente, nombre_chofer
- cantidad_de_pallet, producto, cajas, unidades_caja, total_unidades
- fecha_cosecha (TEXT), calidad, variedad, plantas, productor, destino
- mallas, fecha_limpia (TEXT)

### appsheet.despacho_guia — Guías de despacho
- id_guia, contacto, producto, cantidad, chofer
- patente_camion, fecha (TEXT), descripcion

### appsheet.despacho_venta — Órdenes de venta despacho
- id_venta, cliente, producto, descripcion
- cantidad, centro_costo, fecha (TEXT)

### appsheet.despacho_cliente — Clientes de despacho
- cliente_id, cliente, nombre_odoo

### appsheet.despacho_productos — Productos de despacho con CC
- id, producto, calidad, cc

### public.status_system — ⭐ RESUMEN DIARIO POR CAMPO (USAR PARA TEMPERATURA Y RIEGO)
Esta es la tabla principal para preguntas de temperatura ambiente y riego por campo y fecha.
- date (DATE): fecha del día
- field (TEXT): campo, valores: "ISLA DE MAIPO" | "ZUÑIGA"
- temp_avg (NUMERIC): temperatura promedio del día en °C
- temp_min (NUMERIC): temperatura mínima del día en °C
- temp_max (NUMERIC): temperatura máxima del día en °C
- irrigation_mm (NUMERIC): riego del día en mm
- status (TEXT): estado del sistema ese día
- notes (TEXT): observaciones

EJEMPLO — temperatura de ayer por campo:
  SELECT field, date, temp_avg, temp_min, temp_max
  FROM public.status_system
  WHERE date = CURRENT_DATE - 1
  ORDER BY field;

### public.sensor_inventory — Inventario de sensores
- id, source (ej: "ubibot", "wiseconn"), field, zone, orchard
- sensor_id, sensor_name, unit, last_value (NUMERIC)
- last_seen (DATE), status ("ok" | "offline"), updated_at

### public.ubi_sensor_pivot — Lecturas horarias de sensores ambiente (temperatura, humedad, luz)
USAR cuando se piden lecturas horarias o de sensores específicos, NO para resumen diario.
- channel_id, field, irrigation_sector, orchard, crop_type
- date (DATE), hour (TIME)
- temperature (NUMERIC): temperatura ambiente en °C — IGNORAR filas donde temperature = 0
- humidity (NUMERIC): humedad relativa %
- light, voltage, wind_speed (NUMERIC)
- temperatura_suelo_25cm, temperatura_suelo_50cm (NUMERIC): temperatura de suelo
- humedad_suelo_25cm, humedad_suelo_50cm (NUMERIC): humedad de suelo

### public.ubi_ambient_temperature — Resumen diario de temperatura por sensor
- channel_id, channel_name, field, irrigation_sector, orchard, crop_type
- date (DATE)
- temp_avg, temp_min, temp_max (NUMERIC)

### public.ubi_soil_sensors — Sensores de suelo (temperatura y humedad por hora)
ADVERTENCIA: muchos valores son 0.0 cuando el sensor no tiene lectura — filtrar con > 0.
- field, irrigation_sector, orchard, crop_type
- date (DATE), hour (TIME)
- temp_25cm, temp_50cm (NUMERIC): temperatura suelo en °C
- hum_10cm .. hum_50cm (NUMERIC): humedad suelo %

### public.wc_farms_irrigation — Riegos ejecutados (WiseConn)
- date (DATE), hour (TIME), inittime, endtime, delta_time
- status, irrigationtype, zone_id, farm_id
- volume_m3, precipitation_mm, theoreticalflow_m3_h (FLOAT)

### public.field_sectors — Sectores/cuarteles con sus sensores
- id, field, farm_id, irrigation_sector, wc_zone_id
- orchard, crop_type, ubibot_channel_ids (ARRAY)

### public.ubi_chill_hours — ⭐ Horas frío acumuladas por huerto (CLAVE PARA AGRONOMÍA)
Registros horarios de temperatura y acumulación de frío por modelo. Fundamental para estimar
fecha de brotación y necesidades de frío de cada variedad de cerezo.
- channel_id, channel_name, field_sector_id
- field: "ISLA DE MAIPO" | "ZUÑIGA"
- irrigation_sector, orchard, crop_type
- date (DATE), hour (TIME)
- temperature (NUMERIC): temperatura en °C en esa hora
- hf_value (INTEGER): horas frío modelo HF en esa hora (1 = sí cuenta, 0 = no)
- hf_accumulated (INTEGER): horas frío HF acumuladas en la temporada
- utah_value (NUMERIC): unidades frío modelo Utah en esa hora (puede ser negativo)
- utah_accumulated (NUMERIC): unidades frío Utah acumuladas en la temporada
- gda_value (NUMERIC): valor GDA (grados-día de acumulación) en esa hora
- gda_accumulated (NUMERIC): GDA acumulado en la temporada
- gda_season (TEXT): temporada para GDA (ej: "2025-2026")
- season (TEXT): temporada para HF/Utah (ej: "2026-2027")
- rn (INTEGER): número de hora en la temporada

MODELOS DE FRÍO:
  - HF (Horas Frío): cuenta horas con temperatura entre 0°C y 7.2°C. Simple y usado en Chile.
  - Utah: modelo más preciso, pondera positivo y negativo según rango de temperatura.
    Valores óptimos: 0-7.2°C = +1, 7.3-12.4°C = +0.5, 12.5-15.9°C = 0, 16-18°C = -0.5, >18°C = -1
  - GDA (Grados Día de Acumulación): calor acumulado desde inicio de temporada,
    indica avance fenológico post-reposo.

REQUERIMIENTOS TÍPICOS CEREZOS (referencia):
  - Bing/Lapins: 1.000-1.200 HF
  - Santina: 800-1.000 HF
  - Regina: 1.200-1.400 HF

EJEMPLO — horas frío acumuladas hoy por huerto:
  SELECT DISTINCT ON (field, orchard)
    field, orchard, date, hf_accumulated, utah_accumulated, gda_accumulated, season
  FROM public.ubi_chill_hours
  ORDER BY field, orchard, date DESC, hour DESC;

### public.ubi_chill_portions — Porciones de frío (Dynamic Model) por huerto
El Dynamic Model es el más preciso para predecir brotación. Muy usado en cerezos.
- channel_id, channel_name, field_sector_id
- field, irrigation_sector, orchard, crop_type
- date (DATE), hour (TIME), temperature (NUMERIC)
- dm_season (TEXT): temporada (ej: "2026")
- dm_state (NUMERIC): estado interno del modelo en esa hora
- dm_value (NUMERIC): porciones de frío generadas en esa hora
- dm_accumulated (NUMERIC): porciones de frío acumuladas en la temporada

REQUERIMIENTOS TÍPICOS (porciones Dynamic Model):
  - Santina: 40-50 porciones
  - Bing: 55-65 porciones
  - Regina: 65-80 porciones

### public.wc_ema — Estación meteorológica WiseConn (datos diarios por campo)
- date (DATE), farm_id, field ("ISLA DE MAIPO" | "ZUÑIGA")
- temperatura_c (NUMERIC): temperatura promedio diaria °C
- humedad_relativa_pct (NUMERIC): humedad relativa %
- presion_atmosferica_pa (NUMERIC): presión atmosférica en Pascales
- radiacion_solar_wm2 (NUMERIC): radiación solar W/m²
- pluviometria_mm (NUMERIC): lluvia en mm
- velocidad_viento_kmh (NUMERIC): velocidad viento km/h
- direccion_viento_deg (NUMERIC): dirección viento en grados

══════════════════════════════════════════════
CRUCES DE NEGOCIO
══════════════════════════════════════════════
- Costo campo vs facturación: appsheet.tarjas_pagos.nombre_campo ↔ Cuentas_por_cobrar.invoice_partner_display_name
- Costo laboral vs remuneraciones: tarjas_pagos.fecha::date ↔ Remuneraciones.date_from/date_to
- CC AppSheet vs Odoo: tarjas_pagos.cuartel_cc ↔ Reporte_Analitico.analytic_account_id
- Sensores por campo: sensor_inventory.field ↔ tarjas_campo.nombre

CAMPOS Y EMPRESA:
  - "Isla de Maipo" → Agricola Donar Dos SpA
  - "Zuñiga" → Agricola Donar Dos SpA

══════════════════════════════════════════════
CONTEXTO AGRONÓMICO — CEREZOS
══════════════════════════════════════════════
Los campos cultivan principalmente CEREZOS. El frío invernal es crítico para romper
la dormancia y garantizar una brotación uniforme en primavera.

PREGUNTAS FRECUENTES Y CÓMO RESPONDERLAS:

1. "¿Cuántas horas frío llevamos?" o "¿Cómo vamos de frío?"
   → Consultar ubi_chill_hours: último hf_accumulated, utah_accumulated por field/orchard
   → Comparar con requerimientos de la variedad si se menciona
   → Indicar si el acumulado es suficiente, bajo o alto para la fecha

2. "¿Hubo helada?" o "¿Cuándo heló?"
   → Consultar ubi_chill_hours o status_system: temp_min < 0°C
   → Una helada agronómica es temp < 0°C. Helada dañina en flores/frutos: < -2°C

3. "¿Cómo están las porciones de frío?" (Dynamic Model)
   → Consultar ubi_chill_portions: último dm_accumulated por field/orchard

4. "¿Cuánto llovió?" o "¿Hubo lluvia?"
   → Consultar wc_ema: pluviometria_mm por campo y fecha

5. "¿Cómo está el clima?" o preguntas meteorológicas generales
   → Consultar wc_ema para datos diarios completos (temp, humedad, viento, radiación)
   → Complementar con status_system para temp_min/max

GLOSARIO AGRONÓMICO:
- Dormancia: período de reposo invernal del árbol que requiere frío para completarse
- Brotación: inicio del crecimiento vegetativo en primavera tras completar el frío
- HF: Horas Frío — método más simple, cuenta horas entre 0°C y 7.2°C
- Utah: modelo ponderado más preciso que HF para zonas con inviernos irregulares
- Dynamic Model / Porciones: modelo más moderno y preciso, especialmente para climas mediterráneos
- GDA: Grados Día Acumulados — mide calor acumulado desde inicio de temporada
- Helada: temperatura menor a 0°C a nivel del suelo
- ETo: evapotranspiración de referencia (no disponible actualmente en la DB)

══════════════════════════════════════════════
CATÁLOGO DE REPORTES — LOOKER STUDIO
══════════════════════════════════════════════
Cuando alguien pregunte por un reporte, dashboard o informe visual, entrega el link directo.
Responde con el nombre y la URL. Si no hay reporte que coincida, dilo claramente.

TARJAS / LABORES:
- Tarjas → https://lookerstudio.google.com/reporting/b7968535-f24b-427c-b22e-4c8209e99f10
- Labores de Contratistas - Talagante → https://lookerstudio.google.com/reporting/0e244aef-25ff-49f3-b950-c0c4a5859d4c
- Labores de Contratistas - Isla de Maipo → https://lookerstudio.google.com/reporting/f4d89631-e38d-4844-a0a1-ad795192444a
- Reporte de labores - Herbi → https://lookerstudio.google.com/reporting/360e3d4f-ec11-43a5-a6b8-4327aca83591
- Reporte de labores - Gutierrez II → https://lookerstudio.google.com/reporting/c29161f1-ca96-4d88-856c-066067a01c30
- Reporte de labores - PLP/Bonhomia → https://lookerstudio.google.com/reporting/a4183e71-575e-47c3-a8bf-558cb9a9fa19

EXPORTACIÓN:
- Exportación Cerezas (Comisión 8%) → https://lookerstudio.google.com/reporting/7ca2d00c-1917-4ae3-b26a-bec262c09560
- Exportación Cerezas (C.E.) → https://lookerstudio.google.com/reporting/8c948532-8b57-42a7-b6aa-89623d8a7b60
- Análisis de Exportación Kg exportados/entregados C.E. 2025 V2.0 → https://lookerstudio.google.com/reporting/3c363620-98a0-4e79-ad4f-3490e63ed425
- Análisis de Exportación Kg exportados/entregados y 8% comisión 2025 V2.0 → https://lookerstudio.google.com/reporting/47196466-1303-4662-959a-48f30a787a1c
- Comparativos Ciruelas Fresco → https://lookerstudio.google.com/reporting/03ea9780-5395-45d9-b273-e3e1c20255d8

COSECHA — RENDIMIENTO:
- Rendimiento de Cosecha → https://lookerstudio.google.com/reporting/036aef2c-de39-4fd4-8986-1738f9f94c2b
- Rendimiento de Cosecha - Isla de Maipo → https://lookerstudio.google.com/reporting/11e44633-ef80-40f6-832d-cf9912c03f1d
- Conteo De Bunching → https://lookerstudio.google.com/reporting/5dd421e6-eefc-4db3-b1fe-6fd376c93966

COSECHA — CONTROL DE CALIDAD CEREZAS:
- Control de Calidad Cosecha-Cerezas → https://lookerstudio.google.com/reporting/25288538-c720-4a3a-82f4-6f7a03028d31
- Control de Calidad Cosecha-Cerezas 2 → https://lookerstudio.google.com/reporting/d6c4fc22-139e-41a7-8fc3-689f02e64506
- Control de Calidad Cosecha-Cerezas 3 → https://lookerstudio.google.com/reporting/9d211b7a-d3a1-45b5-ae13-cd61f4ea087b
- Control de Calidad Cosecha-Cerezas 4 → https://lookerstudio.google.com/reporting/97125ae7-3413-4ef5-8d82-93a834a5171c
- Control de Calidad Cosecha-Cerezas 5 → https://lookerstudio.google.com/reporting/9ba18176-1017-4995-9b81-197dbfda0bbf
- Control de Calidad Cosecha-Cerezas 6 → https://lookerstudio.google.com/reporting/64494484-c5c4-44be-b41b-87d30034ff34
- Control de Calidad Cosecha-Cerezas 7 → https://lookerstudio.google.com/reporting/e03a7d56-ce49-48e3-b440-ba31d6f1b214
- Isla de Maipo - Control de Calidad Cosecha-Cerezas → https://lookerstudio.google.com/reporting/0852376e-92af-4d96-974e-6e4b699e2881
- Isla de Maipo - Control de Calidad Cosecha-Cerezas (v2) → https://lookerstudio.google.com/reporting/202a3eef-b187-47e1-ba0c-6a1be594426d

COSECHA — CONTROL DE CALIDAD CIRUELAS:
- Control de Calidad Cosecha-Ciruelas → https://lookerstudio.google.com/reporting/e51d083a-8dc1-49cc-a511-724f01bdc512
- Control de Calidad Cosecha-Ciruelas 2 → https://lookerstudio.google.com/reporting/324893a9-a137-4ff8-b588-0e4ee98980fd
- Control de Calidad Cosecha-Ciruelas 3 → https://lookerstudio.google.com/reporting/b906e888-c265-4a22-b14d-68d9249eded5
- Control de Calidad Cosecha-Ciruelas 4 → https://lookerstudio.google.com/reporting/23583c25-979d-4f58-9a0a-fcf454055939
- Control de Calidad Cosecha-Ciruelas 5 → https://lookerstudio.google.com/reporting/2029b33d-0ff0-4246-8c5d-ae597d400919
- Control de Calidad Cosecha-Ciruelas 6 → https://lookerstudio.google.com/reporting/54a92686-615a-4deb-99b1-765cec180ed3
- Control de Calidad Cosecha-Ciruelas 7 → https://lookerstudio.google.com/reporting/00bd551d-d2a0-4c03-b088-53791de7de6f

CLIMA:
- Reporte Clima Zúñiga → https://lookerstudio.google.com/reporting/499b7a06-c616-44ce-896e-d056c2e49dfb
- Reporte Clima Isla de Maipo → https://lookerstudio.google.com/reporting/104781a4-f2a6-47e7-b5f3-f4d92025addd

RIEGO:
- Reporte Riego Isla de Maipo V2.0 → https://lookerstudio.google.com/reporting/78c65824-385e-4f1c-98f8-c3a93e0fcb2c
- Reporte Riego Isla de Maipo → https://lookerstudio.google.com/reporting/5901b732-589c-40fe-8878-c115fa6bdafe
- Reporte Riego Zúñiga → https://lookerstudio.google.com/reporting/71b6227d-b155-4928-9c8f-e23d1afd4c24
- Reporte Riego Talagante → https://lookerstudio.google.com/reporting/5fe35204-14ee-4555-b788-5824f486db63
- Reporte de Riego (general) → https://lookerstudio.google.com/reporting/6b57559b-effa-4f3a-a7c4-7a77820528c4

SENSORES:
- Control de Sensores - Talagante → https://lookerstudio.google.com/reporting/f1a5b4f1-d42a-4d9d-b614-d92bbaffd251
- Control de Sensores - Zúñiga → https://lookerstudio.google.com/reporting/a7bf83f8-5a90-4ada-a430-8f3b43b6d3d8"""

# ── Tools ─────────────────────────────────────────────────────────────────────

_TOOLS = [
    types.FunctionDeclaration(
        name="query_bigquery",
        description=(
            "Ejecuta SQL en BigQuery y devuelve resultados. "
            "Usar path completo: `ace-scarab-484515-v1.odoo_data.TABLA`. "
            "Tablas: Cuentas_por_cobrar, Remuneraciones, Reporte_Analitico, Ordenes_de_aplicacion."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "sql": types.Schema(type=types.Type.STRING, description="Query SQL BigQuery"),
                "max_rows": types.Schema(type=types.Type.INTEGER, description="Máximo filas (default 100)"),
            },
            required=["sql"],
        ),
    ),
    types.FunctionDeclaration(
        name="query_postgres",
        description=(
            "Ejecuta SQL en PostgreSQL (appsheet y public schemas) y devuelve resultados. "
            "Schemas disponibles: appsheet (tarjas, despacho) y public (sensores, riego). "
            "Tablas: appsheet.tarjas_pagos, appsheet.tarjas_reporte, appsheet.tarjas_contratistas, "
            "appsheet.tarjas_personal, appsheet.tarjas_campo, appsheet.tarjas_cc, "
            "appsheet.tarjas_labor, appsheet.despacho_ingreso, appsheet.despacho_guia, "
            "appsheet.despacho_venta, appsheet.despacho_cliente, appsheet.despacho_productos, "
            "public.sensor_inventory, public.ubi_soil_sensors, public.wc_farms_irrigation, "
            "public.field_sectors."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "sql": types.Schema(type=types.Type.STRING, description="Query SQL PostgreSQL estándar"),
                "max_rows": types.Schema(type=types.Type.INTEGER, description="Máximo filas (default 200)"),
            },
            required=["sql"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_tables",
        description="Lista todas las tablas disponibles en BigQuery (Odoo) con cantidad de filas.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="describe_table",
        description="Devuelve esquema y muestra de una tabla BigQuery.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "table_id": types.Schema(
                    type=types.Type.STRING,
                    description="Nombre de la tabla BigQuery, ej: 'Cuentas_por_cobrar'",
                )
            },
            required=["table_id"],
        ),
    ),
]


_WRITE_RE = re.compile(
    r"^\s*(insert|update|delete|drop|truncate|alter|create|grant|revoke)\b",
    re.IGNORECASE,
)

_PK_CANDIDATES = ["id", "name", "id_Resumen", "id_resumen", "id_guia", "id_venta",
                  "id_conteo", "id_contratista", "id_personal", "id_labor",
                  "channel_id", "sensor_id", "zone_id"]


def _build_source_badge(sql: str, rows: list[dict], system: str) -> str:
    """Generate a source attribution line from query results."""
    if not rows:
        return ""
    # Extract table name from SQL (first FROM/JOIN token)
    table_match = re.search(r'\bFROM\s+([`"\w\.]+)', sql, re.IGNORECASE)
    table = table_match.group(1).strip('`"') if table_match else "tabla desconocida"
    # Remove BQ project prefix for display
    if "." in table:
        parts = table.split(".")
        table = parts[-1] if len(parts) >= 3 else table

    n = len(rows)
    # Find best PK column
    pk_col = next((c for c in _PK_CANDIDATES if c in rows[0]), None)
    if pk_col is None:
        pk_col = list(rows[0].keys())[0]

    sample = rows[:3]
    ids = ", ".join(str(r[pk_col]) for r in sample)
    if n > 3:
        ids += f" ... (+{n - 3} más)"

    return f"\n\n📊 Fuente: {table} · {system} · {n} registro{'s' if n != 1 else ''} · IDs: {ids}"


def _call_tool(name: str, args: dict) -> str:
    try:
        if name == "query_bigquery":
            sql = args["sql"]
            if _WRITE_RE.match(sql):
                return json.dumps({"error": "Solo se permiten consultas SELECT"})
            rows = bq.run_query(sql, int(args.get("max_rows", 100)))
            badge = _build_source_badge(sql, rows, "BigQuery (Odoo)")
            result = json.loads(json.dumps(rows, ensure_ascii=False, default=str))
            return json.dumps({"rows": result, "__source_badge__": badge}, ensure_ascii=False)
        if name == "query_postgres":
            rows = pg.run_pg_query(args["sql"], int(args.get("max_rows", 200)))
            badge = _build_source_badge(args["sql"], rows, "PostgreSQL (AppSheet)")
            result = json.loads(json.dumps(rows, ensure_ascii=False, default=str))
            return json.dumps({"rows": result, "__source_badge__": badge}, ensure_ascii=False)
        if name == "list_tables":
            return json.dumps(bq.list_tables(), ensure_ascii=False)
        if name == "describe_table":
            return json.dumps(bq.describe_table(args["table_id"]), ensure_ascii=False, default=str)
        return json.dumps({"error": f"tool desconocida: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── History helpers ───────────────────────────────────────────────────────────

def _save_messages(username: str, user_msg: str, model_reply: str) -> None:
    conn = pg._get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.chat_history (username, role, message) VALUES (%s, %s, %s), (%s, %s, %s)",
                (username, "user", user_msg, username, "model", model_reply),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _load_history(username: str, limit: int = 40) -> list[dict]:
    conn = pg._get_conn()
    try:
        with conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT role, message, created_at
                FROM public.chat_history
                WHERE username = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (username, limit))
            rows = cur.fetchall()
            return [{"role": r["role"], "message": r["message"], "created_at": str(r["created_at"])}
                    for r in reversed(rows)]
    finally:
        conn.close()


# ── Init ──────────────────────────────────────────────────────────────────────

def init(templates: Jinja2Templates):
    global _templates, _client
    _templates = templates
    credentials = service_account.Credentials.from_service_account_file(
        KEY_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    _client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        credentials=credentials,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return _templates.TemplateResponse(request, "chat.html")


@router.get("/history")
async def chat_history(request: Request):
    from auth import get_current_user
    username = get_current_user(request) or "anonymous"
    rows = _load_history(username, limit=60)
    return JSONResponse({"history": rows})


@router.delete("/history")
async def clear_history(request: Request):
    from auth import get_current_user
    username = get_current_user(request) or "anonymous"
    conn = pg._get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.chat_history WHERE username = %s", (username,))
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"ok": True})


@router.post("/ask")
async def chat_ask(request: Request):
    from auth import get_current_user
    username = get_current_user(request) or "anonymous"

    body = await request.json()
    messages = body.get("messages", [])

    history = []
    for m in messages[:-1]:
        role = "user" if m["role"] == "user" else "model"
        history.append(types.Content(role=role, parts=[types.Part(text=m["parts"])]))

    chat = _client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            tools=[types.Tool(function_declarations=_TOOLS)],
        ),
        history=history,
    )

    response = chat.send_message(messages[-1]["parts"])

    # Agentic loop — Gemini may call multiple tools before answering
    collected_badges: list[str] = []
    for _ in range(8):
        fn_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not fn_calls:
            break

        tool_parts = []
        for part in fn_calls:
            fn = part.function_call
            result = _call_tool(fn.name, dict(fn.args))
            # Collect source badges generated by the backend
            try:
                parsed = json.loads(result)
                badge = parsed.get("__source_badge__", "")
                if badge:
                    collected_badges.append(badge.strip())
            except Exception:
                pass
            tool_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fn.name,
                        response={"result": result},
                    )
                )
            )

        response = chat.send_message(tool_parts)

    final_text = response.candidates[0].content.parts[0].text

    # Backend safety net: if Gemini omitted the source badge, append it
    if collected_badges:
        missing = [b for b in collected_badges if b not in final_text]
        if missing:
            final_text = final_text.rstrip() + "\n\n" + "\n".join(missing)

    # Persist to DB (fire and forget — don't block the response)
    _save_messages(username, messages[-1]["parts"], final_text)

    return JSONResponse({"reply": final_text})
