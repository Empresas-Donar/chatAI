# Todos los PDF de Tarjas rotos: decorador de ruta mal ubicado tras refactor
# Path: specs/120-pdf-routes-decorator-fix/spec.md
issue: #120 · branch: 120-pdf-routes-decorator-fix · date: 2026-08-14

## What
Los 10 endpoints de descarga de PDF de Tarjas devolvían `422 {"detail":[{"loc":["query","cur"],"msg":"Field required"}]}` en vez del PDF, porque el decorador `@router.get(...)` quedó en la función helper en vez de en la función de ruta real. Ahora cada decorador está en la función de ruta correcta y los 11 endpoints (10 corregidos + `tractorista` que ya estaba bien) responden.

## Acceptance
- [x] `/api/tarjas/detalle/download-pdf` (y los otros 9 reportes de Tarjas) ya no devuelven el error `cur`.
- [x] Cada ruta registrada en `tc.router.routes` apunta a la función `async def download_tarjas_*_pdf`, no a `_build_*_html`.
- [x] Los tests existentes de PDF siguen pasando.

## Context
- Módulo: `chatai/backend/controllers/tarjas_controller.py`
- Causado por PR #119 (issue #116, "make bulk /reportes PDF sections identical to standalone PDFs"): extrajo la lógica de cada PDF a `_build_<reporte>_html(cur, fecha_inicio, ...)`, compartida entre el endpoint standalone y el PDF masivo de `/reportes`. Al mover el cuerpo a la función helper, el decorador `@router.get(...)` se quedó pegado a esa función en vez de mudarse junto con la función de ruta real `async def download_tarjas_<reporte>_pdf(...)`.
- Como `_build_*_html` recibe `cur` como primer parámetro posicional sin default ni anotación `Depends`, FastAPI lo interpreta como query param obligatorio — de ahí el error reportado por el usuario.
- La función de ruta real quedaba sin decorador, es decir, **no registrada** — no un bug de lógica sino de que la ruta ni siquiera existía.
- Afectó los 10 endpoints que pasaron por ese refactor: `detalle-tractorista`, `general-tractorista`, `resumen-persona`, `general`, `detalle`, `contratista`, `resumen-horas`, `jornadas-trabajador`, `bono-mensual`, `hora-ponderada-9h`. `tractorista` no fue tocado por el refactor y seguía funcionando.

## Decisions
- Fix puramente mecánico: mover cada línea `@router.get(...)` desde encima de `def _build_*_html(` hacia encima de `async def download_tarjas_*_pdf(` correspondiente, sin tocar el cuerpo de ninguna función. Se hizo con un script Python de una sola pasada (no manual) para evitar errores de transcripción al repetir la operación 10 veces sobre un archivo de +5000 líneas.
- No se tocan los tests de PR #119 (`test_116_pdf_bulk_standalone_parity.py`, etc.) porque llaman a `download_tarjas_*_pdf` como función Python directa (`asyncio.run(tc.download_tarjas_detalle_pdf(...))`), sin pasar por el router — por eso pasaban igual con el bug presente y no lo habían detectado. Se verificó el fix con un chequeo adicional fuera de la suite de tests: listar `tc.router.routes` y confirmar `route.endpoint.__name__` para cada path `download-pdf`.

## Implemented
### Controllers
- `chatai/backend/controllers/tarjas_controller.py`: 10 decoradores `@router.get(...)` movidos de su `_build_*_html` a su `async def download_tarjas_*_pdf` correspondiente. Ningún otro cambio de código.

## Routes
| Method | Path | Antes | Ahora |
|--------|------|-------|-------|
| GET | /api/tarjas/detalle-tractorista/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/general-tractorista/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/resumen-persona/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/general/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/detalle/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/contratista/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/resumen-horas/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/jornadas-trabajador/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/bono-mensual/download-pdf | sin registrar | registrada |
| GET | /api/tarjas/hora-ponderada-9h/download-pdf | sin registrar | registrada |

## Tests
```
pytest tests/test_96_pdf_detalle_resumen_grafico.py tests/test_54_pdf_titles_contratista.py tests/test_116_pdf_bulk_standalone_parity.py -v
38 passed in 17.27s
```
Verificación adicional (no cubierta por la suite existente, ver Decisions): `tc.router.routes` — las 11 rutas `download-pdf` (10 corregidas + `tractorista`) apuntan a su `async def download_tarjas_*_pdf` real. Reproducido también vía `TestClient` real contra `/api/tarjas/detalle/download-pdf`: antes del fix fallaba con 422 `cur`; después, la request llega correctamente hasta el `Depends(require_auth)` del router (falla solo por falta de cookie de sesión en el script de prueba, no por el bug original).

Cross-farm isolation: no aplica — fix de registro de rutas, no de lógica de negocio ni de filtros por campo/farm.

## Manual QA
1. Ir a "Detalle de la semana" (`/tarjas/detalle`), aplicar filtros, clic en "PDF" → debe descargar el PDF (antes daba el error `cur`).
2. Repetir en cualquiera de los otros reportes de Tarjas (General, Contratista, Resumen por Persona, Horas Extra, Jornadas Trabajador, Bonos Mensuales, Hora Ponderada 9h, Detalle/General Tractorista) → todos deben descargar su PDF correctamente.

## Deferred
- No se investiga por qué la suite de tests de PR #119 no detectó esta regresión (llaman a la función directamente, sin pasar por el router) — se deja como posible mejora futura agregar un test de registro de rutas (`TestClient` + `app.include_router`) que habría atrapado esto.
