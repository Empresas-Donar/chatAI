"""Default report week is the last completed Wednesday–Tuesday close."""

from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "frontend" / "static" / "global-filters.js"


def test_js_documents_close_week_examples():
    text = JS.read_text(encoding="utf-8")
    assert "2026-09-02 .. 2026-09-08" in text
    assert "2026-09-09 .. 2026-09-15" in text
    assert "DATE_SESSION_KEY" in text
    assert "donar.globalFilterDates" in text
    assert "getDay() !== 2" in text


def test_current_week_range_matches_close_examples():
    import json
    import subprocess

    src = JS.read_text(encoding="utf-8")
    start = src.index("function _toLocalISO")
    end = src.index("function _readStored")
    fns = src[start:end]
    script = fns + """
const cases = [
  [new Date(2026, 8, 11), '2026-09-02', '2026-09-08'],
  [new Date(2026, 8, 16), '2026-09-09', '2026-09-15'],
  [new Date(2026, 8, 15), '2026-09-02', '2026-09-08'],
];
const out = cases.map(([d, from, to]) => {
  const w = currentWeekRange(d);
  return { ok: w.from === from && w.to === to, got: w, from, to };
});
process.stdout.write(JSON.stringify(out));
"""
    raw = subprocess.check_output(["node", "-e", script], text=True)
    results = json.loads(raw)
    for row in results:
        assert row["ok"], row
