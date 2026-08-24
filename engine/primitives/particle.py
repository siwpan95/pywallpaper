"""
粒子系统原语 — Particle System Visual Effect
==============================================
支持：
1. 粒子发射器（位置、速率、生命周期）
2. 力场（重力、风力、吸引力）
3. 音频驱动（音量→发射速率，频率→颜色/大小）
4. 多种粒子类型（点、圆、线、尾迹）

配置示例:
  {
    "type": "particle",
    "emitters": [
      {
        "position": [0.5, 0.5],  // 归一化坐标
        "rate": 10,                 // 每秒发射粒子数
        "lifetime": [1.0, 3.0],   // 生命周期范围（秒）
        "speed": [50, 150],         // 速度范围（像素/秒）
        "direction": [0, 360],      // 方向范围（度）
        "color": [255, 128, 0],    // 基础颜色
        "size": [2, 5]             // 大小范围
      }
    ],
    "forces": [
      {"type": "gravity", "y": 200},  // 重力
      {"type": "wind", "x": 50}       // 风力
    ],
    "audio_modulation": {
      "rate": "rms * 50 + 10",           // 音量控制发射速率
      "color_hue": "band_energy(0) * 360" // 低频控制色相
    },
    "particle_type": "circle",  // point, circle, line, trail
    "max_particles": 1000
  }

依赖:
  - numpy (粒子属性数组)
  - PIL (绘制)
"""
import numpy as np
from PIL import Image, ImageDraw
from engine.formula_engine import FormulaEngine
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('particle')
class ParticlePrimitive(RenderPrimitive):
    """
    粒子系统原语 — 高效的粒子模拟与渲染
    """
    
    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        
        # 粒子系统配置
        self.emitters = config.get('emitters', [{
            'position': [0.5, 0.5],
            'rate': 10,
            'lifetime': [1.0, 3.0],
            'speed': [50, 150],
            'direction': [0, 360],
            'color': [255, 255, 255],
            'size': [2, 5]
        }])
        
        self.forces = config.get('forces', [])
        self.particle_type = config.get('particle_type', 'circle')
        self.max_particles = config.get('max_particles', 1000)
        
        # 音频调制配置
        self.audio_modulation = config.get('audio_modulation', {})
        self.engine = FormulaEngine()
        self.audio_funcs = {}
        for param, expr in self.audio_modulation.items():
            variables = self.engine._extract_variables(expr)
            self.audio_funcs[param] = (self.engine.compile(expr, variables), variables)
        
        # 粒子数据存储（使用结构化数组）
        self._init_particle_storage()
        
        # 颜色调制状态
        self.color_hue = 0.0
        self.color_sat = 1.0
        self.color_val = 1.0
        
        # 累加器（用于发射速率控制）
        self._emit_accumulator = 0.0
        
    def _init_particle_storage(self):
        """初始化粒子数据存储"""
        # 使用分离数组存储粒子属性（性能优于结构化数组）
        self._count = 0  # 当前粒子数
        
        # 预分配数组
        self._x = np.zeros(self.max_particles, dtype=np.float32)      # x 坐标
        self._y = np.zeros(self.max_particles, dtype=np.float32)      # y 坐标
        self._vx = np.zeros(self.max_particles, dtype=np.float32)    # x 速度
        self._vy = np.zeros(self.max_particles, dtype=np.float32)    # y 速度
        self._life = np.zeros(self.max_particles, dtype=np.float32)   # 剩余生命
        self._max_life = np.zeros(self.max_particles, dtype=np.float32)  # 总生命
        self._size = np.zeros(self.max_particles, dtype=np.float32)  # 大小
        self._color = np.zeros((self.max_particles, 3), dtype=np.uint8)  # 颜色
        
        # 尾迹历史（仅用于 trail 类型）
        self._trail_len = 10
        self._trail = np.zeros((self.max_particles, self._trail_len, 2), dtype=np.float32)
        
    def _emit_particle(self, emitter: dict, dt: float):
        """发射粒子"""
        # 计算发射数量
        rate = emitter.get('rate', 10)
        
        # 应用音频调制
        for param, (func, variables) in self.audio_funcs.items():
            if param == 'rate':
                try:
                    kwargs = {v: self._get_audio_value(v) for v in variables}
                    rate = max(0, int(self.engine.evaluate(func, **kwargs)))
                except:
                    pass
        
        self._emit_accumulator += rate * dt
        emit_count = int(self._emit_accumulator)
        self._emit_accumulator -= emit_count
        
        # 发射粒子
        for _ in range(emit_count):
            if self._count >= self.max_particles:
                break
            
            idx = self._count
            
            # 位置（归一化坐标 → 像素坐标）
            pos = emitter.get('position', [0.5, 0.5])
            self._x[idx] = pos[0] * self.width
            self._y[idx] = pos[1] * self.height
            
            # 速度（极坐标 → 直角坐标）
            speed_range = emitter.get('speed', [50, 150])
            direction_range = emitter.get('direction', [0, 360])
            
            speed = np.random.uniform(*speed_range)
            direction = np.radians(np.random.uniform(*direction_range))
            
            self._vx[idx] = speed * np.cos(direction)
            self._vy[idx] = speed * np.sin(direction)
            
            # 生命周期
            lifetime_range = emitter.get('lifetime', [1.0, 3.0])
            self._life[idx] = np.random.uniform(*lifetime_range)
            self._max_life[idx] = self._life[idx]
            
            # 大小
            size_range = emitter.get('size', [2, 5])
            self._size[idx] = np.random.uniform(*size_range)
            
            # 颜色（应用音频调制）
            color = emitter.get('color', [255, 255, 255])
            if 'color_hue' in self.audio_modulation:
                # HSV 调制（纯 numpy 实现，不依赖 colorsys）
                r, g, b = color[0]/255, color[1]/255, color[2]/255
                # 简化：直接用 HSV 到 RGB 的近似转换
                h = (self.color_hue % 360) / 360.0
                s = self.color_sat
                v = self.color_val
                # 使用 PIL 的 HSV 转换
                from PIL import ImageColor
                rgb = ImageColor.getrgb(f"hsv({int(h*360)},{int(s*100)}%,{int(v*100)}%)")
                color = list(rgb)
            self._color[idx] = color
            
            self._count += 1
        
    def _apply_forces(self, dt: float):
        """应用力场"""
        for force in self.forces:
            ftype = force.get('type', 'gravity')
            
            if ftype == 'gravity':
                self._vy -= force.get('y', 200) * dt
                
            elif ftype == 'wind':
                self._vx += force.get('x', 50) * dt
                
            elif ftype == 'attract':
                # 吸引力（指向某点）
                ax, ay = force.get('position', [0.5, 0.5])
                ax *= self.width
                ay *= self.height
                strength = force.get('strength', 100)
                
                for i in range(self._count):
                    dx = ax - self._x[i]
                    dy = ay - self._y[i]
                    dist = np.sqrt(dx*dx + dy*dy) + 1e-5
                    self._vx[i] += strength * dx / dist * dt
                    self._vy[i] += strength * dy / dist * dt
                    
    def _update_particles(self, dt: float):
        """更新粒子状态"""
        # 应用力场
        self._apply_forces(dt)
        
        # 更新位置
        self._x[:self._count] += self._vx[:self._count] * dt
        self._y[:self._count] += self._vy[:self._count] * dt
        
        # 更新生命
        self._life[:self._count] -= dt
        
        # 更新尾迹
        if self.particle_type == 'trail':
            for i in range(self._count):
                # 将当前位置插入尾迹开头
                self._trail[i] = np.roll(self._trail[i], 1, axis=0)
                self._trail[i, 0] = [self._x[i], self._y[i]]
        
        # 移除死亡粒子（压缩数组）
        alive = self._life[:self._count] > 0
        new_count = alive.sum()
        
        if new_count < self._count:
            # 压缩数组
            self._x[:new_count] = self._x[:self._count][alive]
            self._y[:new_count] = self._y[:self._count][alive]
            self._vx[:new_count] = self._vx[:self._count][alive]
            self._vy[:new_count] = self._vy[:self._count][alive]
            self._life[:new_count] = self._life[:self._count][alive]
            self._max_life[:new_count] = self._max_life[:self._count][alive]
            self._size[:new_count] = self._size[:self._count][alive]
            self._color[:new_count] = self._color[:self._count][alive]
            self._trail[:new_count] = self._trail[:self._count][alive]
            self._count = new_count
        
    def update(self, dt: float, audio, global_time):
        """更新粒子系统"""
        super().update(dt, audio, global_time)
        
        # 应用音频调制
        self._apply_audio_modulation(audio)
        
        # 发射新粒子
        for emitter in self.emitters:
            self._emit_particle(emitter, dt)
            
        # 更新现有粒子
        self._update_particles(dt)
        
    def _apply_audio_modulation(self, audio):
        """应用音频调制"""
        for param, (func, variables) in self.audio_funcs.items():
            try:
                kwargs = {}
                for v in variables:
                    if v == 'rms':
                        kwargs[v] = audio.get_rms() if hasattr(audio, 'get_rms') else 0.5
                    elif v == 'beat':
                        kwargs[v] = 1.0 if (hasattr(audio, 'detect_beat') and audio.detect_beat()) else 0.0
                    elif v.startswith('band_energy_'):
                        # 下划线格式：band_energy_0, band_energy_1, ...
                        try:
                            idx = int(v.split('_')[-1])
                        except ValueError:
                            idx = 0
                        kwargs[v] = audio.get_band_energy(idx) if hasattr(audio, 'get_band_energy') else 0.5
                    else:
                        kwargs[v] = self._time
                        
                value = float(self.engine.evaluate(func, **kwargs))
                
                if param == 'color_hue':
                    self.color_hue = value % 360
                elif param == 'color_sat':
                    self.color_sat = max(0, min(1, value))
                elif param == 'color_val':
                    self.color_val = max(0, min(1, value))
                    
            except Exception as e:
                print(f"[Particle] 音频调制错误: {e}")
        
    def draw(self, drawer):
        """绘制粒子"""
        if self._count == 0:
            return
            
        if self.particle_type == 'point':
            # 绘制点
            for i in range(self._count):
                alpha = self._life[i] / self._max_life[i]
                color = tuple(self._color[i])
                drawer.point((self._x[i], self._y[i]), fill=color)
                
        elif self.particle_type == 'circle':
            # 绘制圆
            for i in range(self._count):
                alpha = self._life[i] / self._max_life[i]
                r = int(self._size[i] * alpha)
                color = tuple(self._color[i])
                drawer.ellipse([
                    self._x[i] - r, self._y[i] - r,
                    self._x[i] + r, self._y[i] + r
                ], fill=color)
                
        elif self.particle_type == 'trail':
            # 绘制尾迹
            for i in range(self._count):
                alpha = self._life[i] / self._max_life[i]
                color = tuple(self._color[i])
                
                # 绘制尾迹线段
                trail = self._trail[i]
                for j in range(len(trail) - 1):
                    if trail[j, 0] > 0 and trail[j+1, 0] > 0:
                        drawer.line(
                            [tuple(trail[j]), tuple(trail[j+1])],
                            fill=color,
                            width=int(self._size[i] * alpha)
                        )
                        
    def _get_audio_value(self, var_name: str):
        """获取音频相关值（用于公式求值）"""
        # 简化实现：返回 0.5
        return 0.5
        
    def get_debug_info(self) -> dict:
        """获取调试信息"""
        return {
            'particle_count': self._count,
            'max_particles': self.max_particles,
            'emitters': len(self.emitters),
            'forces': len(self.forces)
        }
