"""
批量效果生成器 — 通过参数化组合生成 850+ 个新引擎效果 JSON

用法:
    python effects/generate_bulk.py          # 生成所有效果
    python effects/generate_bulk.py --dry     # 仅预览不写入
    python effects/generate_bulk.py --count   # 仅显示数量

设计:
    - 对每种原语定义多维度参数变体，笛卡尔积展开
    - 颜色方案、音频映射、背景主题按预设池复用
    - 编号从 147 开始，自动递增
"""
import json
import os
import sys
import glob
import re
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 可复用配置片段
# ============================================================

COLOR_SCHEMES = {
    # hsv_flow 系列
    'warm':       {'type': 'hsv_flow', 'hue': [0.0, 0.12], 'speed': 0.08,  'sat': 0.9,  'val': 0.9},
    'cool':       {'type': 'hsv_flow', 'hue': [0.50, 0.68], 'speed': 0.08,  'sat': 0.75, 'val': 0.9},
    'sunset':     {'type': 'hsv_flow', 'hue': [0.05, 0.18], 'speed': 0.06,  'sat': 0.85, 'val': 0.95},
    'ocean':      {'type': 'hsv_flow', 'hue': [0.52, 0.62], 'speed': 0.06,  'sat': 0.8,  'val': 0.85},
    'forest':     {'type': 'hsv_flow', 'hue': [0.22, 0.38], 'speed': 0.07,  'sat': 0.85, 'val': 0.8},
    'purple':     {'type': 'hsv_flow', 'hue': [0.68, 0.82], 'speed': 0.07,  'sat': 0.8,  'val': 0.9},
    'candy':      {'type': 'hsv_flow', 'hue': [0.82, 1.05], 'speed': 0.1,   'sat': 0.85, 'val': 0.9},
    'gold':       {'type': 'hsv_flow', 'hue': [0.12, 0.20], 'speed': 0.05,  'sat': 0.9,  'val': 0.95},
    'aqua':       {'type': 'hsv_flow', 'hue': [0.48, 0.56], 'speed': 0.09,  'sat': 0.7,  'val': 0.9},
    'neon':       {'type': 'hsv_flow', 'hue': [0.58, 0.88], 'speed': 0.12,  'sat': 0.95, 'val': 1.0},
    'vintage':    {'type': 'hsv_flow', 'hue': [0.08, 0.16], 'speed': 0.04,  'sat': 0.5,  'val': 0.75},
    'arctic':     {'type': 'hsv_flow', 'hue': [0.55, 0.65], 'speed': 0.04,  'sat': 0.4,  'val': 0.85},
    'toxic':      {'type': 'hsv_flow', 'hue': [0.18, 0.35], 'speed': 0.11,  'sat': 0.95, 'val': 0.95},
    'midnight':   {'type': 'hsv_flow', 'hue': [0.58, 0.72], 'speed': 0.03,  'sat': 0.6,  'val': 0.7},
    # rainbow
    'rainbow_slow':  {'type': 'rainbow', 'speed': 0.05, 'sat': 0.8,  'val': 0.9},
    'rainbow_fast':  {'type': 'rainbow', 'speed': 0.15, 'sat': 0.85, 'val': 0.95},
    'rainbow_pastel':{'type': 'rainbow', 'speed': 0.08, 'sat': 0.4,  'val': 0.95},
    # solid
    'green':      {'type': 'solid', 'value': [0, 230, 80]},
    'cyan':       {'type': 'solid', 'value': [0, 220, 220]},
    'magenta':    {'type': 'solid', 'value': [220, 30, 220]},
    'orange':     {'type': 'solid', 'value': [255, 140, 20]},
    'white':      {'type': 'solid', 'value': [220, 220, 240]},
    'yellow':     {'type': 'solid', 'value': [240, 220, 40]},
    'red':        {'type': 'solid', 'value': [240, 40, 40]},
    'blue':       {'type': 'solid', 'value': [40, 120, 240]},
}

AUDIO_BE = lambda t, s, sm=0.85: {'source': 'band_energy', 'target': t, 'scale': s, 'smoothing': sm}
AUDIO_RMS = lambda t, s, sm=0.85: {'source': 'rms', 'target': t, 'scale': s, 'smoothing': sm}

BG = ['星空', '渐变', '极光', '无']

# ============================================================
# 效果生成器函数 — 每个生成器 yield (id, name, category, bg, layers)
# ============================================================

def gen_bars():
    """频谱柱状图 — 方向/数量/颜色/背景 组合"""
    directions = [
        ('up', '向上'), ('down', '向下'), ('left', '向左'), ('right', '向右'),
        ('center_v', '居中竖'), ('center_h', '居中横'),
    ]
    counts = [16, 24, 32, 48, 64, 80, 96, 128]
    colors = ['warm', 'cool', 'sunset', 'ocean', 'neon', 'rainbow_slow', 'green', 'cyan', 'gold', 'purple']
    gaps = [1, 2, 3, 4]
    
    for dir_key, dir_name in directions:
        for count in counts:
            for ci, ck in enumerate(colors[:6]):
                for gi, gap in enumerate(gaps[:2]):
                    if (ci + gi) % 2 == 0:
                        bid = f'bars_{dir_key}_{count}_{ck}'
                        name = f'柱状图·{dir_name}·{count}柱·{ck}'
                        yield bid, name, '频谱', BG[(count + ci) % 4], [{
                            'type': 'bars', 'count': count, 'direction': dir_key,
                            'position': {'x': 0, 'y': '100%'}, 'size': {'width': '100%', 'height': '70%'},
                            'gap': gap, 'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('height', [0.02, 1.0], 0.85),
                        }]
    
    # 镜像模式
    for dir_key, dir_name in [('up', '上'), ('down', '下'), ('center_v', '中竖')]:
        for count in [24, 48, 64]:
            for ck in ['warm', 'cool', 'neon']:
                bid = f'bars_mirror_{dir_key}_{count}_{ck}'
                name = f'柱状图·镜像{dir_name}·{count}柱·{ck}'
                yield bid, name, '频谱', BG[count % 4], [{
                    'type': 'bars', 'count': count, 'direction': dir_key,
                    'position': {'x': 0, 'y': '100%'}, 'size': {'width': '100%', 'height': '70%'},
                    'gap': 2, 'mirror': True, 'color': COLOR_SCHEMES[ck],
                    'audio': AUDIO_BE('height', [0.02, 1.0], 0.85),
                }]


def gen_spikes():
    """径向尖峰"""
    counts = [32, 48, 64, 80, 96, 128, 160, 200]
    radii = [(20, 250, '小'), (40, 280, '中'), (60, 320, '大'), (30, 350, '长')]
    speeds = [0.0, 0.2, 0.5, 1.0, 2.0]
    colors = ['warm', 'cool', 'sunset', 'ocean', 'rainbow_slow', 'rainbow_fast', 'neon', 'purple']
    lw = [1, 2, 3, 4]
    
    for ci, ck in enumerate(colors):
        for count in counts[:6]:
            for ir, or_, rl in radii[:3]:
                for sp in speeds[:3]:
                    if (count + ci) % 3 == 0:
                        bid = f'spikes_{count}_{rl}_{ck}_s{sp}'
                        name = f'尖峰·{count}条·{rl}半径·{ck}'
                        yield bid, name, '圆形', BG[ci % 4], [{
                            'type': 'spikes', 'count': count,
                            'center': {'x': '50%', 'y': '50%'},
                            'inner_radius': ir, 'outer_radius': or_,
                            'line_width': lw[ci % 4], 'rotation_speed': sp,
                            'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('length', [0, 1.0], 0.85),
                        }]


def gen_waveform():
    """波形"""
    line_counts = [1, 2, 3, 4, 5]
    points = [100, 200, 300, 400]
    amps = [80, 120, 160, 200]
    freqs = [0.02, 0.04, 0.06, 0.08]
    colors = ['warm', 'cool', 'ocean', 'purple', 'neon', 'rainbow_slow', 'cyan', 'gold']
    
    for lc in line_counts:
        for pt in points[1:3]:
            for amp in amps:
                for fr in freqs:
                    for ci, ck in enumerate(colors[:5]):
                        if (lc + ci) % 2 == 0:
                            bid = f'wave_{lc}l_{pt}p_a{amp}_{ck}'
                            name = f'波形·{lc}线·{pt}点·{ck}'
                            yield bid, name, '波浪', BG[lc % 4], [{
                                'type': 'waveform', 'lines': lc, 'points': pt,
                                'amplitude': amp, 'frequency': fr, 'line_width': 2,
                                'position': {'x': 0, 'y': '50%'}, 'size': {'width': '100%', 'height': '60%'},
                                'color': COLOR_SCHEMES[ck],
                                'audio': AUDIO_BE('y', [0.0, 1.0], 0.85),
                            }]


def gen_vortex():
    """漩涡"""
    counts = [100, 150, 200, 250, 300, 400, 500]
    twists = [0.5, 1.0, 1.5, 2.0, 3.0]
    speeds = [0.5, 1.0, 1.5, 2.0, 3.0]
    colors = ['warm', 'cool', 'sunset', 'ocean', 'neon', 'rainbow_slow', 'rainbow_fast', 'purple', 'candy']
    
    for ci, ck in enumerate(colors):
        for count in counts[:5]:
            for tw in twists[:3]:
                for sp in speeds[:3]:
                    if (count + ci) % 4 == 0:
                        bid = f'vortex_{count}_{ck}_tw{tw}_sp{sp}'
                        name = f'漩涡·{count}粒·{ck}'
                        yield bid, name, '圆形', BG[ci % 4], [{
                            'type': 'vortex', 'count': count,
                            'center': {'x': '50%', 'y': '50%'},
                            'radius': {'min': 40, 'step': 5}, 'twist': tw, 'speed': sp,
                            'element_size': 3, 'size_scale': 5.0,
                            'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('radius_scale', [1.0, 1.5], 0.8),
                        }]


def gen_circle_map():
    """圆形映射/频谱环"""
    configs = [
        ([80], '单环80'),
        ([120], '单环120'),
        ([160], '单环160'),
        ([200], '单环200'),
        ([80, 140], '双环80+140'),
        ([100, 170], '双环100+170'),
        ([60, 120, 180], '三环60+120+180'),
        ([80, 140, 200, 260], '四环80+140+200+260'),
        ([60, 110, 160, 210, 260], '五环'),
    ]
    counts_per = [36, 48, 64, 72, 90, 120]
    colors = ['warm', 'cool', 'ocean', 'sunset', 'neon', 'rainbow_slow', 'rainbow_fast', 'purple', 'candy']
    
    for ci, ck in enumerate(colors):
        for ri, (radii, rl) in enumerate(configs[:6]):
            for cp in counts_per[:4]:
                if (ri + ci) % 2 == 0:
                    rings = [{'count': cp, 'radius': r, 'line': True, 'line_width': 2} for r in radii]
                    bid = f'circle_{rl}_{cp}_{ck}'
                    name = f'频谱环·{rl}·{cp}点·{ck}'
                    yield bid, name, '圆形', BG[ri % 4], [{
                        'type': 'circle_map', 'center': {'x': '50%', 'y': '50%'},
                        'rings': rings,
                        'color': COLOR_SCHEMES[ck],
                        'audio': AUDIO_BE('radius_offset', [0, 60], 0.85),
                    }]
    
    # 点模式（非连线）
    for ci, ck in enumerate(colors[:5]):
        for count in [48, 72, 96]:
            for r in [120, 180, 240]:
                bid = f'circle_dots_{count}_{r}_{ck}'
                name = f'圆点阵·{count}点·半径{r}·{ck}'
                yield bid, name, '圆形', BG[ci % 4], [{
                    'type': 'circle_map', 'center': {'x': '50%', 'y': '50%'},
                    'rings': [{'count': count, 'radius': r, 'line': False, 'fill': True}],
                    'element_size': 3, 'rotation_speed': 0.3,
                    'color': COLOR_SCHEMES[ck],
                    'audio': AUDIO_BE('radius_offset', [0, 50], 0.8),
                }]


def gen_particles():
    """粒子系统 — 5种行为 × 多种参数"""
    behaviors = [
        ('drift', '飘移'),
        ('orbit', '轨道'),
        ('fall', '下落'),
        ('rise', '上升'),
        ('bounce', '弹跳'),
    ]
    counts = [60, 100, 150, 200, 300]
    colors = ['warm', 'cool', 'sunset', 'ocean', 'neon', 'rainbow_slow', 'purple', 'candy', 'gold', 'aqua']
    connect_modes = [True, False]
    
    for bi, (beh, bname) in enumerate(behaviors):
        for ci, ck in enumerate(colors[:6]):
            for cnt in counts[:4]:
                for conn in connect_modes:
                    if (bi + ci + cnt) % 3 == 0:
                        cs = '' if conn else '_nc'
                        bid = f'particles_{beh}_{cnt}_{ck}{cs}'
                        name = f'粒子·{bname}·{cnt}粒·{ck}'
                        layers = [{
                            'type': 'particles', 'count': cnt,
                            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
                            'particle': {'size': {'min': 2, 'max': 8}, 'speed': {'min': 20, 'max': 80},
                                        'lifetime': {'min': 3, 'max': 8}, 'behavior': beh},
                            'connect': {'enabled': conn, 'max_distance': 120, 'line_width': 1},
                            'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('particle_size', [0.5, 3.0], 0.8),
                        }]
                        yield bid, name, '粒子', BG[(bi + ci) % 4], layers
    
    # 大粒子 + 不同重力
    for beh, bname in [('fall', '下落'), ('bounce', '弹跳')]:
        for cnt in [80, 150]:
            for ck in ['warm', 'cool', 'neon']:
                for grav in [100, 300, 500]:
                    bid = f'particles_{beh}_g{grav}_{cnt}_{ck}'
                    name = f'粒子·{bname}·重力{grav}·{cnt}粒·{ck}'
                    yield bid, name, '粒子', BG[0], [{
                        'type': 'particles', 'count': cnt,
                        'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
                        'particle': {'size': {'min': 3, 'max': 10}, 'speed': {'min': 30, 'max': 120},
                                    'lifetime': {'min': 3, 'max': 8}, 'behavior': beh, 'gravity': grav},
                        'connect': {'enabled': False, 'max_distance': 0, 'line_width': 0},
                        'color': COLOR_SCHEMES[ck],
                        'audio': AUDIO_BE('particle_size', [0.3, 2.5], 0.8),
                    }]


def gen_grid():
    """网格"""
    grid_sizes = [(12, 8), (16, 10), (20, 12), (24, 16), (30, 20), (36, 24), (48, 30), (60, 36)]
    elements = [('circle', '圆点'), ('rect', '方块')]
    colors = ['warm', 'cool', 'ocean', 'neon', 'rainbow_slow', 'sunset', 'purple', 'candy', 'gold']
    ratios = [0.4, 0.6, 0.8]
    
    for ci, ck in enumerate(colors[:7]):
        for gi, (cols, rows) in enumerate(grid_sizes[:6]):
            for el, eln in elements:
                for rat in ratios:
                    if (gi + ci) % 3 == 0:
                        bid = f'grid_{cols}x{rows}_{el}_{ck}_r{rat}'
                        name = f'网格·{eln}·{cols}x{rows}·{ck}'
                        yield bid, name, '网格', BG[gi % 4], [{
                            'type': 'grid', 'cols': cols, 'rows': rows,
                            'element': el, 'element_ratio': rat,
                            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
                            'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('scale', [0.1, 2.0], 0.7),
                        }]


def gen_text_rain():
    """文字雨"""
    charsets = [
        ('01', '二进'),
        ('01アイウエオカキクケコサシスセソ', '日文'),
        ('ABCDEFGHIJKLMNOPQRSTUVWXYZ', '字母'),
        ('01ABCDEFabcdef', '十六进'),
        ('░▒▓█▄▀■□▪▫', '方块'),
        ('零一二三四五六七八九', '中文数字'),
        ('◢◣◤◥●○◎◇◆□■△▲▽▼☆★', '几何符号'),
    ]
    counts = [30, 40, 50, 60, 80]
    speeds = [(40, 100), (60, 150), (80, 200), (100, 250)]
    trails = [6, 8, 10, 15, 20]
    colors = ['green', 'cyan', 'magenta', 'white', 'yellow', 'red', 'blue']
    sizes = [12, 14, 16, 18, 22]
    
    for ci, ck in enumerate(colors):
        for chi, (chars, cn) in enumerate(charsets[:5]):
            for cnt in counts[1:4]:
                for sp in speeds[:3]:
                    for tr in trails[1:4]:
                        if (ci + chi + cnt) % 5 == 0:
                            bid = f'rain_{cn}_{cnt}_{ck}_t{tr}'
                            name = f'文字雨·{cn}·{cnt}列·{ck}'
                            yield bid, name, '粒子', '无', [{
                                'type': 'text_rain', 'chars': chars,
                                'count': cnt, 'font_size': sizes[chi % 5],
                                'speed': {'min': sp[0], 'max': sp[1]}, 'trail_length': tr,
                                'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
                                'color': COLOR_SCHEMES[ck],
                                'audio': AUDIO_BE('brightness', [0.3, 1.0], 0.85),
                            }]


def gen_wireframe_3d():
    """3D线框"""
    geoms = [
        ('cube', '立方体'),
        ('hypercube', '超立方体'),
        ('mobius', '莫比乌斯'),
        ('tunnel', '隧道'),
        ('helix', '螺旋'),
    ]
    colors = ['warm', 'cool', 'neon', 'rainbow_slow', 'rainbow_fast', 'ocean', 'sunset', 'purple', 'cyan']
    scales = [100, 150, 200]
    rots = [
        (0.3, 0.5, 0.0),
        (0.5, 0.7, 0.0),
        (0.7, 1.0, 0.0),
        (0.2, 0.3, 0.2),
        (0.5, 0.5, 0.5),
    ]
    lws = [1, 2, 3]
    
    for gi, (geom, gn) in enumerate(geoms):
        for ci, ck in enumerate(colors[:5]):
            for sc in scales:
                for rx, ry, rz in rots[:3]:
                    if (gi + ci) % 2 == 0:
                        bid = f'3d_{geom}_{ck}_s{sc}'
                        name = f'3D·{gn}·{ck}'
                        extra = {}
                        if geom == 'tunnel':
                            extra = {'ring_count': 12 + gi * 3}
                        layers = [{
                            'type': 'wireframe_3d', 'geometry': geom,
                            'scale': sc, 'line_width': lws[gi % 3],
                            'rotation': {'x_speed': rx, 'y_speed': ry, 'z_speed': rz},
                            'color': COLOR_SCHEMES[ck],
                            **extra,
                        }]
                        yield bid, name, '3D', BG[gi % 4], layers


def gen_texture():
    """纹理"""
    modes = [
        ('plasma', '等离子体'),
        ('moire', '莫尔条纹'),
        ('grid', '频谱网格'),
        ('pixel', '像素排序'),
        ('field', '频率场'),
        ('mandelbrot', '曼德博'),
        ('fire', '火焰'),
    ]
    cell_sizes = [4, 6, 8, 10, 12, 16]
    colors = ['warm', 'cool', 'ocean', 'neon', 'rainbow_slow', 'sunset', 'purple', 'candy']
    
    for mi, (mode, mn) in enumerate(modes):
        for ci, ck in enumerate(colors[:5]):
            for cs in cell_sizes[:4]:
                if (mi + ci) % 2 == 0:
                    bid = f'texture_{mode}_{ck}_c{cs}'
                    name = f'纹理·{mn}·{ck}'
                    yield bid, name, '纹理', '无', [{
                        'type': 'texture', 'mode': mode, 'cell_size': cs,
                        'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
                        'color': COLOR_SCHEMES[ck],
                        'audio': AUDIO_BE('value', [0, 1.0], 0.8),
                    }]


def gen_curve():
    """曲线"""
    presets = [
        ('cardioid', '心形线'),
        ('rose', '玫瑰线'),
        ('lemniscate', '双纽线'),
        ('flower', '花瓣'),
    ]
    layers_range = [1, 2, 3, 4]
    colors = ['warm', 'cool', 'sunset', 'neon', 'rainbow_slow', 'purple', 'candy', 'ocean']
    
    for pi, (preset, pn) in enumerate(presets):
        for ci, ck in enumerate(colors[:5]):
            for lc in layers_range:
                bid = f'curve_{preset}_{lc}l_{ck}'
                name = f'曲线·{pn}·{lc}层·{ck}'
                yield bid, name, '曲线', BG[pi % 4], [{
                    'type': 'curve', 'preset': preset,
                    'steps': 120, 'layers': lc, 'line_width': 2,
                    'center': {'x': '50%', 'y': '50%'},
                    'color': COLOR_SCHEMES[ck],
                    'audio': AUDIO_BE('value', [0, 1.0], 0.8),
                }]
    
    # 公式模式
    formulas = [
        ({'x': 'cos(t)*3', 'y': 'sin(t*2)', 't_min': 0, 't_max': 6.28, 't_step': 0.05}, '李萨如'),
        ({'x': '(1+cos(t))*cos(t)', 'y': '(1+cos(t))*sin(t)', 't_min': 0, 't_max': 6.28, 't_step': 0.05}, '心形参数'),
        ({'x': 'sin(t)*cos(t)*log(t+1)', 'y': 'cos(t)*sqrt(t+1)', 't_min': 0, 't_max': 10, 't_step': 0.05}, '对数螺线'),
    ]
    for fi, (fconfig, fn) in enumerate(formulas):
        for ck in ['warm', 'neon', 'rainbow_slow']:
            bid = f'curve_formula_{fn}_{ck}'
            name = f'公式曲线·{fn}·{ck}'
            yield bid, name, '曲线', BG[fi % 4], [{
                'type': 'curve', 'preset': 'formula', 'line_width': 2,
                'center': {'x': '50%', 'y': '50%'},
                'formula': fconfig,
                'color': COLOR_SCHEMES[ck],
                'audio': AUDIO_BE('value', [0, 1.0], 0.85),
            }]


def gen_cellular():
    """元胞自动机"""
    grids = [(32, 18), (48, 27), (64, 36), (80, 45), (96, 54)]
    intervals = [0.1, 0.15, 0.2, 0.3]
    colors = ['warm', 'cool', 'ocean', 'neon', 'green', 'rainbow_slow']
    
    for ci, ck in enumerate(colors):
        for gi, (cols, rows) in enumerate(grids):
            for inv in intervals[:3]:
                if (ci + gi) % 2 == 0:
                    bid = f'cellular_{cols}x{rows}_{ck}'
                    name = f'元胞·{cols}x{rows}·{ck}'
                    yield bid, name, '生命游戏', BG[0], [{
                        'type': 'cellular', 'cols': cols, 'rows': rows,
                        'rule': 'conway', 'audio_birth': True, 'update_interval': inv,
                        'color': COLOR_SCHEMES[ck],
                        'audio': AUDIO_BE('value', [0, 1.0], 0.8),
                    }]


def gen_pulse():
    """脉冲/涟漪"""
    modes = [
        ('ripple', '涟漪'),
        ('ring_pulse', '环形脉冲'),
        ('sonar', '声纳'),
        ('spectrum_ripples', '频谱涟漪'),
    ]
    triggers = [('audio', '音频'), ('random', '随机'), ('beat', '节拍')]
    speeds = [1.0, 2.0, 3.0, 5.0]
    colors = ['warm', 'cool', 'ocean', 'neon', 'rainbow_slow', 'sunset', 'purple', 'cyan']
    
    for mi, (mode, mn) in enumerate(modes):
        for ti, (trig, tn) in enumerate(triggers):
            for ci, ck in enumerate(colors[:5]):
                for sp in speeds[:3]:
                    if (mi + ti + ci) % 3 == 0:
                        bid = f'pulse_{mode}_{trig}_{ck}_s{sp}'
                        name = f'脉冲·{mn}·{tn}触发·{ck}'
                        yield bid, name, '涟漪', BG[mi % 4], [{
                            'type': 'pulse', 'mode': mode,
                            'center': {'x': '50%', 'y': '50%'},
                            'max_radius': 400, 'speed': sp, 'count': 1,
                            'trigger': trig, 'trigger_threshold': 0.3, 'line_width': 2,
                            'color': COLOR_SCHEMES[ck],
                            'audio': AUDIO_BE('value', [0, 1.0], 0.8),
                        }]


def gen_gauge():
    """仪表盘"""
    layouts = [
        ({'x': '50%', 'y': '55%'}, '居中'),
        ({'x': '30%', 'y': '55%'}, '偏左'),
        ({'x': '70%', 'y': '55%'}, '偏右'),
    ]
    radii = [150, 180, 220, 260]
    colors = ['warm', 'cool', 'neon', 'rainbow_slow', 'sunset']
    labels = ['dB', 'Hz', '%', 'VU', 'Lv', 'Peak']
    
    # 单表
    for ci, ck in enumerate(colors[:5]):
        for li, (center, ln) in enumerate(layouts):
            for r in radii[:3]:
                bid = f'gauge_{ln}_{r}_{ck}'
                name = f'仪表·{ln}·半径{r}·{ck}'
                yield bid, name, '仪表', '无', [{
                    'type': 'gauge', 'center': center, 'radius': r,
                    'arc': {'start': 210, 'end': 330}, 'arc_width': 8,
                    'segments': [
                        {'from': 0, 'to': 5, 'color': [30, 200, 80]},
                        {'from': 5, 'to': 7, 'color': [220, 200, 20]},
                        {'from': 7, 'to': 8, 'color': [220, 50, 30]},
                    ],
                    'ticks': {'step': 1, 'major_step': 2, 'length': 10,
                              'color': [180, 180, 200], 'major_color': [240, 240, 255], 'major_width': 2},
                    'needle': {'length_ratio': 0.78, 'width': 2, 'color': [255, 60, 20]},
                    'audio': AUDIO_RMS('value', [0, 1], 0.82),
                    'label': labels[li],
                }]
    
    # 双表盘
    for ck in ['warm', 'cool', 'neon']:
        for r in [180, 220]:
            bid = f'gauge_dual_{r}_{ck}'
            name = f'双仪表·半径{r}·{ck}'
            yield bid, name, '仪表', '无', [
                {
                    'type': 'gauge', 'center': {'x': '30%', 'y': '55%'}, 'radius': r,
                    'arc': {'start': 210, 'end': 330}, 'arc_width': 8,
                    'segments': [
                        {'from': 0, 'to': 5, 'color': [30, 200, 80]},
                        {'from': 5, 'to': 7, 'color': [220, 200, 20]},
                        {'from': 7, 'to': 8, 'color': [220, 50, 30]},
                    ],
                    'ticks': {'step': 1, 'major_step': 2, 'length': 10,
                              'color': [180, 180, 200], 'major_color': [240, 240, 255], 'major_width': 2},
                    'needle': {'length_ratio': 0.78, 'width': 2, 'color': [255, 60, 20]},
                    'audio': AUDIO_BE('value', [0, 1], 0.82), 'label': 'L',
                },
                {
                    'type': 'gauge', 'center': {'x': '70%', 'y': '55%'}, 'radius': r,
                    'arc': {'start': 210, 'end': 330}, 'arc_width': 8,
                    'segments': [
                        {'from': 0, 'to': 60, 'color': [30, 200, 80]},
                        {'from': 60, 'to': 90, 'color': [220, 200, 20]},
                        {'from': 90, 'to': 120, 'color': [220, 50, 30]},
                    ],
                    'ticks': {'step': 10, 'major_step': 20, 'length': 10,
                              'color': [180, 180, 200], 'major_color': [240, 240, 255], 'major_width': 2},
                    'needle': {'length_ratio': 0.78, 'width': 2, 'color': [255, 60, 20]},
                    'audio': AUDIO_RMS('value', [0, 1], 0.8), 'label': 'R',
                },
            ]


def gen_drawing():
    """自由绘制"""
    configs = [
        # 几何构图
        ('draw_3circles', '三圆', [{'shape': 'circle', 'x': '30%', 'y': '40%', 'radius': 60, 'color': None},
                                    {'shape': 'circle', 'x': '70%', 'y': '40%', 'radius': 60, 'color': None},
                                    {'shape': 'circle', 'x': '50%', 'y': '65%', 'radius': 60, 'color': None}]),
        ('draw_cross', '十字', [{'shape': 'line', 'x1': '50%', 'y1': '20%', 'x2': '50%', 'y2': '80%', 'width': 3, 'color': None},
                                 {'shape': 'line', 'x1': '20%', 'y1': '50%', 'x2': '80%', 'y2': '50%', 'width': 3, 'color': None}]),
        ('draw_diamond', '菱形', [{'shape': 'polygon', 'points': [['50%','20%'],['80%','50%'],['50%','80%'],['20%','50%']], 'color': None, 'fill': False}]),
        ('draw_rect_frame', '方框', [{'shape': 'rect', 'x1': '25%', 'y1': '25%', 'x2': '75%', 'y2': '75%', 'color': None, 'fill': False}]),
        ('draw_star5', '五角星', [{'shape': 'line', 'x1': '50%', 'y1': '15%', 'x2': '62%', 'y2': '47%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '62%', 'y1': '47%', 'x2': '98%', 'y2': '47%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '98%', 'y1': '47%', 'x2': '68%', 'y2': '65%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '68%', 'y1': '65%', 'x2': '80%', 'y2': '95%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '80%', 'y1': '95%', 'x2': '50%', 'y2': '77%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '50%', 'y1': '77%', 'x2': '20%', 'y2': '95%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '20%', 'y1': '95%', 'x2': '32%', 'y2': '65%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '32%', 'y1': '65%', 'x2': '2%', 'y2': '47%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '2%', 'y1': '47%', 'x2': '38%', 'y2': '47%', 'width': 2, 'color': None},
                                   {'shape': 'line', 'x1': '38%', 'y1': '47%', 'x2': '50%', 'y2': '15%', 'width': 2, 'color': None}]),
        ('draw_arcs', '弧线', [{'shape': 'arc', 'x': '35%', 'y': '50%', 'radius': 120, 'start': 0, 'end': 180, 'width': 3, 'color': None},
                                {'shape': 'arc', 'x': '65%', 'y': '50%', 'radius': 120, 'start': 180, 'end': 360, 'width': 3, 'color': None}]),
        ('draw_ellipses', '椭圆', [{'shape': 'ellipse', 'x1': '15%', 'y1': '30%', 'x2': '45%', 'y2': '70%', 'color': None, 'fill': False},
                                    {'shape': 'ellipse', 'x1': '55%', 'y1': '30%', 'x2': '85%', 'y2': '70%', 'color': None, 'fill': False}]),
        ('draw_eye', '眼睛', [{'shape': 'ellipse', 'x1': '20%', 'y1': '25%', 'x2': '50%', 'y2': '75%', 'color': None, 'fill': False},
                               {'shape': 'ellipse', 'x1': '50%', 'y1': '25%', 'x2': '80%', 'y2': '75%', 'color': None, 'fill': False},
                               {'shape': 'circle', 'x': '35%', 'y': '50%', 'radius': 15, 'color': None},
                               {'shape': 'circle', 'x': '65%', 'y': '50%', 'radius': 15, 'color': None}]),
        ('draw_triangle', '三角形', [{'shape': 'polygon', 'points': [['50%','15%'],['90%','85%'],['10%','85%']], 'color': None, 'fill': False}]),
        ('draw_hexagon', '六边形', [{'shape': 'polygon', 'points': [['50%','15%'],['80%','32%'],['80%','68%'],['50%','85%'],['20%','68%'],['20%','32%']], 'color': None, 'fill': False}]),
    ]
    colors = ['warm', 'cool', 'neon', 'rainbow_slow', 'sunset', 'purple', 'candy', 'ocean', 'cyan', 'gold']
    
    for di, (did, dn, commands) in enumerate(configs):
        for ci, ck in enumerate(colors[:6]):
            bid = f'{did}_{ck}'
            name = f'绘制·{dn}·{ck}'
            yield bid, name, '绘制', BG[di % 4], [{
                'type': 'drawing', 'commands': commands,
                'color': COLOR_SCHEMES[ck],
                'audio': AUDIO_BE('value', [0, 1.0], 0.8),
            }]


def gen_combos():
    """多层组合效果"""
    # 所有可能的 2-层组合
    primitives_2layer = [
        ('bars', 'spikes', '柱+尖峰'),
        ('bars', 'waveform', '柱+波形'),
        ('bars', 'vortex', '柱+漩涡'),
        ('bars', 'particles', '柱+粒子'),
        ('bars', 'circle_map', '柱+环'),
        ('spikes', 'waveform', '尖峰+波形'),
        ('spikes', 'vortex', '尖峰+漩涡'),
        ('spikes', 'particles', '尖峰+粒子'),
        ('spikes', 'circle_map', '尖峰+环'),
        ('spikes', 'pulse', '尖峰+脉冲'),
        ('vortex', 'particles', '漩涡+粒子'),
        ('vortex', 'waveform', '漩涡+波形'),
        ('vortex', 'circle_map', '漩涡+环'),
        ('vortex', 'pulse', '漩涡+脉冲'),
        ('waveform', 'particles', '波形+粒子'),
        ('waveform', 'circle_map', '波形+环'),
        ('waveform', 'grid', '波形+网格'),
        ('particles', 'grid', '粒子+网格'),
        ('particles', 'circle_map', '粒子+环'),
        ('particles', 'pulse', '粒子+脉冲'),
        ('particles', 'text_rain', '粒子+雨'),
        ('circle_map', 'pulse', '环+脉冲'),
        ('circle_map', 'texture', '环+纹理'),
        ('bars', 'text_rain', '柱+雨'),
        ('bars', 'grid', '柱+网格'),
        ('spikes', 'grid', '尖峰+网格'),
        ('vortex', 'grid', '漩涡+网格'),
        ('waveform', 'text_rain', '波形+雨'),
        ('circle_map', 'grid', '环+网格'),
        ('particles', 'texture', '粒子+纹理'),
    ]
    
    colors = ['warm', 'cool', 'neon', 'rainbow_slow', 'sunset', 'ocean']
    
    for (a, b, cn) in primitives_2layer:
        for ci, ck in enumerate(colors[:4]):
            bid = f'combo_{a}_{b}_{ck}'
            name = f'组合·{cn}·{ck}'
            
            # 构建两层配置
            lb = _make_layer(a, ck, 0)
            l2 = _make_layer(b, ck, 1)
            # 调整位置避免重叠
            _adjust_combo_layers(a, b, lb, l2)
            layers = [lb, l2]
            
            yield bid, name, '组合', BG[ci % 4], layers
    
    # 3层组合
    combos_3layer = [
        (['bars', 'spikes', 'particles'], '柱+尖峰+粒子'),
        (['bars', 'vortex', 'particles'], '柱+漩涡+粒子'),
        (['spikes', 'vortex', 'particles'], '尖峰+漩涡+粒子'),
        (['bars', 'spikes', 'circle_map'], '柱+尖峰+环'),
        (['spikes', 'circle_map', 'particles'], '尖峰+环+粒子'),
        (['bars', 'waveform', 'particles'], '柱+波形+粒子'),
        (['vortex', 'circle_map', 'particles'], '漩涡+环+粒子'),
        (['bars', 'circle_map', 'pulse'], '柱+环+脉冲'),
        (['spikes', 'pulse', 'particles'], '尖峰+脉冲+粒子'),
        (['vortex', 'pulse', 'particles'], '漩涡+脉冲+粒子'),
        (['bars', 'spikes', 'grid'], '柱+尖峰+网格'),
        (['vortex', 'particles', 'grid'], '漩涡+粒子+网格'),
        (['bars', 'circle_map', 'text_rain'], '柱+环+雨'),
        (['particles', 'circle_map', 'texture'], '粒子+环+纹理'),
        (['spikes', 'waveform', 'circle_map'], '尖峰+波形+环'),
    ]
    
    for (prims, cn) in combos_3layer:
        for ci, ck in enumerate(colors[:3]):
            bid = f'combo3_{prims[0]}_{prims[1]}_{prims[2]}_{ck}'
            name = f'三重组合·{cn}·{ck}'
            layers = []
            for pi, pt in enumerate(prims):
                l = _make_layer(pt, ck, pi)
                layers.append(l)
            _adjust_combo_layers_multi(layers)
            yield bid, name, '组合', BG[ci % 4], layers


def _make_layer(ptype, ck, idx):
    """创建一个原语 layer 配置"""
    c = COLOR_SCHEMES[ck]
    if ptype == 'bars':
        return {
            'type': 'bars', 'count': 32, 'direction': 'up',
            'position': {'x': 0, 'y': '100%'}, 'size': {'width': '100%', 'height': '40%'},
            'gap': 2, 'color': c,
            'audio': AUDIO_BE('height', [0.02, 0.8], 0.9),
        }
    elif ptype == 'spikes':
        return {
            'type': 'spikes', 'count': 48,
            'center': {'x': '50%', 'y': '45%'}, 'inner_radius': 60, 'outer_radius': 240,
            'line_width': 2, 'rotation_speed': 0.3,
            'color': c, 'audio': AUDIO_BE('length', [0, 1.0], 0.85),
        }
    elif ptype == 'vortex':
        return {
            'type': 'vortex', 'count': 150,
            'center': {'x': '50%', 'y': '50%'}, 'radius': {'min': 40, 'step': 4},
            'twist': 1.5, 'speed': 0.8, 'element_size': 2, 'size_scale': 3.0,
            'color': c, 'audio': AUDIO_BE('radius_scale', [1.0, 1.3], 0.8),
        }
    elif ptype == 'waveform':
        return {
            'type': 'waveform', 'lines': 2, 'points': 150, 'amplitude': 100,
            'frequency': 0.04, 'line_width': 2,
            'position': {'x': 0, 'y': '50%'}, 'size': {'width': '100%', 'height': '50%'},
            'color': c, 'audio': AUDIO_BE('y', [0.0, 1.0], 0.85),
        }
    elif ptype == 'particles':
        return {
            'type': 'particles', 'count': 80,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'particle': {'size': {'min': 2, 'max': 6}, 'speed': {'min': 15, 'max': 60},
                        'lifetime': {'min': 3, 'max': 7}, 'behavior': 'drift'},
            'connect': {'enabled': True, 'max_distance': 100, 'line_width': 1},
            'color': c, 'audio': AUDIO_BE('particle_size', [0.5, 2.5], 0.8),
        }
    elif ptype == 'circle_map':
        return {
            'type': 'circle_map', 'center': {'x': '50%', 'y': '50%'},
            'rings': [{'count': 48, 'radius': 100, 'line': True, 'line_width': 2}],
            'color': c, 'audio': AUDIO_BE('radius_offset', [0, 40], 0.85),
        }
    elif ptype == 'grid':
        return {
            'type': 'grid', 'cols': 20, 'rows': 12, 'element': 'circle', 'element_ratio': 0.5,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'color': c, 'audio': AUDIO_BE('scale', [0.1, 1.5], 0.7),
        }
    elif ptype == 'pulse':
        return {
            'type': 'pulse', 'mode': 'ripple', 'center': {'x': '50%', 'y': '50%'},
            'max_radius': 350, 'speed': 2.0, 'count': 1,
            'trigger': 'audio', 'trigger_threshold': 0.25, 'line_width': 2,
            'color': c, 'audio': AUDIO_BE('value', [0, 1.0], 0.8),
        }
    elif ptype == 'text_rain':
        return {
            'type': 'text_rain', 'chars': '01アイウエオ', 'count': 40, 'font_size': 14,
            'speed': {'min': 50, 'max': 120}, 'trail_length': 6,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'color': c, 'audio': AUDIO_BE('brightness', [0.2, 0.8], 0.85),
        }
    elif ptype == 'texture':
        return {
            'type': 'texture', 'mode': 'plasma', 'cell_size': 6,
            'position': {'x': 0, 'y': 0}, 'size': {'width': '100%', 'height': '100%'},
            'color': c, 'audio': AUDIO_BE('value', [0, 1.0], 0.8),
        }
    return {}


def _adjust_combo_layers(a, b, la, lb):
    """调整两层组合中的位置，避免重叠"""
    if a == 'bars':
        la['size']['height'] = '35%'
    if b == 'bars':
        lb['size']['height'] = '35%'
    if a == 'spikes':
        la['center'] = {'x': '35%', 'y': '45%'}
        la['outer_radius'] = 200
    if b == 'spikes' and a == 'bars':
        lb['center'] = {'x': '65%', 'y': '45%'}
        lb['outer_radius'] = 200
    if a == 'vortex' and b != 'vortex':
        la['center'] = {'x': '35%', 'y': '50%'}
    if b == 'vortex' and a != 'vortex':
        lb['center'] = {'x': '65%', 'y': '50%'}


def _adjust_combo_layers_multi(layers):
    """调整多层组合"""
    for i, l in enumerate(layers):
        t = l.get('type', '')
        l['color'] = COLOR_SCHEMES[['warm', 'cool', 'neon'][i % 3]]
        if t == 'bars':
            l['size'] = l.get('size', {})
            l['size']['height'] = '30%'
        elif t == 'spikes':
            l['outer_radius'] = 160
        elif t == 'vortex':
            l['count'] = 100
            l['size_scale'] = 2.5
        elif t == 'particles':
            l['count'] = 60


# ============================================================
# 工具函数
# ============================================================

def get_next_number(effects_dir):
    max_n = 0
    for path in glob.glob(os.path.join(effects_dir, '*_*.json')):
        m = re.match(r'(\d+)_', os.path.basename(path))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def make_effect(number, eff_id, name, category, bg, layers):
    return {
        'id': eff_id,
        'name': name,
        'full_name': f'{number:03d}. {name}',
        'category': category,
        'background_theme': bg,
        'class': 'EngineEffect',
        'params': {'layers': layers},
    }


def write_effect(effect, number, eff_id, dry=False):
    filename = f'{number:03d}_{eff_id}.json'
    filepath = os.path.join(OUT, filename)
    if not dry:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(effect, f, ensure_ascii=False, indent=2)
    return filepath


# ============================================================
# 种子效果管理
# ============================================================

SEEDS_DIR = os.path.join(OUT, 'seeds')
SEED_MAX_NUMBER = 146  # 1-146 为手工制作效果，不可自动生成


def _collect_all_effects():
    """收集所有生成器的效果（去重后返回列表）"""
    generators = [
        gen_bars, gen_spikes, gen_waveform, gen_vortex,
        gen_circle_map, gen_particles, gen_grid, gen_text_rain,
        gen_wireframe_3d, gen_texture, gen_curve, gen_cellular,
        gen_pulse, gen_gauge, gen_drawing, gen_combos,
    ]
    all_effects = []
    seen_ids = set()

    for gen in generators:
        for eff_id, name, cat, bg, layers in gen():
            if len(eff_id) > 80:
                eff_id = eff_id[:80]
            base_id = eff_id
            counter = 1
            while eff_id in seen_ids:
                eff_id = f'{base_id}_{counter}'
                counter += 1
            seen_ids.add(eff_id)
            all_effects.append((eff_id, name, cat, bg, layers))

    return all_effects


def _save_seeds():
    """将当前手工效果 (1-146) 保存到 seeds/ 目录"""
    os.makedirs(SEEDS_DIR, exist_ok=True)
    saved = 0
    for f in sorted(glob.glob(os.path.join(OUT, '*_*.json'))):
        m = re.match(r'(\d+)_', os.path.basename(f))
        if m and int(m.group(1)) <= SEED_MAX_NUMBER:
            import shutil as _shutil
            dest = os.path.join(SEEDS_DIR, os.path.basename(f))
            _shutil.copy2(f, dest)
            saved += 1
    return saved


def _restore_seeds():
    """从 seeds/ 恢复手工效果"""
    if not os.path.isdir(SEEDS_DIR):
        return 0
    import shutil as _shutil
    restored = 0
    for sf in sorted(glob.glob(os.path.join(SEEDS_DIR, '*_*.json'))):
        dest = os.path.join(OUT, os.path.basename(sf))
        _shutil.copy2(sf, dest)
        restored += 1
    return restored


def _clear_generated():
    """清除所有效果文件（保留 seeds/ 目录）"""
    removed = 0
    for f in glob.glob(os.path.join(OUT, '*_*.json')):
        os.remove(f)
        removed += 1
    return removed


# ============================================================
# 主流程
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='批量效果生成器 — 参数化生成 4300+ 引擎效果 JSON',
        epilog='示例:\n'
               '  python generate_bulk.py --count          # 预览数量\n'
               '  python generate_bulk.py --dry            # 预览不写入\n'
               '  python generate_bulk.py                  # 追加生成（默认）\n'
               '  python generate_bulk.py --regenerate     # 清空后从种子重建全部\n'
               '  python generate_bulk.py --save-seeds     # 仅保存种子文件\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry', action='store_true',
                       help='仅预览，不写入文件')
    parser.add_argument('--count', action='store_true',
                       help='仅显示数量')
    parser.add_argument('--start', type=int, default=None,
                       help='起始编号（默认自动检测下一个可用编号）')
    parser.add_argument('--regenerate', action='store_true',
                       help='清空全部效果 → 恢复种子(1-146) → 重新生成147+')
    parser.add_argument('--save-seeds', action='store_true',
                       help='仅将当前手工效果保存到 seeds/ 目录')
    args = parser.parse_args()

    # --save-seeds
    if args.save_seeds:
        n = _save_seeds()
        print(f'已保存 {n} 个种子效果到 {SEEDS_DIR}/')
        return

    # --regenerate: 清空 + 恢复种子 + 重新生成
    if args.regenerate:
        # 1) 自动保存种子（如果 seeds/ 不存在或为空）
        seed_count = len(glob.glob(os.path.join(SEEDS_DIR, '*_*.json')))
        if seed_count == 0:
            n = _save_seeds()
            print(f'[SEED] 已保存 {n} 个种子效果')
        else:
            print(f'[SEED] 已有 {seed_count} 个种子效果')

        # 2) 清空
        removed = _clear_generated()
        print(f'[CLEAR] 已清理 {removed} 个旧效果')

        # 3) 恢复种子
        restored = _restore_seeds()
        print(f'[RESTORE] 已恢复 {restored} 个种子效果 (1-{SEED_MAX_NUMBER})')

        # 4) 自动起始编号
        args.start = get_next_number(OUT)
        print(f'[START] 批量效果起始编号: {args.start}')
        print()

    # 收集所有效果
    all_effects = _collect_all_effects()

    # --count
    if args.count:
        start_num = args.start if args.start else get_next_number(OUT)
        print(f'将生成 {len(all_effects)} 个新效果')
        print(f'编号范围: {start_num:04d} ~ {start_num + len(all_effects) - 1:04d}')
        if os.path.isdir(SEEDS_DIR):
            n_seeds = len(glob.glob(os.path.join(SEEDS_DIR, '*_*.json')))
            print(f'种子效果: {n_seeds} 个')
            print(f'合计: {n_seeds + len(all_effects)} 个效果')
        return

    number = args.start if args.start else get_next_number(OUT)

    # --regenerate 模式：需要多次生成循环才能填满 147-4486
    if args.regenerate:
        TARGET = 4486
        passes = 0
        total_generated = 0
        while number <= TARGET:
            passes += 1
            all_effects = _collect_all_effects()
            if not all_effects:
                break
            batch_start = number
            print(f'[PASS {passes}] 起始编号: {number}, 共 {len(all_effects)} 个效果')
            for eff_id, name, cat, bg, layers in all_effects:
                effect = make_effect(number, eff_id, name, cat, bg, layers)
                path = write_effect(effect, number, eff_id, dry=args.dry)
                if number % 500 == 0:
                    print(f'  进度: {number} ({path})')
                number += 1
            batch_end = number - 1
            total_generated += len(all_effects)
            print(f'[PASS {passes}] 完成: {batch_start}-{batch_end} ({len(all_effects)} 个)')
            print()
        print(f'全部完成! {passes} 轮共生成 {total_generated} 个效果 ({args.start if args.start else SEED_MAX_NUMBER + 1}-{number - 1})')
    else:
        print(f'起始编号: {number}')
        print(f'共 {len(all_effects)} 个效果待生成')

        for eff_id, name, cat, bg, layers in all_effects:
            effect = make_effect(number, eff_id, name, cat, bg, layers)
            path = write_effect(effect, number, eff_id, dry=args.dry)
            if number % 100 == 0:
                print(f'  进度: {number} ({path})')
            number += 1

        print(f'\n{"[DRY RUN] " if args.dry else ""}完成! 生成了 {len(all_effects)} 个效果')


if __name__ == '__main__':
    main()
