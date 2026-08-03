# Conexión MCP con app AppSheet Tarjas + vínculo con PostgreSQL
# Path: specs/78-doc-appsheet-tarjas-mcp/spec.md
issue: #78 · branch: 78-doc-appsheet-tarjas-mcp · date: 2026-08-03

## What
Documentar la conexión MCP directa a la app AppSheet **Tarjas** (fuente en vivo, pre-migración) y su vínculo con las tablas ya migradas en PostgreSQL, de forma que quede registrado el alcance de edición conjunta (AppSheet + PostgreSQL) disponible para diagnosticar y resolver errores de sincronización de datos.

## Acceptance
- [x] Existe un spec en `specs/` que documenta el servidor MCP, sus herramientas, sus límites y el mapeo de tablas AppSheet ↔ tablas PostgreSQL.
- [x] El spec explica el flujo de diagnóstico: comparar datos AppSheet (fuente en vivo) vs PostgreSQL (datos sincronizados) para detectar y corregir discrepancias.
- [x] El spec deja constancia de que las credenciales están fuera del repositorio.

## Context
- No hay cambios de código en la app FastAPI — esta issue es puramente documentación de una capacidad de tooling nueva a nivel de sesión de Claude Code.
- Módulo relacionado en el repo: `chatai/backend/controllers/tarjas_controller.py`, `chatai/backend/controllers/purchase_orders_controller.py` (consumidores de `appsheet.tarjas_*`).
- Vistas SQL relevantes: `sql/tarjas/01_views_reporte.sql` (`tarjas_reporte`), `sql/tarjas/02_views_odoo.sql` (`tarjas_reporte_odoo`).
- Mapeo de labores con 4 niveles de fallback (id_labor exacto → texto normalizado → prefijo → BONHOMIA) documentado en `CLAUDE.md`, crítico para que las herramientas de escritura de AppSheet no rompan el JOIN `tarjas_pagos → tarjas_labores`.

## Decisions
- El servidor MCP (`appsheet-mcp-server`, paquete npm de terceros — repo `IslomIlkhom/appsheet-mcp-server`) se registró en el **scope local del proyecto** dentro de `~/.claude.json` (`projects["<ruta-repo>"].mcpServers`), **no** en `.mcp.json` del repositorio ni en ningún archivo versionado. Motivo: las credenciales (`APPSHEET_APP_ID`, `APPSHEET_API_KEY`) no deben llegar a git.
- Se creó una **API Key dedicada** para esta integración en AppSheet (Editor → Settings → Integrations → Application Access Keys) en vez de reusar las keys existentes de Looker Studio/Zapier, para poder revocarla de forma independiente.
- Se optó por acceso de **lectura + escritura completa** desde el arranque (Find, Add, Update, Delete rows, Run Action, Run Workflow) en vez de partir solo con lectura, decisión explícita del usuario.
- Requirió instalar **Node.js LTS** (v24.18.1, vía `winget install OpenJS.NodeJS.LTS`) en la máquina porque el servidor corre como `npx -y appsheet-mcp-server`.
- Alcance inicial: solo la app **Tarjas**. Cada app adicional de AppSheet requiere su propio App ID + API Key y se registra como un servidor MCP independiente (`appsheet-<nombre>`), porque `appsheet-mcp-server` no soporta credenciales multi-app en una sola instancia sin configuración adicional por app.

## Servidor MCP — herramientas disponibles
Prefijo de invocación: `mcp__appsheet-tarjas__<tool>`

| Herramienta | Uso |
|---|---|
| `appsheet_find_rows` | Consulta/filtra filas de una tabla con expresión AppSheet (`[Status] = "Active"`) |
| `appsheet_add_rows` | Agrega una o más filas |
| `appsheet_update_rows` | Actualiza filas existentes (requiere columna clave) |
| `appsheet_delete_rows` | Elimina filas por clave |
| `appsheet_list_tables` | Descubre en vivo las tablas de la app |
| `appsheet_describe_table` | Infiera columnas a partir de una fila de muestra |
| `appsheet_run_action` | Ejecuta una Action ya definida en el editor (nombre exacto requerido) |
| `appsheet_run_workflow` | Dispara un bot/workflow ya configurado como trigger de Action |
| `appsheet_get_app_info` | Config resumida de la app (no expone la API key) |
| `appsheet_list_apps` | Lista apps configuradas en este servidor MCP |

**Límites de la REST API de AppSheet (no del MCP):** no expone definiciones de fórmulas, tipos de columna, virtual columns, ni discovery de Actions/Workflows — los nombres de Action/Workflow deben conocerse de antemano desde el editor. No permite cambios estructurales de la app (columnas, vistas, permisos, UI): eso sigue siendo manual en el Editor de AppSheet.

## Mapeo tablas AppSheet ↔ PostgreSQL (schema `appsheet`)

| Tabla AppSheet (app Tarjas) | Tabla PostgreSQL | Notas |
|---|---|---|
| `Pagos` | `appsheet.tarjas_pagos` | Registro de pago origen; consumida en casi todos los reportes (`tarjas_controller.py`, `reports_controller.py`) |
| `Labor` | `appsheet.tarjas_labores` | Catálogo de labores + `codigo_labor` (Odoo); JOIN con `tarjas_pagos` vía 4 niveles de fallback |
| `Contratistas` | `appsheet.tarjas_contratistas` | Empresas/cuadrilleros |
| `Personal` | `appsheet.tarjas_personal` | Trabajadores |
| `campo` | `appsheet.tarjas_campo` | Predios |
| `CC` | `appsheet.tarjas_cc` | Centros de costo, `analytic_distribution` JSON (Odoo) |
| `Maquina` | `appsheet.tarjas_maquina` | Catálogo maquinaria (ver issue #73) |
| `PLAN_DIARIO`, `Usuarios`, `supervisor`, `Trato`, `Jornada`, `tarjas_bono`, `tarjas_det_supervisor` | `appsheet.tarjas_<snake_case>` (convención) | No confirmadas por grep directo en el backend; siguen la misma convención de nombre `appsheet.tarjas_<tabla>` |
| _(vista, no tabla AppSheet)_ | `appsheet.tarjas_reporte`, `appsheet.tarjas_reporte_odoo`, `appsheet.tarjas_reporte_odoo_tractorista` | Vistas consolidadas — solo existen en PostgreSQL, no tienen equivalente 1:1 en AppSheet |

`Process for estado Process Table`, `New step Output`, `Process for pagos Process Table`, `New step Output 2` son tablas internas de automatizaciones de AppSheet (bots/process), sin equivalente en PostgreSQL.

## Flujo de diagnóstico habilitado
Con ambas conexiones activas en la misma sesión (AppSheet vía MCP + PostgreSQL vía `pg_client`/conexión directa ya existente en el proyecto), el flujo para resolver errores de datos es:
1. Consultar el registro en PostgreSQL (`appsheet.tarjas_pagos`, etc.) para identificar la fila con el problema (ej. `id_labor` sin mapeo, monto corrupto, contratista mal escrito).
2. Consultar la misma fila en AppSheet (`appsheet_find_rows`) usando su clave para comparar el valor "fuente" contra el valor migrado.
3. Si el error está en el origen (AppSheet), corregirlo ahí con `appsheet_update_rows` — la corrección se refleja en la próxima sincronización a PostgreSQL.
4. Si el error es de mapeo/transformación (ej. fallback de labor, tipos numéricos), corregirlo directamente en PostgreSQL con las migraciones/UPSERT existentes, sin tocar AppSheet.
5. Para acciones que requieren recalcular o disparar lógica de negocio ya definida en AppSheet (ej. recalcular un bono), usar `appsheet_run_action` / `appsheet_run_workflow` en vez de replicar la lógica manualmente en SQL.

## Implemented
### Docs
- `specs/78-doc-appsheet-tarjas-mcp/spec.md`

### Config (fuera del repositorio, no versionado)
- `~/.claude.json` → `projects["c:/Users/gesti/OneDrive/Documents/Códigos/chatAI"].mcpServers.appsheet-tarjas` — nueva entrada con `command: npx`, `args: ["-y", "appsheet-mcp-server"]`, `env: { APPSHEET_APP_ID, APPSHEET_API_KEY }`
- Node.js LTS instalado en la máquina del usuario (`winget install OpenJS.NodeJS.LTS`)

## Routes
N/A — sin cambios de API en esta issue.

## Tests
N/A — sin cambios de código. Validación manual: ver Manual QA.

## Manual QA
1. En una sesión de Claude Code sobre este repo, pedir "lista las tablas de la app Tarjas" → debe responder con las 18 tablas vía `mcp__appsheet-tarjas__appsheet_list_tables`.
2. Pedir una consulta puntual, ej. "buscá en Pagos los registros de esta semana" → debe ejecutar `appsheet_find_rows` y devolver filas reales.
3. Confirmar que `git status` no muestra ningún archivo con `APPSHEET_APP_ID` o `APPSHEET_API_KEY` — las credenciales solo deben existir en `~/.claude.json`, fuera del repo.
4. Verificar cruzando un registro puntual entre `appsheet_find_rows` (AppSheet) y una consulta SQL directa a `appsheet.tarjas_pagos` (PostgreSQL) para el mismo ID, confirmando que ambos valores son consistentes.

## Deferred
- Registrar servidores MCP para las demás apps de la cuenta (despacho, sensores, etc.) — se hará bajo demanda, un servidor por app.
- Automatizar la comparación AppSheet vs PostgreSQL (hoy es un flujo manual guiado por el asistente, no un script/endpoint).
