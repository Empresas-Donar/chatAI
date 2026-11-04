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
            assert worked <= set(scoped)
            # A tarjas crew from another campo stays out. Harvest-only names
            # are not in this tarjas set, so they may be added for Zúñiga.
            foreign = {name for name, campo in pairs if campo != sample} - worked
            assert not (set(scoped) & foreign)
    finally:
        conn.close()


def test_harvest_only_contractor_shows_for_zuniga_week():
    """M y G has scans from 28/10 and no tarja after 23/10, so the bar must
    still list the intranet name the detail filter matches."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            names, _ = bar_options_for_period(cur, "2026-10-28", "2026-11-03", "ZUÑIGA")
            other, _ = bar_options_for_period(
                cur, "2026-10-28", "2026-11-03", "ISLA DE MAIPO"
            )
        assert "AGROSERVICIOS M Y G SPA" in names
        assert "Myd betzabe" in names
        assert "AGROSERVICIOS M Y G SPA" not in other
    finally:
        conn.close()
