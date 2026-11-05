"""Presentation-only Chicago views. Never mutate frames used for queries or exports."""
import json
import re
import pandas as pd
import altair as alt
from timestamps import CHICAGO

_AWARE_ISO = re.compile(r"^\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)$")


def chicago_time(value):
    """Leave unknown/naive legacy times alone; aware timestamps identify an instant."""
    if isinstance(value, str) and not _AWARE_ISO.fullmatch(value):
        return value
    if not isinstance(value, (str, pd.Timestamp)):
        return value
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            return value
        local = stamp.tz_convert(CHICAGO)
        fraction = f"{local.microsecond:06d}" + (f"{local.nanosecond:03d}" if local.nanosecond else "")
        return local.strftime("%Y-%m-%d %H:%M:%S") + "." + fraction + local.strftime(" %Z (UTC%z)")
    except (ValueError, TypeError, OverflowError):
        return value


def chicago_frame(frame):
    """A separate human-readable copy, including arbitrary audit/summary timestamp cells."""
    if not isinstance(frame, pd.DataFrame):
        return frame
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]) or out[column].dtype == object:
            out[column] = out[column].map(chicago_time)
    # Explicit UTC labels belong to the canonical export, not the displayed copy.
    out.columns = [str(c).replace('(UTC)', '(Chicago)').replace('_utc', '_chicago')
                   if 'UTC' in str(c) or str(c).endswith('_utc') else c for c in out.columns]
    return out


def chicago_record(value):
    """Keep raw JSON/provenance fields visible; add clearly separate display fields."""
    if isinstance(value, dict):
        out = {k: chicago_record(v) for k, v in value.items()}
        displays = {k: chicago_time(v) for k, v in value.items()
                    if isinstance(v, (str, pd.Timestamp)) and chicago_time(v) != v}
        if displays:
            out['_display_America_Chicago'] = displays
        return out
    if isinstance(value, list):
        return [chicago_record(v) for v in value]
    return value


def chicago_axis(values):
    """UTC coordinates preserve order/DST folds; explicit labels avoid browser timezone."""
    times = pd.to_datetime(values, utc=True, errors='coerce').dropna().sort_values().drop_duplicates()
    chosen = times.iloc[::max(1, len(times) // 5)] if isinstance(times, pd.Series) else times[::max(1, len(times) // 5)]
    labels = {str(t.value // 1_000_000): chicago_time(t) for t in chosen}
    return alt.Axis(values=[int(v) for v in labels], labelExpr=json.dumps(labels) + '[toString(datum.value)]', labelLimit=250)


def chicago_chart_data(frame, column):
    out = frame.copy()
    out['display_time_chicago'] = pd.to_datetime(out[column], utc=True, errors='coerce').map(chicago_time)
    return out
