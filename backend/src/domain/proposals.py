"""Find pending-scan phase peaks and translate them into circular recheck windows."""

from collections import defaultdict
from functools import lru_cache

from .regression import RidgeModel, calibration_features, fit_ridge, phase_features

PROFILE_ALPHA = 0.025
MAX_COVERAGE_GAP_DEG = 90
SPIKE_DIFFERENCE_MM = 0.25
ACTION_NAMES = {0: '补扫后复测', 1: '优先复测', 2: '常规复测'}


@lru_cache(maxsize=4)
def phase_grid(harmonics: int) -> tuple[tuple[float, tuple[float, ...]], ...]:
    return tuple((half_degree / 2, phase_features(half_degree / 2, harmonics)) for half_degree in range(720))


def recheck_window(center: float, radius: int) -> tuple[float, float, bool]:
    start = round((center - radius) % 360, 6) % 360
    end = round((center + radius) % 360, 6) % 360
    return start, end, start > end


def phase_proposal(rows: list[dict], calibration: RidgeModel, harmonics: int, radius: int,
                   threshold: float, trained_fixtures: set[str]) -> tuple[int, dict]:
    angles = [row['angle_deg'] for row in rows]
    gap_pairs = zip(angles, (*angles[1:], angles[0] + 360), strict=True)
    gap_start, gap_end = max(gap_pairs, key=lambda pair: (pair[1] - pair[0], -pair[0]))
    gap = gap_end - gap_start
    profile_harmonics = min(harmonics, (len(angles) - 1) // 2)
    target = [calibration.predict(calibration_features(row, harmonics)) for row in rows]
    profile = fit_ridge([phase_features(angle, profile_harmonics) for angle in angles], target, PROFILE_ALPHA)
    phase, peak = max(((angle, profile.predict(features)) for angle, features in phase_grid(profile_harmonics)),
                      key=lambda point: (abs(point[1]), -point[0]))
    raw = max(rows, key=lambda row: (abs(row['probe_mm']), -row['angle_deg']))
    raw_excess = abs(raw['probe_mm']) - abs(profile.predict(phase_features(raw['angle_deg'], profile_harmonics)))
    spike = abs(raw['probe_mm']) >= threshold and raw_excess >= SPIKE_DIFFERENCE_MM
    priority = 2
    reason = '拟合峰和探针尖峰均未触发优先复测'
    if gap > MAX_COVERAGE_GAP_DEG:
        priority, reason = 0, '最大采样空档超过 90°，估计峰所在角区需与缺测角区一并核查'
    elif abs(peak) >= threshold:
        priority, reason = 1, '拟合峰达到优先复测阈值'
    if spike:
        if priority == 2:
            priority, reason = 1, '探针尖峰高于同角度拟合幅度，需核查探针峰角'
        else:
            reason += '；探针峰角也需单独核查'
    start, end, wraps_zero = recheck_window(phase, radius)
    row = rows[0]
    return priority, {
        'wheel_id': row['wheel_id'], 'scan_id': row['scan_id'], 'fixture_id': row['fixture_id'],
        'fixture_seen_in_train': row['fixture_id'] in trained_fixtures, 'points': len(rows),
        'profile_harmonics': profile_harmonics, 'max_gap_deg': gap,
        'gap_start_deg': gap_start, 'gap_end_deg': gap_end % 360, 'peak_deg': phase,
        'peak_mm': round(peak, 6), 'raw_peak_deg': raw['angle_deg'], 'raw_peak_mm': raw['probe_mm'],
        'raw_peak_excess_mm': round(raw_excess, 6), 'check_raw_peak': spike,
        'recheck_radius_deg': radius, 'recheck_start_deg': start, 'recheck_end_deg': end,
        'wraps_zero': wraps_zero, 'action': ACTION_NAMES[priority], 'reason': reason,
    }


def build_proposals(rows: list[dict], calibration: RidgeModel, options: dict,
                    trained_fixtures: set[str]) -> tuple[list[dict], int]:
    scans = defaultdict(list)
    for row in rows:
        scans[row['scan_id']].append(row)
    proposals = [phase_proposal(sorted(scan_rows, key=lambda row: row['angle_deg']), calibration,
                                options['harmonics'], options['recheck_radius_deg'], options['review_threshold_mm'],
                                trained_fixtures) for scan_rows in scans.values()]
    proposals.sort(key=lambda entry: (entry[0], -abs(entry[1]['peak_mm']), entry[1]['scan_id']))
    return ([{'position': rank, **row} for rank, (_, row) in enumerate(proposals, start=1)],
            sum(priority < 2 for priority, _ in proposals))
