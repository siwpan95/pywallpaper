"""
自由绘制原语 — 通过命令序列执行任意绘制操作

支持的命令:
    circle(x, y, radius, color, fill)
    rect(x1, y1, x2, y2, color, fill)
    line(x1, y1, x2, y2, color, width)
    polygon(points, color, fill)
    ellipse(x1, y1, x2, y2, color, fill)
    arc(x, y, radius, start, end, color, width)

每个命令中的值可以引用音频数据: {"audio": "rms", "scale": [10, 100]}
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive

# 支持的形状
SHAPES = ('circle', 'rect', 'line', 'polygon', 'ellipse', 'arc')


@register_primitive('drawing')
class DrawingPrimitive(RenderPrimitive):
    """自由绘制 — 命令序列

    配置:
        commands: list  绘制命令列表
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.commands = config.get('commands', [])

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def draw(self, drawer: ImageDraw.ImageDraw):
        for cmd in self.commands:
            self._exec_command(drawer, cmd)

    def _exec_command(self, drawer, cmd):
        shape = cmd.get('shape', 'circle')
        if shape not in SHAPES:
            return

        # 解析参数值（支持音频映射）
        def val(key, default=0):
            v = cmd.get(key, default)
            if isinstance(v, dict) and 'audio' in v:
                return self._resolve_audio(v)
            if isinstance(v, str):
                return self._parse_coord(v)
            return v

        if shape == 'circle':
            x, y = val('x', self.cx), val('y', self.cy)
            r = val('radius', 10)
            color = self._resolve_color(cmd.get('color'))
            fill = cmd.get('fill', True)
            drawer.ellipse([x - r, y - r, x + r, y + r],
                          fill=color if fill else None,
                          outline=None if fill else color)

        elif shape == 'rect':
            x1 = val('x1', 0)
            y1 = val('y1', 0)
            x2 = val('x2', 100)
            y2 = val('y2', 100)
            color = self._resolve_color(cmd.get('color'))
            fill = cmd.get('fill', True)
            if fill:
                drawer.rectangle([x1, y1, x2, y2], fill=color)
            else:
                drawer.rectangle([x1, y1, x2, y2], outline=color)

        elif shape == 'line':
            x1, y1 = val('x1', 0), val('y1', 0)
            x2, y2 = val('x2', 100), val('y2', 100)
            color = self._resolve_color(cmd.get('color'))
            width = val('width', 1)
            drawer.line([x1, y1, x2, y2], fill=color, width=width)

        elif shape == 'polygon':
            pts = cmd.get('points', [])
            if pts:
                color = self._resolve_color(cmd.get('color'))
                fill = cmd.get('fill', True)
                # 解析百分比坐标
                resolved = [(self._parse_coord(p[0]), self._parse_coord(p[1])) for p in pts]
                if fill:
                    drawer.polygon(resolved, fill=color)
                else:
                    drawer.polygon(resolved, outline=color)

        elif shape == 'ellipse':
            x1, y1 = val('x1', 0), val('y1', 0)
            x2, y2 = val('x2', 100), val('y2', 100)
            color = self._resolve_color(cmd.get('color'))
            fill = cmd.get('fill', True)
            if fill:
                drawer.ellipse([x1, y1, x2, y2], fill=color)
            else:
                drawer.ellipse([x1, y1, x2, y2], outline=color)

        elif shape == 'arc':
            x, y = val('x', self.cx), val('y', self.cy)
            r = val('radius', 50)
            start = val('start', 0)
            end = val('end', 180)
            color = self._resolve_color(cmd.get('color'))
            width = val('width', 2)
            drawer.arc([x - r, y - r, x + r, y + r], start=start, end=end,
                      fill=color, width=width)

    def _resolve_audio(self, spec: dict) -> float:
        """解析音频映射值"""
        source = spec.get('audio', 'rms')
        scale = spec.get('scale', [0, 1])
        smoothing = spec.get('smoothing', 0.85)
        # 使用 audio_map 的逻辑
        raw = 0.0
        if source == 'rms':
            import math as m
            raw = m.sqrt(sum(self._audio.get_band_energy(i)**2 for i in range(64)) / 64)
        elif source == 'band_energy':
            raw = self._audio.get_band_energy(spec.get('index', 0) % 64)
        return scale[0] + raw * (scale[1] - scale[0])

    def _resolve_color(self, color_spec) -> tuple:
        """解析颜色"""
        if color_spec is None:
            return self._get_color(0, 1, 0)
        if isinstance(color_spec, (list, tuple)):
            return tuple(color_spec[:3])
        if isinstance(color_spec, dict):
            return self._get_color(0, 1, 0)
        return (255, 255, 255)

    def _parse_coord(self, val) -> float:
        """解析坐标值（支持数值、百分比字符串）"""
        if isinstance(val, (int, float)):
            return float(val)
        if not isinstance(val, str):
            return float(val)
        val = val.strip()
        if val.endswith('%'):
            return float(val.rstrip('%')) / 100 * self.width
        if val == 'center':
            return self.width / 2
        return float(val)
