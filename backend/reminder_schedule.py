"""Conservative scheduling helpers for deadline reminders.

Only explicit, parseable dates are eligible for durable reminders.  This
module deliberately does not infer a time of day or turn vague language into
a deadline.
"""

from __future__ import annotations

import re
from datetime import date, datetime


def parse_deadline(value: str | None, today: date | None = None) -> date | None:
    """Parse supported deadline strings and leave everything else alone."""
    if not value:
        return None

    normalized = value.strip()
    for format_string in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(normalized, format_string).date()
        except ValueError:
            pass

    month_day = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\b", normalized)
    if not month_day:
        return None
    try:
        parsed = datetime.strptime(f"2000 {month_day.group(1)} {month_day.group(2)}", "%Y %B %d").date()
    except ValueError:
        try:
            parsed = datetime.strptime(f"2000 {month_day.group(1)} {month_day.group(2)}", "%Y %b %d").date()
        except ValueError:
            return None

    current_day = today or date.today()
    try:
        candidate = parsed.replace(year=current_day.year)
    except ValueError:
        # A yearless February 29 is ambiguous in a non-leap current year.
        return None
    if candidate >= current_day:
        return candidate
    try:
        return candidate.replace(year=current_day.year + 1)
    except ValueError:
        return None


def reminder_window(deadline: date | None, today: date) -> str | None:
    """Return the one safe reminder cadence supported by date-only metadata."""
    if deadline is None:
        return None
    days_away = (deadline - today).days
    if days_away == 1:
        return "tomorrow"
    if days_away == 0:
        return "today"
    return None
