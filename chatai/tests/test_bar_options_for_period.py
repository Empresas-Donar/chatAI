"""The shared filter bar lists campos with rows in the dates, then who worked there."""

import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), interpolate=False)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from controllers.tarjas_controller import bar_options_for_period  # noqa: E402
from db import get_connection  # noqa: E402

WEEK = ("2026-10-14", "2026-10-20")


def _pairs(cur):
    cur.execute(
        """
        SELECT contratista, nombre_campo
        FROM appsheet.tarjas_pagos
        WHERE contratista IS NOT NULL
          AND nombre_campo IS NOT NULL
          AND fecha::date BETWEEN %s AND %s
        GROUP BY contratista, nombre_campo
        ORDER BY contratista, nombre_campo
        """,
        WEEK,
    )
    return cur.fetchall()


def test_empresa_limits_contractors_to_who_worked_there():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            pairs = _pairs(cur)
            if not pairs:
                pytest.skip("no tarjas in the sample week")
            by_campo = {}
            for name, campo in pairs:
                by_campo.setdefault(campo, set()).add(name)
            names, all_campos = bar_options_for_period(cur, *WEEK, None)
            sample = next(campo for campo in all_campos if campo in by_campo)
            worked = by_campo[sample]

            scoped, still_all = bar_options_for_period(cur, *WEEK, sample)
            assert still_all == all_campos
            assert set(scoped) <= worked
            others = [name for name in names if name not in worked]
            if others:
                assert others[0] not in scoped
    finally:
        conn.close()
