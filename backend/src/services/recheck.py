"""Supplementary measurements, candidate elimination and the signed recheck window."""

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select

from src.constants.workflow import RunStatus
from src.domain.recheck import scan_state
from src.models.measurement import RecheckMeasurement
from src.models.run import Run
from src.services.audit import record
from src.utils.time import utc_stamp

WINDOW_LABELS = {
    'position': '复测顺序', 'scan_id': '扫描编号', 'wheel_id': '轮组编号', 'fixture_id': '校正支架挡位',
    'surviving_count': '签核时存活候选峰数', 'surviving_sources': '签核时存活候选来源',
    'window_start_deg': '角窗起始角（°）', 'window_end_deg': '角窗终止角（°）',
    'wraps_zero': '角窗跨零度', 'window_width_deg': '角窗宽度（°）',
}


def load_measurements(session, run_id):
    statement = (select(RecheckMeasurement).where(RecheckMeasurement.run_id == run_id)
                 .order_by(RecheckMeasurement.id))
    return list(session.scalars(statement))


def group_measurements(measurements):
    by_scan = defaultdict(list)
    for measurement in measurements:
        by_scan[measurement.scan_id].append({'angle_deg': measurement.angle_deg,
                                             'measured_mm': measurement.measured_mm,
                                             'created_at': measurement.created_at})
    return by_scan


def scan_overview(scan, taken, radius):
    state = scan_state(scan, taken, radius)
    alive_ids = {id(candidate) for candidate in state['alive']}
    return {
        'scan_id': scan['scan_id'], 'wheel_id': scan['wheel_id'], 'fixture_id': scan['fixture_id'],
        'candidates': [{key: candidate[key] for key in
                        ('source', 'label', 'peak_deg', 'peak_mm', 'error_bound_mm')} |
                       {'alive': id(candidate) in alive_ids} for candidate in scan['candidates']],
        'measurements': taken,
        'alive_count': len(state['alive']), 'fits_window': state['window'] is not None,
        'eligible': state['eligible'], 'window': state['window'], 'next_angle': state['next_angle'],
    }


def recheck_overview(session, run, review=None):
    """Current candidate state for the run detail; late measurements are counted here."""
    recheck = (run.result or {}).get('recheck')
    if recheck is None:
        return None
    by_scan = group_measurements(load_measurements(session, run.id))
    scans = [scan_overview(scan, by_scan.get(scan['scan_id'], []), recheck['radius_deg'])
             for scan in recheck['scans']]
    return {'radius_deg': recheck['radius_deg'], 'window_width_deg': recheck['window_width_deg'],
            'eligible': all(scan['eligible'] for scan in scans), 'scans': scans,
            'signed': review.snapshot if review is not None else None}


def submit_measurement(session, run_id, payload, actor):
    # Lock the run row so a concurrent sign-off either precedes or follows this record.
    run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None:
        raise LookupError('找不到运行')
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, '计算成功完成后才能登记补测记录')
    recheck = (run.result or {}).get('recheck')
    if recheck is None:
        raise HTTPException(409, '该运行没有候选峰复测数据')
    scan = next((entry for entry in recheck['scans'] if entry['scan_id'] == payload.scan_id), None)
    if scan is None:
        raise LookupError('找不到该运行的待测扫描')
    angle = payload.angle_deg % 360
    duplicate = session.scalar(select(RecheckMeasurement).where(
        RecheckMeasurement.run_id == run_id, RecheckMeasurement.scan_id == payload.scan_id,
        RecheckMeasurement.angle_deg == angle))
    if duplicate is not None:
        raise HTTPException(409, f'扫描 {payload.scan_id} 在 {angle:g}° 已有补测记录')
    measurement = RecheckMeasurement(run_id=run_id, scan_id=payload.scan_id, angle_deg=angle,
                                     measured_mm=payload.measured_mm, created_by=actor.id,
                                     created_at=utc_stamp())
    session.add(measurement)
    record(session, 'measurement.submitted', run_id, actor.id)
    session.commit()
    taken = [{'angle_deg': item.angle_deg, 'measured_mm': item.measured_mm, 'created_at': item.created_at}
             for item in load_measurements(session, run_id) if item.scan_id == payload.scan_id]
    return scan_overview(scan, taken, recheck['radius_deg'])


def signoff_snapshot(session, run):
    """Window covering the candidates still valid at sign-off; None for legacy runs."""
    recheck = (run.result or {}).get('recheck')
    if recheck is None:
        return None
    by_scan = group_measurements(load_measurements(session, run.id))
    rows, scans = [], []
    for position, scan in enumerate(recheck['scans'], start=1):
        state = scan_state(scan, by_scan.get(scan['scan_id'], []), recheck['radius_deg'])
        if not state['alive']:
            raise HTTPException(409, f"扫描 {scan['scan_id']} 的候选峰已全部淘汰，至少剩一个峰才能签核")
        if state['window'] is None:
            raise HTTPException(409, f"扫描 {scan['scan_id']} 剩 {len(state['alive'])} 个候选峰，"
                                     f"装不进 {recheck['window_width_deg']:g}° 的同宽角窗，请先补测未扫角")
        window = state['window']
        rows.append({'position': position, 'scan_id': scan['scan_id'], 'wheel_id': scan['wheel_id'],
                     'fixture_id': scan['fixture_id'], 'surviving_count': len(state['alive']),
                     'surviving_sources': '；'.join(candidate['label'] for candidate in state['alive']),
                     'window_start_deg': window['start_deg'], 'window_end_deg': window['end_deg'],
                     'wraps_zero': window['wraps_zero'], 'window_width_deg': recheck['window_width_deg']})
        scans.append({'scan_id': scan['scan_id'],
                      'surviving': [candidate['source'] for candidate in state['alive']],
                      'window': window})
    table = {'key': 'recheck_windows', 'title': '签核复测角窗', 'columns': list(WINDOW_LABELS),
             'labels': WINDOW_LABELS, 'rows': rows}
    return {'window_width_deg': recheck['window_width_deg'], 'scans': scans, 'table': table}
