"""RFID Offline Pilot: private Streamlit Cloud + immutable S3 session files."""
from __future__ import annotations

import hashlib
from io import BytesIO
import pandas as pd
import streamlit as st
from rfid_formats import parse_session, SessionValidationError
from s3_store import S3SessionStore
from offline_views import render_session, render_session_comparison

st.set_page_config(page_title="RFID Offline Pilot", page_icon="📡", layout="wide")
st.title("RFID Offline Pilot")
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


def session_view(parsed, prefix="session_"):
    """Preserve the storage flow; use the original Dashboard's charts and metrics."""
    return render_session(parsed, prefix)


upload_tab, library_tab, compare_tab = st.tabs(["Upload Session", "Session Library", "Compare Sessions"])
with upload_tab:
    st.info("Supported pilot format: one UTF-8 CSV with timestamp_utc, session_id, reader_id, epc, user0, user1, rssi; or ZIP containing manifest.json + readings.csv. This is NOT yet a direct importer for your current Android export format.")
    upl = st.file_uploader("Session ZIP or CSV", type=["csv", "zip"], key="uploader")
    if upl is not None:
        raw = upl.getvalue()
        try:
            parsed = parse_session(raw, upl.name)
            st.success(f"Validated session {parsed.manifest['session_id']} | {len(parsed.rows):,} readings | SHA256 {parsed.raw_sha256[:16]}…")
            st.json(parsed.manifest, expanded=False)
            session_view(parsed, prefix="upload_")
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
                render_session_comparison(sessions)
        except Exception as exc:
            st.error(f"Comparison failed ({type(exc).__name__}).")
    else:
        st.info("Configure S3 for comparison across uploaded sessions.")
