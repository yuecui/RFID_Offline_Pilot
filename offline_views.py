"""Data-only Streamlit views reusing the verified Dashboard plotting helpers."""
from __future__ import annotations
import pandas as pd
import altair as alt
import streamlit as st

from offline_analysis import frame_from_parsed, time_window, describe_quality, metric_options, pair_tags
from offline_extended import (tag_details, session_annotation_editor, calibration_planning, reference_dataset,
                              readiness, trace_and_package, pressure_state)
from dashboard_components.charts import make_multitag_chart
from dashboard_components.colors import build_tag_colors
from dashboard_components.chicago import chicago_frame, chicago_chart_data, chicago_axis
from dashboard_components.labels import short_epc

TIME_WINDOWS = {"Full session": None, "Last 5 min": 5, "Last 15 min": 15,
                "Last 60 min": 60, "Last 360 min": 360, "Last 1440 min": 1440}


def render_session(parsed, prefix, store=None, tag_catalog=None, session_catalog=None):
    frame = frame_from_parsed(parsed, tag_catalog, session_catalog)
    if frame.empty:
        st.info("No valid timestamps")
        return frame
    top = st.columns(4)
    top[0].metric("Readings", f"{len(frame):,}")
    top[1].metric("Unique EPCs", f"{frame['epc'].nunique():,}")
    top[2].metric("Mean RSSI", f"{frame['rssi'].mean():.1f} dBm")
    top[3].metric("Duration", f"{(frame['time'].max()-frame['time'].min()).total_seconds():.1f} s")
    temp_count = int(pd.to_numeric(frame.get("temperature_c"), errors="coerce").notna().sum())
    heuristic_count = int(frame.get("offline_variant_origin",pd.Series(dtype="object")).astype(str)
                          .str.contains("REVIEW",regex=False).sum())
    st.caption("USER words are raw diagnostics. Temperature uses the original Android equations "
               "only where its variant and header checks pass; it is not independently physically validated. "
               "Pressure requires an approved calibration and verified decoder.")
    if temp_count:
        st.info(f"Temperature calculated for {temp_count:,} of {len(frame):,} recorded readings "
                "under format/variant checks. Validate tag identities and environmental calibration before "
                "treating these values as measurements.")
    if heuristic_count:
        st.warning(f"{heuristic_count:,} readings use a presentation-level variant inference. "
                   "Confirm tag type in Tag identity / Rename; the raw session is not altered.")
    (overview,trend,quality,pairing,identity,session_detail,calibration,reference,
     readiness_tab,pressure,package,replay,raw) = st.tabs([
        "EPC overview","Recorded trends","Data quality","Two-tag alignment",
        "Tag identity / Rename","Session details","Calibration coverage","Reference dataset",
        "Readiness","Pressure status","Provenance / Package","Replay","Raw / Export"])
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
        st.subheader("Variant-aware USER header diagnostics")
        if "sensor_header_status" in frame:
            variant_counts=(frame.groupby(["epc","offline_variant","sensor_header_status", "temperature_calc_status"],
                        dropna=False).size().rename("readings").reset_index())
            st.dataframe(variant_counts,hide_index=True,use_container_width=True)
            st.caption("S.5 requires documented USER0/USER1 0b10 (with reserved bit checks); "
                       "T.5 requires USER1 0b11. Unknown variants remain unclassified. "
                       "Header validity is NOT proof of physical calibration.")
        if "s5_interpretation_status" in frame and frame["s5_interpretation_status"].notna().any():
            st.warning("S.5 exploratory values with nonconforming headers remain NON-VALIDATED.")
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
    with identity:
        tag_details(frame, store, tag_catalog or {}, prefix)
    with session_detail:
        session_annotation_editor(parsed,frame,store,session_catalog or {},prefix)
    with calibration:
        calibration_planning(frame,prefix)
    with reference:
        reference_dataset(frame,prefix)
    with readiness_tab:
        readiness(frame,prefix)
    with pressure:
        pressure_state(frame)
    with package:
        trace_and_package(parsed,frame,prefix)
    with replay:
        st.subheader("Recorded Session Replay")
        st.caption("Historical visualization only. This does not connect to a live RFID Reader or generate ACK messages.")
        if not frame.empty:
            pct=st.slider("Playback progress (%)",0,100,100,1,key=prefix+"replay_pct")
            first=frame["time"].min(); last=frame["time"].max()
            cutoff=first + (last-first)*pct/100
            replayed=frame.loc[frame["time"].le(cutoff)].copy()
            st.metric("Replayed readings",len(replayed))
            choices=metric_options(frame)
            if choices:
                metric=st.selectbox("Replay metric",list(choices),key=prefix+"replay_metric")
                value,unit=choices[metric]
                if not replayed.empty:
                    chart=make_multitag_chart(replayed,"time",value,metric,unit,
                                              build_tag_colors(sorted(frame["epc"].unique())))
                    if chart is not None:st.altair_chart(chart,use_container_width=True)
    with raw:
        st.dataframe(chicago_frame(frame),use_container_width=True,hide_index=True)
        st.download_button("Download derived analysis CSV", frame.to_csv(index=False).encode("utf-8"),
                           file_name=f"{parsed.manifest['session_id']}_derived.csv", mime="text/csv",key=prefix+"export")
        st.caption("Original uploaded bytes remain unchanged in S3; this CSV is a separate derived view.")
    return frame


def render_session_comparison(parsed_sessions, tag_catalog=None, session_catalog=None):
    """Compare session trends by elapsed minutes, preserving source session IDs."""
    frames=[]
    for session in parsed_sessions:
        df=frame_from_parsed(session,tag_catalog, session_catalog)
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
    st.subheader("Compare two recorded days (America/Chicago local time)")
    local=combined["time"].dt.tz_convert("America/Chicago")
    combined["recorded_date_local"]=local.dt.date.astype(str)
    combined["local_time_minutes"]=(local.dt.hour * 60 + local.dt.minute +
                                      local.dt.second / 60.0 + local.dt.microsecond / 60000000.0)
    days=sorted(combined["recorded_date_local"].unique())
    if len(days)<2:
        st.info("Upload two distinct recording dates to compare them by local time of day.")
    else:
        a,b=st.columns(2)
        day_a=a.selectbox("Day A",days,key="comparison_day_a")
        day_b=b.selectbox("Day B",[d for d in days if d!=day_a],key="comparison_day_b")
        daily=combined.loc[combined["recorded_date_local"].isin([day_a,day_b])].copy()
        choice=st.selectbox("Two-day metric",list(options),key="two_day_metric")
        column,units=options[choice]
        daily[column]=pd.to_numeric(daily[column],errors="coerce")
        daily=daily.dropna(subset=[column])
        if daily.empty:
            st.info("Selected days have no numeric values for this metric.")
        else:
            daily["series"]=daily["recorded_date_local"]+" · "+daily["epc"].map(lambda x:short_epc(x,6))
            graph=(alt.Chart(daily).mark_line(point=True).encode(
                x=alt.X("local_time_minutes:Q",title="Minutes after midnight (America/Chicago)"),
                y=alt.Y(f"{column}:Q",title=units),color="series:N",
                tooltip=["recorded_date_local:N","epc:N","local_time_minutes:Q",
                         alt.Tooltip(f"{column}:Q",title=units)]).properties(height=350).interactive())
            st.altair_chart(graph,use_container_width=True)
            st.caption("Comparison is by local wall-clock time, not matched sensor timestamps; "
                       "DST transitions may repeat a clock hour. Raw UTC time is preserved.")
            st.download_button("Download two-day derived data CSV",daily.to_csv(index=False).encode(),
                               file_name="two_day_comparison.csv",mime="text/csv",key="two_day_export")
