"""Domain entry points used by the CSV catalog, demo seed and asynchronous worker."""

from .evaluation import compare, predict_holdout
from .fixtures import demo_rows
from .proposals import MAX_COVERAGE_GAP_DEG, build_proposals
from .recheck import build_recheck
from .records import normalize_rows
from .regression import calibration_features, fit_ridge
from .reports import (candidate_table, coefficient_table, comparison_table, error_bound_table,
                      holdout_table, proposal_table)
from .settings import SPEC, parse_settings

__all__ = ['SPEC', 'demo_rows', 'normalize_rows', 'analyze']


def analyze(rows: list[dict], settings: dict) -> dict:
    options = parse_settings(settings)
    harmonics = options['harmonics']
    ordered = sorted(normalize_rows(rows), key=lambda row: row['id'])
    train = [row for row in ordered if row['split'] == 'train']
    holdout = [row for row in ordered if row['split'] == 'holdout']
    pending = [row for row in ordered if row['split'] == 'pending']
    if len({row['angle_deg'] for row in train}) < 2 * harmonics + 1:
        raise ValueError(f'历史至少需要 {2 * harmonics + 1} 个不同角度才能拟合 {harmonics} 阶周期特征。')

    target = [row['reference_mm'] for row in train]
    alpha = options['ridge_alpha']
    fourier = fit_ridge([calibration_features(row, harmonics) for row in train], target, alpha)
    bare = fit_ridge([calibration_features(row, 0) for row in train], target, alpha)
    trained_fixtures = {row['fixture_id'] for row in train}
    train_wheels = len({row['wheel_id'] for row in train})
    evaluated = predict_holdout(holdout, fourier, bare, harmonics)
    diagnostics = compare(evaluated, trained_fixtures)
    overall, seam = diagnostics[:2]
    proposals, priority_count = build_proposals(pending, fourier, options, trained_fixtures)
    recheck, bound_rows, candidate_rows, recheck_warnings = build_recheck(train, holdout, pending,
                                                                          fourier, options)
    pending_recheck = sum(not scan['fits_window'] for scan in recheck['scans'])
    warnings = []
    if not any(row['fixture_id'] not in trained_fixtures for row in holdout):
        warnings.append('留出扫描的支架挡位均曾参与训练，本次仅能检验新轮组。')
    if not seam['points']:
        warnings.append('留出扫描在零度附近 ±15° 没有测点。')
    if any(row['max_gap_deg'] > MAX_COVERAGE_GAP_DEG for row in proposals):
        warnings.append('部分待测扫描的采样空档超过 90°，需按提案先补扫。')
    if any(not row['fixture_seen_in_train'] for row in proposals):
        warnings.append('部分待测轮组使用历史未见挡位，复测时需核对支架设定。')
    if not pending:
        warnings.append('本次台账未包含待测扫描。')
    warnings += recheck_warnings
    return {
        'summary': (f'用 {train_wheels} 个历史轮组的 {len(train)} 个测点拟合校正。'
                    f'在 {overall["wheels"]} 个独立轮组的 {len(holdout)} 个测点对照傅里叶与裸角度模型。'
                    f'{len(proposals)} 次待测扫描中有 {priority_count} 次须优先复测或先补扫。'),
        'metrics': {'历史轮组数': train_wheels, '留出轮组数': overall['wheels'],
                    '留出傅里叶 MAE（mm）': overall['fourier_mae_mm'],
                    '留出裸角度 MAE（mm）': overall['bare_mae_mm'],
                    '零度接缝留出测点数': seam['points'], '需优先处理的扫描数': priority_count,
                    '候选峰待补测的扫描数': pending_recheck},
        'tables': [proposal_table(proposals), comparison_table(diagnostics), holdout_table(evaluated),
                   coefficient_table(fourier, bare, options), error_bound_table(bound_rows),
                   candidate_table(candidate_rows)],
        'recheck': recheck,
        'warnings': warnings,
    }
