"""Fourier features and a centered ridge fit solved with a Cholesky factor."""

from dataclasses import dataclass
from math import cos, fsum, radians, sin, sqrt


@dataclass(frozen=True)
class RidgeModel:
    intercept: float
    coefficients: tuple[float, ...]

    def predict(self, features: tuple[float, ...]) -> float:
        return self.intercept + fsum(coef * value for coef, value in zip(self.coefficients, features, strict=True))


def phase_features(angle_deg: float, harmonics: int) -> tuple[float, ...]:
    theta = radians(angle_deg % 360)
    return tuple(value for order in range(1, harmonics + 1)
                 for value in (sin(order * theta), cos(order * theta)))


def calibration_features(row: dict, harmonics: int) -> tuple[float, ...]:
    angle = row['angle_deg']
    probe = row['probe_mm']
    if harmonics == 0:
        return (probe, angle / 180 - 1)
    return (probe, *phase_features(angle, harmonics))


def calibration_labels(harmonics: int) -> tuple[str, ...]:
    if harmonics == 0:
        return ('probe_mm', 'angle_deg/180-1')
    return ('probe_mm', *(f'{function}({order}θ)' for order in range(1, harmonics + 1)
                          for function in ('sin', 'cos')))


def solve_positive_definite(matrix: list[list[float]], target: list[float]) -> tuple[float, ...]:
    size = len(target)
    lower = [[0.0] * size for _ in target]
    for row in range(size):
        for column in range(row + 1):
            value = matrix[row][column] - fsum(lower[row][k] * lower[column][k] for k in range(column))
            lower[row][column] = sqrt(value) if row == column else value / lower[column][column]

    intermediate = [0.0] * size
    for row in range(size):
        subtotal = fsum(lower[row][k] * intermediate[k] for k in range(row))
        intermediate[row] = (target[row] - subtotal) / lower[row][row]
    solution = [0.0] * size
    for row in reversed(range(size)):
        subtotal = fsum(lower[k][row] * solution[k] for k in range(row + 1, size))
        solution[row] = (intermediate[row] - subtotal) / lower[row][row]
    return tuple(solution)


def fit_ridge(features: list[tuple[float, ...]], target: list[float], alpha: float) -> RidgeModel:
    count = len(target)
    feature_columns = list(zip(*features, strict=True))
    means = [fsum(column) / count for column in feature_columns]
    average_target = fsum(target) / count
    centered = [[value - mean for value in column] for column, mean in zip(feature_columns, means)]
    centered_target = [value - average_target for value in target]

    def mean_product(left, right):
        return fsum(a * b for a, b in zip(left, right, strict=True)) / count

    matrix = [[mean_product(left, right) + (alpha if row == column else 0)
               for column, right in enumerate(centered)] for row, left in enumerate(centered)]
    target_vector = [mean_product(column, centered_target) for column in centered]
    coefficients = solve_positive_definite(matrix, target_vector)
    intercept = average_target - fsum(mean * coefficient for mean, coefficient in zip(means, coefficients))
    return RidgeModel(intercept, coefficients)
