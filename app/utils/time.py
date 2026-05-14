from __future__ import annotations

import re
from datetime import date, datetime, timezone


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def parse_entry_date(text: str) -> date | None:
    text = text.strip()
    if re.search(r"מיידי|מידי", text):
        return date.today()
    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year_raw = m.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            today = date.today()
            year = today.year
            if date(year, month, day) < today:
                year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None
