"""Detalle contratista marks payments strictly above the configured cap.

The cap lives in appsheet.tarjas_configuracion (row 'general'), not in the
report. $30.000 stays unmarked when the cap is 30000.
"""
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import controllers.tarjas_controller as tc  # noqa: E402

_SQL = (
    Path(__file__).resolve().parents[2] / "sql" / "tarjas" / "29_tarjas_configuracion.sql"
).read_text()

_CELL_RE = re.compile(r'<td class="(num|total)" style="([^"]*)">([^<]*)</td>')


class _Cur:
    def __init__(self, exists, valor):
        self.exists = exists
        self.valor = valor
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        if "information_schema.tables" in self.sql:
            return (1,) if self.exists else None
        if self.valor is None:
            return None
        return (self.valor,)


def _amount(text):
    if text.strip() in ("", "-"):
        return None
    return int(text.replace("$", "").replace(".", ""))


class TestUmbralDiario:
    def test_strictly_above_the_cap(self):
        assert tc._exceeds_umbral_diario(30000, 30000) is False
        assert tc._exceeds_umbral_diario(30001, 30000) is True
        assert tc._exceeds_umbral_diario(None, 30000) is False
        assert tc._exceeds_umbral_diario("-", 30000) is False

    def test_marked_cell_carries_the_highlight_style(self):
        plain = tc._marked_money_td("num", "width:5%", "$28.000", False)
        marked = tc._marked_money_td("total", "width:9%", "$35.000", True)
        assert "ffedd5" not in plain
        assert "$28.000" in plain
        assert tc._UMBRAL_HIGHLIGHT_STYLE in marked
        assert 'class="total"' in marked

    def test_missing_config_keeps_the_default(self):
        assert tc._umbral_diario(_Cur(False, None)) == 30000

    def test_missing_row_keeps_the_default(self):
        assert tc._umbral_diario(_Cur(True, None)) == 30000

    def test_reads_the_stored_cap(self):
        assert tc._umbral_diario(_Cur(True, Decimal("45000"))) == 45000


@pytest.fixture
def conn():
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    yield c
    c.rollback()
    c.close()


def test_failed_config_read_does_not_abort_the_transaction(conn):
    """A broken config SELECT must not poison the cursor. The bulk PDF runs
    every report on this same transaction; an aborted transaction would 500
    the whole download."""

    class _FailingConfig:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, sql, params=None):
            if "FROM appsheet.tarjas_configuracion" in sql:
                self.inner.execute("SELECT * FROM appsheet.no_existe_umbral_diario")
                return
            if params is None:
                self.inner.execute(sql)
            else:
                self.inner.execute(sql, params)

        def fetchone(self):
            return self.inner.fetchone()

    with conn.cursor() as cur:
        assert tc._umbral_diario(_FailingConfig(cur)) == tc._UMBRAL_DIARIO_DEFAULT
        cur.execute("SELECT 42")
        assert cur.fetchone()[0] == 42


def test_contratista_html_leaves_the_cursor_usable(conn):
    with conn.cursor() as cur:
        contratista = tc._build_contratista_html(
            cur,
            "2026-09-30",
            "2026-10-06",
            contratista="HERBI ML SPA",
            empresa="TALAGANTE",
        )
        general = tc._build_general_html(
            cur,
            "2026-09-30",
            "2026-10-06",
            contratista="HERBI ML SPA",
            empresa="TALAGANTE",
        )
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
    assert "En naranja: montos sobre $30.000." in contratista
    assert general


def test_pdf_marks_follow_the_stored_cap(conn):
    """HERBI ML SPA, 30/09–06/10/2026: days and row totals over the cap
    are marked, and a higher cap clears every mark."""
    with conn.cursor() as cur:
        for stmt in _SQL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        html = tc._build_contratista_html(
            cur,
            "2026-09-30",
            "2026-10-06",
            contratista="HERBI ML SPA",
            empresa="TALAGANTE",
        )
        umbral = tc._umbral_diario(cur)
        assert umbral == 30000
        assert f"En naranja: montos sobre {tc._fmt_clp(umbral)}." in html

        cells = _CELL_RE.findall(html)
        assert cells, "expected payment cells in the contratista PDF"
        marked = [text for _cls, style, text in cells if "ffedd5" in style]
        assert marked, "expected at least the $35.000 day and row totals over the cap"
        for _cls, style, text in cells:
            amount = _amount(text)
            if amount is None:
                assert "ffedd5" not in style
                continue
            assert ("ffedd5" in style) is (amount > umbral)

        cur.execute(
            """
            UPDATE appsheet.tarjas_configuracion
            SET "umbral_diario" = 999999999
            WHERE "id_configuracion" = 'general'
            """
        )
        raised = tc._build_contratista_html(
            cur,
            "2026-09-30",
            "2026-10-06",
            contratista="HERBI ML SPA",
            empresa="TALAGANTE",
        )
        assert "ffedd5" not in raised
        assert "montos sobre $999.999.999." in raised
