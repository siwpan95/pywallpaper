"""
波形原语 — 绘制音频波形曲线
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('waveform')
class WaveformPrimitive(RenderPrimitive):
    """音频波形曲线

    配置:
        lines: int          曲线数量 (默认 2)
        points: int         每条曲线点数 (默认 200)
        amplitude: float    振幅 (默认 150)
        frequency: float    空间频率 (默认 0.05)
        line_width: int     线宽 (默认 2)
        mode: str           模式 'wave'(波形)/'spectrum'(频谱) (默认 'wave')
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.line_count = config.get('lines', config.get('count', 2))
        self.points = config.get('points', 200)
        self.amplitude = min(config.get('amplitude', 150), self._max_safe_radius)
        self.frequency = config.get('frequency', 0.05)
        self.line_width = config.get('line_width', 2)
        self.mode = config.get('mode', 'wave')

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def draw(self, drawer: ImageDraw.ImageDraw):
        mid_y = self.y + self.h / 2
        for li in range(self.line_count):
            pts = []
            for i in range(self.points):
                x = self.x + (i / (self.points - 1)) * self.w
                band_idx = int((i / self.points) * 64)
                energy = self._get_audio_value('y', band_idx, default=0.0)
                phase = li * 0.5 + self._time * (2.0 + li)
                y = mid_y + math.sin(i * self.frequency + phase) * (30 + energy * self.amplitude)
                pts.append((x, y))
            color = self._get_color(li, self.line_count, 0)
            for pi in range(len(pts) - 1):
                drawer.line([pts[pi], pts[pi + 1]], fill=color, width=self.line_width)
