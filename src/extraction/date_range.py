"""Dependency-free Turkish campaign date-range extraction."""

from __future__ import annotations

import re
from datetime import date


MONTHS = {
    "ocak": 1, "\u015fubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "may\u0131s": 5, "mayis": 5, "haziran": 6, "temmuz": 7,
    "a\u011fustos": 8, "agustos": 8, "eyl\u00fcl": 9, "eylul": 9,
    "ekim": 10, "kas\u0131m": 11, "kasim": 11, "aral\u0131k": 12,
    "aralik": 12,
}
MONTH_PATTERN = "|".join(MONTHS)
NUMERIC = r"\d{1,2}[./-]\d{1,2}[./-]\d{4}"
TEXTUAL = rf"\d{{1,2}}\s+(?:{MONTH_PATTERN})(?:\s+\d{{4}})?"
FULL_TEXTUAL = rf"\d{{1,2}}\s+(?:{MONTH_PATTERN})\s+\d{{4}}"


def _parse(value: str, default_year: int | None = None) -> date | None:
    normalized = value.strip().casefold().replace("i\u0307", "i")
    numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", normalized)
    if numeric:
        day, month, year = map(int, numeric.groups())
    else:
        textual = re.fullmatch(
            rf"(\d{{1,2}})\s+({MONTH_PATTERN})(?:\s+(\d{{4}}))?", normalized
        )
        if not textual:
            return None
        day = int(textual.group(1))
        month = MONTHS[textual.group(2)]
        year = int(textual.group(3)) if textual.group(3) else default_year
        if year is None:
            return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_date_range(text: str) -> tuple[date | None, date | None]:
    """Return the first explicit range, otherwise a labelled campaign end date."""
    source = str(text or "")
    numeric = re.search(rf"({NUMERIC})\s*(?:-|\u2013|\u2014)\s*({NUMERIC})", source)
    if numeric:
        return _parse(numeric.group(1)), _parse(numeric.group(2))

    textual = re.search(
        rf"({TEXTUAL})\s*(?:-|\u2013|\u2014)\s*({FULL_TEXTUAL})", source, re.IGNORECASE
    )
    if textual:
        end = _parse(textual.group(2))
        return _parse(textual.group(1), end.year if end else None), end

    end_only = re.search(
        rf"(?:son\s+ge\u00e7erlilik\s+tarihi|sona\s+erme\s+tarihi|"
        rf"tarihinde\s+sona\s+er)\D{{0,24}}({NUMERIC}|{FULL_TEXTUAL})",
        source,
        re.IGNORECASE,
    )
    return (None, _parse(end_only.group(1))) if end_only else (None, None)
