"""Exact ISO instant conversion. Storage/correlation never pass through float seconds."""
from datetime import datetime, timedelta, timezone
import re

CHICAGO = "America/Chicago"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ISO = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?")


def unix_ns(value, *, assume_utc=False):
    """Parse 0–9 fractional digits exactly; naive legacy UTC requires explicit opt-in.

    Reject unsupported precision instead of truncating beyond datetime microseconds.
    Offsets describe the instant; the original string is never modified in storage.
    """
    text = str(value)
    if assume_utc and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00"
    match = _ISO.fullmatch(text)
    if not match:
        raise ValueError("Expected ISO timestamp with at most nine fractional digits")
    day, clock, fraction, offset = match.groups()
    if offset is None and not assume_utc:
        raise ValueError("Timestamp requires a timezone offset")
    base = datetime.fromisoformat(day + "T" + clock).replace(tzinfo=timezone.utc)
    if offset and offset != "Z":
        hours, minutes = map(int, offset[1:].split(":"))
        if hours > 23 or minutes > 59:
            raise ValueError("Invalid timestamp offset")
        base -= timedelta(minutes=(1 if offset[0] == "+" else -1) * (hours * 60 + minutes))
    delta = base - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int((fraction or "0").ljust(9, "0"))


def utc_iso(ns):
    """Exact UTC ISO representation for query boundaries, including pre-epoch instants."""
    seconds, fraction = divmod(ns, 1_000_000_000)
    return (_EPOCH + timedelta(seconds=seconds)).isoformat(timespec="seconds").removesuffix("+00:00") + f".{fraction:09d}Z"
