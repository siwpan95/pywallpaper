"""
文字雨原语 — 矩阵雨/字符下落效果
"""
import math
import random
from PIL import ImageDraw, ImageFont
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('text_rain')
class TextRainPrimitive(RenderPrimitive):
    """文字雨

    配置:
        chars: str           字符集 (默认 "01アイウエオ")
        count: int           列数 (默认 60)
        font_size: int       字号 (默认 16)
        speed: {min, max}    下落速度范围 (默认 50~150)
        trail_length: int    拖尾长度 (默认 10)
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.chars = config.get('chars', '01アイウエオカキクケコ')
        self.count = config.get('count', 60)
        self.font_size = config.get('font_size', 16)
        spd = config.get('speed', {'min': 50, 'max': 150})
        if isinstance(spd, dict):
            self.speed_min, self.speed_max = spd.get('min', 50), spd.get('max', 150)
        else:
            self.speed_min, self.speed_max = 50, 150
        self.trail = config.get('trail_length', 10)

        # 初始化下落列
        self.columns = []
        col_w = self.w / max(self.count, 1)
        for i in range(self.count):
            self.columns.append({
                'x': self.x + i * col_w + col_w / 2,
                'y': random.uniform(0, self.h),
                'speed': random.uniform(self.speed_min, self.speed_max),
            })

        # 字体
        self._font = None
        try:
            self._font = ImageFont.truetype('consola.ttf', self.font_size)
        except Exception:
            try:
                self._font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', self.font_size)
            except Exception:
                self._font = ImageFont.load_default()

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        for col in self.columns:
            col['y'] += col['speed'] * dt
            if col['y'] > self.y + self.h + self.font_size:
                col['y'] = self.y - random.uniform(0, self.font_size * 5)
                col['speed'] = random.uniform(self.speed_min, self.speed_max)

    def draw(self, drawer: ImageDraw.ImageDraw):
        for i, col in enumerate(self.columns):
            energy = self._get_audio_value('brightness', i, default=0.5)
            bright = 0.3 + energy * 0.7

            # 拖尾效果
            for ti in range(self.trail):
                cy = col['y'] - ti * self.font_size * 1.2
                if cy < self.y - self.font_size:
                    continue
                alpha = (1.0 - ti / self.trail) * bright
                char_idx = int(cy / self.h * len(self.chars)) % len(self.chars)
                ch = self.chars[char_idx]
                color = self._get_color(i, self.count, energy)
                # 亮度衰减
                trail_color = tuple(int(c * alpha) for c in color[:3])
                try:
                    drawer.text((col['x'], cy), ch, fill=trail_color, font=self._font, anchor='mm')
                except Exception:
                    drawer.text((col['x'], cy), ch, fill=trail_color, font=self._font)
