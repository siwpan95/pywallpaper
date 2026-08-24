"""
渲染系统 - 总控层，仅负责逻辑调度

效果已全面引擎化：所有效果由 effects/*.json 配置驱动，class: "EngineEffect"。
添加新效果只需创建 JSON，无需修改 Python 代码。

详见 engine/README.md
"""
import math
import random
import json
import os
import glob
import re

from PIL import ImageDraw, ImageFont
from utils.helpers import hsv_to_rgb, get_energy_color


# ==================== 装饰器（主题保留） ====================
_THEME_META = {}


def register_theme(theme_id, name, description=""):
    def decorator(cls):
        _THEME_META[cls.__name__] = {"id": theme_id, "name": name, "description": description}
        return cls
    return decorator


def get_theme_meta() -> dict:
    return dict(_THEME_META)


# ==================== 背景主题 ====================
class BackgroundTheme:
    def __init__(self, drawer: ImageDraw.ImageDraw, width: int, height: int):
        self.drawer = drawer
        self.width = width
        self.height = height
        self.time = 0.0

    def update(self, dt: float):
        self.time += dt

    def draw(self):
        self.drawer.rectangle([0, 0, self.width, self.height], fill=(192, 192, 192))


@register_theme("starfield", "星空", "星空飘移背景")
class StarFieldTheme(BackgroundTheme):
    def __init__(self, drawer, width, height):
        super().__init__(drawer, width, height)
        self.stars = [{
            'x': random.randint(0, width), 'y': random.randint(0, height),
            'size': random.uniform(0.5, 2), 'speed': random.uniform(0.1, 0.5),
            'brightness': random.uniform(0.3, 1.0)
        } for _ in range(200)]

    def update(self, dt):
        super().update(dt)
        for s in self.stars:
            s['y'] = (s['y'] + s['speed']) % self.height

    def draw(self):
        for s in self.stars:
            twinkle = (math.sin(self.time * 3 + s['x']) + 1) / 2
            brightness = int(s['brightness'] * twinkle * 255)
            color = (brightness, brightness, min(brightness + 50, 255))
            sz = s['size']
            self.drawer.ellipse([s['x'] - sz, s['y'] - sz, s['x'] + sz, s['y'] + sz], fill=color)


@register_theme("gradient", "渐变", "渐变流动背景")
class GradientTheme(BackgroundTheme):
    def __init__(self, drawer, width, height):
        super().__init__(drawer, width, height)
        self.hue_offset = 0

    def update(self, dt):
        super().update(dt)
        self.hue_offset = (self.time * 0.02) % 1.0

    def draw(self):
        for y in range(0, self.height, 4):
            hue = (self.hue_offset + y / self.height * 0.3) % 1.0
            color = hsv_to_rgb(hue, 0.3, 0.05)
            self.drawer.rectangle([0, y, self.width, min(y + 4, self.height)], fill=color)


@register_theme("aurora", "极光", "极光效果背景")
class AuroraTheme(BackgroundTheme):
    def __init__(self, drawer, width, height):
        super().__init__(drawer, width, height)
        self.waves = [{
            'phase': random.uniform(0, math.pi * 2),
            'amplitude': random.uniform(20, 50),
            'frequency': random.uniform(0.005, 0.02),
            'speed': random.uniform(0.2, 0.5),
            'hue': random.uniform(0.3, 0.7)
        } for _ in range(5)]

    def update(self, dt):
        super().update(dt)
        for w in self.waves:
            w['phase'] += dt * w['speed']

    def draw(self):
        for w in self.waves:
            for x in range(0, self.width, 3):
                y = self.height * 0.5 + math.sin(x * w['frequency'] + w['phase']) * w['amplitude']
                alpha = 0.15 + 0.1 * math.sin(x * 0.01 + w['phase'])
                color = hsv_to_rgb(w['hue'], 0.6, alpha)
                self.drawer.rectangle([x, y - 20, x + 3, y], fill=color)


@register_theme("empty", "无", "微光呼吸背景")
class EmptyTheme(BackgroundTheme):
    def draw(self):
        cx, cy = self.width / 2, self.height / 2
        max_r = min(self.width, self.height) * 0.45
        breath = 0.3 + 0.15 * math.sin(self.time * 0.6)
        for layer in range(12, 0, -1):
            r = max_r * layer / 12
            alpha = breath * 0.04 * (1.0 - layer / 14)
            hue = (0.6 + self.time * 0.01) % 1.0
            color = hsv_to_rgb(hue, 0.05, alpha)
            self.drawer.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


# ==================== 注册表 ====================
BACKGROUND_THEMES = {}
EFFECT_REGISTRY = {}


# ==================== 效果加载器 ====================

def _build_theme_map() -> dict:
    return {cls.__name__: cls for cls in BackgroundTheme.__subclasses__()}


def load_effects(effects_dir: str = None) -> dict:
    """从 effects/ 目录加载全部效果配置

    所有效果均使用 class: "EngineEffect"，存储为 (config_dict,) 单元素组。
    """
    global EFFECT_REGISTRY
    if effects_dir is None:
        effects_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'effects')

    EFFECT_REGISTRY.clear()

    pattern = os.path.join(effects_dir, '*_*.json')
    json_files = sorted(
        glob.glob(pattern),
        key=lambda f: int(re.match(r'(\d+)_', os.path.basename(f)).group(1))
    )

    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[LOAD] 跳过 {os.path.basename(jf)}: {e}")
            continue

        full_name = data.get('full_name', data.get('name', ''))
        if full_name:
            EFFECT_REGISTRY[full_name] = (data,)

    print(f"[LOAD] 从 effects/ 加载了 {len(EFFECT_REGISTRY)} 个引擎效果")
    return EFFECT_REGISTRY


def load_background_themes(themes_path: str = None) -> dict:
    """从 effects/themes.json 加载背景主题"""
    global BACKGROUND_THEMES
    if themes_path is None:
        themes_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'effects', 'themes.json')

    theme_class_map = _build_theme_map()

    try:
        with open(themes_path, 'r', encoding='utf-8') as f:
            themes_list = json.load(f)
    except Exception as e:
        print(f"[LOAD] 加载主题 JSON 失败: {e}")
        themes = {}
        for cls_name, cls in theme_class_map.items():
            meta = _THEME_META.get(cls_name, {})
            themes[meta.get('name', cls_name)] = cls
        BACKGROUND_THEMES.clear()
        BACKGROUND_THEMES.update(themes)
        return BACKGROUND_THEMES

    themes = {}
    for t in themes_list:
        cls_name = t.get('class')
        name = t.get('name', '')
        if cls_name is None:
            themes[name] = None
        else:
            themes[name] = theme_class_map.get(cls_name, None)

    BACKGROUND_THEMES.clear()
    BACKGROUND_THEMES.update(themes)
    print(f"[LOAD] 从 themes.json 加载了 {len(themes)} 个背景主题 "
          f"(Python 共注册 {len(theme_class_map)} 个主题类)")
    return themes


def _auto_load():
    if not EFFECT_REGISTRY:
        try:
            load_effects()
            load_background_themes()
        except Exception as e:
            print(f"[LOAD] 自动加载失败: {e}")

_auto_load()
