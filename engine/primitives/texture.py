"""
纹理原语 — 块级/像素级纹理生成

支持的纹理:
  plasma   — 等离子体（多频正弦叠加）
  moire    — 莫尔条纹（干涉图案）
  grid     — 频谱渐变网格
  pixel    — 像素排序效果
  field    — 频率场

配置:
  mode: str         纹理类型
  cell_size: int    块大小 (默认 8)
"""
import math
import random
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('texture')
class TexturePrimitive(RenderPrimitive):
    """块级纹理生成

    配置:
        mode: str        'plasma'/'moire'/'grid'/'pixel'/'field'
        cell_size: int   块大小
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.mode = config.get('mode', 'plasma')
        self.cell_size = config.get('cell_size', 8)

    def draw(self, drawer):
        s = self.cell_size
        w, h = self.width, self.height
        t = self._time

        if self.mode == 'plasma':
            for x in range(0, w, s):
                for y in range(0, h, s):
                    v = (math.sin(x*0.01+t) + math.sin((y*0.01+t)*0.5) +
                         math.sin((x*0.01+y*0.01+t)*0.5)) / 3
                    e = self._get_audio_value('value', (x+y) % 64)
                    hue = ((v+1)*0.5 + e*0.2) % 1.0
                    color = self._get_color(int(hue*64), 64, e)
                    drawer.rectangle([x, y, x+s-1, y+s-1], fill=color)

        elif self.mode == 'moire':
            cx, cy = self.w//2, self.h//2
            for y in range(0, h, s):
                for x in range(0, w, s):
                    d1 = ((x-cx)**2+(y-cy)**2)**0.5
                    d2 = abs(x*math.sin(t)-y*math.cos(t))
                    interf = math.sin(d1*0.05+t*2)*math.sin(d2*0.03)
                    e = self._get_audio_value('value', int(x/w*64))
                    v = (interf+1)*0.5+e*0.3
                    hue = (v+t*0.2) % 1.0
                    color = self._get_color(int(hue*64), 64, v)
                    drawer.rectangle([x, y, x+s-1, y+s-1], fill=color)

        elif self.mode == 'grid':
            for y in range(0, h, s):
                for x in range(0, w, s):
                    e = self._get_audio_value('value', int(x/w*64))
                    hue = (x/w + y/h + t*0.1) % 1.0
                    color = self._get_color(int(hue*64), 64, e)
                    drawer.rectangle([x, y, x+s-1, y+s-1], fill=color)

        elif self.mode == 'field':
            for y in range(0, h, s):
                for x in range(0, w, s):
                    v = math.sin(x*0.02+t)*math.cos(y*0.02+t*0.7)*math.sin((x+y)*0.01+t*0.5)
                    e = self._get_audio_value('value', int(x/w*64))
                    hue = ((v+1)*0.5 + e*0.3) % 1.0
                    color = self._get_color(int(hue*64), 64, max(0, v*0.7+e*0.3))
                    drawer.rectangle([x, y, x+s-1, y+s-1], fill=color)

        elif self.mode == 'pixel':
            # 频谱像素排序
            for row in range(0, h, s):
                e = self._get_audio_value('value', int(row/h*64))
                offset = int(e * 60)
                for col in range(0, w, s):
                    idx = (col + offset + int(math.sin(t*2+row*0.05)*20)) % (w//s)
                    hue = (idx*s/w + t*0.05) % 1.0
                    color = self._get_color(int(hue*64), 64, e*0.7)
                    drawer.point((col, row), fill=color)

        elif self.mode == 'mandelbrot':
            avg_e = sum(self._audio.get_band_energy(i) for i in range(32)) / 32
            depth = int(3 + avg_e * 5)
            max_iter = 10 + depth * 3
            cs = max(4, self.cell_size)

            for px in range(0, w, cs):
                for py in range(0, h, cs):
                    cx = (px/w - 0.5) * 3
                    cy = (py/h - 0.5) * 3
                    x, y = 0.0, 0.0
                    it = max_iter
                    for i in range(max_iter):
                        if x*x + y*y > 4:
                            it = i
                            break
                        x, y = x*x - y*y + cx, 2*x*y + cy
                    if it < max_iter:
                        color = self._get_color(int(it/max_iter*64), 64, it/max_iter*0.8)
                        drawer.rectangle([px, py, px+cs-1, py+cs-1], fill=color)

        elif self.mode == 'fire':
            # 火焰纹理 — 热力传播 + 音频驱动底部火焰
            if not hasattr(self, '_fire_cols'):
                self._fire_cols = [[0.0] * int(w/4) for _ in range(int(h/4))]

            fh = len(self._fire_cols)
            fw = len(self._fire_cols[0])
            for y in range(fh - 1, 0, -1):
                for x in range(fw):
                    self._fire_cols[y][x] = self._fire_cols[y-1][x] * 0.95 + \
                        (random.random() - 0.5) * 0.1

            for x in range(fw):
                self._fire_cols[0][x] = self._audio.get_band_energy(int(x/fw*64)) * 2

            cs = max(2, self.cell_size)
            for y, row in enumerate(self._fire_cols):
                for x, val in enumerate(row):
                    val = min(max(val, 0), 1.0)
                    color = self._get_color(int((1-val)*10), 64, val)
                    drawer.rectangle([x*cs, h - y*cs, (x+1)*cs-1, h - y*cs+cs], fill=color)
