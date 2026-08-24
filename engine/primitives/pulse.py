"""
脉冲/涟漪/声纳统一原语 — 内置状态管理

支持的脉冲类型:
  sonar         声纳扫描（扇形脉冲从中心出发）
  ring_pulse    环形脉冲（圆环从中心扩散）
  ripple        水波涟漪（从随机点扩散的同心圆）
  spectrum_ripples  频谱涟漪（基于音频频段触发）

配置:
  mode: str         类型
  center: {x, y}    中心点
  max_radius: float 最大扩散半径
  speed: float      扩散速度
  count: int        环/扇区数量
  trigger: str      触发源 ('audio'/'random'/'beat')
  trigger_threshold: float  触发阈值
  line_width: int   线宽
"""
import math
import random
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('pulse')
class PulsePrimitive(RenderPrimitive):
    """脉冲/涟漪/声纳系统

    配置:
        mode: str          'sonar'/'ring_pulse'/'ripple'/'spectrum_ripples'
        center: {x, y}     中心点
        max_radius: float  最大半径
        speed: float       扩散速度
        count: int         每次创建的脉冲数
        trigger: str       'audio'/'random'/'beat'
        trigger_threshold: float
        line_width: int
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.mode = config.get('mode', 'ripple')
        self.max_radius = min(config.get('max_radius', 400), self._max_safe_radius)
        self.speed = config.get('speed', 2.0)
        self.count = config.get('count', 1)
        self.trigger = config.get('trigger', 'audio')
        self.threshold = config.get('trigger_threshold', 0.3)
        self.line_width = config.get('line_width', 2)
        self._pulses = []
        self._timer = 0.0
        self._seeded = False  # 首次保证有可见脉冲

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        self._timer += dt

        avg_e = sum(audio.get_band_energy(i) for i in range(64)) / 64

        should_fire = False
        if self.trigger == 'audio' and avg_e > self.threshold and random.random() < avg_e:
            should_fire = True
        elif self.trigger == 'random' and random.random() < self.threshold * 0.05:
            should_fire = True
        elif self.trigger == 'beat':
            low = sum(audio.get_band_energy(i) for i in range(4)) / 4
            if low > self.threshold and self._timer > 0.1:
                should_fire = True
                self._timer = 0.0

        if should_fire:
            if self.mode == 'ripple':
                for _ in range(self.count):
                    self._pulses.append({
                        'x': random.random() * self.width,
                        'y': random.random() * self.height,
                        'radius': 0,
                        'band': random.randint(0, 63),
                    })
            elif self.mode == 'sonar':
                for _ in range(self.count):
                    self._pulses.append({
                        'radius': 0,
                        'angle': random.uniform(0, math.pi * 2),
                        'band': random.randint(0, 63),
                    })
            elif self.mode == 'ring_pulse':
                for _ in range(self.count):
                    self._pulses.append({
                        'radius': 0,
                        'band': random.randint(0, 63),
                        'born': global_time,
                    })
            elif self.mode == 'spectrum_ripples':
                for i in range(self.count):
                    band = random.randint(0, 63)
                    if audio.get_band_energy(band) > 0.2:
                        self._pulses.append({'radius': 0, 'band': band})

        # 更新所有脉冲
        for p in self._pulses[:]:
            p['radius'] += self.speed
            if p['radius'] > self.max_radius:
                self._pulses.remove(p)

        # 首次更新时预置脉冲，确保启动就有可见内容
        if not self._seeded:
            self._seeded = True
            if self.mode in ('ripple', 'spectrum_ripples'):
                for _ in range(max(1, self.count)):
                    self._pulses.append({
                        'x': random.random() * self.width,
                        'y': random.random() * self.height,
                        'radius': random.uniform(0, self.max_radius * 0.5),
                        'band': random.randint(0, 63),
                    })
            elif self.mode == 'ring_pulse':
                for _ in range(max(1, self.count)):
                    self._pulses.append({
                        'radius': random.uniform(0, self.max_radius * 0.5),
                        'band': random.randint(0, 63),
                        'born': global_time,
                    })
            elif self.mode == 'sonar':
                for _ in range(max(1, self.count)):
                    self._pulses.append({
                        'radius': random.uniform(0, self.max_radius * 0.3),
                        'angle': random.uniform(0, math.pi * 2),
                        'band': random.randint(0, 63),
                    })

    def draw(self, drawer):
        cx, cy = self.cx, self.cy

        if self.mode == 'sonar':
            # 背景网格圆
            for r in range(50, int(self.max_radius), 80):
                for i in range(36):
                    a = (i / 36) * math.pi * 2
                    x = cx + math.cos(a) * r
                    y = cy + math.sin(a) * r
                    drawer.point((x, y), fill=(30, 30, 30))

            for p in self._pulses:
                a_ratio = 1 - p['radius'] / self.max_radius
                hue = p['angle'] / (math.pi * 2)
                e = self._get_audio_value('value', p['band'])
                color = self._get_color(int(hue * 64), 64, e)
                x1 = cx + math.cos(p['angle']) * p['radius']
                y1 = cy + math.sin(p['angle']) * p['radius']
                x2 = cx + math.cos(p['angle'] + 0.1) * p['radius']
                y2 = cy + math.sin(p['angle'] + 0.1) * p['radius']
                drawer.line([x1, y1, x2, y2], fill=color, width=self.line_width)

        elif self.mode == 'ring_pulse':
            for p in self._pulses:
                a_ratio = 1 - p['radius'] / self.max_radius
                if a_ratio <= 0:
                    continue
                age = self._time - p.get('born', self._time)
                alpha = a_ratio * (1 - age % 1)
                hue = (p['band'] / 64 + self._time * 0.05) % 1.0
                e = self._get_audio_value('value', p['band'])
                color = self._get_color(int(hue * 64), 64, e)
                for i in range(72):
                    ang = (i / 72) * math.pi * 2
                    wb = math.sin(ang * 8 + self._time * 5) * 5
                    r = p['radius'] + wb + e * 20
                    x1 = cx + math.cos(ang) * r
                    y1 = cy + math.sin(ang) * r
                    x2 = cx + math.cos(ang + 0.1) * r
                    y2 = cy + math.sin(ang + 0.1) * r
                    drawer.line([x1, y1, x2, y2], fill=color, width=1)

        elif self.mode in ('ripple', 'spectrum_ripples'):
            for p in self._pulses:
                a_ratio = 1 - p['radius'] / self.max_radius
                if a_ratio <= 0:
                    continue
                px = p.get('x', cx)
                py = p.get('y', cy)
                hue = (p['band'] / 64 + self._time * 0.1) % 1.0
                e = self._get_audio_value('value', p['band'])
                color = self._get_color(int(hue * 64), 64, e)
                for i in range(36):
                    ang = (i / 36) * math.pi * 2
                    wb = math.sin(ang * 5 + self._time * 4) * 5
                    r = p['radius'] + wb
                    x1 = px + math.cos(ang) * r
                    y1 = py + math.sin(ang) * r
                    x2 = px + math.cos(ang + 0.2) * r
                    y2 = py + math.sin(ang + 0.2) * r
                    drawer.line([x1, y1, x2, y2], fill=color, width=self.line_width)
