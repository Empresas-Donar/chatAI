# Spec: PDF exportar resumen-persona muestra montos corruptos

**Issue:** #12
**Branch:** `12-pdf-export-montos-corruptos`

## What

Al exportar PDF desde `/tarjas/resumen-persona`, la columna de montos muestra
caracteres corruptos (ej: `$1$38FEBS0C0`) en lugar de valores CLP formateados
(ej: `$1.234.567`). El encabezado de la tercera columna (primera fecha) también
aparece ilegible.

## Acceptance Criteria

- El PDF exportado de `/api/tarjas/resumen-persona/download-pdf` muestra valores
  CLP correctamente formateados (ej: `$1.234.567`).
- Los encabezados de columna de fechas son legibles (ej: `01/07`).
- Los demás PDFs del sistema que usan logo (contratista, general, detalle, horas,
  reportes bulk, purchase orders) tampoco muestran corrupción.

## Context

### Causa raíz

La función `_logo_b64()` (duplicada en `tarjas_controller.py`,
`reports_controller.py` y `purchase_orders_controller.py`) lee el archivo
`donar_logo.png` (1288×539 px, 680 KB) y lo codifica en base64 sin
redimensionar, produciendo una cadena de **~907 KB** que se embebe directamente
en el HTML.

El documento HTML resultante supera 1 MB. xhtml2pdf/ReportLab no puede procesar
correctamente imágenes base64 tan grandes dentro del mismo buffer de string,
lo que corrompe el layout de texto en celdas adyacentes y produce los
caracteres ilegibles reportados.

### Archivos involucrados

- `chatai/backend/controllers/tarjas_controller.py` — `_logo_b64()` (línea ~149)
- `chatai/backend/controllers/reports_controller.py` — `_logo_b64()` (línea ~107)
- `chatai/backend/controllers/purchase_orders_controller.py` — `_logo_b64()` (línea ~921)

### Solución

Redimensionar el PNG a un máximo de 200 px de ancho con Pillow antes de
codificarlo en base64. Esto reduce la cadena de 907 KB a ~29 KB (31×), dentro
del rango que xhtml2pdf procesa sin errores.

Pillow ya es dependencia transitiva de xhtml2pdf (y de ReportLab), por lo que
no se agrega ninguna nueva dependencia.

## Decisions

- **Máximo de ancho:** 200 px — suficiente para verse bien en PDF A4/landscape
  a 80 px de ancho en el `<img>` tag, y reduce el tamaño >30×.
- **Formato de salida:** PNG (mismo que el original) — mantiene transparencia.
- **Cache:** la función `_logo_b64()` carga el archivo en cada llamada igual
  que antes; no se agrega caché para mantener el diff mínimo.
- **Tres archivos:** las tres copias de `_logo_b64()` se corrigen de forma
  idéntica para que todos los PDFs del sistema estén sanos.

## Implemented

- `chatai/backend/controllers/tarjas_controller.py` — `_logo_b64()` redimensiona el logo antes de codificar
- `chatai/backend/controllers/reports_controller.py` — idem
- `chatai/backend/controllers/purchase_orders_controller.py` — idem
- `chatai/tests/test_pdf_logo.py` — tests de regresión

## Tests

<!-- Completar tras ejecutar pytest -->

## Manual QA

1. Ir a `http://localhost:8000/tarjas/resumen-persona`, seleccionar un rango con
   datos (ej. toda la semana actual) y hacer clic en **PDF**.
2. Verificar que la columna "Total" y las columnas de fecha muestran valores como
   `$50.000`, `$1.234.567` — sin caracteres extraños.
3. Repetir para `/tarjas/contratista` → PDF y `/reportes` → descargar PDF bulk
   para confirmar que los otros PDFs también están sanos.
