"""
漩涡原语 — 螺旋/漩涡粒子效果
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('vortex')
class VortexPrimitive(RenderPrimitive):
    """漩涡/螺旋粒子

    配置:
        count: int            粒子数量 (默认 150)
        radius_min: float     最小半径 (默认 50)
        radius_step: float    半径步进 (默认 5)
        twist: float          扭曲度 (默认 1.0)
        speed: float          旋转速度 (默认 1.0)
        element_size: float   粒子大小 (默认 3)
        size_scale: float     粒子大小缩放 (默认 5.0)
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.count = config.get('count', 150)
        max_r = self._max_safe_radius
        rad_cfg = config.get('radius', {})
        if isinstance(rad_cfg, dict):
            self.r_min = min(rad_cfg.get('min', 50), max_r * 0.5)
            self.r_step = min(rad_cfg.get('step', 5), max_r / 60)
        else:
            self.r_min = min(50, max_r * 0.5)
            self.r_step = min(config.get('radius_step', 5), max_r / 60)
        self.twist = config.get('twist', 1.0)
        self.speed = config.get('speed', 1.0)
        self.elem_size = config.get('element_size', 3)
        self.size_scale = config.get('size_scale', 5.0)

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def draw(self, drawer: ImageDraw.ImageDraw):
        n = self.count
        for i in range(n):
            angle = (i / n) * math.pi * 2 * self.twist + self._time * self.speed
            r = self.r_min + (i % 32) * self.r_step + math.sin(self._time * 2 + i) * 20
            energy = self._get_audio_value('radius_scale', i, default=1.0)
            r *= (1.0 + energy * 0.5)
            x = self.cx + math.cos(angle) * r
            y = self.cy + math.sin(angle) * r
            color = self._get_color(i, n, energy)
            sz = self.elem_size + energy * self.size_scale
            x, y = self._rotated_point(x, y)
            drawer.ellipse([x - sz, y - sz, x + sz, y + sz], fill=color)
