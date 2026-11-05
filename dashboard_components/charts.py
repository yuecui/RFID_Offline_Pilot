"""Extracted charts responsibilities; original calculations and widget behavior preserved."""
from dashboard_components.chicago import chicago_axis, chicago_chart_data
from dashboard_components.colors import stable_tag_color
from dashboard_components.labels import short_epc
import altair as alt
import pandas as pd

def chart_builders(short_epc=short_epc):
    def make_date_comparison_chart(
        frame,
        value_column,
        y_title,
        tag_colors,
    ):
        """Overlay multiple calendar days on elapsed time from each day's first reading."""
        if frame.empty or value_column not in frame.columns:
            return None

        data = frame.copy()
        data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
        data["time"] = pd.to_datetime(data["time"], errors="coerce", utc=True)
        data = data.dropna(subset=["time", "epc", value_column, "comparison_date"])
        if data.empty:
            return None

        first_times = data.groupby("comparison_date")["time"].transform("min")
        data["elapsed_minutes"] = (data["time"] - first_times).dt.total_seconds() / 60.0
        data["series_label"] = (
            data["comparison_date"].astype(str)
            + " · "
            + data["epc"].astype(str).map(lambda value: short_epc(value, 6))
        )

        domain = sorted(data["series_label"].unique().tolist())

        # Use stable tag color as the basis, but alter dash pattern by date so the
        # same tag remains recognizable across comparison dates.
        color_map = {}
        for label in domain:
            epc_short = label.split(" · ", 1)[-1]
            matching = data.loc[data["series_label"] == label, "epc"]
            epc = str(matching.iloc[0]) if not matching.empty else epc_short
            color_map[label] = tag_colors.get(epc, stable_tag_color(epc))

        color_range = [color_map[label] for label in domain]

        data = chicago_chart_data(data, "time")
        return (
            alt.Chart(data)
            .mark_line(point=False)
            .encode(
                x=alt.X(
                    "elapsed_minutes:Q",
                    title="Elapsed time from first reading (minutes)",
                ),
                y=alt.Y(f"{value_column}:Q", title=y_title),
                color=alt.Color(
                    "series_label:N",
                    title="Date · Tag",
                    scale=alt.Scale(domain=domain, range=color_range),
                ),
                strokeDash=alt.StrokeDash(
                    "comparison_date:N",
                    title="Date",
                ),
                tooltip=[
                    alt.Tooltip("comparison_date:N", title="Date"),
                    alt.Tooltip("epc:N", title="EPC"),
                    alt.Tooltip("display_time_chicago:N", title="Chicago time"),
                    alt.Tooltip("elapsed_minutes:Q", title="Elapsed min", format=".2f"),
                    alt.Tooltip(f"{value_column}:Q", title=y_title),
                ],
            )
            .properties(height=360)
            .interactive()
        )

    def make_multitag_chart(
        df: pd.DataFrame,
        time_column: str,
        value_column: str,
        title: str,
        y_title: str,
        tag_colors,
    ):
        if df.empty or value_column not in df.columns:
            return None

        chart_data = df[[time_column, "epc", value_column]].copy()
        chart_data[value_column] = pd.to_numeric(chart_data[value_column], errors="coerce")
        chart_data = chart_data.dropna(subset=[time_column, "epc", value_column])
        if chart_data.empty:
            return None

        chart_data["tag_display"] = chart_data["epc"].astype(str).map(short_epc)
        epcs = sorted(chart_data["epc"].astype(str).unique().tolist())
        domain = [short_epc(epc) for epc in epcs]
        color_range = [tag_colors.get(epc, stable_tag_color(epc)) for epc in epcs]

        chart_data = chicago_chart_data(chart_data, time_column)
        return (
            alt.Chart(chart_data)
            .mark_line(point=False)
            .encode(
                x=alt.X(f"{time_column}:T", title="Time (America/Chicago)", scale=alt.Scale(type="utc"), axis=chicago_axis(chart_data[time_column])),
                y=alt.Y(f"{value_column}:Q", title=y_title),
                color=alt.Color(
                    "tag_display:N",
                    title="Tag",
                    scale=alt.Scale(domain=domain, range=color_range),
                ),
                tooltip=[
                    alt.Tooltip("display_time_chicago:N", title="Chicago time"),
                    alt.Tooltip("epc:N", title="EPC"),
                    alt.Tooltip(f"{value_column}:Q", title=y_title),
                ],
            )
            .properties(title=title, height=360)
            .interactive()
        )

    return make_date_comparison_chart, make_multitag_chart

make_date_comparison_chart, make_multitag_chart = chart_builders()
