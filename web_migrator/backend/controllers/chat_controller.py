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

_SYSTEM = """Eres un analista de datos experto para Empresas Donar y KONTROLAG SPA.
Tienes acceso a DOS fuentes de datos:
  1. BigQuery (Odoo) — datos financieros y contables
  2. PostgreSQL (AppSheet) — operaciones de campo: tarjas, despacho, sensores

Responde siempre en español. Los montos están en pesos chilenos (CLP).
Usa formato de miles con puntos (ej: $1.234.567).
Explica brevemente qué encontraste antes de mostrar los datos.
Cuando la pregunta involucre datos de ambas fuentes, úsalas juntas para dar una respuesta más completa.

REGLA OBLIGATORIA — FUENTE DE DATOS:
Al final de CADA respuesta que incluya datos, agrega siempre una línea con el formato exacto:
  📊 Fuente: [nombre tabla o tablas] · [BigQuery (Odoo) | PostgreSQL (AppSheet) | Ambas fuentes]

Ejemplos:
  📊 Fuente: Cuentas_por_cobrar · BigQuery (Odoo)
  📊 Fuente: appsheet.tarjas_pagos · PostgreSQL (AppSheet)
  📊 Fuente: appsheet.tarjas_pagos + Cuentas_por_cobrar · Ambas fuentes
  📊 Fuente: public.status_system · PostgreSQL (AppSheet)

Si la respuesta no usa datos (ej: saludo o pregunta de contexto), omite la línea de fuente.

REGLAS CRÍTICAS DE CALIDAD:
- Nunca reportes valores 0.0 como datos válidos de temperatura o humedad de sensores — son lecturas fallidas. Filtra siempre con WHERE columna != 0 o columna > 0 en ubi_soil_sensors y ubi_sensor_pivot.
- Para preguntas de temperatura del día o "ayer" por campo: USA SIEMPRE public.status_system primero — tiene el resumen diario consolidado (temp_avg, temp_min, temp_max) que es lo que se muestra en el dashboard de sensores.
- "ayer" = CURRENT_DATE - 1, "hoy" = CURRENT_DATE, "esta semana" = CURRENT_DATE - 7.
- Si una query falla con error de PostgreSQL, lee el mensaje de error, corrige el SQL y vuelve a intentar.

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

══════════════════════════════════════════════
CRUCES DE NEGOCIO
══════════════════════════════════════════════
- Costo campo vs facturación: appsheet.tarjas_pagos.nombre_campo ↔ Cuentas_por_cobrar.invoice_partner_display_name
- Costo laboral vs remuneraciones: tarjas_pagos.fecha::date ↔ Remuneraciones.date_from/date_to
- CC AppSheet vs Odoo: tarjas_pagos.cuartel_cc ↔ Reporte_Analitico.analytic_account_id
- Sensores por campo: sensor_inventory.field ↔ tarjas_campo.nombre

CAMPOS Y EMPRESA:
  - "Isla de Maipo" → Agricola Donar Dos SpA
  - "Zuñiga" → Agricola Donar Dos SpA"""

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


def _call_tool(name: str, args: dict) -> str:
    try:
        if name == "query_bigquery":
            sql = args["sql"]
            if _WRITE_RE.match(sql):
                return json.dumps({"error": "Solo se permiten consultas SELECT"})
            rows = bq.run_query(sql, int(args.get("max_rows", 100)))
            return json.dumps(rows, ensure_ascii=False, default=str)
        if name == "query_postgres":
            rows = pg.run_pg_query(args["sql"], int(args.get("max_rows", 200)))
            return json.dumps(rows, ensure_ascii=False, default=str)
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
    for _ in range(8):
        fn_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not fn_calls:
            break

        tool_parts = []
        for part in fn_calls:
            fn = part.function_call
            result = _call_tool(fn.name, dict(fn.args))
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

    # Persist to DB (fire and forget — don't block the response)
    _save_messages(username, messages[-1]["parts"], final_text)

    return JSONResponse({"reply": final_text})
