"""
脚本原语 — 嵌入 Python 绘制代码，处理无法用组合原语表达的复杂效果

兼容 API (self = ScriptCompat):
    self.width, self.height, self.center_x, self.center_y, self.time
    self.audio.get_band_energy(idx)
    self.draw_rect/circle/line/polygon
    self.rgb(h,s,v)

状态管理:
    init 代码执行一次，结果挂到 self 上（如 self.fire_cols = [...]）
    update 代码每帧执行，可更新 self 上的状态
    draw 代码每帧执行，读取 self 上累积的状态
"""
import math
import random as _random
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive
from utils.helpers import hsv_to_rgb


class ScriptCompat:
    """兼容 VisualEffect API 的持久包装对象 — 跨帧保留状态"""

    def __init__(self, drawer: ImageDraw.ImageDraw, width: int, height: int,
                 audio, time: float, params: dict = None):
        self.drawer = drawer
        self.audio = audio
        self.width = width
        self.height = height
        self.center_x = width // 2
        self.center_y = height // 2
        self.time = time
        self._params = params or {}

    def p(self, key, default=None):
        return self._params.get(key, default)

    def rgb(self, h, s, v):
        return hsv_to_rgb(h, s, v)

    def draw_rect(self, x1, y1, x2, y2, color, fill=True):
        if x1 > x2: x1, x2 = x2, x1
        if y1 > y2: y1, y2 = y2, y1
        if fill:
            self.drawer.rectangle([x1, y1, x2, y2], fill=color)
        else:
            self.drawer.rectangle([x1, y1, x2, y2], outline=color)

    def draw_circle(self, x, y, radius, color, fill=True):
        bbox = (x - radius, y - radius, x + radius, y + radius)
        if fill:
            self.drawer.ellipse(bbox, fill=color)
        else:
            self.drawer.ellipse(bbox, outline=color)

    def draw_line(self, x1, y1, x2, y2, color, width=1):
        self.drawer.line([x1, y1, x2, y2], fill=color, width=width)

    def draw_polygon(self, points, color, fill=True):
        if fill:
            self.drawer.polygon(points, fill=color)
        else:
            self.drawer.polygon(points, outline=color)

    def draw_text(self, x, y, text, color, font=None):
        try:
            self.drawer.text((x, y), text, fill=color, font=font)
        except Exception:
            pass


@register_primitive('script')
class ScriptPrimitive(RenderPrimitive):
    """嵌入式脚本原语 — 有状态

    配置:
        init: str   初始化代码（执行一次，可向 self 挂属性）
        update: str 更新代码（每帧执行，用于状态更新）
        draw: str   绘制代码（每帧执行）
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self._draw_code = config.get('draw', '')
        self._update_code = config.get('update', '')
        self._params = config.get('params', {})

        # 创建持久 ScriptCompat（drawer 稍后注入）
        self._compat = ScriptCompat(None, width, height, None, 0.0, self._params)

        # 执行 init
        init_code = config.get('init', '')
        if init_code.strip():
            ns = {
                'self': self._compat,
                'math': math, 'random': _random,
                'width': width, 'height': height,
                'int': int, 'float': float, 'range': range,
                'len': len, 'min': min, 'max': max,
                'sum': sum, 'abs': abs,
            }
            try:
                exec(init_code, ns)
            except Exception as e:
                print(f"[SCRIPT] init error in {config.get('_name', '?')}: {e}")

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        self._compat.audio = audio
        self._compat.time = global_time

        if self._update_code.strip():
            ns = {
                'self': self._compat,
                'math': math, 'random': _random,
                'dt': dt,
            }
            try:
                exec(self._update_code, ns)
            except Exception:
                pass

    def draw(self, drawer: ImageDraw.ImageDraw):
        if not self._draw_code.strip():
            return

        self._compat.drawer = drawer

        ns = {
            'self': self._compat,
            'math': math, 'random': _random,
            'hsv_to_rgb': hsv_to_rgb,
            'draw_rect': self._compat.draw_rect,
            'draw_circle': self._compat.draw_circle,
            'draw_line': self._compat.draw_line,
            'draw_polygon': self._compat.draw_polygon,
            'rgb': self._compat.rgb,
            'audio': self._compat.audio,
            'width': self._compat.width,
            'height': self._compat.height,
            'time': self._compat.time,
            'center_x': self._compat.center_x,
            'center_y': self._compat.center_y,
        }

        try:
            exec(self._draw_code, ns)
        except Exception:
            pass
