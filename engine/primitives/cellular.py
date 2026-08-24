"""
元胞自动机原语 — Conway生命游戏 + 音频驱动的随机激活

配置:
  cols, rows: int  网格尺寸
  cell_size: int   格点像素大小
  rule: str        规则名 ('conway')
"""
import math
import random
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('cellular')
class CellularPrimitive(RenderPrimitive):
    """元胞自动机

    配置:
        cols: int       列数
        rows: int       行数
        cell_size: int  像素大小
        rule: str       'conway' (默认)
        audio_birth: bool  音频驱动随机激活
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.cols = config.get('cols', 48)
        self.rows = config.get('rows', 27)
        self.rule = config.get('rule', 'conway')
        self.audio_birth = config.get('audio_birth', True)

        # 根据屏幕分辨率自动计算格点大小（占屏幕约 85%）
        self.cell_size = max(1, int(min(self.width / self.cols, self.height / self.rows) * 0.85))
        # 居中偏移
        self._offset_x = (self.width - self.cols * self.cell_size) // 2
        self._offset_y = (self.height - self.rows * self.cell_size) // 2

        self._grid = [[random.randint(0, 1) for _ in range(self.cols)] for _ in range(self.rows)]
        self._update_timer = 0.0
        self._update_interval = config.get('update_interval', 0.15)

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        self._update_timer += dt

        if self._update_timer < self._update_interval:
            return
        self._update_timer = 0.0

        avg_e = sum(audio.get_band_energy(i) for i in range(64)) / 64

        # 音频驱动随机激活
        if self.audio_birth and random.random() < avg_e:
            y = random.randint(0, self.rows - 1)
            x = random.randint(0, self.cols - 1)
            self._grid[y][x] = 1

        # Conway 规则
        new = [row[:] for row in self._grid]
        for y in range(1, self.rows - 1):
            for x in range(1, self.cols - 1):
                nb = sum(self._grid[ny][nx]
                        for ny in range(y-1, y+2)
                        for nx in range(x-1, x+2)) - self._grid[y][x]
                if self._grid[y][x]:
                    new[y][x] = 1 if nb in [2, 3] else 0
                else:
                    new[y][x] = 1 if nb == 3 else 0
        self._grid = new

    def draw(self, drawer):
        cs = self.cell_size
        ox = self._offset_x
        oy = self._offset_y
        for y in range(self.rows):
            for x in range(self.cols):
                if self._grid[y][x]:
                    e = self._get_audio_value('value', x % 64)
                    color = self._get_color(x + y, self.cols + self.rows, e)
                    drawer.rectangle(
                        [ox + x*cs, oy + y*cs, ox + (x+1)*cs-1, oy + (y+1)*cs-1],
                        fill=color)
