"""
圆形映射原语 — 沿圆形排列的元素/环

支持多环、连线模式
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('circle_map')
class CircleMapPrimitive(RenderPrimitive):
    """圆形映射 — 沿圆排列元素

    配置:
        rings: list          环配置列表
            - count: int          每环元素数
            - radius: float       半径
            - line: bool          是否连线 (默认 False)
            - line_width: int     线宽 (默认 2)
            - fill: bool          是否填充
        element_size: float   元素大小 (默认 4)
        rotation_speed: float 旋转速度 (默认 0)
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.rings = config.get('rings', [])
        if not self.rings:
            # 默认单环
            self.rings = [{'count': config.get('count', 72),
                           'radius': min(config.get('radius', 150), self._max_safe_radius),
                           'line': True}]
        self.elem_size = config.get('element_size', 4)
        self.rot_speed = config.get('rotation_speed', 0.0)
        self._rot = 0.0

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        self._rot += self.rot_speed * dt

    def draw(self, drawer: ImageDraw.ImageDraw):
        ring_colors = [self._get_color(ri, len(self.rings), 0) for ri in range(len(self.rings))]

        for ri, ring in enumerate(self.rings):
            count = ring.get('count', 72)
            radius = min(ring.get('radius', 150), self._max_safe_radius)
            line = ring.get('line', False)
            lw = ring.get('line_width', 2)
            do_fill = ring.get('fill', False)
            color = ring_colors[ri]

            pts = []
            for i in range(count):
                angle = (i / count) * math.pi * 2 + self._rot
                energy = self._get_audio_value('radius_offset', int(i * 64 / count), default=0.0)
                r = radius + energy * self._get_audio_value('radius_offset', i, default=0.0) * 40
                if not line:
                    r = radius + energy * 40
                x = self.cx + math.cos(angle) * r
                y = self.cy + math.sin(angle) * r
                pts.append((x, y))

                if not line:
                    elem_color = self._get_color(i, count, energy)
                    sz = self.elem_size + energy * 3
                    drawer.ellipse([x - sz, y - sz, x + sz, y + sz], fill=elem_color)

            if line:
                for pi in range(len(pts)):
                    p1, p2 = pts[pi], pts[(pi + 1) % count]
                    drawer.line([p1, p2], fill=color, width=lw)
