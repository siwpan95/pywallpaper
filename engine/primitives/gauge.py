"""
仪表盘原语 — 弧形表盘，音频驱动的指针

配置:
    center: {x, y}    中心点
    radius: float     表盘半径
    arc: {start, end} 数学角度范围 (0°=右, 90°=下, 225°~315°=底部弧形)
    arc_width: int    弧带宽度
    segments: list    彩色段 [{from, to, color}]
    ticks: dict       刻度 {step, major_step, length, color, major_color}
    needle: dict      指针 {length_ratio, width, color}
    audio: dict       映射 {source, range: [min, max], smoothing}
    label: str        标签文字（可选）
"""
import math
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('gauge')
class GaugePrimitive(RenderPrimitive):
    """弧形仪表盘

    配置:
        center: {x, y}
        radius: float
        arc: {start, end}
        arc_width: int
        segments: [{from, to, color}]
        ticks: {step, major_step, length, color, major_color, major_width}
        needle: {length_ratio, width, color}
        audio: {source, range: [min, max], smoothing}
        label: str
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.r = config.get('radius', min(width, height) * 0.38)
        arc_cfg = config.get('arc', {})
        self.arc_start = arc_cfg.get('start', 225.0)
        self.arc_end = arc_cfg.get('end', 315.0)
        self.arc_width = config.get('arc_width', 8)
        self.segments = config.get('segments', [])
        ticks = config.get('ticks', {})
        self.tick_step = ticks.get('step', 1)
        self.tick_major = ticks.get('major_step', 5)
        self.tick_len = ticks.get('length', 10)
        self.tick_color = tuple(ticks.get('color', [200, 200, 230])[:3])
        self.tick_major_color = tuple(ticks.get('major_color', [220, 220, 230])[:3])
        self.tick_major_width = ticks.get('major_width', 3)
        needle = config.get('needle', {})
        self.needle_ratio = needle.get('length_ratio', 0.82)
        self.needle_width = needle.get('width', 3)
        self.needle_color = tuple(needle.get('color', [200, 210, 220])[:3])
        self.label = config.get('label', '')
        self._smoothed = 0.0

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        raw = self._get_audio_value('value', 0, dt, 0.0)
        smoothing = 0.85
        self._smoothed = self._smoothed * smoothing + raw * (1 - smoothing)

    def draw(self, drawer):
        cx, cy = self.cx, self.cy
        r = self.r
        t = self._time

        # 1. 表盘背景
        drawer.ellipse([cx - r - 15, cy - r - 15, cx + r + 15, cy + r + 15],
                       fill=(20, 22, 32))
        drawer.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6],
                       fill=(40, 42, 55))

        # 2. 弧形段
        if self.segments:
            for seg in self.segments:
                a_start = seg['from']
                a_end = seg['to']
                color = tuple(seg['color'][:3]) if isinstance(seg['color'], list) else self._get_color(0, 1, 0)
                total_span = self.arc_end - self.arc_start
                val_span = 23.0  # -20 to +3
                frac_start = (a_start + 20) / val_span
                frac_end = (a_end + 20) / val_span
                deg_start = self.arc_start + frac_start * total_span
                deg_end = self.arc_start + frac_end * total_span
                band_r = r - 1
                band_w = self.arc_width
                steps = max(4, int((deg_end - deg_start) / 1.5))
                for i in range(steps):
                    f1 = i / steps
                    f2 = (i + 1) / steps
                    a1 = math.radians(deg_start + f1 * (deg_end - deg_start))
                    a2 = math.radians(deg_start + f2 * (deg_end - deg_start))
                    x1 = cx + math.cos(a1) * (band_r - band_w)
                    y1 = cy - math.sin(a1) * (band_r - band_w)
                    x2 = cx + math.cos(a1) * band_r
                    y2 = cy - math.sin(a1) * band_r
                    x3 = cx + math.cos(a2) * band_r
                    y3 = cy - math.sin(a2) * band_r
                    x4 = cx + math.cos(a2) * (band_r - band_w)
                    y4 = cy - math.sin(a2) * (band_r - band_w)
                    drawer.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)], fill=color)

        # 3. 刻度线
        val_min = -20.0
        val_max = 3.0
        total_span = self.arc_end - self.arc_start
        val_span = val_max - val_min
        db = val_min
        while db <= val_max:
            frac = (db - val_min) / val_span
            a = math.radians(self.arc_start + frac * total_span)
            inner = r - 16
            outer = r - 4
            x1 = cx + math.cos(a) * inner
            y1 = cy - math.sin(a) * inner
            x2 = cx + math.cos(a) * outer
            y2 = cy - math.sin(a) * outer
            w = self.tick_major_width if abs(db - round(db)) < 0.001 and int(round(db)) % self.tick_major == 0 else 1
            c = self.tick_major_color if w > 1 else self.tick_color
            drawer.line([x1, y1, x2, y2], fill=c, width=w)
            db += self.tick_step

        # 4. 指针
        level = self._smoothed  # 0~1 mapped from audio range
        needle_deg = self.arc_start + level * total_span
        needle_a = math.radians(needle_deg)
        needle_len = r * self.needle_ratio
        px = cx + math.cos(needle_a) * needle_len
        py = cy - math.sin(needle_a) * needle_len
        # 指针颜色随值变化
        nc = self.needle_color
        if level > (2.0 / 23.0) * total_span / total_span * 23 + 20:
            # 偏红区域时变红
            red_frac = min(level, 1.0)
            nc = (min(255, self.needle_color[0] + int(35 * red_frac)),
                  max(0, self.needle_color[1] - int(30 * red_frac)),
                  self.needle_color[2])
        drawer.line([cx, cy, px, py], fill=nc, width=self.needle_width)

        # 5. 中心轴承
        drawer.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(180, 185, 195))
        drawer.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(40, 42, 55))

        # 6. 标签
        if self.label:
            label_y = cy + r + 35
            label_size = max(10, int(r * 0.15))
            drawer.rectangle([cx - 22, label_y, cx + 22, label_y + label_size],
                           fill=(100, 110, 130))
