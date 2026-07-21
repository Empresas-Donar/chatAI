# Spec: Panel de previa de sincronización Odoo en pantalla de órdenes de venta

**Issue:** #17
**Branch:** `17-sync-preview-ordenes`
**Labels:** enhancement

---

## What

Agregar en la pantalla `/despacho/ordenes` (Órdenes de Venta) un panel de previa de sincronización con Odoo,
similar al modal que existe en purchase orders (`/odoo/tarjas`).

El usuario debe poder verificar si los Centros de Costo (CC) asignados a las órdenes de venta
del período filtrado están correctamente mapeados en Odoo, antes de usar o exportar los datos.

---

## Acceptance Criteria

- [ ] Botón "Verificar CCs en Odoo" en la barra de filtros, deshabilitado hasta que haya resultados
- [ ] Nuevo endpoint `GET /api/despacho/ordenes/sync-preview` devuelve CCs únicos con estado
- [ ] Estado por CC: `ok` (activo en Odoo), `unknown` (no encontrado en BQ), `empty` (CC vacío o `—`)
- [ ] Modal con tabla: Centro de Costo, Órdenes (cantidad), Cantidad total, Estado
- [ ] Chips de resumen: N mapeados / M sin mapear
- [ ] Alerta si BigQuery no está disponible (no bloquea)
- [ ] Alerta si hay CCs sin mapear
- [ ] UX idéntica al modal de purchase orders (mismas clases CSS cc-modal-*)
- [ ] Tests de regresión en `chatai/tests/test_despacho_sync_preview.py`
- [ ] Lint limpio (ruff)

---

## Context

**Tabla fuente:** `appsheet.despacho_venta`
- `centro_costo` — texto libre con el nombre/código del CC (p.ej. "CC-421", "CEREZOS LAPINS")
- Los filtros activos (fecha_inicio, fecha_termino, cliente, producto) se pasan al endpoint

**Validación Odoo:**
- BigQuery tabla `CC_analiticos` (ya usada en purchase_orders_controller via `_BQ_ALL_CC_QUERY`)
- Coincidencia por `code` del CC analítico (case-insensitive, trim)
- Si `active = TRUE` → ok; si no existe → unknown; si `centro_costo` vacío o `—` → empty
- BQ no disponible → estado `unknown` para todos, con alerta informativa

**Patrón replicado de purchase orders:**
- Modal HTML con clase `cc-modal-overlay` (usa estilos de `purchase_orders.css`)
- Objeto `syncModal` en JS que centraliza referencias DOM
- Función `loadSyncPreview()` async que llama al endpoint y renderiza
- Filas con problema usan clase `cc-row-error` (fondo rojo)
- `purchase_orders.css` ya incluido en `despacho_ordenes.html` — sin cambios de CSS

---

## Decisions

- Se compara `centro_costo` con el campo `code` de `CC_analiticos` (no con `nombre`) porque los CC
  en `despacho_venta` parecen ser códigos cortos (p.ej. "CC-421"), no nombres largos.
  Si no coincide por código, se intenta comparación case-insensitive también con `nombre`.
- No se agrega botón de "Sincronizar" (diferente a purchase orders) porque `despacho_venta.centro_costo`
  es texto libre de AppSheet, no un JSON de IDs de Odoo que se pueda actualizar automáticamente.
  El modal es de consulta/verificación solamente.
- Se reutilizan todas las clases CSS del modal de purchase orders — cero CSS nuevo.

---

## Implemented

- `chatai/backend/controllers/despacho_controller.py` — nuevo endpoint `GET /api/despacho/ordenes/sync-preview`
- `chatai/frontend/templates/despacho_ordenes.html` — modal HTML + botón "Verificar CCs en Odoo"
- `chatai/frontend/static/despacho_ordenes.js` — lógica del modal (syncModal, loadSyncPreview)
- `chatai/tests/test_despacho_sync_preview.py` — tests de regresión
- `specs/17-sync-preview-ordenes/spec.md` — este archivo

---

## Tests

15 passed, 0 failed · aislamiento: N/A (tests de análisis estático, no requieren DB/BQ)

Cobertura:
- Endpoint: existencia de ruta, handler, validación de fechas, try/except BQ, clasificaciones ok/unknown/empty, forma de respuesta, SQL con GROUP BY
- Frontend: botón, modal, tbody, loadSyncPreview(), llamada al endpoint, syncModal object, alertas BQ y CCs sin mapear

---

## Manual QA

1. Ir a `/despacho/ordenes`, seleccionar un rango de fechas con datos y hacer clic en "Consultar".
   Verificar que el botón "Verificar CCs en Odoo" se habilita al recibir resultados.

2. Hacer clic en "Verificar CCs en Odoo": el modal debe abrirse con un spinner mientras carga.
   Al terminar, la tabla muestra cada CC único con columnas: Centro de Costo, Órdenes, Cantidad total, Estado.
   Si hay CCs sin mapear, aparece la alerta naranja con el conteo.

3. Consultar un período sin datos → botón "Verificar CCs" permanece deshabilitado.
   Hacer clic en "Cerrar" o en el overlay cierra el modal correctamente.

1. Ir a `/despacho/ordenes`, seleccionar un rango de fechas con datos y hacer clic en "Consultar"
2. Verificar que el botón "Verificar CCs en Odoo" se habilita al recibir resultados
3. Hacer clic en "Verificar CCs en Odoo":
   - El modal debe abrirse con un spinner mientras carga
   - Al cargar, debe mostrar la tabla de CCs con estados (OK / Sin mapear)
   - Si hay CCs sin mapear, debe aparecer la alerta naranja
4. Cerrar el modal y verificar que se puede volver a abrir con datos frescos
