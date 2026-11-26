"""Normalize scan CSV values and keep both scans and wheels within one split."""

import re
from collections import defaultdict
from math import isfinite

from .settings import COLUMNS, FIELDS

CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
SPLITS = ('train', 'holdout', 'pending')
CODE_FIELDS = ('id', 'wheel_id', 'scan_id', 'fixture_id')
MIN_SCAN_POINTS = 4


def code(value, field: str, line: int) -> str:
    if isinstance(value, str) and CODE.fullmatch(value.strip()):
        return value.strip()
    raise ValueError(f'第 {line} 条的{FIELDS[field]}须以英文字母或数字开头，长度为 1 至 64。')


def number(value, field: str, line: int, low: float, high: float) -> float:
    try:
        if type(value) not in (float, int, str):
            raise ValueError
        parsed = float(value)
        if not isfinite(parsed) or not low <= parsed <= high:
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError(f'第 {line} 条的{FIELDS[field]}须为 {low:g} 至 {high:g} 的有限数值。') from None
    return 0.0 if parsed == 0 else parsed


def normalize_rows(rows: list[dict]) -> list[dict]:
    if not 1 <= len(rows) <= 5000:
        raise ValueError('扫描台账须有 1 至 5000 个测点。')
    normalized = []
    ids = set()
    wheel_splits = {}
    scan_context = {}
    scan_angles = defaultdict(set)
    cohort_wheels = defaultdict(set)
    for line, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.keys() != set(COLUMNS):
            raise ValueError(f'第 {line} 条列名须为 {", ".join(COLUMNS)}。')
        item = {field: code(row[field], field, line) for field in CODE_FIELDS}
        point, wheel, scan, fixture = (item[key] for key in CODE_FIELDS)
        split = row['split'].strip() if isinstance(row['split'], str) else None
        if split not in SPLITS:
            raise ValueError(f'第 {line} 条的测点用途须为 train、holdout 或 pending。')
        if point in ids:
            raise ValueError(f'测点记录号 {point} 重复。')
        ids.add(point)
        if wheel_splits.setdefault(wheel, split) != split:
            raise ValueError(f'轮组 {wheel} 跨用途，须整组归入同一个分区。')
        if scan_context.setdefault(scan, (wheel, fixture, split)) != (wheel, fixture, split):
            raise ValueError(f'扫描 {scan} 中的轮组、支架挡位和用途须一致。')
        angle = number(row['angle_deg'], 'angle_deg', line, 0, 360) % 360
        if angle in scan_angles[scan]:
            raise ValueError(f'扫描 {scan} 的角度 {angle:g}° 重复，360° 与 0° 为同一点。')
        scan_angles[scan].add(angle)
        probe = number(row['probe_mm'], 'probe_mm', line, -20, 20)
        reference = row['reference_mm']
        if split == 'pending':
            if reference is not None and not (isinstance(reference, str) and not reference.strip()):
                raise ValueError(f'第 {line} 条待测点的复测侧向读数须留空。')
            reference = None
        else:
            reference = number(reference, 'reference_mm', line, -20, 20)
        item.update(split=split, angle_deg=angle, probe_mm=probe, reference_mm=reference)
        normalized.append(item)
        cohort_wheels[split].add(wheel)

    for scan, angles in scan_angles.items():
        if len(angles) < MIN_SCAN_POINTS:
            raise ValueError(f'扫描 {scan} 至少需要 {MIN_SCAN_POINTS} 个不同角度。')
    if len(cohort_wheels['train']) < 2 or not cohort_wheels['holdout']:
        raise ValueError('至少需要 2 个历史轮组及 1 个独立留出轮组。')
    return normalized
