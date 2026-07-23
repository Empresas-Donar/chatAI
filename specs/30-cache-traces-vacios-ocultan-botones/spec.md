# Spec: Cache con traces vacíos oculta botones de descarga y SQL

## Qué

El caché semántico del Chat IA guarda entradas con `traces: []` cuando el modelo llama
herramientas que no producen traces (`render_chart`, `list_tables`, `describe_table`).
Cuando otro usuario hace una pregunta similar y recibe ese cache hit, el frontend filtra
`traces.filter(t => t.sql && t.row_count > 0)` y obtiene array vacío — sin botones de
descarga (Excel/PDF/Google Sheets) ni panel SQL.

## Criterios de aceptación

- [x] El caché semántico solo guarda entradas cuando `collected_traces` tiene al menos un trace válido (con `sql` y `row_count > 0`)
- [x] Respuestas que solo llaman `render_chart`, `list_tables` o `describe_table` NO se cachean
- [x] Los botones de descarga aparecen en todas las respuestas con datos reales, sin importar si vienen del caché o no
- [x] Test de regresión `test_30_cache_traces_vacios_regression` que verifica que el caché no se guarda cuando `traces` está vacío

## Contexto

### Archivos involucrados

- `chatai/backend/controllers/chat_controller.py` — guarda del caché semántico (línea ~1574)
- `chatai/backend/chat_cache.py` — serialización/deserialización de traces

### Causa raíz

En `chat_controller.py`, la condición para guardar en caché es:

```python
_tool_was_called = (
    len(collected_badges) > 0
    or len(collected_charts) > 0
    or len(collected_traces) > 0
)
if embedding and _tool_was_called:
    cache.put(user_question, embedding, final_text, collected_traces, ...)
```

Si el modelo llama solo `render_chart` (sin query), entonces:
- `collected_charts = [chart_payload]` → `_tool_was_called = True`
- `collected_traces = []`
- Se cachea con `traces: []`

Cuando un usuario posterior (ej: `gestion@empresasdonar.cl`) hace una pregunta semánticamente
similar (distancia coseno < 0.08), recibe `{"traces": [], "from_cache": true}`.

El frontend en `buildDownloadBar`:
```javascript
const downloadable = (traces || []).filter(t => t.sql && t.row_count > 0);
if (downloadable.length === 0) return null;  // no hay botones
```

→ Sin botones de descarga ni panel SQL.

### Decisiones

- La condición de guarda del caché se cambia a: solo cachear si `collected_traces` tiene al menos
  un trace con `row_count > 0` y `sql` no vacío. Las respuestas con solo gráficos (sin query de
  datos) no se cachean porque son dinámicas por naturaleza (los datos del gráfico dependen del
  momento de la consulta).
- No se modifican las entradas ya existentes en el caché — caducan solas (TTL 1-6h).
- Se agrega una función helper `_has_valid_traces(traces)` para centralizar la lógica de validación.

## Implementado

- `chatai/backend/controllers/chat_controller.py` — condición de guarda del caché cambiada de `_tool_was_called` a `_has_valid_traces(collected_traces)`

## Tests

9 passed, 0 failed · isolation: ✓ (test_does_not_mutate_traces_list)

## Manual QA

1. Hacer una pregunta de gráfico en el chat (ej: "graficá el costo mensual de remuneraciones")
2. Verificar en los logs del backend que NO aparece `cache put` para esa pregunta
3. Hacer la misma pregunta como usuario `gestion@empresasdonar.cl` — verificar que el modelo
   re-ejecuta la query en lugar de usar el caché, y que aparecen los botones de descarga
4. Hacer una pregunta de datos normales (ej: "cuántos trabajadores hay en Isla de Maipo")
   como admin → verificar que SÍ aparece `cache put` y los botones de descarga están visibles
5. Hacer la misma pregunta como `gestion@empresasdonar.cl` → verificar cache hit con botones
