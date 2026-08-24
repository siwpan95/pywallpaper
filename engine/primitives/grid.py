"""
网格原语 — 2D 网格排列元素
"""
import math
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('grid')
class GridPrimitive(RenderPrimitive):
    """2D 网格

    配置:
        cols: int           列数 (默认 20)
        rows: int           行数 (默认 10)
        element: str        元素类型 'circle'/'rect' (默认 'rect')
        element_ratio: float 元素占格比例 (默认 0.8)
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.cols = config.get('cols', 20)
        self.rows = config.get('rows', 10)
        self.element_type = config.get('element', 'rect')
        self.elem_ratio = config.get('element_ratio', 0.8)
        self.cell_w = self.w / max(self.cols, 1)
        self.cell_h = self.h / max(self.rows, 1)

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def draw(self, drawer: ImageDraw.ImageDraw):
        total = self.cols * self.rows
        idx = 0
        for row in range(self.rows):
            for col in range(self.cols):
                energy = self._get_audio_value('scale', idx, default=0.0)
                color = self._get_color(idx, total, energy)

                cx = self.x + col * self.cell_w + self.cell_w / 2
                cy = self.y + row * self.cell_h + self.cell_h / 2
                scale = 0.5 + energy * 0.5
                sz = min(self.cell_w, self.cell_h) * self.elem_ratio * scale / 2

                if self.element_type == 'circle':
                    drawer.ellipse([cx - sz, cy - sz, cx + sz, cy + sz], fill=color)
                elif self.element_type == 'rect':
                    drawer.rectangle([cx - sz, cy - sz, cx + sz, cy + sz], fill=color)

                idx += 1
