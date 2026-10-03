from __future__ import annotations


def money(value: float, currency: str = "EUR") -> str:
    return f"{currency} {value:,.0f}"


def safe_get(mapping: dict, key: str, default="Not available"):
    value = mapping.get(key, default)
    return default if value in (None, "") else value
