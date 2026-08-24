"""
径向尖峰原语 — 从中心点向四周发射的尖峰线

类似音频可视化中的圆形频谱图
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('spikes')
class SpikesPrimitive(RenderPrimitive):
    """径向尖峰

    配置:
        count: int             尖峰数量 (默认 64)
        inner_radius: float    内半径 (默认 30)
        outer_radius: float    外半径/最大长度 (默认 300)
        line_width: int        线宽 (默认 3)
        rotation_speed: float  自转速度 (默认 0)
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.count = config.get('count', 64)
        max_r = self._max_safe_radius
        self.inner_r = min(config.get('inner_radius', 30), max_r * 0.5)
        self.outer_r = min(config.get('outer_radius', 300), max_r)
        self.line_width = config.get('line_width', 3)
        self.rot_speed = config.get('rotation_speed', 0.0)
        self._rot = 0.0

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        self._rot += self.rot_speed * dt

    def draw(self, drawer: ImageDraw.ImageDraw):
        n = self.count
        for i in range(n):
            angle = (i / n) * math.pi * 2 + self._rot
            energy = self._get_audio_value('length', i, default=0.0)
            length = self.inner_r + energy * self.outer_r
            x1 = self.cx + math.cos(angle) * self.inner_r
            y1 = self.cy + math.sin(angle) * self.inner_r
            x2 = self.cx + math.cos(angle) * length
            y2 = self.cy + math.sin(angle) * length
            color = self._get_color(i, n, energy)
            x1, y1 = self._rotated_point(x1, y1)
            x2, y2 = self._rotated_point(x2, y2)
            drawer.line([x1, y1, x2, y2], fill=color, width=self.line_width)
