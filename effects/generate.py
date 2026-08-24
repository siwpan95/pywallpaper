"""
引擎效果生成器 — 创建新的 JSON 效果配置

用法:
    python effects/generate.py --id my_effect --name "我的效果" --category "自定义" --bg "无"
    python effects/generate.py --id my_effect --name "我的效果" --type bars
    python effects/generate.py --id my_effect --name "我的效果" --type combo
"""
import json
import os
import sys
import glob
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.dirname(os.path.abspath(__file__))

TEMPLATES = {
    'bars': {
        'description': '频谱柱状图 — FFT 能量映射到柱高',
        'layers': [{
            'type': 'bars', 'count': 48, 'direction': 'up',
            'position': {'x': 0, 'y': '100%'}, 'size': {'width': '100%', 'height': '70%'},
            'gap': 2,
            'color': {'type': 'hsv_flow', 'hue': [0, 0.7], 'speed': 0.1, 'sat': 0.8, 'val': 0.85},
            'audio': {'source': 'band_energy', 'target': 'height', 'scale': [0.02, 1.0], 'smoothing': 0.85},
        }]
    },
    'spikes': {
        'description': '径向尖峰 — 从中心向四周发射的频谱线',
        'layers': [{
            'type': 'spikes', 'count': 64,
            'center': {'x': '50%', 'y': '50%'}, 'inner_radius': 30, 'outer_radius': 300,
            'line_width': 3, 'rotation_speed': 0.3,
            'color': {'type': 'hsv_flow', 'hue': [0, 0.7], 'speed': 0.1, 'sat': 0.8, 'val': 0.9},
            'audio': {'source': 'band_energy', 'target': 'length', 'scale': [0, 1.0], 'smoothing': 0.85},
        }]
    },
    'vortex': {
        'description': '漩涡粒子 — 螺旋旋转的光点',
        'layers': [{
            'type': 'vortex', 'count': 200,
            'center': {'x': '50%', 'y': '50%'}, 'radius': {'min': 50, 'step': 5},
            'twist': 1.0, 'speed': 1.0, 'element_size': 3, 'size_scale': 5.0,
            'color': {'type': 'hsv_flow', 'hue': [0, 0.8], 'speed': 0.1, 'sat': 0.8, 'val': 0.85},
            'audio': {'source': 'band_energy', 'target': 'radius_scale', 'scale': [1.0, 1.5], 'smoothing': 0.8},
        }]
    },
    'particles': {
        'description': '粒子系统 — 自由漂浮的粒子',
        'layers': [{
            'type': 'particles', 'count': 100,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'particle': {'size': {'min': 2, 'max': 8}, 'speed': {'min': 20, 'max': 80},
                         'lifetime': {'min': 3, 'max': 8}, 'behavior': 'drift'},
            'connect': {'enabled': True, 'max_distance': 120, 'line_width': 1},
            'color': {'type': 'hsv_flow', 'hue': [0.55, 0.75], 'speed': 0.05, 'sat': 0.6, 'val': 0.9},
            'audio': {'source': 'band_energy', 'target': 'particle_size', 'scale': [0.5, 3.0], 'smoothing': 0.8},
        }]
    },
    'waveform': {
        'description': '波形曲线 — 音频波形可视化',
        'layers': [{
            'type': 'waveform', 'lines': 2, 'points': 200,
            'amplitude': 150, 'frequency': 0.05, 'line_width': 2,
            'position': {'x': 0, 'y': '50%'}, 'size': {'width': '100%', 'height': '60%'},
            'color': {'type': 'hsv_flow', 'hue': [0, 0.6], 'speed': 0.08, 'sat': 0.8, 'val': 0.9},
            'audio': {'source': 'band_energy', 'target': 'y', 'scale': [0.0, 1.0], 'smoothing': 0.85},
        }]
    },
    'grid': {
        'description': '脉冲网格 — 音频驱动的 2D 网格',
        'layers': [{
            'type': 'grid', 'cols': 30, 'rows': 18,
            'element': 'circle', 'element_ratio': 0.6,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'color': {'type': 'hsv_flow', 'hue': [0.55, 0.8], 'speed': 0.05, 'sat': 0.7, 'val': 0.9},
            'audio': {'source': 'band_energy', 'target': 'scale', 'scale': [0.1, 2.0], 'smoothing': 0.7},
        }]
    },
    'rain': {
        'description': '文字雨 — 矩阵风格的字符下落',
        'layers': [{
            'type': 'text_rain', 'chars': '01アイウエオカキクケコ',
            'count': 60, 'font_size': 16, 'speed': {'min': 50, 'max': 150}, 'trail_length': 10,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'color': {'type': 'solid', 'value': [0, 230, 80]},
            'audio': {'source': 'band_energy', 'target': 'brightness', 'scale': [0.3, 1.0], 'smoothing': 0.85},
        }]
    },
    'combo': {
        'description': '组合效果 — 多层叠加（bar + spikes 为例）',
        'layers': [
            {
                'type': 'bars', 'count': 32, 'direction': 'up',
                'position': {'x': 0, 'y': '100%'}, 'size': {'width': '100%', 'height': '40%'},
                'gap': 3,
                'color': {'type': 'hsv_flow', 'hue': [0, 0.4], 'speed': 0.06, 'sat': 0.6, 'val': 0.7},
                'audio': {'source': 'band_energy', 'target': 'height', 'scale': [0.02, 0.8], 'smoothing': 0.9},
            },
            {
                'type': 'spikes', 'count': 48,
                'center': {'x': '50%', 'y': '45%'}, 'inner_radius': 80, 'outer_radius': 250,
                'line_width': 2, 'rotation_speed': 0.5,
                'color': {'type': 'rainbow', 'speed': 0.1, 'sat': 0.8, 'val': 0.95},
                'audio': {'source': 'band_energy', 'target': 'length', 'scale': [0.1, 1.0], 'smoothing': 0.75},
            }
        ]
    },
    'script': {
        'description': '自定义脚本 — 嵌入 Python 绘制代码',
        'layers': [{
            'type': 'script',
            'init': '',
            'draw': '# 在此编写绘制代码\n# self = ScriptCompat 对象，提供 draw_rect/draw_circle/draw_line 等\n# self.audio.get_band_energy(idx), self.width, self.height, self.time\npass\n',
        }]
    },
}


def get_next_number(effects_dir):
    max_n = 0
    for path in glob.glob(os.path.join(effects_dir, '*_*.json')):
        m = re.match(r'(\d+)_', os.path.basename(path))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def main():
    parser = argparse.ArgumentParser(description='生成引擎效果 JSON')
    parser.add_argument('--id', required=True, help='效果 ID (英文)')
    parser.add_argument('--name', required=True, help='效果名称 (中文)')
    parser.add_argument('--category', default='自定义', help='分类')
    parser.add_argument('--bg', default='无', help='背景主题 (星空/渐变/极光/无)')
    parser.add_argument('--type', default='bars', choices=list(TEMPLATES.keys()),
                       help='效果模板类型')
    parser.add_argument('--list', action='store_true', help='列出可用模板')
    args = parser.parse_args()

    if args.list:
        print("可用效果模板:")
        for name, tmpl in TEMPLATES.items():
            print(f"  {name:12s} — {tmpl['description']}")
        return

    template = TEMPLATES.get(args.type, TEMPLATES['bars'])

    number = get_next_number(OUT)
    effect = {
        'id': args.id,
        'name': args.name,
        'full_name': f'{number:03d}. {args.name}',
        'category': args.category,
        'background_theme': args.bg,
        'class': 'EngineEffect',
        'params': {'layers': template['layers']},
    }

    filename = f'{number:03d}_{args.id}.json'
    filepath = os.path.join(OUT, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(effect, f, ensure_ascii=False, indent=2)

    print(f'✓ 已生成: {filepath}')
    print(f'  编号: {number}')
    print(f'  类型: {args.type} ({template["description"]})')
    print(f'  → 启动程序即生效，无需任何代码修改')


if __name__ == '__main__':
    main()
