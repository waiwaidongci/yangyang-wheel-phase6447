"""Simulated dial-gauge readings with independent fixture settings and pending spikes."""

from math import cos, radians, sin
from random import Random

from .settings import COLUMNS


def demo_rows() -> list[dict]:
    rng = Random(20261125)
    rows = []
    cohorts = (
        ('train', 'H', 8, ('STAND-A1', 'STAND-A2'), 15),
        ('holdout', 'V', 4, ('STAND-A2', 'STAND-B3'), 15),
        ('pending', 'P', 3, ('STAND-A1', 'STAND-B3'), 15),
    )
    for split, prefix, wheels, fixtures, step in cohorts:
        for index in range(1, wheels + 1):
            wheel = f'WH-{prefix}{index:02d}'
            scan_count = 2 if split == 'train' and index == 1 else 1
            fixture = fixtures[(index - 1) % len(fixtures)]
            amplitude = rng.uniform(0.32, 0.86)
            phase = rng.uniform(25, 345)
            harmonic_phase = rng.uniform(0, 360)
            if split == 'pending' and index == 1:
                amplitude, phase, harmonic_phase = 0.96, 354, 352
            for scan_index in range(1, scan_count + 1):
                scan = f'{wheel}-S{scan_index}'
                angles = list(range((index + scan_index) % 3 * 5, 360, step))
                if split == 'pending' and index == 3:
                    angles = [angle for angle in angles if not 58 <= angle <= 160]
                for point, angle in enumerate(angles, start=1):
                    true_runout = (0.12 + amplitude * cos(radians(angle - phase))
                                   + 0.13 * cos(radians(2 * (angle - harmonic_phase))))
                    mounting_bias = {'STAND-A1': -0.025, 'STAND-A2': 0.02, 'STAND-B3': 0.045}[fixture]
                    probe = (true_runout + 0.33 * cos(radians(angle - 347))
                             + 0.17 * sin(radians(2 * (angle + 16))) + mounting_bias
                             + rng.gauss(0, 0.045))
                    if split == 'pending' and index == 1 and point == 5:
                        probe += 1.9
                    reference = None if split == 'pending' else round(true_runout + rng.gauss(0, 0.015), 5)
                    values = (f'{scan}-{point:02d}', wheel, scan, fixture, split, angle % 360,
                              round(probe, 5), reference)
                    rows.append(dict(zip(COLUMNS, values)))
    return rows
