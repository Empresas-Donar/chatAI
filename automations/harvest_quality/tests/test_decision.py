from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pypdf import PdfWriter

from harvest_quality.decision import ENVIADO, SIN_CAMBIOS, SIN_DATOS, decide
from harvest_quality.fingerprint import fingerprint_text
from harvest_quality.pages import split_pages
from harvest_quality.report import SessionMissing, run_attempts
from harvest_quality.schedule import is_due, needs_n8n_force
from harvest_quality.state import dotenv_paths

SANTIAGO = ZoneInfo("America/Santiago")
HOURS = [8, 9, 10, 11, 12, 13, 14, 15, 16]


def test_same_fingerprint_does_not_send():
    assert decide("abc", "abc") == SIN_CAMBIOS


def test_first_data_sends():
    assert decide("abc", None) == ENVIADO


def test_changed_fingerprint_sends():
    assert decide("nuevo", "viejo") == ENVIADO


def test_no_pages_does_not_send():
    assert decide(None, "viejo") == SIN_DATOS
    assert decide("", "viejo") == SIN_DATOS


def test_stamp_line_is_not_a_change():
    base = "Cuadrilla 1\n10 monitoreos"
    later = base + "\nFecha de la última actualización: 29/10/2026 16:12:24"
    assert fingerprint_text(base) == fingerprint_text(later)


def test_empty_text_has_no_fingerprint():
    assert fingerprint_text("Fecha de la última actualización: 29/10/2026 16:12:24") is None


def test_window_includes_eight_and_sixteen():
    assert is_due(datetime(2026, 10, 29, 8, 0, tzinfo=SANTIAGO), HOURS, 25)
    assert is_due(datetime(2026, 10, 29, 16, 12, tzinfo=SANTIAGO), HOURS, 25)
    assert not is_due(datetime(2026, 10, 29, 17, 0, tzinfo=SANTIAGO), HOURS, 25)


def test_evening_hours_need_forzar_for_n8n():
    assert not needs_n8n_force(16)
    assert needs_n8n_force(17)
    assert needs_n8n_force(21)


def test_outside_hours_and_late_grace_are_skipped():
    assert not is_due(datetime(2026, 10, 29, 7, 0, tzinfo=SANTIAGO), HOURS, 25)
    assert not is_due(datetime(2026, 10, 29, 22, 0, tzinfo=SANTIAGO), HOURS, 25)
    assert not is_due(datetime(2026, 10, 29, 8, 40, tzinfo=SANTIAGO), HOURS, 25)


def test_sunday_inside_the_hour_is_due():
    sunday = datetime(2026, 11, 1, 10, 0, tzinfo=SANTIAGO)
    assert sunday.weekday() == 6
    assert is_due(sunday, HOURS, 25)


def _pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_empty_marker_drops_a_page_without_a_table():
    kept, huella = split_pages(_pdf("No hay datos"), "No hay datos")
    assert kept == b""
    assert huella is None


def test_column_title_without_rows_is_dropped():
    kept, huella = split_pages(
        _pdf("Cosechero Muestras No hay datos"),
        "No hay datos",
    )
    assert kept == b""
    assert huella is None


def test_page_with_table_stays_even_if_one_chart_is_empty():
    kept, huella = split_pages(
        _pdf("No hay datos 1 2 5 6 3 4 2 3"),
        "No hay datos",
    )
    assert kept
    assert huella


def test_page_with_data_keeps_a_fingerprint():
    kept, huella = split_pages(_pdf("Cuadrilla 1"), "No hay datos")
    assert kept
    assert huella


def test_cloud_run_image_has_no_dotenv_parent():
    assert dotenv_paths(Path("/app")) == []


def test_looker_download_retries_five_times():
    calls = {"n": 0}

    def fail():
        calls["n"] += 1
        raise TimeoutError("download")

    try:
        run_attempts(fail, attempts=6)
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected the last attempt to raise")
    assert calls["n"] == 6


def test_looker_download_returns_when_a_later_attempt_works():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("download")
        return b"pdf"

    assert run_attempts(flaky, attempts=6) == b"pdf"
    assert calls["n"] == 3


def test_missing_session_is_not_retried():
    calls = {"n": 0}

    def fail():
        calls["n"] += 1
        raise SessionMissing("empty")

    try:
        run_attempts(fail, attempts=6)
    except SessionMissing:
        pass
    else:
        raise AssertionError("expected SessionMissing")
    assert calls["n"] == 1

