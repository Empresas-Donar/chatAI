import json
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

import vertexai
from vertexai.generative_models import (
    FunctionDeclaration,
    GenerativeModel,
    Tool,
    Content,
    Part,
)
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
import mcp_server.bigquery_client as bq

router = APIRouter(prefix="/chat", tags=["chat"])
_templates: Jinja2Templates = None

GCP_PROJECT = "ace-scarab-484515-v1"
GCP_LOCATION = "us-central1"
KEY_PATH = os.environ.get(
    "BIGQUERY_KEY_PATH",
    "/Users/bedomax/startups/donar/bigquery-odoo-key.json",
)


def init(templates: Jinja2Templates):
    global _templates
    _templates = templates
    credentials = service_account.Credentials.from_service_account_file(
        KEY_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION, credentials=credentials)


# ── Tool declarations ─────────────────────────────────────────────────────────

_list_tables = FunctionDeclaration(
    name="list_tables",
    description="Lista todas las tablas disponibles en BigQuery (Odoo data) con cantidad de filas.",
    parameters={"type": "object", "properties": {}},
)

_describe_table = FunctionDeclaration(
    name="describe_table",
    description="Devuelve el esquema y 3 filas de muestra de una tabla BigQuery.",
    parameters={
        "type": "object",
        "properties": {
            "table_id": {
                "type": "string",
                "description": "Nombre exacto de la tabla, ej: 'Cuentas_por_cobrar'",
            }
        },
        "required": ["table_id"],
    },
)

_query_bigquery = FunctionDeclaration(
    name="query_bigquery",
    description=(
        "Ejecuta SQL en BigQuery y devuelve los resultados. "
        "Usar siempre el path completo: `ace-scarab-484515-v1.odoo_data.TABLA`. "
        "Tablas disponibles: Cuentas_por_cobrar, Remuneraciones, "
        "Reporte_Analitico, Ordenes_de_aplicacion."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Query SQL estándar de BigQuery"},
            "max_rows": {
                "type": "integer",
                "description": "Máximo de filas a retornar (default 100)",
            },
        },
        "required": ["sql"],
    },
)

_tools = Tool(function_declarations=[_list_tables, _describe_table, _query_bigquery])

_SYSTEM = """Eres un analista de datos experto para KONTROLAG SPA y el grupo Empresas Donar.
Tienes acceso a BigQuery con datos de Odoo: facturas, remuneraciones, líneas analíticas y órdenes de aplicación.
Responde siempre en español. Sé conciso y presenta los números de forma clara.
Los montos están en pesos chilenos (CLP). Usa formato de miles con puntos (ej: $1.234.567).
Cuando hagas consultas, explica brevemente qué encontraste antes de mostrar los datos."""


def _call_tool(name: str, args: dict) -> str:
    if name == "list_tables":
        return json.dumps(bq.list_tables(), ensure_ascii=False)
    if name == "describe_table":
        return json.dumps(bq.describe_table(args["table_id"]), ensure_ascii=False, default=str)
    if name == "query_bigquery":
        rows = bq.run_query(args["sql"], int(args.get("max_rows", 100)))
        return json.dumps(rows, ensure_ascii=False, default=str)
    return json.dumps({"error": f"tool desconocida: {name}"})


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    return _templates.TemplateResponse("chat.html", {"request": request})


@router.post("/ask")
async def chat_ask(request: Request):
    body = await request.json()
    messages = body.get("messages", [])

    model = GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=_SYSTEM,
        tools=[_tools],
    )

    # Rebuild history as Vertex AI Content objects
    history = []
    for m in messages[:-1]:
        history.append(Content(role=m["role"], parts=[Part.from_text(m["parts"])]))

    chat = model.start_chat(history=history)
    response = chat.send_message(messages[-1]["parts"])

    # Agentic loop — Gemini may call multiple tools before answering
    for _ in range(5):
        fn_calls = [p for p in response.candidates[0].content.parts if p.function_call.name]
        if not fn_calls:
            break

        tool_parts = []
        for part in fn_calls:
            fn = part.function_call
            result = _call_tool(fn.name, dict(fn.args))
            tool_parts.append(
                Part.from_function_response(name=fn.name, response={"result": result})
            )

        response = chat.send_message(tool_parts)

    final_text = response.candidates[0].content.parts[0].text
    return JSONResponse({"reply": final_text})
