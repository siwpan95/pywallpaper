"""
频谱柱状图原语 — 将 FFT 频段能量映射为柱状图

方向: up/down/left/right/center（从中心向两侧展开）
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('bars')
class BarsPrimitive(RenderPrimitive):
    """频谱柱状图

    配置:
        count: int          柱数 (默认 64)
        direction: str      方向 up/down/left/right/center_h/center_v (默认 up)
        gap: int            柱间距 (默认 2)
        round_caps: bool    圆角 (默认 False)
        mirror: bool        镜像模式（上下对称，从中心线出发）
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.count = config.get('count', 64)
        self.direction = config.get('direction', 'up')
        self.gap = config.get('gap', 2)
        self.round_caps = config.get('round_caps', False)
        self.mirror = config.get('mirror', False)

        # 修复位置超出屏幕的问题：确保所有方向的柱状图区域都在屏幕内
        if self.direction in ('up', 'center_v', 'down') and self.y + self.h > height:
            self.y = max(0, height - self.h)
        if self.direction in ('right', 'center_h') and self.x + self.w > width:
            self.x = max(0, width - self.w)
        if self.direction == 'left':
            self.y = max(0, min(self.y, height - self.h))

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def draw(self, drawer: ImageDraw.ImageDraw):
        n = self.count
        if self.direction in ('up', 'down', 'center_v'):
            bar_w = max(1, self.w / n - self.gap)
            for i in range(n):
                energy = self._get_audio_value('height', i, default=0.0)
                h_val = energy * self.h
                color = self._get_color(i, n, energy)

                if self.direction == 'up':
                    x0 = self.x + i * (bar_w + self.gap)
                    self._draw_bar(drawer, x0, self.y + self.h - h_val,
                                   bar_w, h_val, color)
                elif self.direction == 'down':
                    x0 = self.x + i * (bar_w + self.gap)
                    self._draw_bar(drawer, x0, self.y, bar_w, h_val, color)
                elif self.direction == 'center_v':
                    half_h = h_val / 2
                    x0 = self.x + i * (bar_w + self.gap)
                    mid_y = self.y + self.h / 2
                    self._draw_bar(drawer, x0, mid_y - half_h, bar_w, half_h, color)
                    self._draw_bar(drawer, x0, mid_y, bar_w, half_h, color)
        else:
            bar_h = max(1, self.h / n - self.gap)
            for i in range(n):
                energy = self._get_audio_value('width', i, default=0.0)
                w_val = energy * self.w
                color = self._get_color(i, n, energy)

                if self.direction == 'right':
                    y0 = self.y + i * (bar_h + self.gap)
                    self._draw_hbar(drawer, self.x, y0, w_val, bar_h, color)
                elif self.direction == 'left':
                    y0 = self.y + i * (bar_h + self.gap)
                    self._draw_hbar(drawer, self.x + self.w - w_val, y0, w_val, bar_h, color)
                elif self.direction == 'center_h':
                    half_w = w_val / 2
                    y0 = self.y + i * (bar_h + self.gap)
                    mid_x = self.x + self.w / 2
                    self._draw_hbar(drawer, mid_x - half_w, y0, half_w, bar_h, color)
                    self._draw_hbar(drawer, mid_x, y0, half_w, bar_h, color)

    def _draw_bar(self, drawer, x, y, w, h, color):
        if h <= 0:
            return
        x, y, w, h = int(x), int(y), max(1, int(w)), max(1, int(h))
        if self.round_caps:
            r = min(w, h) // 3
            drawer.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=color)
        else:
            drawer.rectangle([x, y, x + w, y + h], fill=color)

    def _draw_hbar(self, drawer, x, y, w, h, color):
        if w <= 0:
            return
        x, y, w, h = int(x), int(y), max(1, int(w)), max(1, int(h))
        if self.round_caps:
            r = min(w, h) // 3
            drawer.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=color)
        else:
            drawer.rectangle([x, y, x + w, y + h], fill=color)
