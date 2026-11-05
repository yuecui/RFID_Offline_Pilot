"""Data-only Streamlit views reusing the verified Dashboard plotting helpers."""
from __future__ import annotations
import pandas as pd
import altair as alt
import streamlit as st

from offline_analysis import frame_from_parsed, time_window, describe_quality, metric_options, pair_tags
from dashboard_components.charts import make_multitag_chart
from dashboard_components.colors import build_tag_colors
from dashboard_components.chicago import chicago_frame, chicago_chart_data, chicago_axis
from dashboard_components.labels import short_epc

TIME_WINDOWS = {"Full session": None, "Last 5 min": 5, "Last 15 min": 15,
                "Last 60 min": 60, "Last 360 min": 360, "Last 1440 min": 1440}


def render_session(parsed, prefix):
    frame = frame_from_parsed(parsed)
    if frame.empty:
        st.info("No valid timestamps")
        return frame
    top = st.columns(4)
    top[0].metric("Readings", f"{len(frame):,}")
    top[1].metric("Unique EPCs", f"{frame['epc'].nunique():,}")
    top[2].metric("Mean RSSI", f"{frame['rssi'].mean():.1f} dBm")
    top[3].metric("Duration", f"{(frame['time'].max()-frame['time'].min()).total_seconds():.1f} s")
    st.caption("Raw USER words and diagnostic payloads are not physically validated pressure/temperature. "
               "No pressure is estimated without approved decoder and model evidence.")
    overview, trend, quality, pairing, raw = st.tabs(["EPC overview", "Recorded trends", "Data quality", "Two-tag alignment", "Raw / Export"])
    with overview:
        left,right=st.columns(2)
        counts=frame["epc"].value_counts().rename_axis("epc").reset_index(name="Readings")
        with left:
            st.subheader("Reads by EPC")
            st.bar_chart(counts.set_index("epc"))
        with right:
            st.subheader("Mean RSSI by EPC")
            st.bar_chart(frame.groupby("epc")["rssi"].mean().sort_values())
    with trend:
        epcs = sorted(frame["epc"].unique().tolist())
        chosen = st.multiselect("EPCs to plot", epcs, default=epcs, key=prefix+"epcs", format_func=short_epc)
        window = st.selectbox("Recorded window", list(TIME_WINDOWS), key=prefix+"window")
        scoped = time_window(frame, TIME_WINDOWS[window])
        scoped = scoped.loc[scoped["epc"].isin(chosen)]
        choices = metric_options(scoped)
        if not choices:
            st.warning("No numeric metrics in this range.")
        else:
            metric = st.selectbox("Trend metric", list(choices), key=prefix+"metric")
            value, unit = choices[metric]
            chart = make_multitag_chart(scoped, "time", value, metric, unit, build_tag_colors(chosen))
            if chart is not None:
                st.altair_chart(chart, use_container_width=True)
            st.caption("The recording window ends at the selected session's final observation, not at today's time.")
            if value in {"user0_word","user1_word"}:
                st.warning("Packed USER words include header/status bits; interpret trends using payload plots.")
            if not scoped.empty:
                st.dataframe(chicago_frame(scoped.groupby("epc")[value].agg(["count","mean","min","max"]).reset_index()), use_container_width=True, hide_index=True)
    with quality:
        metrics = describe_quality(frame)
        st.subheader("Acquisition quality by EPC")
        st.dataframe(chicago_frame(metrics["by_tag"]), use_container_width=True, hide_index=True)
        st.subheader("Session tag summary")
        st.dataframe(chicago_frame(metrics["summary"]), use_container_width=True, hide_index=True)
        st.subheader("Session metadata integrity")
        st.dataframe(metrics["metadata"], use_container_width=True, hide_index=True)
        for field in ("user0_word_header_valid", "user1_word_header_valid"):
            if field in frame.columns:
                matches = frame[field].fillna(False).sum()
                st.caption(f"{field}: {int(matches)}/{len(frame)} satisfy the documented 0b10 header rule; "
                           "a match alone is not a physical decoder validation.")
    with pairing:
        epcs = sorted(frame["epc"].unique().tolist())
        if len(epcs) < 2:
            st.info("At least two EPCs required.")
        else:
            a, b, c = st.columns([2,2,1])
            ea = a.selectbox("Tag A", epcs, key=prefix+"tag_a")
            eb = b.selectbox("Tag B", [x for x in epcs if x!=ea], key=prefix+"tag_b")
            tolerance = c.number_input("Max gap (ms)", min_value=10, max_value=10000,
                                       value=2000, step=100, key=prefix+"gap")
            options = metric_options(frame)
            if options:
                name = st.selectbox("Comparison metric", list(options), key=prefix+"pairmetric")
                column, axis = options[name]
                paired = pair_tags(frame, ea, eb, column, int(tolerance))
                if paired.empty:
                    st.info("No timestamp pairs within tolerance; do not assume scans are simultaneous.")
                else:
                    d1,d2,d3 = st.columns(3)
                    d1.metric("Matched pairs", len(paired))
                    d2.metric("Mean A − B", f"{paired['difference'].mean():.3f}")
                    d3.metric("Mean gap", f"{paired['time_gap_ms'].mean():.1f} ms")
                    data = chicago_chart_data(paired,"pair_time")
                    chart = (alt.Chart(data).mark_line(point=True)
                             .encode(x=alt.X("pair_time:T", title="Time (America/Chicago)", scale=alt.Scale(type="utc"),axis=chicago_axis(data["pair_time"])),
                                     y=alt.Y("difference:Q", title=f"A − B ({axis})"),
                                     tooltip=["display_time_chicago:N","tag_a:Q","tag_b:Q","difference:Q","time_gap_ms:Q"])
                             .properties(height=330))
                    st.altair_chart(chart,use_container_width=True)
                    st.dataframe(chicago_frame(paired),hide_index=True,use_container_width=True)
    with raw:
        st.dataframe(chicago_frame(frame),use_container_width=True,hide_index=True)
        st.download_button("Download derived analysis CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"{parsed.manifest['session_id']}_derived.csv", mime="text/csv",key=prefix+"export")
        st.caption("Original uploaded bytes remain unchanged in S3; this CSV is a separate derived view.")
    return frame


def render_session_comparison(parsed_sessions):
    """Compare session trends by elapsed minutes, preserving source session IDs."""
    frames=[]
    for session in parsed_sessions:
        df=frame_from_parsed(session)
        if df.empty: continue
        df["session_label"] = session.manifest["session_id"] + " · " + session.raw_sha256[:8]
        df["elapsed_min"] = (df["time"] - df["time"].min()).dt.total_seconds()/60.0
        frames.append(df)
    if len(frames)<2:
        st.info("At least two valid sessions required.")
        return
    combined=pd.concat(frames,ignore_index=True)
    labels=sorted(combined["session_label"].unique())
    rows=[]
    for label in labels:
        group=combined.loc[combined["session_label"]==label]
        rows.append({"Session":label,"Readings":len(group),"Unique EPCs":group["epc"].nunique(),
                     "Mean RSSI":group["rssi"].mean(),"Duration (s)":(group["time"].max()-group["time"].min()).total_seconds()})
    summary=pd.DataFrame(rows)
    st.dataframe(summary,hide_index=True,use_container_width=True)
    options=metric_options(combined)
    if not options:return
    name=st.selectbox("Overlay metric",list(options),key="overlay_metric")
    column, axis=options[name]
    data=combined[["elapsed_min","epc","session_label",column]].copy()
    data[column]=pd.to_numeric(data[column],errors="coerce")
    data=data.dropna(subset=[column])
    data["series"] = data["session_label"] + " · " + data["epc"].map(lambda s:short_epc(s,6))
    chart=(alt.Chart(data).mark_line(point=True)
           .encode(x=alt.X("elapsed_min:Q",title="Elapsed minutes since session start"),
                   y=alt.Y(f"{column}:Q",title=axis),color="series:N",
                   tooltip=["session_label:N","epc:N","elapsed_min:Q",alt.Tooltip(f"{column}:Q",title=axis)])
           .properties(height=380).interactive())
    st.altair_chart(chart,use_container_width=True)
    st.download_button("Download summary CSV",summary.to_csv(index=False).encode("utf-8"),
                       file_name="session_comparison.csv",mime="text/csv",key="overlay_export")
