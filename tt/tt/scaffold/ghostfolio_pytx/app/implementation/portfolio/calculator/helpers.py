"""Helper functions for the ROAI portfolio calculator.

These are generic financial calculation helpers used by the translated
calculator. They live in the scaffold so the translator can reference them
without embedding domain logic in tt/.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal


D = Decimal


def get_factor(activity_type: str) -> int:
    """BUY adds units (+1), SELL removes them (-1), everything else is 0."""
    if activity_type == "BUY":
        return 1
    elif activity_type == "SELL":
        return -1
    return 0


def parse_date(s: str) -> date:
    """Parse YYYY-MM-DD string to date."""
    return date.fromisoformat(s)


def date_str(d: date) -> str:
    """Format date as YYYY-MM-DD string."""
    return d.isoformat()


def each_year_of_interval(start: date, end: date) -> list[date]:
    """Return Jan 1 of each year in the range [start, end]."""
    return [date(y, 1, 1) for y in range(start.year, end.year + 1)]


def difference_in_days(a: date, b: date) -> int:
    """Number of days between two dates."""
    return (a - b).days
