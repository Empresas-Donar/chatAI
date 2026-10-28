"""Answers that state data must come from a query in the same turn."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controllers.chat_controller import _answer_is_ungrounded

_FAKE = """
En total, se utilizaron 17 bins para recolectar los 752 capachos del día.

| Bin | Trabajador | RUT | Contratista | Capachos |
| 74 | ALVARO NICOLAS CORNEJO CORNEJO | 20.245.029-4 | HALCON | 42 |

📊 Fuente: appsheet.cosecha_zuniga_escaneo · PostgreSQL (AppSheet) · 18 registros
"""


def test_invented_table_without_a_query_is_blocked():
    assert _answer_is_ungrounded(_FAKE, [], "")


def test_same_table_is_blocked_when_the_rut_was_not_in_the_rows():
    traces = [{"sql": "select 1", "row_count": 2}]
    grounded = "gutierrez ii\n12.345.678-9"
    assert _answer_is_ungrounded(_FAKE, traces, grounded)


def test_rut_from_the_query_is_allowed():
    traces = [{"sql": "select 1", "row_count": 1}]
    grounded = "alvaro nicolas cornejo cornejo\n20.245.029-4\nhalcon"
    assert not _answer_is_ungrounded(_FAKE, traces, grounded)


def test_zero_rows_cannot_carry_a_table():
    traces = [{"sql": "select 1", "row_count": 0}]
    assert _answer_is_ungrounded(_FAKE, traces, "")


def test_a_date_with_no_rows_can_be_reported():
    traces = [{"sql": "select 1", "row_count": 0}]
    text = "No encontré registros de cosecha para el 27 de octubre de 2026."
    assert not _answer_is_ungrounded(text, traces, "")


def test_a_greeting_needs_no_query():
    assert not _answer_is_ungrounded("Hola, ¿en qué te ayudo?", [], "")
