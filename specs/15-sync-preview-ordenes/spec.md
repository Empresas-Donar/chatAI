# Spec: Panel de previa de sincronización Odoo en órdenes de aplicación

**Issue:** #15
**Branch:** `15-sync-preview-ordenes`
**Labels:** bug

---

## What

La pantalla `/despacho/ordenes` muestra órdenes de venta con una columna `CC` (centro de costo)
pero no indica si cada CC está correctamente sincronizado con Odoo.
El módulo de purchase orders ya tiene un panel de previa completo (modal con estado OK / excluido,
indicador de CC archivado, botón de sync). Se agrega un patrón equivalente en la pantalla de órdenes de despacho.

---

## Acceptance Criteria

- [ ] Nuevo endpoint `GET /api/despacho/ordenes/sync-preview` devuelve filas con estado CC
- [ ] El estado puede ser: `ok` (CC activo en Odoo), `archived` (CC existe pero archivado), `empty` (CC vacío o `—`), `unknown` (BQ no disponible)
- [ ] El panel frontend muestra tabla con columnas: Cliente, Producto, CC, Cantidad, Estado
- [ ] Los chips de estado usan los mismos colores que en purchase orders (verde/rojo/gris/amarillo)
- [ ] Si BigQuery no está disponible, se muestra alerta informativa (no error bloqueante)
- [ ] Existe un test de regresión para el endpoint `sync-preview`

---

## Context

**Tabla afectada:** `appsheet.despacho_venta`
- Columna `centro_costo` — texto libre con el nombre/código del CC
- Los filtros activos (fecha, cliente, producto) se pasan al endpoint para acotar el scope

**Validación Odoo:**
- BigQuery tabla `CC_analiticos` — ya usada en `purchase_orders_controller.py` via `_BQ_ALL_CC_QUERY`
- Se compara `centro_costo` con el campo `code` de `CC_analiticos` (comparación case-insensitive)
- Si `active = TRUE` → ok; si `active = FALSE` → archived; si no existe en BQ → unknown (o empty si CC vacío)

**Patrón a replicar:** modal de export-preview de purchase orders:
- `ccModal` object en JS para referencias a los elementos del DOM
- `loadSyncPreview()` async function que llama al endpoint y renderiza
- Tabla unificada con filas OK (fondo normal) y filas con problemas (fondo rojo `cc-row-error`)
- Chips de summary: N filas OK, M con problema

---

## Decisions

---

## Implemented

---

## Tests

---

## Manual QA
