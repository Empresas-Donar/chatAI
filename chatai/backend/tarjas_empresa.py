"""Platform factors for company-side tarjas money (Costo Empresa).

Trato ×1.45 (+45 %) and Al Día ×1.50 (+50 %) on SUM(total_trabajado).
Other tipo_pago values (Bono, Tractorista, …) keep factor 1.0 — do not
invent a markup. NEVER invert these percentages.

MUST use these helpers for any report that shows what the company pays
for labores: Detalle Costo Empresa, Orden de compra, Orden de facturación,
Nota de crédito, Dashboard tarjas totals. Never AppSheet total_pagar
(often 0) nor total_trabajado+total_contratista as billed company cost —
billed cost is always total_trabajado × factor via total_empresa().
AppSheet total_contratista happens to use the same percentages
(~45 % trato / ~50 % al día); still never bill from those columns.

Worker-pay reports (General, Por persona, ranking) stay on total_trabajado.
The Odoo xlsx is priced by calling these helpers from
`costo_empresa_odoo_lines` (purchase_orders_controller). Do not copy the
factors into JS, SQL views, or controllers — change FACTOR_EMPRESA_* here
only.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

FACTOR_EMPRESA_AL_DIA = Decimal("1.50")
FACTOR_EMPRESA_TRATO = Decimal("1.45")
FACTOR_EMPRESA_DEFAULT = Decimal("1")

_AL_DIA = frozenset({"al dia", "al día"})
_TRATO = frozenset({"trato"})


def _as_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def factor_empresa(tipo_pago: str | None) -> Decimal:
    key = (tipo_pago or "").strip().lower()
    if key in _AL_DIA:
        return FACTOR_EMPRESA_AL_DIA
    if key in _TRATO:
        return FACTOR_EMPRESA_TRATO
    return FACTOR_EMPRESA_DEFAULT


def total_empresa(tipo_pago: str | None, total_trabajado) -> Decimal:
    """Money amount: total_trabajado × factor, rounded to whole CLP."""
    amount = _as_decimal(total_trabajado) * factor_empresa(tipo_pago)
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def pct_of(part, whole) -> Decimal | None:
    """Share of `part` over `whole` as a 1-decimal percentage, or None if whole is 0."""
    w = _as_decimal(whole)
    if w <= 0:
        return None
    return (_as_decimal(part) / w * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def format_pct(pct: Decimal | float | None) -> str:
    if pct is None:
        return "—"
    return f"{float(pct):.1f} %"


def markup_pct(tipo_pago: str | None) -> Decimal:
    """Added percentage on Total trabajado: 50 Al Día, 45 Trato, 0 otherwise."""
    return (factor_empresa(tipo_pago) - FACTOR_EMPRESA_DEFAULT) * 100


def format_markup(pct: Decimal | float | None) -> str:
    if pct is None:
        return "—"
    value = _as_decimal(pct)
    if value == 0:
        return "—"
    if value == value.to_integral_value():
        return f"+{int(value)} %"
    return f"+{float(value):.1f} %"


def annotate_detalle_rows(rows: list[dict]) -> list[dict]:
    """Add Costo Empresa (total_trabajado × factor) to each Detalle row."""
    out = []
    for r in rows:
        row = dict(r)
        row["total_empresa"] = float(
            total_empresa(row.get("tipo_pago"), row.get("total_trabajado"))
        )
        out.append(row)
    return out


def annotate_detalle_resumen(resumen: list[dict]) -> list[dict]:
    """Add total_empresa, recargo_pct and pct (vs grand Total trabajadores)."""
    grand_trab = sum(_as_decimal(r.get("total_trabajado")) for r in resumen)
    out = []
    for r in resumen:
        row = dict(r)
        trab = _as_decimal(row.get("total_trabajado"))
        tipo = row.get("tipo_pago")
        row["total_empresa"] = float(total_empresa(tipo, trab))
        recargo = markup_pct(tipo)
        row["recargo_pct"] = float(recargo)
        row["recargo"] = format_markup(recargo)
        pct = pct_of(trab, grand_trab)
        row["pct"] = float(pct) if pct is not None else None
        out.append(row)
    return out


def fold_costo_empresa(pairs) -> float:
    """Sum Costo Empresa over (tipo_pago, total_trabajado) pairs."""
    total = Decimal("0")
    for tipo, trab in pairs:
        total += total_empresa(tipo, trab)
    return float(total)
