"""Datumsrechnung, die an mehreren Stellen gebraucht wird (Fristen, Wiedervorlagen, Aufbewahrung)."""
from calendar import monthrange
from datetime import date


def add_months(d: date, months: int) -> date:
    """Monate addieren (auch negativ); der Tag wird auf das Monatsende begrenzt (31.01. + 1 -> 28.02.)."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))
