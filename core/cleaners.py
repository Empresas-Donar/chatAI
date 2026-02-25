import re


def clean_currency(value) -> float:
    """'$18.000' → 18000.0"""
    if not value or str(value).strip() == "":
        return None
    cleaned = re.sub(r"[\$\.\s]", "", str(value)).replace(",", ".")
    return float(cleaned)


def clean_percentage(value) -> float:
    """'45,00%' → 0.45"""
    if not value or str(value).strip() == "":
        return None
    cleaned = str(value).replace("%", "").replace(",", ".").strip()
    return round(float(cleaned) / 100, 6)


def clean_boolean(value) -> bool:
    """'Yes'/'No'/'TRUE'/'FALSE' → True/False"""
    if value is None:
        return None
    return str(value).strip().upper() in ("YES", "TRUE", "1", "SI", "SÍ")


def clean_date(value) -> str:
    """Normaliza fechas a ISO YYYY-MM-DD"""
    import pandas as pd
    if not value or str(value).strip() == "":
        return None
    try:
        return pd.to_datetime(value, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def clean_enumlist(value) -> list:
    """'a, b, c' → ['a', 'b', 'c']"""
    if not value or str(value).strip() == "":
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]
