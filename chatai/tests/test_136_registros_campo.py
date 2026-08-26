"""
Regression tests for issue #136: Tarjas App → Registros de campo timeline.

Verifies:
1. Page route /tarjas/registros-campo exists in the controller.
2. API routes exist (/api/tarjas/registros-campo and /filters).
3. Nav in base.html has subgroup "App" and leaf "Registros de campo".
4. SQL uses parameterized fecha::date BETWEEN %s AND %s.
5. UI dates are DD/MM/YYYY.
6. Query is ordered newest-first.
7. Pagination params exist (limit/offset).

Run locally:
    cd /path/to/ChatAI
    python -m pytest chatai/tests/test_136_registros_campo.py -v
"""

import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TARJAS_CTRL = (
    Path(__file__).parent.parent / "backend" / "controllers" / "tarjas_controller.py"
)
BASE_HTML = (
    Path(__file__).parent.parent / "frontend" / "templates" / "base.html"
)
PAGE_HTML = (
    Path(__file__).parent.parent
    / "frontend"
    / "templates"
    / "tarjas_registros_campo.html"
)
PAGE_JS = (
    Path(__file__).parent.parent / "frontend" / "static" / "tarjas_registros_campo.js"
)


def _ctrl_source() -> str:
    return TARJAS_CTRL.read_text(encoding="utf-8")


def _base_html() -> str:
    return BASE_HTML.read_text(encoding="utf-8")


def _page_html() -> str:
    return PAGE_HTML.read_text(encoding="utf-8")


def _page_js() -> str:
    return PAGE_JS.read_text(encoding="utf-8")


def _registros_campo_ctrl_block() -> str:
    src = _ctrl_source()
    marker = "App → Registros de campo"
    idx = src.rfind(marker)
    assert idx != -1, "Missing registros-campo section in tarjas_controller.py"
    return src[idx:]


def test_136_page_route_exists():
    src = _ctrl_source()
    assert '@router.get("/tarjas/registros-campo"' in src
    assert "tarjas_registros_campo.html" in src


def test_136_api_routes_exist():
    src = _ctrl_source()
    assert '@router.get("/api/tarjas/registros-campo")' in src
    assert '@router.get("/api/tarjas/registros-campo/filters")' in src
    assert '@router.patch("/api/tarjas/registros-campo/{id_resumen}")' in src


def test_136_mal_digitado_patch_is_allowlisted():
    """Mal-digitado rows can be corrected via PATCH; only 4 columns, parameterized."""
    block = _registros_campo_ctrl_block()
    assert '@router.patch("/api/tarjas/registros-campo/{id_resumen}")' in block
    assert "_REGISTROS_CAMPO_EDITABLE" in block
    for col in ("trabajador", "rut_trabajador", "horas_trabajadas", "horas_extras"):
        assert f'"{col}"' in block or col in block
    assert "psql.Identifier" in block
    assert "UPDATE appsheet.tarjas_pagos SET" in block
    assert "Campos no editables" in block
    assert "payload.get(\"fields\")" in block
    assert "@router.post" not in block
    assert "@router.put" not in block
    assert "INSERT INTO" not in block.upper()
    js_cal = CAL_JS.read_text(encoding="utf-8")
    assert "tcal-edit" in js_cal
    assert "Guardar corrección" in js_cal
    assert "method: 'PATCH'" in js_cal
    js_tl = _page_js()
    assert "trc-edit" in js_tl
    assert "Guardar corrección" in js_tl
    assert "method: 'PATCH'" in js_tl


def test_136_excel_route_exists():
    src = _ctrl_source()
    assert '@router.get("/api/tarjas/registros-campo/download-excel")' in src


def test_136_nav_has_app_subgroup_and_leaf():
    html = _base_html()
    assert '"label": "App"' in html
    assert '"label": "Registros de campo"' in html
    assert '"href": "/tarjas/registros-campo"' in html
    assert '"label": "Calendario"' in html
    assert '"href": "/tarjas/calendario"' in html


def test_136_sql_uses_parameterized_date_between():
    block = _registros_campo_ctrl_block()
    assert "fecha::date BETWEEN %s AND %s" in block
    assert re.search(r"BETWEEN\s+['\"]", block) is None
    assert re.search(
        r"fecha::date BETWEEN\s+[f]?['\"].*fecha_inicio",
        block,
    ) is None


def test_136_query_ordered_newest_first():
    block = _registros_campo_ctrl_block()
    assert "ORDER BY fecha::date DESC" in block


def test_136_pagination_params_exist():
    block = _registros_campo_ctrl_block()
    assert "limit" in block
    assert "offset" in block
    assert "LIMIT %s OFFSET %s" in block


def test_136_ui_dates_are_dd_mm_yyyy():
    js = _page_js()
    assert "DD/MM/YYYY" in js
    assert "${m[3]}/${m[2]}/${m[1]}" in js
    html = _page_html()
    assert 'lang="es-CL"' in html
    excel_block = _registros_campo_ctrl_block()
    assert "%d/%m/%Y" in excel_block


def test_136_template_and_js_exist():
    assert PAGE_HTML.exists()
    assert PAGE_JS.exists()
    html = _page_html()
    assert "url-filters.js" in html
    assert "fil-from" in html
    assert "fil-to" in html
    assert "Sin resultados" in html
    js = _page_js()
    assert "syncFiltersToURL" in js
    assert "loadFiltersFromURL" in js or "autoTriggerFromURL" in js
    assert "bindPopstate" in js


def test_136_flags_are_computed_in_python():
    block = _registros_campo_ctrl_block()
    for flag in (
        "missing_labor",
        "missing_campo",
        "missing_trabajador",
        "missing_estado",
        "unexpected_estado",
        "invalid_fecha",
        "bad_rut",
        "double_space_name",
        "implausible_horas_extra",
        "hours_and_extras",
    ):
        assert flag in block
    assert "flags" in block


def test_136_source_is_tarjas_pagos():
    block = _registros_campo_ctrl_block()
    assert "appsheet.tarjas_pagos" in block


def test_136_flag_heuristics_unit():
    """Exec just the flag helpers so the test does not import xhtml2pdf."""
    src = _ctrl_source()
    start = src.index("_REGISTROS_CAMPO_KNOWN_ESTADOS")
    end = src.index("def _build_registros_campo_where")
    ns: dict = {"re": re, "decimal": __import__("decimal")}
    exec(src[start:end], ns)
    flags_fn = ns["_registros_campo_flags"]
    mal_fn = ns["_is_mal_digitado"]

    clean = {
        "labor": "PODA",
        "nombre_campo": "ZUÑIGA",
        "trabajador": "Ana",
        "estado": "Aprobado",
        "fecha": "08/24/2026 00:00:00",
        "fecha_iso": "2026-08-24",
        "id_supervisor": "Yasmin mejias",
    }
    assert flags_fn(clean) == []

    incomplete = {
        "labor": "  ",
        "nombre_campo": None,
        "trabajador": "",
        "estado": "Weird",
        "fecha": None,
        "fecha_iso": None,
        "id_supervisor": None,
    }
    flags = flags_fn(incomplete)
    assert "missing_labor" in flags
    assert "missing_campo" in flags
    assert "missing_trabajador" in flags
    assert "unexpected_estado" in flags
    assert "invalid_fecha" in flags
    assert "missing_supervisor" in flags

    typo = {
        **clean,
        "rut_trabajador": "6,67E+12",
        "trabajador": "Roseline  Marcelus",
        "horas_extras": 26,
        "horas_trabajadas": 9,
        "tipo_pago": "Al dia",
    }
    typo_flags = flags_fn(typo)
    assert "bad_rut" in typo_flags
    assert "double_space_name" in typo_flags
    assert "implausible_horas_extra" in typo_flags
    assert mal_fn(typo_flags)

    extras_only = {
        **clean,
        "horas_trabajadas": 0,
        "horas_extras": 2,
        "tipo_pago": "Al dia",
    }
    assert "hours_and_extras" not in flags_fn(extras_only)
    both = {
        **clean,
        "horas_trabajadas": 9,
        "horas_extras": 2,
        "tipo_pago": "Al dia",
    }
    both_flags = flags_fn(both)
    assert "hours_and_extras" in both_flags
    assert mal_fn(both_flags)
    assert "hours_and_extras" not in flags_fn(clean)
    assert "bad_rut" not in flags_fn(clean)


CAL_HTML = (
    Path(__file__).parent.parent
    / "frontend"
    / "templates"
    / "tarjas_calendario.html"
)
CAL_JS = (
    Path(__file__).parent.parent / "frontend" / "static" / "tarjas_calendario.js"
)


def test_136_calendario_page_and_api_exist():
    src = _ctrl_source()
    assert '@router.get("/tarjas/calendario"' in src
    assert '@router.get("/api/tarjas/calendario")' in src
    assert '@router.get("/api/tarjas/calendario/planes")' in src
    assert "tarjas_calendario.html" in src
    assert CAL_HTML.exists()
    assert CAL_JS.exists()


def test_136_calendario_sql_is_parameterized_group_by_day():
    src = _ctrl_source()
    marker = "App → Calendario"
    idx = src.rfind(marker)
    assert idx != -1
    block = src[idx:]
    assert "_build_registros_campo_where" in block
    assert "GROUP BY fecha::date" in block
    assert "COUNT(*)" in block
    assert "sospechosos" in block
    assert "_REGISTROS_CAMPO_MAL_SQL" in block
    assert "_REGISTROS_CAMPO_SELECT" not in block
    # psycopg2 pyformat treats unescaped % as placeholders (IndexError).
    mal = _ctrl_source()
    start = mal.index("_REGISTROS_CAMPO_MAL_SQL")
    end = mal.index("def _is_blank")
    assert "LIKE '%" not in mal[start:end]
    assert "position('  ' in trabajador)" in mal[start:end]
    assert "params," in block
    assert "tarjas_plan_diario" in block
    assert "generate_series" in block
    assert "_build_plan_diario_where" in block
    assert "COUNT(DISTINCT p.id_plan)" in block
    assert "LIMIT 1" in block
    assert "tarjas_usuarios" not in block
    assert re.search(r"BETWEEN\s+['\"]", block) is None


def test_136_calendario_reuses_registros_filters():
    js = CAL_JS.read_text(encoding="utf-8")
    assert "/api/tarjas/registros-campo/filters" in js
    assert "/tarjas/registros-campo?" in js
    assert "/api/tarjas/calendario/planes" in js
    assert "dayPlanes" in js
    assert "planificados" in js
    assert "fmtValue" in js or "toLocaleString('es-CL')" in js
    assert "aplicados" in js
    assert "tcal-range" in js
    assert "day-panel" in js
    assert "mal digitado" in js.lower() or "mal_digitado" in js
    html = CAL_HTML.read_text(encoding="utf-8")
    assert "fil-month" in html
    assert "fil-empresa" in html
    assert "url-filters.js" in html
    assert "day-panel" in html
    assert "fil-solo-sospechosos" in html
    assert "pan-fecha" in html
    assert "tab-aplicados" in html
    assert "tab-planificados" in html
    assert "pan-empresa" in html


def test_136_month_to_date_range():
    src = _ctrl_source()
    start = src.index("def _month_to_date_range")
    end = src.index("@router.get(\"/tarjas/calendario\"")
    ns: dict = {"datetime": __import__("datetime")}
    exec(src[start:end], ns)
    assert ns["_month_to_date_range"]("2026-08") == ("2026-08-01", "2026-08-31")
    assert ns["_month_to_date_range"]("2026-02") == ("2026-02-01", "2026-02-28")
    assert ns["_month_to_date_range"]("2024-02") == ("2024-02-01", "2024-02-29")
    assert ns["_month_to_date_range"]("2026-12") == ("2026-12-01", "2026-12-31")


def test_136_plan_diario_where_is_range_overlap():
    src = _ctrl_source()
    start = src.index("def _build_plan_diario_where")
    end = src.index("@router.get(\"/api/tarjas/calendario\")")
    block = src[start:end]
    assert "p.fecha_inicio::date <= %s" in block
    assert ">= %s" in block
    assert "BETWEEN" not in block
    assert "campo.nombre = %s" in block
    assert "c.nombre = %s" in block
    assert "id_supervisor" not in block
    assert 'filters.append("estado' not in block
    assert "generate_series" in src[src.index("App → Calendario") :]
