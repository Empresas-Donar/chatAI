# Spec: Jornadas por trabajador

## Qué

Nuevo reporte **Jornadas por trabajador** en el submenú Tarjas > Contratistas.
Muestra cuántas jornadas (conteo de fechas distintas de trabajo) tuvo cada trabajador en un período.

## Criterios de aceptación

- [x] Accesible desde Tarjas > Contratistas > "Jornadas por trabajador"
- [x] Filtros: fecha desde, fecha hasta, contratista, empresa
- [x] Tabla: trabajador | contratista | jornadas
- [x] Fila de suma total al pie de la tabla
- [x] Descarga Excel (.xlsx)
- [x] Descarga PDF

## Contexto

- Tabla fuente: `appsheet.tarjas_pagos`
- Métrica: `COUNT(DISTINCT fecha::date)` agrupado por `trabajador, contratista`
- Patrones idénticos a `/tarjas/resumen-persona` (filtros, CSS, URL sync)

## Decisiones

- Se reutiliza el CSS de `tarjas_resumen_persona.css` — la tabla es lo suficientemente similar
- Sin filtro de tipo_pago ni labor para mantener el reporte simple como solicitó el cliente
- El PDF incluye fila de total con fondo azul claro igual al Excel

## Implementado

- `chatai/backend/controllers/tarjas_controller.py` — 5 nuevas rutas: page, filters, data, download-excel, download-pdf
- `chatai/frontend/templates/tarjas_jornadas_trabajador.html` — template HTML
- `chatai/frontend/static/tarjas_jornadas_trabajador.js` — lógica de filtros, tabla y descargas
- `chatai/frontend/templates/base.html` — entrada en submenú Contratistas

## Rutas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/tarjas/jornadas-trabajador` | Página HTML |
| GET | `/api/tarjas/jornadas-trabajador/filters` | Dropdowns de filtros |
| GET | `/api/tarjas/jornadas-trabajador` | Datos JSON |
| GET | `/api/tarjas/jornadas-trabajador/download-excel` | Descarga Excel |
| GET | `/api/tarjas/jornadas-trabajador/download-pdf` | Descarga PDF |

## QA Manual

1. Ir a Tarjas > Contratistas > "Jornadas por trabajador"
2. Seleccionar rango de fechas con datos conocidos y presionar Consultar
3. Verificar que la tabla muestra trabajador, contratista y conteo de jornadas
4. Verificar que la fila "Suma total" muestra la suma correcta
5. Descargar Excel y PDF — comprobar que los datos coinciden con la tabla
