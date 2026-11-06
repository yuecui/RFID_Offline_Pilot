"""RFID Offline Pilot: private Streamlit Cloud + immutable S3 session files."""
from __future__ import annotations

import hashlib
import json
from io import BytesIO
import pandas as pd
import streamlit as st
from rfid_formats import parse_session, SessionValidationError
from s3_store import S3SessionStore
from offline_views import render_session, render_session_comparison
from offline_metadata import load_events, tag_catalog, calibration_plans, session_annotations, save_event

st.set_page_config(page_title="RFID Offline Pilot v0.3", page_icon="📡", layout="wide")
st.title("RFID Offline Pilot v0.3 — Offline Analysis")
st.caption("Import and compare offline experimental sessions. Raw data is preserved; no live MQTT/InfluxDB required.")

try:
    aws = st.secrets["aws"]
    store = S3SessionStore(aws)
    configured = True
except KeyError:
    configured = False
    store = None
    st.warning("S3 is not configured. Upload preview works, but nothing can be saved. Configure Streamlit Secrets to enable storage.")
except Exception as exc:
    configured = False
    store = None
    st.error(f"Could not initialize S3 connection: {type(exc).__name__}. Check Secrets without pasting credentials into chat.")


try:
    events = load_events(store) if configured else []
    catalog = tag_catalog(events)
    session_catalog = session_annotations(events)
except Exception as exc:
    catalog, session_catalog, events = {}, {}, []
    st.warning(f"Optional S3 metadata unavailable: {type(exc).__name__}. The immutable Session Library is unaffected.")


def session_view(parsed, prefix="session_"):
    """Preserve the storage flow; use the original Dashboard's charts and metrics."""
    return render_session(parsed, prefix, store=store, tag_catalog=catalog, session_catalog=session_catalog)


upload_tab, library_tab, compare_tab, plans_tab = st.tabs([
    "Upload Session", "Session Library", "Compare Sessions", "Calibration Plans"])
st.caption("Offline analysis · no live MQTT, real-time ACK, or Reader Management. "
           "Only approved users should be invited to this private Streamlit app.")
with upload_tab:
    st.info("Supported: TC22R Offline Session ZIP (manifest.json + readings.csv) or one-session CSV. "
            "Original raw bytes are archived unchanged. Derived plots and labels are separate.")
    upl = st.file_uploader("Session ZIP or CSV", type=["csv", "zip"], key="uploader")
    if upl is not None:
        raw = upl.getvalue()
        try:
            parsed = parse_session(raw, upl.name)
            st.success(f"Validated session {parsed.manifest['session_id']} | {len(parsed.rows):,} readings | SHA256 {parsed.raw_sha256[:16]}…")
            st.json(parsed.manifest, expanded=False)
            session_view(parsed, prefix="upload_")
            st.download_button("Download original uploaded Session",raw,file_name=upl.name,
                               mime="application/zip" if upl.name.lower().endswith("zip") else "text/csv")
            confirmation = st.checkbox("I confirm this is approved research data and that this is the correct session to archive.")
            if st.button("Save immutable raw file to S3", disabled=not configured or not confirmation, type="primary"):
                with st.spinner("Uploading to S3…"):
                    try:
                        key, created = store.put(parsed, raw)
                        if created:
                            st.success("S3 confirmed upload: " + key)
                        else:
                            st.info("Same file already archived. No overwrite: " + key)
                    except Exception as exc:
                        st.error(f"S3 upload failed ({type(exc).__name__}); upload NOT confirmed. Check credentials, policy and bucket.")
        except SessionValidationError as exc:
            st.error("Validation failed: " + str(exc))

with library_tab:
    if configured:
        if st.button("Refresh S3 sessions"):
            st.rerun()
        try:
            entries = store.list()
            st.caption(f"{len(entries)} archived file(s). Individual uploads are immutable; no delete permission is granted to this application.")
            if entries:
                chosen = st.selectbox("Archived file", [e["key"] for e in entries], key="library_choice")
                if st.button("Load selected session", key="load_library"):
                    data = store.get(chosen)
                    parsed = parse_session(data, chosen)
                    st.session_state["loaded_library"] = (chosen, data)
                saved = st.session_state.get("loaded_library")
                if saved and saved[0] == chosen:
                    parsed = parse_session(saved[1], chosen)
                    session_view(parsed, prefix="library_")
                    st.download_button("Download ORIGINAL raw upload", saved[1], file_name=chosen.rsplit("/",1)[-1])
            else:
                st.info("No sessions in S3. Upload the sample ZIP first.")
        except Exception as exc:
            st.error(f"S3 listing/loading failed ({type(exc).__name__}).")
    else:
        st.info("Configure S3 before viewing the shared session library.")

with compare_tab:
    if configured:
        try:
            entries = store.list()
            choices = st.multiselect("Choose 2–5 archived files", [e["key"] for e in entries], max_selections=5)
            if st.button("Compare selected sessions", disabled=len(choices)<2):
                st.session_state["comparison_loaded"] = choices
            loaded = st.session_state.get("comparison_loaded", [])
            if loaded and set(loaded) == set(choices) and len(loaded)>=2:
                sessions = [parse_session(store.get(key), key) for key in loaded]
                render_session_comparison(sessions, catalog, session_catalog)
        except Exception as exc:
            st.error(f"Comparison failed ({type(exc).__name__}).")
    else:
        st.info("Configure S3 for comparison across uploaded sessions.")

with plans_tab:
    st.subheader("Research calibration plans (archive only)")
    st.info("Uploaded plans are immutable research documents. Uploading a plan does NOT activate "
            "a decoder or a production pressure model, and does not create verified pressure values.")
    existing = calibration_plans(events)
    if existing:
        st.caption(f"{len(existing)} immutable plan revision(s) in S3")
        names = [f"{e['value'].get('title', 'Untitled')} · {e['timestamp_utc']}" for e in existing]
        idx = st.selectbox("Archived plan", list(range(len(names))), format_func=lambda i:names[i])
        selected_plan=existing[idx]["value"].get("plan", {})
        st.json(selected_plan,expanded=False)
        if "model_type" in selected_plan:
            from pressure_calibration import validate_model, PressureModelError
            from pressure_decision import simulate_pressure_decision
            try:
                model=validate_model(selected_plan)
                st.info("Original pressure-model schema validated. Synthetic preview only; "
                        "not activation and not a measurement.")
                with st.form("synthetic_pressure_preview"):
                    input_strain=st.number_input("Synthetic strain feature",value=0.0)
                    input_temp=st.number_input("Synthetic temperature (°C)",value=20.0)
                    target=st.number_input("Synthetic target PSI",min_value=0.01,value=100.0)
                    lower=st.number_input("Synthetic low tolerance PSI",min_value=0.0,value=5.0)
                    upper=st.number_input("Synthetic high tolerance PSI",min_value=0.0,value=5.0)
                    preview=st.form_submit_button("Run SYNTHETIC calculation")
                if preview:
                    decoded={"decode_status":"VALID","sensor_format_valid":True,
                        "strain_format_valid":True,"temperature_format_valid":True,
                        model["input_feature"]:float(input_strain),"temperature_c":float(input_temp),
                        "feature_units":{model["input_feature"]:model["input_units"],
                                          "temperature_c":"degC"}}
                    result=simulate_pressure_decision(model,decoded,{
                        "target_pressure_psi":float(target),"lower_tolerance_psi":float(lower),
                        "upper_tolerance_psi":float(upper)})
                    st.warning("SYNTHETIC / UNVALIDATED — cannot be used as experimental pressure output")
                    st.json(result)
            except (PressureModelError,KeyError,ValueError) as exc:
                st.warning("Pressure model is not valid for preview: " + str(exc))
        st.download_button("Download plan JSON", json.dumps(existing[idx]["value"]["plan"],indent=2).encode(),
                           file_name="rfid_calibration_plan.json",mime="application/json")
    upl_plan = st.file_uploader("Calibration plan JSON", type=["json"],key="plan_upload")
    title = st.text_input("Plan title / revision", key="plan_title")
    actor = st.text_input("Editor identifier",key="plan_actor")
    if upl_plan is not None:
        try:
            if upl_plan.size>100_000: raise ValueError("Plan exceeds 100 KiB")
            plan_data = json.loads(upl_plan.getvalue())
            if not isinstance(plan_data,dict):raise ValueError("Plan must contain a JSON object")
            st.json(plan_data, expanded=False)
            if "model_type" in plan_data:
                from pressure_calibration import validate_model, PressureModelError
                try:
                    validate_model(plan_data, importing=True)
                except PressureModelError as exc:
                    raise ValueError("Pressure-model archive requires a schema-valid DRAFT model: "+str(exc))
                st.info("Draft pressure model passes original schema validation. "
                        "It will not be activated or used on acquisition records.")
            if st.button("Archive plan to S3",disabled=not configured):
                key=save_event(store,"plan",{"title":title,"plan":plan_data},actor)
                st.success("Plan archived. This is not a model activation: " + key)
        except (ValueError,UnicodeDecodeError) as exc:
            st.error("Invalid plan JSON: " + str(exc))
