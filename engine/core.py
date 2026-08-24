"""
渲染引擎核心 — EngineEffect

一个 EngineEffect 由多个 Layer 组成。
每个 Layer 使用一种绘制原语 (Primitive)。
原语从 JSON 配置中动态实例化，完全数据驱动。
"""
from PIL import ImageDraw

from engine.utils import parse_position, parse_size


class EngineEffect:
    """声明式效果 — 100% 由 JSON 驱动

    与旧的 VisualEffect 接口兼容:
        - update(dt)
        - draw()
        - self.time, self.width, self.height, self.audio
    """

    def __init__(self, drawer: ImageDraw.ImageDraw, width: int, height: int,
                 audio, effect_config: dict = None):
        self.drawer = drawer
        self.width = width
        self.height = height
        self.audio = audio
        self.time = 0.0

        # 中心点
        self.center_x = width // 2
        self.center_y = height // 2

        # 参数（从 JSON params 传入）
        self._config = effect_config or {}
        params = self._config.get('params', {})
        if isinstance(params, dict):
            self._params = params
        else:
            self._params = {}

        # 解析图层
        self._layers = []
        layers_config = self._params.get('layers', [])
        if isinstance(layers_config, list):
            from engine.primitives import create_primitive
            for layer_cfg in layers_config:
                try:
                    primitive = create_primitive(layer_cfg, width, height)
                    self._layers.append(primitive)
                except Exception as e:
                    import sys
                    print(f"[Engine] 跳过图层 {layer_cfg.get('type', '?')}: {e}", file=sys.stderr, flush=True)

    def p(self, key: str, default=None):
        """读取 params 中的参数（兼容旧接口）"""
        return self._params.get(key, default)

    def update(self, dt: float):
        self.time += dt
        for layer in self._layers:
            layer.update(dt, self.audio, self.time)

    def draw(self):
        for layer in self._layers:
            layer.draw(self.drawer)

    # --- 绘制辅助方法（兼容旧效果类的调用） ---
    def draw_circle(self, x, y, radius, color, fill=True):
        bbox = (x - radius, y - radius, x + radius, y + radius)
        if fill:
            self.drawer.ellipse(bbox, fill=color)
        else:
            self.drawer.ellipse(bbox, outline=color)

    def draw_rect(self, x1, y1, x2, y2, color, fill=True):
        if x1 > x2: x1, x2 = x2, x1
        if y1 > y2: y1, y2 = y2, y1
        if fill:
            self.drawer.rectangle([x1, y1, x2, y2], fill=color)
        else:
            self.drawer.rectangle([x1, y1, x2, y2], outline=color)

    def draw_line(self, x1, y1, x2, y2, color, width=1):
        self.drawer.line([x1, y1, x2, y2], fill=color, width=width)

    def draw_polygon(self, points, color, fill=True):
        if fill:
            self.drawer.polygon(points, fill=color)
        else:
            self.drawer.polygon(points, outline=color)

    def rgb(self, h, s, v):
        from utils.helpers import hsv_to_rgb
        return hsv_to_rgb(h, s, v)

    def energy_color(self, energy, hue_offset=0.0):
        from utils.helpers import get_energy_color
        return get_energy_color(energy, hue_offset)
