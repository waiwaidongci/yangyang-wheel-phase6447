"""CSV schema and configuration for wheel runout calibration."""

from math import isfinite

FIELDS = {
    'id': '测点记录号',
    'wheel_id': '轮组编号',
    'scan_id': '扫描编号',
    'fixture_id': '校正支架挡位',
    'split': '测点用途',
    'angle_deg': '气嘴零点顺时针角度（°）',
    'probe_mm': '快速探针侧向读数（mm）',
    'reference_mm': '复测侧向读数（mm）',
}
COLUMNS = tuple(FIELDS)
SETTINGS = [
    {'key': 'harmonics', 'label': '傅里叶谐波阶数', 'default': 2, 'min': 1, 'max': 4, 'step': 1},
    {'key': 'ridge_alpha', 'label': '岭回归惩罚', 'default': 0.025, 'min': 0.001, 'max': 2, 'step': 0.001},
    {'key': 'recheck_radius_deg', 'label': '人工复测角半径（°）', 'default': 15, 'min': 5, 'max': 60, 'step': 1},
    {'key': 'review_threshold_mm', 'label': '优先复测绝对跳动（mm）', 'default': 0.7,
     'min': 0.1, 'max': 5, 'step': 0.01},
]

SPEC = {
    'columns': list(COLUMNS),
    'fields': FIELDS,
    'settings': SETTINGS,
    'modules': {
        'datasets': '轮组扫描台账',
        'runs': '傅里叶校正配置',
        'results': '相位峰与复调提案',
        'reviews': '复测交班签核',
    },
    'limitation': '留出误差来自本次带复测的轮组。复调峰由待测扫描估计，稀疏角区和探针尖峰需人工复测。',
    'dataset_name': '20261125-轮组跳动扫描.csv',
    'recommendation': '按提案角区复测拟合峰和值得核查的探针尖峰，确认跳动方向后再安排复调。',
}


def parse_settings(raw: dict) -> dict[str, int | float]:
    if not isinstance(raw, dict) or raw.keys() - {item['key'] for item in SETTINGS}:
        raise ValueError('存在本项目未定义的运行参数。')
    values = {}
    for item in SETTINGS:
        key = item['key']
        value = raw.get(key, item['default'])
        if type(value) not in (int, float) or not item['min'] <= value <= item['max'] or not isfinite(value):
            raise ValueError(f"{item['label']}须在 {item['min']} 至 {item['max']} 之间。")
        if item['step'] == 1:
            if value != int(value):
                raise ValueError(f"{item['label']}须为整数。")
            value = int(value)
        values[key] = value
    return values
