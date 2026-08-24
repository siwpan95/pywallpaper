"""
效果管理器 - 效果切换、过渡、背景主题管理
EFFECT_REGISTRY 的值为 (EffectClass, params_dict) 元组或 (engine_config,) 单元素组。
"""
import random
import time
from typing import Optional, Tuple

from PIL import Image, ImageDraw


def _make_effect(entry, draw, width, height, audio):
    """统一实例化入口

    支持三种格式:
      1. EffectClass                              → cls(draw, w, h, audio)
      2. (EffectClass, params_dict)               → cls(draw, w, h, audio, params=params)
      3. (engine_config_dict,)                    → EngineEffect(draw, w, h, audio, config)
    """
    if isinstance(entry, tuple):
        first = entry[0]
        if isinstance(first, dict):
            # 引擎效果: (engine_config,) — 必须有 class 或 primitive 字段
            if first.get('class') or first.get('primitive'):
                from engine.effect_loader import create_effect
                return create_effect(first, draw, width, height, audio)
            # 无法识别的 dict 配置
            name = first.get('full_name', first.get('name', '?'))
            raise ValueError(
                f"效果 '{name}' 配置缺少 'class' 或 'primitive' 字段，无法实例化"
            )
        # 旧格式: (EffectClass, params)
        cls, params = entry[0], entry[1] if len(entry) > 1 else {}
        return cls(draw, width, height, audio, params=params)
    else:
        # 旧格式: EffectClass
        cls = entry
        return cls(draw, width, height, audio)


class EffectManager:
    """管理效果切换和过渡"""

    def __init__(self, effect_registry: dict, config: dict):
        self.effect_registry = effect_registry
        self.effect_names = list(effect_registry.keys())
        self.config = config

        # 当前状态
        self.current_idx = 0
        self.current_name = self.effect_names[0]

        # 背景主题
        bg_themes = config['wallpaper']['background_themes']
        self.bg_theme_names = bg_themes
        self.current_bg_name = config['wallpaper']['default_bg_theme']
        self.bg_default_color = tuple(config['wallpaper']['background_default_color'])

        # 自动切换
        es = config['effect_switch']
        self.auto_switch = es['enabled']
        self.switch_interval_min = es['interval_min']
        self.switch_interval_max = es['interval_max']
        self.switch_interval = random.uniform(self.switch_interval_min, self.switch_interval_max)
        self.last_switch_time = time.time()

        # 平滑过渡
        self.transition_duration = es['transition_duration']
        self.is_transitioning = False
        self.transition_start = 0.0
        self.transition_progress = 0.0
        self.prev_effect_name: Optional[str] = None
        self.next_effect_name: Optional[str] = None

    def update(self):
        """检查是否需要切换效果"""
        now = time.time()
        if self.auto_switch and not self.is_transitioning:
            if now - self.last_switch_time > self.switch_interval:
                self._start_transition()

        if self.is_transitioning:
            elapsed = now - self.transition_start
            self.transition_progress = min(elapsed / self.transition_duration, 1.0)
            if self.transition_progress >= 1.0:
                self._finish_transition()

    def _start_transition(self):
        self.prev_effect_name = self.current_name
        self.current_idx = (self.current_idx + 1) % len(self.effect_names)
        self.next_effect_name = self.effect_names[self.current_idx]
        self.is_transitioning = True
        self.transition_start = time.time()
        self.transition_progress = 0.0
        self.last_switch_time = time.time()
        self.switch_interval = random.uniform(self.switch_interval_min, self.switch_interval_max)
        print(f"过渡效果: {self.prev_effect_name} -> {self.next_effect_name}")

    def _finish_transition(self):
        self.is_transitioning = False
        self.current_name = self.next_effect_name
        assert self.current_name is not None
        self.prev_effect_name = None

    def get_current_effect_name(self) -> str:
        return self.next_effect_name if self.is_transitioning else self.current_name

    def get_current_effect_entry(self):
        """返回 (EffectClass, params_dict) 元组"""
        name = self.get_current_effect_name()
        return self.effect_registry.get(name)

    # 向后兼容：旧代码调用 get_current_effect_class() 只取类
    def get_current_effect_class(self):
        entry = self.get_current_effect_entry()
        if entry is None:
            return None
        return entry[0] if isinstance(entry, tuple) else entry

    def get_prev_effect_class(self):
        if self.is_transitioning and self.prev_effect_name:
            entry = self.effect_registry.get(self.prev_effect_name)
            if entry is None:
                return None
            return entry[0] if isinstance(entry, tuple) else entry
        return None

    def render_with_transition(self, draw: ImageDraw.ImageDraw, width: int, height: int,
                                audio, dt: float) -> Optional[Image.Image]:
        """
        处理过渡渲染。如果需要过渡，返回一个 overlay Image（新效果渲染在其上）；
        否则返回 None（表示正常渲染）。
        """
        if not self.is_transitioning:
            return None

        # 创建 overlay 图像
        overlay = Image.new('RGB', (width, height), self.bg_default_color)
        overlay_draw = ImageDraw.Draw(overlay)

        # 渲染新效果到 overlay（携带 params）
        entry = self.effect_registry.get(self.next_effect_name)
        if entry:
            effect = _make_effect(entry, overlay_draw, width, height, audio)
            effect.update(dt)
            effect.draw()
            return overlay

        return None
