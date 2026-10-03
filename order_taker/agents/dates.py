"""Turn the delivery day a customer wrote into a date, in plain code (INT-21).
Small models are bad at calendar arithmetic; a lookup table isn't."""

from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
# English plus common Hindi / Kannada / Tamil words typed in English letters
OFFSETS = [
    (r"day after tomorrow|day after tmrw|parso|parson|naadidhu|naalai marunaal", 2),
    (r"tomorrow|tmrw|tmr|tomo|kal|naale|nale|naalai", 1),
    (r"today|tonight|aaj|ivattu|indru|inniki", 0),
]


def resolve_date(written: str, ref: date) -> str:
    """ISO date for what the customer wrote, relative to `ref`; unchanged text if it can't be worked out."""
    text = (written or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    low = text.lower()

    for pattern, days in OFFSETS:
        if re.search(rf"\b({pattern})\b", low):
            return (ref + timedelta(days=days)).isoformat()

    explicit = _day_month(low, ref)
    if explicit:
        return explicit.isoformat()

    m = re.search(r"\b(next|this|coming)?\s*(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")\b", low)
    if m:
        ahead = (WEEKDAYS[m.group(2)] - ref.weekday()) % 7
        if m.group(1) == "next" and ahead == 0:
            ahead = 7
        return (ref + timedelta(days=ahead)).isoformat()
    return text


def _day_month(low: str, ref: date) -> date | None:
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    patterns = [
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({month_names})\b", "dm"),
        (rf"\b({month_names})\s*(\d{{1,2}})(?:st|nd|rd|th)?\b", "md"),
        (r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", "num"),  # day first, as in India
    ]
    for pattern, kind in patterns:
        m = re.search(pattern, low)
        if not m:
            continue
        try:
            if kind == "dm":
                day, month, year = int(m.group(1)), MONTHS[m.group(2)], None
            elif kind == "md":
                day, month, year = int(m.group(2)), MONTHS[m.group(1)], None
            else:
                day, month = int(m.group(1)), int(m.group(2))
                year = int(m.group(3)) if m.group(3) else None
                if year is not None and year < 100:
                    year += 2000
            d = date(year or ref.year, month, day)
        except ValueError:
            return None
        if year is None and d < ref - timedelta(days=30):  # "5th Jan" said in December means next year
            d = d.replace(year=d.year + 1)
        return d
    return None
