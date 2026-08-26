# Spec: Línea de tiempo de registros de campo (App)

## Qué

Nueva sección **App → Registros de campo** en Tarjas: una línea de tiempo de inspección de cada registro crudo ingresado desde la app de campo (AppSheet), para validar visualmente si labor, fecha, estado, usuario, campo y el resto del payload se ven correctos.

No es un reporte agregado tipo Looker: es una vista de auditoría. Los registros **mal digitados** se pueden corregir (trabajador, RUT, horas, extras).

## Criterios de aceptación

- [x] Accesible desde **Catálogo de Reportes → Tarjas → App → Registros de campo**
- [x] Ruta de página: `/tarjas/registros-campo`
- [x] Fuente: `appsheet.tarjas_pagos`, una fila = un registro de campo
- [x] Los mal digitados se pueden editar (trabajador, RUT, horas trabajadas, horas extras) y persistir con PATCH allowlist
- [x] Línea de tiempo agrupada por fecha (más reciente primero)
- [x] Filtros: rango de fechas (default últimos 7 días), empresa/campo, labor, estado, contratista, y usuario/supervisor
- [x] Expandir un registro para ver el payload relevante (horas, rendimientos, totales, RUT, ids)
- [x] Badges heurísticos de filas incompletas/sospechosas (labor, campo, trabajador, fecha, estado) — sin columna nueva en BD
- [x] Paginación (no volcar miles de filas al DOM)
- [x] Fechas en UI `DD/MM/YYYY`; APIs en `YYYY-MM-DD`
- [x] Descarga Excel reutilizando el helper existente (sin PDF en v1)
- [x] Calendario mensual en **Tarjas → App → Calendario** con total de registros por día y los mismos filtros
- [x] Clic en un día del calendario abre la línea de tiempo de esa fecha
- [x] Clic en un día abre un panel lateral con los registros de esa fecha (qué se hizo)
- [x] Se identifican registros mal digitados (RUT científico, espacios dobles, horas extra improbables, horas y extras en la misma fila)
- [x] El calendario muestra planificación (`tarjas_plan_diario`) superpuesta: un plan se pinta en cada día entre `fecha_inicio` y `fecha_fin`

## Contexto

- Tabla fuente: `appsheet.tarjas_pagos`
- `fecha` es TEXT (cast `fecha::date`); UI muestra `DD/MM/YYYY`
- `id_supervisor` en esta tabla guarda el **nombre** del supervisor/usuario (no un hash). No hay join a `tarjas_usuarios` (esa tabla tiene contraseñas) ni a `tarjas_supervisor` / `tarjas_det_supervisor` (ids, sin nombres útiles)
- Columnas extra confirmadas en vivo: `maquina`, `total_tractor`, `total_hora_extra`, `id_tarja_supervisor`, `id_labor`
- Estados observados: `Aprobado`, `Pendiente`
- Patrón de página: `/tarjas/jornadas-trabajador` y `/tarjas/detalle` (filtros, URL sync, Excel)

## Decisiones

- v1 es inspección visual **más corrección de mal digitados**: sin workflow de validado/rechazado y sin tablas nuevas. Las alertas son un array `flags` calculado en Python por fila. PATCH allowlist: `trabajador`, `rut_trabajador`, `horas_trabajadas`, `horas_extras` (SQL parametrizado + `psycopg2.sql.Identifier`). Un sync posterior de AppSheet puede sobrescribir la corrección.
- `id_supervisor` se muestra como Supervisor/usuario. No se hace JOIN a `tarjas_usuarios` (contiene contraseñas en claro) ni a `tarjas_supervisor`.
- Timeline agrupada en el frontend a partir de una lista plana ordenada `fecha::date DESC, "id_Resumen" DESC`.
- Default de fechas: últimos 7 días (incluye hoy). La página consulta al cargar, no espera un click vacío.
- Paginación `limit` (default 100, max 500) + `offset`, con botón **Cargar más**. Excel exporta el filtro completo (tope 10.000 filas), sin PDF.
- Estados esperados: `Aprobado` y `Pendiente`. Cualquier otro valor dispara `unexpected_estado` (badge rojo "Revisar"); campos vacíos disparan "Incompleto".
- El calendario es otra vista de la misma fuente (`tarjas_pagos`): `GROUP BY fecha::date` del mes visible, con heatmap por volumen. Reutiliza `/api/tarjas/registros-campo/filters` y `_build_registros_campo_where`. Clic en un día abre un **panel lateral** con labores del día y cada registro; “Abrir línea de tiempo” sigue disponible. Mal digitado = heurística Python (RUT tipo `6,67E+12`, espacios dobles en el nombre, horas extra > 8, **horas y extras juntas** en la misma fila). 0 horas regulares con extras > 0 es válido. No se marca RUT vacío ni nombres en MAYÚSCULAS (así se cargan en AppSheet).
- Planificación viene de `appsheet.tarjas_plan_diario` (no de `tarjas_pagos`). AppSheet pinta un plan en **todos** los días entre `fecha_inicio` y `fecha_fin`; ChatAI replica ese overlap con `generate_series` recortado al mes. Días solo con planes (p. ej. futuro) son clicables. El panel lista planes (labor, contratista, CC, personas, rango) y después los registros. Filtros de estado/supervisor no aplican a planes. No se hace JOIN a `tarjas_usuarios`.

## Implementado

- `chatai/backend/controllers/tarjas_controller.py` — timeline, filters, Excel, flags, PATCH allowlist de mal digitados, calendario mensual (`GROUP BY` día) y overlay de `tarjas_plan_diario`
- `chatai/frontend/templates/tarjas_registros_campo.html` — template de la línea de tiempo
- `chatai/frontend/static/tarjas_registros_campo.js` — filtros, URL sync, agrupación por día, expandir, paginación
- `chatai/frontend/static/tarjas_registros_campo.css` — cards/timeline con tokens terra existentes
- `chatai/frontend/templates/base.html` — subgrupo Tarjas → App → Registros de campo / Calendario
- `chatai/frontend/templates/tarjas_calendario.html` — calendario mensual
- `chatai/frontend/static/tarjas_calendario.js` — mes, filtros, heatmap, click-through a la timeline
- `chatai/frontend/static/tarjas_calendario.css` — grilla 7×N y densidad por color
- `chatai/tests/test_136_registros_campo.py` — análisis estático + heurísticas de flags + calendario
- `specs/136-registros-campo-timeline/spec.md` — este spec

## Rutas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/tarjas/registros-campo` | Página HTML de auditoría |
| GET | `/api/tarjas/registros-campo/filters` | Distincts: empresas, labores, estados, contratistas, supervisores |
| GET | `/api/tarjas/registros-campo` | Timeline JSON paginada (`limit`/`offset`) |
| PATCH | `/api/tarjas/registros-campo/{id_Resumen}` | Corregir campos mal digitados (allowlist) |
| GET | `/api/tarjas/registros-campo/download-excel` | Descarga Excel del filtro (máx. 10.000) |
| GET | `/tarjas/calendario` | Calendario mensual HTML |
| GET | `/api/tarjas/calendario` | Conteos por día (`mes=YYYY-MM`): registros + planes |
| GET | `/api/tarjas/calendario/planes` | Planes que cubren un día (`fecha=YYYY-MM-DD`) |

## Tests

pytest chatai/tests/test_136_registros_campo.py · isolation: PATCH allowlist (sin INSERT/POST; columnas vía Identifier)

## QA Manual

1. Ir a **Catálogo de Reportes → Tarjas → App → Registros de campo**
2. Verificar que el rango por defecto cubre los últimos 7 días y que la línea de tiempo carga agrupada por fecha `DD/MM/YYYY` (día más reciente arriba)
3. Abrir un registro con **Ver detalle** y comprobar labor, estado, supervisor, campo, trabajador, horas y totales
4. Filtrar por campo / labor / estado / contratista / supervisor y pulsar Consultar; usar **Cargar más** si hay más de 100 filas
5. Descargar Excel y comprobar que las fechas salen `DD/MM/YYYY` y las filas con alertas van resaltadas
6. Ir a **Tarjas → App → Calendario**, verificar totales por día del mes actual, el desglose aprobado/pendiente y el chip morado de planes
7. Clic en un día con registros → se abre el panel con **Planificación** y **Registros de campo**; los mal digitados van marcados en rojo
8. Activar “Solo mal digitados” y comprobar RUTs tipo `E+`, horas extra > 8 o nombres con espacios dobles
9. En un mal digitado, editar el campo marcado (p. ej. quitar espacios dobles del nombre), **Guardar corrección**, y verificar que el badge rojo desaparece si el error quedó resuelto
10. Ir a un día futuro (o julio 2026) y comprobar que VIGILANCIA / ISLACOR aparece como plan de rango largo, no como registro de campo
