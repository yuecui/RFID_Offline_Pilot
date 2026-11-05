from pathlib import Path
import pandas as pd
from rfid_formats import parse_session
from offline_analysis import frame_from_parsed, metric_options, describe_quality, pair_tags, time_window, word_to_int

BASE = Path(__file__).resolve().parent.parent

def load_sample():
    p=BASE / 'examples/sample_session.zip'
    return parse_session(p.read_bytes(),p.name)

def test_hex_word_adapter():
    assert word_to_int('0x2339') == 0x2339
    assert word_to_int('9017') == 9017
    assert word_to_int('invalid') is None

def test_sample_with_original_dashboard_payload():
    df=frame_from_parsed(load_sample())
    assert len(df)==6
    assert df['epc'].nunique()==2
    assert int(df.iloc[0]['user0_word'])==0x2339
    assert int(df.iloc[0]['user0_payload'])==(0x2339 & 0xFFF)
    assert df['user0_word_header_valid'].eq(False).all()
    assert 'rssi' in [col for col,_ in metric_options(df).values()]

def test_original_metrics_and_quality():
    df=frame_from_parsed(load_sample())
    report=describe_quality(df)
    assert len(report['by_tag'])==2
    assert report['by_tag']['Readings'].sum()==6
    assert len(time_window(df,5))==6

def test_timestamp_alignment_not_index_pairing():
    df=frame_from_parsed(load_sample())
    tags=sorted(df['epc'].unique())
    assert pair_tags(df,tags[0],tags[1],'rssi',250).empty
    assert not pair_tags(df,tags[0],tags[1],'rssi',2500).empty

def test_raw_file_is_unchanged_by_adapter():
    p=BASE/'examples/sample_session.zip'
    raw=p.read_bytes()
    parsed=parse_session(raw,p.name)
    frame_from_parsed(parsed)
    assert raw==p.read_bytes()
