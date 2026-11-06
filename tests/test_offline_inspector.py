"""Regression tests for the v0.3.1 advanced read inspector."""
import pandas as pd
from offline_inspector import readings_for_epc, reading_label, find_readings


def sample_frame():
    return pd.DataFrame([
        {"epc": "300833B2DDD9014000000002", "time": pd.Timestamp("2026-11-05T16:09:12Z"),
         "timestamp_utc": "2026-11-05T16:09:12Z", "reading_id": "reading-c"},
        {"epc": "300833B2DDD9014000000001", "time": pd.Timestamp("2026-11-05T16:09:11Z"),
         "timestamp_utc": "2026-11-05T16:09:11Z", "reading_id": "reading-b"},
        {"epc": "300833B2DDD9014000000001", "time": pd.Timestamp("2026-11-05T16:09:10Z"),
         "timestamp_utc": "2026-11-05T16:09:10Z", "reading_id": "reading-a"},
    ])


def test_epc_filter_and_chronological_order_no_source_mutation():
    original = sample_frame()
    unmodified = original.copy(deep=True)
    scoped = readings_for_epc(original,"300833B2DDD9014000000001")
    assert scoped["reading_id"].tolist() == ["reading-a","reading-b"]
    pd.testing.assert_frame_equal(original,unmodified)


def test_label_contains_timestamp_short_epc_and_id():
    row = readings_for_epc(sample_frame(), "300833B2DDD9014000000001").iloc[0]
    label = reading_label(row,0)
    assert "#1" in label and "2026-11-05 16:09:10.000 UTC" in label
    assert "300833B2" in label and "00000001" in label and "reading-a" in label


def test_search_time_id_number_case_insensitive():
    scoped=readings_for_epc(sample_frame(),"300833B2DDD9014000000001")
    assert find_readings(scoped,"16:09:10")==([0],1)
    assert find_readings(scoped,"READING-B")==([1],1)
    assert find_readings(scoped,"missing")==([],0)
    assert find_readings(scoped,"")==([],0)


def test_search_limited_results_reports_total():
    frame = pd.DataFrame([{"epc":"EPC","timestamp_utc":"2026-11-05T16:09:10Z", "reading_id":f"id-{i}"} for i in range(120)])
    selected = readings_for_epc(frame,"EPC")
    hits,total=find_readings(selected,"2026",limit=30)
    assert len(hits)==30 and total==120


def test_missing_fields_fallback_and_empty():
    df=pd.DataFrame([{"epc":"ONE", "reading_id":None}])
    scoped=readings_for_epc(df,"ONE")
    assert "Time unavailable" in reading_label(scoped.iloc[0],0)
    assert "ID unavailable" in reading_label(scoped.iloc[0],0)
    assert readings_for_epc(df,"MISSING").empty
