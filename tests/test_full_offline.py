from pathlib import Path
from io import BytesIO
import json
import zipfile
import pandas as pd
from rfid_formats import parse_session
from offline_analysis import frame_from_parsed, metric_options
from offline_metadata import tag_catalog, validate_record, calibration_plans
from dashboard_services.coverage import build_condition_coverage_table, build_expected_condition_grid,compare_expected_to_observed_conditions
from dashboard_services.readiness import build_experiment_readiness_checks, build_readiness_zip,readiness_overall_status
from dashboard_services.references import build_reference_session_summary, build_reference_dataset_zip
from dashboard_services.exports import build_experiment_package
from dashboard_services.provenance import deterministic_session_hash

BASE=Path(__file__).resolve().parents[1]
REAL=BASE/'examples/diagnostic_t5_sample.zip'

def sample():
    p=BASE/'examples/sample_session.zip'
    return parse_session(p.read_bytes(),p.name)

def synthetic_t5():
    """Synthetic 192-bit inventory-format T.5-like records (not field data)."""
    parsed=sample()
    original=parsed.rows[0]["epc"]
    for row in parsed.rows:
        if row["epc"]==original:
            row["epc"]="A"*48
            row["user0"]="0xE000"
            row["user1"]="0xED7E"
            row["user5"]="0x0BB8"
            row["user6"]="0x0F7B"
    return parsed

def test_synthetic_temperature_with_original_t5_equation():
    df=frame_from_parsed(synthetic_t5())
    assert len(df)==6
    # A 192-bit T.5-like EPC, USER1 header 11, plus USER5/6 calibrations.
    t5=df[df['offline_variant']=='AS3213T.5']
    assert len(t5)==3
    assert t5['temperature_c'].notna().all()
    assert t5['temperature_c'].between(-100,200).all()
    assert t5['temperature_calc_status'].eq('HEADER_VALID_CALCULATED_NOT_PHYSICALLY_VALIDATED').all()
    assert any('Temperature' in label and '°C' in label for label in metric_options(df))
    # For unknown-variant tags, never invent a physical reading.
    unknown=df[df['offline_variant']=='UNKNOWN']
    assert len(unknown)==3
    assert unknown['temperature_c'].isna().all()

def test_s5_explicit_assignment_does_not_fabricate_temperature_when_header_bad():
    parsed=sample()
    tag=parsed.rows[0]['epc']
    for row in parsed.rows:
        row['user5']='0x0BB8'
        row['user6']='0x0F7B'
    df=frame_from_parsed(parsed,{tag:{'alias':'Sensor A','variant':'AS3213S.5'}})
    sub=df[df['epc']==tag]
    assert sub['tag_name'].eq('Sensor A').all()
    assert sub['temperature_c'].isna().all()
    assert sub['s5_accepted_temperature_c'].notna().any()  # exploratory NON-VALIDATED only
    assert sub['s5_interpretation_status'].notna().all()

def test_documented_s5_strict_temp():
    p=sample()
    # a constructed valid strict S5 example: header=10, reserved bit12=0
    p.rows[0]['user0']='0x8339'
    p.rows[0]['user1']='0x81EC'
    p.rows[0]['user5']='0x0BB8'
    p.rows[0]['user6']='0x0F7B'
    epc=p.rows[0]['epc']
    df=frame_from_parsed(p,{epc:{'alias':'','variant':'AS3213S.5'}})
    row=df.iloc[0]
    assert row['sensor_header_status']=='S5_USER01_MATCH'
    assert abs(row['temperature_c']-(30+((0x1ec/4)-(0x0f7b&0x1fff)/8)/2.99))<1e-9
    assert row['strain_raw_strict'] == (0x339/4)

def test_readiness_reference_exports_original_functions():
    df=frame_from_parsed(sample())
    checks=build_experiment_readiness_checks(df,mode='Diagnostic acquisition',
       min_readings_per_tag=1,max_missing_user_pct=5,min_best_acc_pct=0,max_sampling_ratio=10)
    assert len(checks)>0
    assert readiness_overall_status(checks) in ('READY','READY WITH REVIEW','NOT READY')
    ready_zip, _, _=build_readiness_zip(df,'Diagnostic acquisition',1,5.,0.,10.)
    assert zipfile.is_zipfile(BytesIO(ready_zip))
    summary=build_reference_session_summary(df,'time')
    assert len(summary)>0
    archive, _=build_reference_dataset_zip(df,summary,[sample().manifest['session_id']])
    assert zipfile.is_zipfile(BytesIO(archive))
    conditions=build_condition_coverage_table(df,'time')
    comparison=compare_expected_to_observed_conditions(build_expected_condition_grid([32],[22.5]),conditions,1)
    assert comparison['coverage_status'].iloc[0] in ('READY','PARTIAL','MISSING')
    package=build_experiment_package(df,sample().manifest['session_id'],'time',2000,'RSSI','rssi',
                            sorted(df['epc'].unique())[0], sorted(df['epc'].unique())[1])
    assert zipfile.is_zipfile(BytesIO(package["bytes"]))
    h,b=deterministic_session_hash(df)
    assert len(h)==64 and b>0

def test_catalog_event_validation_and_versioning():
    v=validate_record('tag',{'epc':'300833B2DDD9014000000001','alias':'Tire 1','variant':'AS3213S.5'})
    assert v['alias']=='Tire 1'
    rows=[{'kind':'tag','timestamp_utc':'2026-11-01T00:00:00Z','event_id':'1', 'value':{'epc':v['epc'],'alias':'old'}},
          {'kind':'tag','timestamp_utc':'2026-11-02T00:00:00Z','event_id':'2','value':v}]
    assert tag_catalog(rows)[v['epc']]['alias']=='Tire 1'
    try:validate_record('tag',{'epc':'bad!','alias':'','variant':'UNKNOWN'})
    except ValueError: pass
    else: assert False

def test_session_annotations_fill_only_missing_references():
    from offline_metadata import session_annotations,validate_record
    p=sample()
    rec=validate_record('session',{'raw_sha256':p.raw_sha256,
          'reference_pressure_psi':99.,'reference_temperature_c':24.5,
          'test_condition':'Lab pilot','operator_note':'Supplement only'})
    e=[{'kind':'session','timestamp_utc':'2026-11-05T00:00:00Z','value':rec}]
    frame=frame_from_parsed(p,session_catalog=session_annotations(e))
    # Original 32 psi / 22.5 C cannot be silently overwritten.
    assert pd.to_numeric(frame['known_pressure_psi']).eq(32.0).all()
    assert pd.to_numeric(frame['known_temperature_c']).eq(22.5).all()
    assert frame['test_condition'].eq('Lab pilot').all()
    q=sample()
    for row in q.rows:
        row['reference_pressure_psi']=''
        row['reference_temperature_c']=''
    df=frame_from_parsed(q,session_catalog=session_annotations(e))
    assert pd.to_numeric(df['known_pressure_psi']).eq(99.).all()
    assert pd.to_numeric(df['known_temperature_c']).eq(24.5).all()


def test_temperature_exclusion_on_wrong_t5_header():
    p=sample()
    for row in p.rows:
        row.update({'user0':'0xE000','user1':'0xA100','user5':'0x0BB8','user6':'0x0DE7'})
    epc=p.rows[0]['epc']
    frame=frame_from_parsed(p,{epc:{'variant':'AS3213T.5'}})
    assert frame.loc[frame['epc']==epc,'temperature_c'].isna().all()
    assert frame.loc[frame['epc']==epc,'sensor_header_status'].eq('T5_USER1_MISMATCH').all()


def test_format_valid_t5_inference_is_labeled_as_review_not_confirmed():
    frame=frame_from_parsed(synthetic_t5())
    subset=frame.loc[frame['offline_variant'].eq('AS3213T.5')]
    assert not subset.empty
    assert subset['offline_variant_origin'].str.contains('REVIEW').all()
    assert subset['temperature_c'].notna().all()


def test_audit_cli_report_does_not_manufacture_pressure():
    from scripts.audit_offline_session import audit
    report=audit(BASE/'examples/sample_session.zip')
    assert report['readings']==6
    assert report['unique_epcs']==2
    assert report['temperature_is_physically_validated'] is False
    assert 'UNAVAILABLE' in report['pressure_estimates']
