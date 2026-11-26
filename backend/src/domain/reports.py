"""Scalar business tables consumed by the API and the signed CSV exporter."""

from .evaluation import HoldoutPoint
from .regression import RidgeModel, calibration_labels
from .settings import FIELDS


def table(key: str, title: str, labels: dict[str, str], rows: list[dict]) -> dict:
    return {'key': key, 'title': title, 'columns': list(labels), 'labels': labels, 'rows': rows}


def proposal_table(rows: list[dict]) -> dict:
    labels = {
        'position': '复测顺序', 'wheel_id': FIELDS['wheel_id'], 'scan_id': FIELDS['scan_id'],
        'fixture_id': FIELDS['fixture_id'], 'fixture_seen_in_train': '历史见过挡位', 'points': '总测点数',
        'profile_harmonics': '扫描相位拟合阶数', 'max_gap_deg': '最大采样空档（°）',
        'gap_start_deg': '最大空档起点（°）', 'gap_end_deg': '最大空档终点（°）',
        'peak_deg': '拟合最大绝对跳动角（°）', 'peak_mm': '拟合峰有符号幅度（mm）',
        'raw_peak_deg': '探针最大绝对跳动角（°）', 'raw_peak_mm': '探针峰有符号幅度（mm）',
        'raw_peak_excess_mm': '探针峰绝对幅度超出同角拟合量（mm）', 'check_raw_peak': '单独核查探针峰',
        'recheck_radius_deg': '人工复测角半径（°）', 'recheck_start_deg': '复测起始角（°）',
        'recheck_end_deg': '复测终止角（°）', 'wraps_zero': '复测区间跨零度',
        'action': '复测安排', 'reason': '判定依据',
    }
    return table('recheck_proposals', '轮组待测相位复调提案', labels, rows)


def comparison_table(rows: list[dict]) -> dict:
    labels = {
        'scope': '对照范围', 'group_id': '范围编号', 'fixture_seen_in_train': '历史见过挡位',
        'wheels': '留出轮组数', 'points': '留出测点数',
        'fourier_mae_mm': '傅里叶 MAE（mm）', 'bare_mae_mm': '裸角度 MAE（mm）',
        'mae_delta_mm': '傅里叶 MAE 减裸角度 MAE（mm）',
        'fourier_rmse_mm': '傅里叶 RMSE（mm）', 'bare_rmse_mm': '裸角度 RMSE（mm）',
    }
    return table('holdout_comparison', '新轮组、支架挡位及零度接缝误差', labels, rows)


def holdout_table(points: list[HoldoutPoint]) -> dict:
    labels = {field: FIELDS[field] for field in ('id', 'wheel_id', 'scan_id', 'fixture_id', 'angle_deg',
                                                'probe_mm', 'reference_mm')}
    rows = [{**{field: point.row[field] for field in labels}, 'fourier_mm': round(point.fourier, 6),
             'bare_mm': round(point.bare, 6)} for point in points]
    labels.update(fourier_mm='傅里叶预测（mm）', bare_mm='裸角度预测（mm）')
    return table('holdout_points', '留出测点复测对账', labels, rows)


def error_bound_table(rows: list[dict]) -> dict:
    labels = {'source': '模型来源', 'label': '模型说明', 'left_out_wheel': '留掉的历史轮组',
              'holdout_points': '留出测点数', 'error_bound_mm': '留出最大绝对预测误差界（mm）'}
    return table('error_bounds', '候选峰误差界（留一重拟合）', labels, rows)


def candidate_table(rows: list[dict]) -> dict:
    labels = {'scan_id': FIELDS['scan_id'], 'wheel_id': FIELDS['wheel_id'], 'fixture_id': FIELDS['fixture_id'],
              'source': '候选来源', 'label': '候选说明', 'peak_deg': '候选峰角（°）',
              'peak_mm': '候选峰有符号幅度（mm）', 'error_bound_mm': '候选误差界（mm）',
              'fits_window': '候选峰可装进同宽角窗', 'proposed_angle_deg': '建议补测角（°）',
              'proposed_min_gap_mm': '建议补测角预测区间最小间隔（mm）'}
    return table('peak_candidates', '待测扫描候选峰与补测角', labels, rows)


def coefficient_table(fourier: RidgeModel, bare: RidgeModel, options: dict) -> dict:
    rows = []
    for name, model, harmonics in (('fourier', fourier, options['harmonics']), ('bare_angle', bare, 0)):
        labels = ('intercept', *calibration_labels(harmonics))
        values = (model.intercept, *model.coefficients)
        for term, value in zip(labels, values, strict=True):
            rows.append({'model': name, 'term': term, 'coefficient': round(value, 9),
                         'harmonics': harmonics, 'ridge_alpha': options['ridge_alpha']})
    labels = {'model': '模型', 'term': '回归项', 'coefficient': '历史冻结系数',
              'harmonics': '谐波阶数', 'ridge_alpha': '运行岭惩罚'}
    return table('model_coefficients', '冻结校正模型系数', labels, rows)
