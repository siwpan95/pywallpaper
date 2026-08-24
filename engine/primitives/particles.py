"""
粒子系统原语 — 音频反应式粒子系统

行为模式:
    drift   — 随机漂移
    orbit   — 绕中心旋转
    fall    — 下落
    rise    — 上升
    bounce  — 反弹
"""
import math
import random
from PIL import ImageDraw
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('particles')
class ParticlesPrimitive(RenderPrimitive):
    """粒子系统

    配置:
        count: int              粒子数量 (默认 100)
        particle:
            size: {min, max}    粒子大小范围 (默认 2~6)
            speed: {min, max}   速度范围 (默认 10~50)
            lifetime: {min, max} 生命周期范围 (默认 2~5)
            behavior: str       行为模式 (默认 'drift')
            gravity: float      重力 (bounce 模式, 默认 200)
        connect:                连线配置
            enabled: bool        是否连线 (默认 False)
            max_distance: float 最大连线距离 (默认 100)
            line_width: int     线宽 (默认 1)
    """

    BEHAVIORS = ('drift', 'orbit', 'fall', 'rise', 'bounce')

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.count = config.get('count', 100)
        pcfg = config.get('particle', {})

        sz = pcfg.get('size', {'min': 2, 'max': 6}) if isinstance(pcfg.get('size'), dict) else {'min': 2, 'max': 6}
        spd = pcfg.get('speed', {'min': 10, 'max': 50}) if isinstance(pcfg.get('speed'), dict) else {'min': 10, 'max': 50}
        life = pcfg.get('lifetime', {'min': 2, 'max': 5}) if isinstance(pcfg.get('lifetime'), dict) else {'min': 2, 'max': 5}

        self.p_size_min = sz.get('min', 2)
        self.p_size_max = sz.get('max', 6)
        self.p_speed_min = spd.get('min', 10)
        self.p_speed_max = spd.get('max', 50)
        self.p_life_min = life.get('min', 2)
        self.p_life_max = life.get('max', 5)
        self.behavior = pcfg.get('behavior', 'drift')
        self.gravity = pcfg.get('gravity', 200.0)

        conn = config.get('connect', {})
        self.connect_enabled = conn.get('enabled', False)
        self.connect_max_dist = conn.get('max_distance', 100)
        self.connect_lw = conn.get('line_width', 1)

        bx, by = self.x, self.y
        self.bbox = (bx, by, bx + self.w, by + self.h)

        self.particles = []
        for _ in range(self.count):
            self.particles.append(self._spawn_particle(random.random()))

    def _spawn_particle(self, age_frac: float = 0.0):
        bx, by, bw, bh = self.bbox
        x = random.uniform(bx, bx + bw)
        y = random.uniform(by, by + bh)
        life = random.uniform(self.p_life_min, self.p_life_max)
        return {
            'x': x, 'y': y,
            'vx': random.uniform(-self.p_speed_max, self.p_speed_max),
            'vy': random.uniform(-self.p_speed_max, self.p_speed_max),
            'size': random.uniform(self.p_size_min, self.p_size_max),
            'life': life,
            'age': life * age_frac,
            'max_life': life,
            'angle': random.uniform(0, math.pi * 2),
            'radius': random.uniform(30, 200),
            'orbit_speed': random.uniform(0.2, 1.0),
        }

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        bx, by, br = self.bbox[0], self.bbox[1], self.bbox[0] + self.w
        bb = self.bbox[3]

        for p in self.particles:
            p['age'] += dt
            if p['age'] >= p['max_life']:
                # 重生
                new_p = self._spawn_particle()
                for k in new_p:
                    p[k] = new_p[k]
                continue

            life_frac = 1.0 - p['age'] / p['max_life']

            if self.behavior == 'drift':
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                if p['x'] < bx: p['x'] = bx + self.w; p['vx'] *= -0.5
                if p['x'] > br: p['x'] = bx; p['vx'] *= -0.5
                if p['y'] < by: p['y'] = bb; p['vy'] *= -0.5
                if p['y'] > bb: p['y'] = by; p['vy'] *= -0.5

            elif self.behavior == 'orbit':
                p['angle'] += p['orbit_speed'] * dt
                p['x'] = self.cx + math.cos(p['angle']) * p['radius']
                p['y'] = self.cy + math.sin(p['angle']) * p['radius']

            elif self.behavior == 'fall':
                p['vy'] += self.gravity * dt
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                if p['y'] > bb:
                    p['y'] = bb
                    p['vy'] *= -0.5

            elif self.behavior == 'rise':
                p['vy'] -= self.gravity * 0.5 * dt
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                if p['y'] < by:
                    p['y'] = bb
                    p['vy'] = -abs(p['vy']) * 0.5

            elif self.behavior == 'bounce':
                p['vy'] += self.gravity * dt
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                if p['x'] < bx or p['x'] > br: p['vx'] *= -0.9
                if p['y'] > bb:
                    p['y'] = bb
                    p['vy'] *= -0.7

    def draw(self, drawer: ImageDraw.ImageDraw):
        px_list = []
        for i, p in enumerate(self.particles):
            life_frac = max(0, 1.0 - p['age'] / p['max_life'])
            energy = self._get_audio_value('particle_size', i, default=0.5)
            sz = p['size'] * (0.5 + life_frac * 0.5) * (0.5 + energy * 1.5)
            alpha = int(min(255, life_frac * 255))
            color = self._get_color(i, self.count, energy)
            color_with_alpha = tuple(min(255, c * alpha // 255) for c in color[:3])
            drawer.ellipse([p['x'] - sz, p['y'] - sz, p['x'] + sz, p['y'] + sz], fill=color_with_alpha)
            px_list.append((p['x'], p['y']))

        # 连线
        if self.connect_enabled and len(px_list) >= 2:
            max_d2 = self.connect_max_dist ** 2
            for i in range(len(px_list)):
                for j in range(i + 1, len(px_list)):
                    dx = px_list[i][0] - px_list[j][0]
                    dy = px_list[i][1] - px_list[j][1]
                    d2 = dx * dx + dy * dy
                    if d2 < max_d2:
                        alpha = int(255 * (1 - d2 / max_d2) * 0.3)
                        color = self._get_color(i, self.count, 0)
                        line_color = tuple(min(255, c * alpha // 255) for c in color[:3])
                        drawer.line([px_list[i], px_list[j]], fill=line_color, width=self.connect_lw)
