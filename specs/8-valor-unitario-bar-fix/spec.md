# Spec: Columna "Valor por hr" incorrecta y cajas naranjas confusas en /tarjas/contratista

**Issue:** #8
**Branch:** `8-valor-unitario-bar-fix`

## What

Dos bugs visuales/lógicos en la tabla "Total trabajador" de `/tarjas/contratista`:

1. La columna "Valor por hr" muestra el `total_trabajado` del primer registro del grupo (ganancia diaria), no una tarifa unitaria. La etiqueta y el valor son incorrectos.
2. Las barras naranjas (`.bar`) aparecen como rectángulos sólidos a la izquierda del monto, semejando botones clickeables sin función. La intención era una barra de fondo proporcional al valor relativo.

## Acceptance Criteria

- La cabecera de la columna dice "Valor unitario" (no "Valor por hr")
- Para `tipo_pago = 'trato'`: la celda muestra `valor_trato` (precio unitario del trato, ej. $500/kg)
- Para cualquier otro `tipo_pago`: la celda muestra `valor_jornada` (valor de la jornada diaria)
- Las barras naranjas están posicionadas como fondo detrás del texto (no como bloque a la izquierda)
- El Excel y PDF de descarga no se ven afectados

## Context

### Bug 1 — Valor incorrecto

En `tarjas_contractor.js`, al construir grupos:
```js
groups.set(key, { worker, labor, tipo, rate: value, byDate: {} });
```
`value = Number(r.total_trabajado)` — es el total diario ganado, no la tarifa unitaria.

La tabla `appsheet.tarjas_pagos` tiene las columnas correctas:
- `valor_jornada` — valor pactado por jornada
- `valor_trato` — precio unitario del trato

El backend (`/api/tarjas/contratista`) hace `SELECT *` por lo que ya incluye estas columnas en la respuesta. Solo hace falta que el frontend las lea correctamente.

La cabecera en `renderPivot`:
```js
hdr += `<th class="th-fixed" style="text-align:right">Valor por hr</th>`;
```
Debe decir "Valor unitario".

### Bug 2 — Barras naranjas

El CSS define `.bar` como un `div` con `height: 22px; background: #f59e0b`. Está dentro de `.bar-wrap` con `display: flex; justify-content: flex-end`. El orden en el HTML es barra primero, texto después:
```html
<div class="bar-wrap">
  <div class="bar" style="width:40%"></div>
  <span class="bar-text">$27.100,00</span>
</div>
```
Resultado: barra naranja sólida visible a la izquierda del texto, parece botón.

La corrección es posicionar `.bar` como `position: absolute` con `left: 0`, y `.bar-wrap` como `position: relative`, de modo que la barra quede de fondo bajo el texto.

## Decisions

- Se mantiene la barra de fondo (no se elimina) porque aporta información visual de magnitud relativa entre días
- No se modifica el backend: `SELECT *` ya retorna `valor_jornada` y `valor_trato`; el frontend solo debe leerlos
- La selección de cuál campo mostrar (`valor_trato` vs `valor_jornada`) se hace en el frontend según `tipo_pago` del grupo

## Implemented

- `chatai/frontend/static/tarjas_contractor.js` — leer `valor_trato`/`valor_jornada` según tipo; renombrar cabecera
- `chatai/frontend/static/tarjas_contractor.css` — barra como fondo absoluto detrás del texto

## Tests

Sin tests automatizados — cambios puramente de frontend/presentación sin lógica de backend. El backend (`SELECT *` en `/api/tarjas/contratista`) ya retornaba `valor_jornada` y `valor_trato`; ningún cambio de server-side fue necesario.

## Manual QA

1. Abrir `/tarjas/contratista?fil-from=2026-07-08&fil-to=2026-07-14` y hacer clic en Consultar.
2. Verificar que la cabecera de la columna dice "Valor unitario" (no "Valor por hr").
3. Para filas con tipo "trato": verificar que el valor mostrado coincide con el precio unitario del trato (ej. $500 o $1.200), no con el total diario ganado.
4. Para filas con tipo "al día": verificar que el valor mostrado coincide con el valor de jornada pactado.
5. Verificar que los montos en las celdas de fecha tienen la barra naranja visible detrás del texto (fondo), sin sobresalir como bloque separado a la izquierda.
