"""Candidate peaks from leave-one-out refits, holdout error bounds and recheck windows.

轮组复测怕找错峰：每个历史轮组留掉一只重拟合，各模型用留出轮组的最大绝对预测
误差定误差界；每个模型在每次待测扫描上给出一个候选峰。候选峰装不进一个复测角窗
时，补测一个未扫角（选预测区间最小间隔最大处），实测值落在区间外才淘汰对应候选。
至少剩一个峰且全能装进同宽角窗才允许签核。
"""

from collections import defaultdict

from .proposals import PROFILE_ALPHA, phase_grid, recheck_window
from .regression import calibration_features, fit_ridge, phase_features

GRID_STEP_DEG = 0.5


def leave_one_out_models(train: list[dict], harmonics: int, alpha: float) -> tuple[list[dict], list[str]]:
    """Refit the calibration leaving each historical wheel out once."""
    models, skipped = [], []
    for wheel in sorted({row['wheel_id'] for row in train}):
        subset = [row for row in train if row['wheel_id'] != wheel]
        if len({row['angle_deg'] for row in subset}) < 2 * harmonics + 1:
            skipped.append(wheel)
            continue
        model = fit_ridge([calibration_features(row, harmonics) for row in subset],
                          [row['reference_mm'] for row in subset], alpha)
        models.append({'source': f'loo:{wheel}', 'label': f'留一重拟合（{wheel}）',
                       'left_out_wheel': wheel, 'model': model})
    return models, skipped


def holdout_error_bound(model, holdout: list[dict], harmonics: int) -> float:
    """Max absolute prediction error of one calibration on the holdout wheels."""
    return max(abs(model.predict(calibration_features(row, harmonics)) - row['reference_mm'])
               for row in holdout)


def scan_candidates(rows: list[dict], models: list[dict], harmonics: int) -> tuple[int, list[dict]]:
    """One candidate peak per calibration model for a single pending scan."""
    angles = [row['angle_deg'] for row in rows]
    profile_harmonics = min(harmonics, (len(angles) - 1) // 2)
    candidates = []
    for entry in models:
        target = [entry['model'].predict(calibration_features(row, harmonics)) for row in rows]
        profile = fit_ridge([phase_features(angle, profile_harmonics) for angle in angles],
                            target, PROFILE_ALPHA)
        phase, peak = max(((angle, profile.predict(features)) for angle, features
                           in phase_grid(profile_harmonics)), key=lambda point: (abs(point[1]), -point[0]))
        candidates.append({'source': entry['source'], 'label': entry['label'],
                           'peak_deg': phase, 'peak_mm': round(peak, 6),
                           'error_bound_mm': round(entry['bound'], 6),
                           'intercept': profile.intercept, 'coefficients': list(profile.coefficients)})
    return profile_harmonics, candidates


def predict_interval(candidate: dict, angle_deg: float, profile_harmonics: int) -> tuple[float, float]:
    """Predicted value interval of one candidate at any angle."""
    value = candidate['intercept'] + sum(coef * feature for coef, feature in
                                         zip(candidate['coefficients'],
                                             phase_features(angle_deg, profile_harmonics), strict=True))
    bound = candidate['error_bound_mm']
    return value - bound, value + bound


def interval_gap(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Distance between two closed intervals; zero when they overlap."""
    return max(0.0, max(first[0], second[0]) - min(first[1], second[1]))


def covering_arc(angles: list[float]) -> tuple[float, float, float]:
    """Smallest circular arc covering all angles: (start_deg, end_deg, width_deg)."""
    ordered = sorted({angle % 360 for angle in angles})
    if len(ordered) == 1:
        return ordered[0], ordered[0], 0.0
    gaps = [(following - current, following % 360)
            for current, following in zip(ordered, (*ordered[1:], ordered[0] + 360), strict=True)]
    gap, start = max(gaps, key=lambda item: (item[0], -item[1]))
    width = 360 - gap
    return start, round((start + width) % 360, 6) % 360, width


def fit_window(angles: list[float], radius: int) -> dict | None:
    """A 2*radius-wide recheck window covering all angles, or None when they do not fit."""
    start, _, width = covering_arc(angles)
    if width > 2 * radius:
        return None
    center = (start + width / 2) % 360
    window_start, window_end, wraps_zero = recheck_window(center, radius)
    return {'start_deg': window_start, 'end_deg': window_end, 'wraps_zero': wraps_zero}


def best_measurement_angle(candidates: list[dict], profile_harmonics: int,
                           excluded: set[float]) -> tuple[float, float] | None:
    """Unswept angle maximizing the minimum gap between candidate prediction intervals."""
    blocked = {angle % 360 for angle in excluded}
    best = None
    for step in range(round(360 / GRID_STEP_DEG)):
        angle = step * GRID_STEP_DEG
        if angle in blocked:
            continue
        intervals = [predict_interval(candidate, angle, profile_harmonics) for candidate in candidates]
        gap = min(interval_gap(first, second)
                  for index, first in enumerate(intervals) for second in intervals[index + 1:])
        if best is None or (gap, -angle) > (best[1], -best[0]):
            best = (angle, gap)
    return best


def eliminated_by(candidate: dict, measurement: dict, profile_harmonics: int) -> bool:
    """A candidate is eliminated only when a measured value falls outside its interval."""
    low, high = predict_interval(candidate, measurement['angle_deg'], profile_harmonics)
    return not low <= measurement['measured_mm'] <= high


def scan_state(scan: dict, measurements: list[dict], radius: int) -> dict:
    """Apply supplementary measurements to a scan's candidates and derive the window state."""
    profile_harmonics = scan['profile_harmonics']
    alive = [candidate for candidate in scan['candidates']
             if not any(eliminated_by(candidate, measurement, profile_harmonics)
                        for measurement in measurements)]
    window = fit_window([candidate['peak_deg'] for candidate in alive], radius) if alive else None
    next_angle = None
    if window is None and len(alive) >= 2:
        excluded = {*scan['swept_angles'], *(measurement['angle_deg'] for measurement in measurements)}
        chosen = best_measurement_angle(alive, profile_harmonics, excluded)
        if chosen is not None:
            next_angle = {'angle_deg': chosen[0], 'min_gap_mm': round(chosen[1], 6)}
    return {'alive': alive, 'window': window, 'next_angle': next_angle,
            'eligible': bool(alive) and window is not None}


def build_recheck(train: list[dict], holdout: list[dict], pending: list[dict], fourier,
                  options: dict) -> tuple[dict, list[dict], list[dict], list[str]]:
    """Candidate peaks with error bounds for every pending scan, plus report rows."""
    harmonics = options['harmonics']
    radius = options['recheck_radius_deg']
    full = {'source': 'full', 'label': '完整模型', 'left_out_wheel': None, 'model': fourier}
    loo_models, skipped = leave_one_out_models(train, harmonics, options['ridge_alpha'])
    models = [full, *loo_models]
    for entry in models:
        entry['bound'] = holdout_error_bound(entry['model'], holdout, harmonics)
    bound_rows = [{'source': entry['source'], 'label': entry['label'],
                   'left_out_wheel': entry['left_out_wheel'], 'holdout_points': len(holdout),
                   'error_bound_mm': round(entry['bound'], 6)} for entry in models]

    scans = defaultdict(list)
    for row in pending:
        scans[row['scan_id']].append(row)
    scan_entries, candidate_rows = [], []
    for scan_id in sorted(scans):
        rows = sorted(scans[scan_id], key=lambda row: row['angle_deg'])
        angles = [row['angle_deg'] for row in rows]
        profile_harmonics, candidates = scan_candidates(rows, models, harmonics)
        window = fit_window([candidate['peak_deg'] for candidate in candidates], radius)
        proposed = None
        if window is None:
            chosen = best_measurement_angle(candidates, profile_harmonics, set(angles))
            if chosen is not None:
                proposed = {'angle_deg': chosen[0], 'min_gap_mm': round(chosen[1], 6)}
        first = rows[0]
        scan_entries.append({'scan_id': scan_id, 'wheel_id': first['wheel_id'],
                             'fixture_id': first['fixture_id'], 'profile_harmonics': profile_harmonics,
                             'swept_angles': angles, 'candidates': candidates,
                             'fits_window': window is not None, 'proposed_angle': proposed})
        for candidate in candidates:
            candidate_rows.append({'scan_id': scan_id, 'wheel_id': first['wheel_id'],
                                   'fixture_id': first['fixture_id'], 'source': candidate['source'],
                                   'label': candidate['label'], 'peak_deg': candidate['peak_deg'],
                                   'peak_mm': candidate['peak_mm'],
                                   'error_bound_mm': candidate['error_bound_mm'],
                                   'fits_window': window is not None,
                                   'proposed_angle_deg': proposed['angle_deg'] if proposed else None,
                                   'proposed_min_gap_mm': proposed['min_gap_mm'] if proposed else None})

    recheck = {'radius_deg': radius, 'window_width_deg': 2 * radius, 'scans': scan_entries}
    warnings = []
    if skipped:
        warnings.append('部分历史轮组留一重拟合后可用角度不足，对应候选已跳过：' + '、'.join(skipped) + '。')
    if any(not entry['fits_window'] for entry in scan_entries):
        warnings.append('部分待测扫描的候选峰装不进同一复测角窗，需补测未扫角淘汰候选后再签核。')
    return recheck, bound_rows, candidate_rows, warnings
