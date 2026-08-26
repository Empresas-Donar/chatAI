"""
Regression tests for issue #137: the "Resumen por persona" PDF sorted rows by
total descending (`-x[1]["total"]`) instead of by worker name. Besides not
being alphabetical, this broke the "print the worker name once" logic added
in issue #134: since the "Al día" and "trato" rows of the same worker rarely
have equal totals, they could land far apart in the total-descending order,
separated by other workers' rows — so the `is_first` check (which only looks
at the immediately preceding row) could fire twice for the same worker,
duplicating their name.

Fix: sort by (trabajador.lower(), tipo_pago) instead — alphabetical, and it
keeps each worker's rows contiguous again.
"""

import os
import re
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import controllers.tarjas_controller as tc

CONTRATISTA = "HERBI ML SPA"
EMPRESA = "TALAGANTE"
FECHA_INICIO = "2026-08-12"
FECHA_TERMINO = "2026-08-18"

_BOLD_NAME_RE = re.compile(r"<td[^>]*><b>([^<]+)</b></td>")


def _connect():
    import psycopg2

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


class TestResumenPersonaAlphabeticalOrder:
    def test_137_workers_appear_in_alphabetical_order(self):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                html = tc._build_resumen_persona_html(
                    cur,
                    FECHA_INICIO,
                    FECHA_TERMINO,
                    contratista=CONTRATISTA,
                    empresa=EMPRESA,
                )
        finally:
            conn.rollback()
            conn.close()

        names_in_order = _BOLD_NAME_RE.findall(html)
        assert len(names_in_order) > 1, "expected multiple workers in the fixture range"
        assert names_in_order == sorted(names_in_order, key=str.lower)

    def test_137_worker_name_appears_exactly_once_even_with_both_tipo_pago(self):
        """A worker with both 'Al día' and 'trato' rows must be bolded only
        once — this is what alphabetical grouping restores (issue #134's
        `is_first` needs same-worker rows to be contiguous)."""
        conn = _connect()
        try:
            with conn.cursor() as cur:
                html = tc._build_resumen_persona_html(
                    cur,
                    FECHA_INICIO,
                    FECHA_TERMINO,
                    contratista=CONTRATISTA,
                    empresa=EMPRESA,
                )
        finally:
            conn.rollback()
            conn.close()

        names_in_order = _BOLD_NAME_RE.findall(html)
        for name in set(names_in_order):
            assert names_in_order.count(name) == 1, f"{name} bolded more than once"


class TestBulkPdfSharesSameOrder:
    def test_137_bulk_section_matches_standalone_builder(self):
        import controllers.reports_controller as rc

        conn = _connect()
        try:
            with conn.cursor() as cur:
                expected = tc._build_resumen_persona_html(
                    cur,
                    FECHA_INICIO,
                    FECHA_TERMINO,
                    contratista=CONTRATISTA,
                    empresa=EMPRESA,
                )
            with conn.cursor() as cur:
                actual = rc._REPORT_GENERATORS["resumen-persona"](
                    cur, FECHA_INICIO, FECHA_TERMINO, EMPRESA, CONTRATISTA
                )
        finally:
            conn.rollback()
            conn.close()
        assert actual == expected
