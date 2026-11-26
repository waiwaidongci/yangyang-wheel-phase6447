"""Compare the frozen calibrators on identical independent scans and fixture groups."""

from collections import defaultdict
from dataclasses import dataclass
from math import fsum, sqrt

from .regression import RidgeModel, calibration_features


@dataclass(frozen=True)
class HoldoutPoint:
    row: dict
    fourier: float
    bare: float


def predict_holdout(rows: list[dict], fourier: RidgeModel, bare: RidgeModel, harmonics: int) -> list[HoldoutPoint]:
    return [HoldoutPoint(row, fourier.predict(calibration_features(row, harmonics)),
                         bare.predict(calibration_features(row, 0))) for row in rows]


def score(scope: str, group_id: str, points: list[HoldoutPoint], seen_fixture: bool | None = None) -> dict:
    count = len(points)
    result = {
        'scope': scope,
        'group_id': group_id,
        'fixture_seen_in_train': seen_fixture,
        'wheels': len({point.row['wheel_id'] for point in points}),
        'points': count,
        'fourier_mae_mm': None,
        'bare_mae_mm': None,
        'mae_delta_mm': None,
        'fourier_rmse_mm': None,
        'bare_rmse_mm': None,
    }
    if count == 0:
        return result
    fourier = [point.fourier - point.row['reference_mm'] for point in points]
    bare = [point.bare - point.row['reference_mm'] for point in points]
    fourier_mae = fsum(map(abs, fourier)) / count
    bare_mae = fsum(map(abs, bare)) / count
    result.update(
        fourier_mae_mm=round(fourier_mae, 6),
        bare_mae_mm=round(bare_mae, 6),
        mae_delta_mm=round(fourier_mae - bare_mae, 6),
        fourier_rmse_mm=round(sqrt(fsum(error * error for error in fourier) / count), 6),
        bare_rmse_mm=round(sqrt(fsum(error * error for error in bare) / count), 6),
    )
    return result


def compare(points: list[HoldoutPoint], trained_fixtures: set[str]) -> list[dict]:
    by_fixture = defaultdict(list)
    by_wheel = defaultdict(list)
    seam = []
    for point in points:
        by_fixture[point.row['fixture_id']].append(point)
        by_wheel[point.row['wheel_id']].append(point)
        angle = point.row['angle_deg']
        if min(angle, 360 - angle) <= 15:
            seam.append(point)
    return [score('all', 'all', points), score('seam', '0±15°', seam),
            *(score('fixture', key, group, key in trained_fixtures) for key, group in sorted(by_fixture.items())),
            *(score('wheel', key, group) for key, group in sorted(by_wheel.items()))]
