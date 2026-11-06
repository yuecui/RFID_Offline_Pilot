"""Offline-only original-dashboard features, guarded for missing reference/calibration.

All numeric and readiness calculations are imported directly from the uploaded
RFID Dashboard source; raw ZIP archive contents are never rewritten.
"""
from __future__ import annotations
import io
import json
import zipfile

import pandas as pd
import streamlit as st

from offline_analysis import frame_from_parsed, metric_options
from dashboard_components.chicago import chicago_frame
from dashboard_services.coverage import (build_session_reference_quality,
    build_condition_coverage_table,build_expected_condition_grid,
    compare_expected_to_observed_conditions)
from dashboard_services.references import (build_reference_session_summary,
    candidate_reference_session_status,build_reference_dataset_zip)
from dashboard_services.readiness import (READINESS_MODES,build_experiment_readiness_checks,
    readiness_overall_status,readiness_summary,build_readiness_zip)
from dashboard_services.provenance import deterministic_session_hash
from dashboard_services.exports import build_experiment_package
from dashboard_services.lineage import build_layered_record
from offline_metadata import save_event


def tag_details(frame, store, catalog, prefix):
    st.subheader("Tag catalog / identity")
    st.caption("Names and variant assignments are append-only S3 annotations, not changes to immutable raw sessions. "
               "Variant assignment is an operator assertion; review chip identification before interpreting a temperature.")
    all_tags=sorted(frame["epc"].astype(str).unique())
    chosen=st.selectbox("Tag EPC",all_tags,key=prefix+"catalog_epc")
    sub=frame.loc[frame["epc"].eq(chosen)]
    current=catalog.get(chosen.upper(),{})
    a,b=st.columns(2)
    with a:
        st.code(chosen)
        st.metric("Recorded readings",len(sub))
        st.metric("Temperature rows (strict format)",int(pd.to_numeric(sub.get("temperature_c"),errors="coerce").notna().sum()))
    with b:
        for field in ("offline_variant","offline_variant_origin","sensor_header_status","temperature_calc_status"):
            if field in sub:
                st.write(f"**{field}**: {sub[field].mode().iloc[0] if not sub[field].mode().empty else 'Unknown'}")
    st.dataframe(chicago_frame(sub.tail(25)),use_container_width=True,hide_index=True)
    if store is None:
        st.caption("Connect S3 to persist tag labels.")
        return
    with st.form(prefix+"tagedit"):
        alias=st.text_input("Friendly tag name", value=current.get("alias", ""))
        variant=st.selectbox("Confirmed sensor variant", ["UNKNOWN","AS3213S.5","AS3213T.5"],
                index=["UNKNOWN","AS3213S.5","AS3213T.5"].index(current.get("variant", "UNKNOWN")))
        actor=st.text_input("Editor identifier (audit only)",key=prefix+"actor")
        submit=st.form_submit_button("Save immutable tag annotation")
    if submit:
        try:
            key=save_event(store,"tag",{"epc":chosen,"alias":alias,"variant":variant},actor)
            st.success("Saved to S3. Reload selected Session to apply this annotation.")
            st.caption(key)
        except Exception as ex:
            st.error(f"Could not save tag metadata: {type(ex).__name__}: {ex}")




def session_annotation_editor(parsed, frame, store, session_catalog, prefix):
    st.subheader("Session / experimental reference annotations")
    st.caption("Append-only annotation to provide missing experimental conditions. Original uploaded "
               "bytes and existing nonempty reference values remain unchanged. Identity is self-declared.")
    current=session_catalog.get(parsed.raw_sha256,{})
    for key in ("reference_pressure_psi","reference_temperature_c"):
        if key in parsed.rows[0] and str(parsed.rows[0].get(key) or "").strip():
            st.info(f"Original {key} is recorded in the ZIP and cannot be overwritten here.")
    if store is None:
        st.info("Connect S3 for persistent annotations.")
        return
    with st.form(prefix+"session_ann"):
        a,b=st.columns(2)
        pressure=a.text_input("Supplemental reference pressure (PSI)",
                              value=str(current.get("reference_pressure_psi") or ""))
        temp=b.text_input("Supplemental reference temperature (°C)",
                          value=str(current.get("reference_temperature_c") or ""))
        condition=st.text_input("Test condition",value=str(current.get("test_condition") or ""))
        note=st.text_area("Operator note",value=str(current.get("operator_note") or ""))
        actor=st.text_input("Editor identifier",key=prefix+"ann_actor")
        submitted=st.form_submit_button("Archive annotation to S3")
    if submitted:
        try:
            key=save_event(store,"session",{
                "raw_sha256":parsed.raw_sha256,
                "reference_pressure_psi":pressure,"reference_temperature_c":temp,
                "test_condition":condition,"operator_note":note},actor)
            st.success("Supplemental conditions saved. Reload this Session to apply. " + key)
        except Exception as ex:
            st.error(f"Annotation rejected: {type(ex).__name__}: {ex}")


def calibration_planning(frame,prefix):
    st.subheader("Calibration coverage planning")
    st.caption("Original Dashboard condition-coverage calculations. This is reference-data planning, "
               "not model fitting or physical pressure validation.")
    n,acc,s=st.columns(3)
    min_reads=n.number_input("Min readings/session/tag",1,100000,50,step=10,key=prefix+"min_r")
    min_acc=acc.number_input("Minimum BEST_ACC %",0.,100.,90.,key=prefix+"min_acc")
    min_s=s.number_input("Min sessions per condition",1,50,2,key=prefix+"min_s")
    eligible=build_session_reference_quality(frame,"time",int(min_reads),float(min_acc))
    if not eligible.empty:
        st.dataframe(chicago_frame(eligible),hide_index=True,use_container_width=True)
    observed=build_condition_coverage_table(frame,"time")
    if not observed.empty:
        st.dataframe(chicago_frame(observed),hide_index=True,use_container_width=True)
    p,t=st.columns(2)
    pressures=p.text_input("Target pressure levels (psi)","80,90,100,110",key=prefix+"pressures")
    temperatures=t.text_input("Target temperature levels (°C)","20,25,30",key=prefix+"temperatures")
    def parse(text):
        numbers=[]
        for item in text.split(","):
            try:
                if item.strip():numbers.append(float(item))
            except ValueError:
                st.warning("Ignoring an invalid numeric level")
        return sorted(set(numbers))
    px,tx=parse(pressures),parse(temperatures)
    if px and tx:
        expected=build_expected_condition_grid(px,tx)
        coverage=compare_expected_to_observed_conditions(expected,observed,int(min_s))
        st.subheader("Coverage matrix")
        st.dataframe(coverage,hide_index=True,use_container_width=True)
        st.download_button("Download coverage CSV",coverage.to_csv(index=False).encode(),
                           file_name="calibration_coverage.csv",mime="text/csv",key=prefix+"coverage_dl")


def reference_dataset(frame, prefix):
    st.subheader("Reference dataset builder")
    st.caption("Preserves recorded source values and reference conditions. No model is fitted automatically.")
    if "session_id" not in frame or frame.empty:
        st.info("No sessions")
        return
    chosen=st.multiselect("Include sessions",sorted(frame["session_id"].dropna().unique().tolist()),
                          default=sorted(frame["session_id"].dropna().unique().tolist()),key=prefix+"ref_sessions")
    selected=frame.loc[frame["session_id"].isin(chosen)]
    if selected.empty:return
    summary=build_reference_session_summary(selected,"time")
    if summary.empty:
        st.info("Reference summary unavailable")
        return
    status=summary.apply(candidate_reference_session_status,axis=1)
    summary["reference_status"]=[x[0] for x in status]
    summary["attention_reason"]=[x[1] for x in status]
    st.dataframe(chicago_frame(summary),hide_index=True,use_container_width=True)
    try:
        archive, _manifest=build_reference_dataset_zip(selected,summary,chosen)
    except (TypeError,ValueError):
        st.download_button("Download reference readings CSV",selected.to_csv(index=False).encode(),
                           file_name="candidate_reference_readings.csv",mime="text/csv",key=prefix+"ref_csv")
    else:
        st.download_button("Download reference dataset ZIP",archive,file_name="candidate_reference_dataset.zip",
                           mime="application/zip",key=prefix+"refzip")


def readiness(frame,prefix):
    st.subheader("Experiment readiness")
    mode=st.radio("Readiness mode",list(READINESS_MODES),horizontal=True,key=prefix+"mode")
    n1,n2,n3,n4=st.columns(4)
    min_r=n1.number_input("Minimum reads/tag",1,100000,50,key=prefix+"rr")
    miss=n2.number_input("Max missing USER %",0.,100.,5.,key=prefix+"missing")
    best=n3.number_input("Min BEST_ACC %",0.,100.,90.,key=prefix+"best")
    ratio=n4.number_input("Max count imbalance",1.,100.,5.,key=prefix+"ratio")
    checks=build_experiment_readiness_checks(frame,mode=mode,
        min_readings_per_tag=int(min_r),max_missing_user_pct=float(miss),
        min_best_acc_pct=float(best),max_sampling_ratio=float(ratio))
    status=readiness_overall_status(checks)
    counts=readiness_summary(checks)
    cols=st.columns(5)
    for col,(name,val) in zip(cols,[("Status",status),("PASS",counts["pass"]),
                                  ("FAIL",counts["fail"]),("REVIEW",counts["review"]),("INFO",counts["info"])]):
        col.metric(name,val)
    st.dataframe(checks,hide_index=True,use_container_width=True)
    st.caption("READY is a structural/data-quality gate, not a certificate of physical sensor validity.")
    try:
        data, _manifest, _checks=build_readiness_zip(frame, mode,
            int(min_r), float(miss), float(best), float(ratio))
    except (TypeError,ValueError,KeyError):
        data=None
    if data:
        st.download_button("Download readiness ZIP",data,file_name="readiness.zip",key=prefix+"readyzip")


def trace_and_package(parsed,frame,prefix):
    st.subheader("Provenance & experiment export")
    st.write("**Original archive SHA-256:**", parsed.raw_sha256)
    st.write("**Session ID:**", parsed.manifest["session_id"])
    st.caption("Separate derived data and software-generated packages never overwrite the source archive.")
    try:
        digest, count = deterministic_session_hash(frame)
        st.write("**Original Dashboard deterministic session digest:**",digest)
        st.write("Canonical snapshot bytes:",count)
    except (ValueError,TypeError,KeyError):
        st.caption("Could not compute the optional canonical digest")
    st.json(parsed.manifest,expanded=False)
    if not frame.empty:
        choice=st.selectbox("Inspect source/derived layer",list(range(min(100,len(frame)))),
                            format_func=lambda i:f"Read {i+1}",key=prefix+"lineage")
        try:
            st.json(build_layered_record(frame.iloc[choice]),expanded=False)
        except Exception:
            st.dataframe(frame.iloc[[choice]],use_container_width=True)
    opt=metric_options(frame)
    metric_name=next(iter(opt)) if opt else "RSSI"
    metric_col=opt[metric_name][0] if opt else "rssi"
    epcs=sorted(frame["epc"].unique())
    try:
        package=build_experiment_package(frame,parsed.manifest["session_id"],"time",2000,
                                          metric_name,metric_col,
                                          epcs[0] if len(epcs)>1 else None,
                                          epcs[1] if len(epcs)>1 else None)
        st.download_button("Download experiment package ZIP",package["bytes"],
             file_name=parsed.manifest["session_id"]+"_experiment_package.zip",
             mime="application/zip",key=prefix+"package")
    except (ValueError,TypeError,KeyError) as exc:
        st.warning(f"Experiment package unavailable: {type(exc).__name__}: {exc}")


def pressure_state(frame):
    st.subheader("Pressure / decision availability")
    st.warning("The current offline Session has raw USER words and optional reference pressure, "
               "but no physically validated strain decoder and no approved active pressure model. "
               "Pressure Estimation and LOW/NORMAL/HIGH decisions MUST NOT be synthesized.")
    st.metric("Verified pressure estimates",0)
    st.caption("The original backend's header-only decoder returns HEADER_MATCH_UNVALIDATED, "
               "not a valid physical strain feature. Upload of a calibration plan is not model activation.")
    if "known_pressure_psi" in frame:
        p=pd.to_numeric(frame["known_pressure_psi"],errors="coerce")
        st.write(f"Reference-pressure records: {int(p.notna().sum())}/{len(frame)}")
    if "temperature_c" in frame:
        c=pd.to_numeric(frame["temperature_c"],errors="coerce")
        st.write(f"Strict-format temperature calculations: {int(c.notna().sum())}/{len(frame)}")
    st.caption("Use the original validated model deployment workflow once physical decoding and "
               "calibration/validation evidence have been established.")
