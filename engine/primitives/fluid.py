"""
流体模拟原语 — Fluid Simulation (Stable Fluids)
==============================================
支持：
1. 基于 Navier-Stokes 方程的简化流体模拟
2. 密度场（dye）和速度场（velocity）
3. 平流（advection）、扩散（diffusion）、施加力（apply force）
4. 音频驱动（音量→施加力，频率→密度源）
5. 实时渲染到 PIL Image

配置示例:
  {
    "type": "fluid",
    "grid_size": [64, 64],
    "viscosity": 0.000001,    // 粘度
    "diffusion": 0.0001,       // 扩散率
    "force": 5.0,               // 施加力的大小
    "audio_modulation": {
      "force_x": "band_energy(0) * 10",  // 低频控制 x 方向力
      "force_y": "band_energy(32) * 10", // 高频控制 y 方向力
      "source": "rms * 0.1"               // 音量控制密度源
    },
    "color_map": "fire",       // 颜色映射（fire, ocean, rainbow）
    "postprocess": ["bloom"]
  }

算法（简化 Stable Fluids）:
  1. 施加外力（add force）
  2. 平流（advect density & velocity）
  3. 扩散（diffuse density & velocity）
  4. 投影（project velocity to be divergence-free）— 可选
  5. 边界处理（boundary conditions）

依赖:
  - numpy (网格计算)
  - PIL (渲染)
  - scipy (可选，用于解线性系统)
"""
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from engine.formula_engine import FormulaEngine
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('fluid')
class FluidPrimitive(RenderPrimitive):
    """
    流体模拟原语 — 简化的 Stable Fluids 算法
    """
    
    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        
        # 流体模拟配置
        self.grid_size = config.get('grid_size', [64, 64])
        self.viscosity = config.get('viscosity', 0.000001)
        self.diffusion = config.get('diffusion', 0.0001)
        self.force_strength = config.get('force', 5.0)
        
        # 颜色映射
        self.color_map = config.get('color_map', 'fire')
        
        # 音频调制配置
        self.audio_modulation = config.get('audio_modulation', {})
        self.engine = FormulaEngine()
        self.audio_funcs = {}
        for param, expr in self.audio_modulation.items():
            variables = self.engine._extract_variables(expr)
            self.audio_funcs[param] = (self.engine.compile(expr, variables), variables)
        
        # 后处理配置
        self.postprocess = config.get('postprocess', [])
        
        # 初始化流体场
        self._init_fluid_fields()
        
        # 预分配图像缓冲区
        self._image = Image.new('RGB', (self.grid_size[0], self.grid_size[1]))
        self._pixels = self._image.load()
        
    def _init_fluid_fields(self):
        """初始化流体场"""
        w, h = self.grid_size
        
        # 密度场（dye）
        self.density = np.zeros((h, w), dtype=np.float32)
        
        # 速度场（u: x方向, v: y方向）
        self.u = np.zeros((h, w), dtype=np.float32)
        self.v = np.zeros((h, w), dtype=np.float32)
        
        # 临时数组
        self._tmp = np.zeros((h, w), dtype=np.float32)
        self._divergence = np.zeros((h, w), dtype=np.float32)
        self._pressure = np.zeros((h, w), dtype=np.float32)
        
        # 边界条件标志
        self._boundary = np.zeros((h, w), dtype=np.uint8)
        self._boundary[0, :] = 1   # 上边界
        self._boundary[-1, :] = 1   # 下边界
        self._boundary[:, 0] = 1     # 左边界
        self._boundary[:, -1] = 1    # 右边界
        
    def update(self, dt: float, audio, global_time):
        """更新流体模拟"""
        super().update(dt, audio, global_time)
        
        # 应用音频调制
        self._apply_audio_modulation(audio)
        
        # 执行流体模拟步骤
        self._fluid_step(dt)
        
    def _fluid_step(self, dt: float):
        """执行一步流体模拟"""
        # 1. 施加外力
        self._add_force(dt)
        
        # 2. 平流（advection）
        self._advect(dt)
        
        # 3. 扩散（diffusion）
        self._diffuse(dt)
        
        # 4. 投影（projection）— 使速度场无散
        self._project()
        
        # 5. 密度平流和扩散
        self._advect_density(dt)
        self._diffuse_density(dt)
        
        # 6. 边界处理
        self._apply_boundary()
        
    def _add_force(self, dt: float):
        """施加外力"""
        w, h = self.grid_size
        
        # 在中心位置施加力
        cx, cy = w // 2, h // 2
        
        # 音频调制力的大小和方向
        fx = self.force_strength
        fy = self.force_strength
        
        for param, (func, variables) in self.audio_funcs.items():
            try:
                kwargs = {v: self._get_audio_value(v, audio=None) for v in variables}
                value = float(self.engine.evaluate(func, **kwargs))
                
                if param == 'force_x':
                    fx = value
                elif param == 'force_y':
                    fy = value
                elif param == 'source':
                    # 在随机位置添加密度源
                    for _ in range(int(value * 10)):
                        x = np.random.randint(1, w-1)
                        y = np.random.randint(1, h-1)
                        self.density[y, x] += 0.1
                        
            except Exception as e:
                print(f"[Fluid] 音频调制错误: {e}")
        
        # 施加力（简化：在中心位置施加）
        radius = 3
        for dy in range(-radius, radius+1):
            for dx in range(-radius, radius+1):
                if dx*dx + dy*dy <= radius*radius:
                    x, y = cx + dx, cy + dy
                    if 0 <= x < w and 0 <= y < h:
                        self.u[y, x] += fx * dt
                        self.v[y, x] += fy * dt
                        
    def _advect(self, dt: float):
        """平流（advection）— 根据速度场移动速度"""
        w, h = self.grid_size
        
        # 使用半拉格朗日方法（semi-Lagrangian）
        # 对于每个网格点，回溯 dt 时间前的位置
        x = np.arange(w, dtype=np.float32)
        y = np.arange(h, dtype=np.float32)
        X, Y = np.meshgrid(x, y)
        
        # 回溯位置
        src_x = X - self.u * dt
        src_y = Y - self.v * dt
        
        # 限制在网格内
        src_x = np.clip(src_x, 0, w-1)
        src_y = np.clip(src_y, 0, h-1)
        
        # 双线性插值
        x0 = np.floor(src_x).astype(np.int32)
        x1 = x0 + 1
        y0 = np.floor(src_y).astype(np.int32)
        y1 = y0 + 1
        
        x0 = np.clip(x0, 0, w-1)
        x1 = np.clip(x1, 0, w-1)
        y0 = np.clip(y0, 0, h-1)
        y1 = np.clip(y1, 0, h-1)
        
        # 插值权重
        wx = src_x - x0
        wy = src_y - y0
        
        # 执行插值
        self._tmp[:, :] = (
            self.u[y0, x0] * (1-wx) * (1-wy) +
            self.u[y0, x1] * wx * (1-wy) +
            self.u[y1, x0] * (1-wx) * wy +
            self.u[y1, x1] * wx * wy
        )
        self.u[:, :] = self._tmp[:, :]
        
        self._tmp[:, :] = (
            self.v[y0, x0] * (1-wx) * (1-wy) +
            self.v[y0, x1] * wx * (1-wy) +
            self.v[y1, x0] * (1-wx) * wy +
            self.v[y1, x1] * wx * wy
        )
        self.v[:, :] = self._tmp[:, :]
        
    def _diffuse(self, dt: float):
        """扩散（diffusion）— 使用 Jacobi 迭代"""
        w, h = self.grid_size
        
        # 扩散系数
        a = dt * self.diffusion * w * h
        
        # Jacobi 迭代
        for _ in range(20):  # 迭代次数
            self._tmp[:, :] = self.u[:, :]
            self.u[1:-1, 1:-1] = (
                self._tmp[1:-1, 1:-1] +
                a * (
                    self._tmp[1:-1, 2:] + self._tmp[1:-1, :-2] +
                    self._tmp[2:, 1:-1] + self._tmp[:-2, 1:-1]
                )
            ) / (1 + 4*a)
            
            self._tmp[:, :] = self.v[:, :]
            self.v[1:-1, 1:-1] = (
                self._tmp[1:-1, 1:-1] +
                a * (
                    self._tmp[1:-1, 2:] + self._tmp[1:-1, :-2] +
                    self._tmp[2:, 1:-1] + self._tmp[:-2, 1:-1]
                )
            ) / (1 + 4*a)
            
    def _project(self):
        """投影（projection）— 使速度场无散"""
        w, h = self.grid_size
        
        # 计算散度（divergence）
        self._divergence[1:-1, 1:-1] = (
            -0.5 * (
                self.u[1:-1, 2:] - self.u[1:-1, :-2] +
                self.v[2:, 1:-1] - self.v[:-2, 1:-1]
            )
        )
        
        # 求解压力（pressure）— 使用 Jacobi 迭代
        self._pressure[:, :] = 0
        
        for _ in range(20):  # 迭代次数
            self._tmp[:, :] = self._pressure[:, :]
            self._pressure[1:-1, 1:-1] = (
                self._divergence[1:-1, 1:-1] +
                self._tmp[1:-1, 2:] + self._tmp[1:-1, :-2] +
                self._tmp[2:, 1:-1] + self._tmp[:-2, 1:-1]
            ) / 4
        
        # 减去压力梯度
        self.u[1:-1, 1:-1] -= 0.5 * (
            self._pressure[1:-1, 2:] - self._pressure[1:-1, :-2]
        )
        self.v[1:-1, 1:-1] -= 0.5 * (
            self._pressure[2:, 1:-1] - self._pressure[:-2, 1:-1]
        )
        
    def _advect_density(self, dt: float):
        """密度平流"""
        w, h = self.grid_size
        
        # 使用半拉格朗日方法
        x = np.arange(w, dtype=np.float32)
        y = np.arange(h, dtype=np.float32)
        X, Y = np.meshgrid(x, y)
        
        # 回溯位置
        src_x = X - self.u * dt
        src_y = Y - self.v * dt
        
        # 限制在网格内
        src_x = np.clip(src_x, 0, w-1)
        src_y = np.clip(src_y, 0, h-1)
        
        # 双线性插值
        x0 = np.floor(src_x).astype(np.int32)
        x1 = x0 + 1
        y0 = np.floor(src_y).astype(np.int32)
        y1 = y0 + 1
        
        x0 = np.clip(x0, 0, w-1)
        x1 = np.clip(x1, 0, w-1)
        y0 = np.clip(y0, 0, h-1)
        y1 = np.clip(y1, 0, h-1)
        
        # 插值权重
        wx = src_x - x0
        wy = src_y - y0
        
        # 执行插值
        self._tmp[:, :] = (
            self.density[y0, x0] * (1-wx) * (1-wy) +
            self.density[y0, x1] * wx * (1-wy) +
            self.density[y1, x0] * (1-wx) * wy +
            self.density[y1, x1] * wx * wy
        )
        self.density[:, :] = self._tmp[:, :]
        
    def _diffuse_density(self, dt: float):
        """密度扩散"""
        w, h = self.grid_size
        
        # 扩散系数
        a = dt * self.diffusion * w * h
        
        # Jacobi 迭代
        for _ in range(20):
            self._tmp[:, :] = self.density[:, :]
            self.density[1:-1, 1:-1] = (
                self._tmp[1:-1, 1:-1] +
                a * (
                    self._tmp[1:-1, 2:] + self._tmp[1:-1, :-2] +
                    self._tmp[2:, 1:-1] + self._tmp[:-2, 1:-1]
                )
            ) / (1 + 4*a)
            
    def _apply_boundary(self):
        """应用边界条件"""
        w, h = self.grid_size
        
        # 上边界
        self.u[0, :] = -self.u[1, :]
        self.v[0, :] = -self.v[1, :]
        self.density[0, :] = self.density[1, :]
        
        # 下边界
        self.u[-1, :] = -self.u[-2, :]
        self.v[-1, :] = -self.v[-2, :]
        self.density[-1, :] = self.density[-2, :]
        
        # 左边界
        self.u[:, 0] = -self.u[:, 1]
        self.v[:, 0] = -self.v[:, 1]
        self.density[:, 0] = self.density[:, 1]
        
        # 右边界
        self.u[:, -1] = -self.u[:, -2]
        self.v[:, -1] = -self.v[:, -2]
        self.density[:, -1] = self.density[:, -2]
        
    def _apply_audio_modulation(self, audio):
        """应用音频调制"""
        # 简化实现：存储调制后的值，在 _add_force 中使用
        for param, (func, variables) in self.audio_funcs.items():
            try:
                kwargs = {}
                for v in variables:
                    if v == 'rms':
                        kwargs[v] = audio.get_rms() if hasattr(audio, 'get_rms') else 0.5
                    elif v == 'beat':
                        kwargs[v] = 1.0 if (hasattr(audio, 'detect_beat') and audio.detect_beat()) else 0.0
                    elif v.startswith('band_energy'):
                        idx = int(v.split('(')[1].split(')')[0]) if '(' in v else 0
                        kwargs[v] = audio.get_band_energy(idx) if hasattr(audio, 'get_band_energy') else 0.5
                    else:
                        kwargs[v] = self._time
                        
                value = float(self.engine.evaluate(func, **kwargs))
                
                # 存储调制后的值
                setattr(self, f'_mod_{param}', value)
                
            except Exception as e:
                print(f"[Fluid] 音频调制错误: {e}")
                
    def _get_audio_value(self, var_name: str, audio=None):
        """获取音频相关值（用于公式求值）"""
        # 简化实现：返回 0.5
        return 0.5
        
    def draw(self, drawer):
        """渲染流体模拟到 PIL Image"""
        w, h = self.grid_size
        
        # 归一化密度场到 [0, 1]
        d = self.density
        d_min, d_max = d.min(), d.max()
        if d_max - d_min > 1e-5:
            d = (d - d_min) / (d_max - d_min)
        else:
            d = np.zeros_like(d)
            
        # 应用颜色映射
        r, g, b = self._apply_color_map(d)
        
        # 创建图像
        img_array = np.zeros((h, w, 3), dtype=np.uint8)
        img_array[:, :, 0] = (np.clip(r, 0, 1) * 255).astype(np.uint8)
        img_array[:, :, 1] = (np.clip(g, 0, 1) * 255).astype(np.uint8)
        img_array[:, :, 2] = (np.clip(b, 0, 1) * 255).astype(np.uint8)
        
        # 转换为 PIL Image
        img = Image.fromarray(img_array, 'RGB')
        
        # 后处理
        img = self._apply_postprocess(img)
        
        # 缩放并粘贴到 drawer 位置
        draw_w = int(self.w) if self.w > 0 else self.width
        draw_h = int(self.h) if self.h > 0 else self.height
        img = img.resize((draw_w, draw_h), Image.NEAREST)
        drawer._image.paste(img, (int(self.x), int(self.y)))
        
    def _apply_color_map(self, d: np.ndarray):
        """应用颜色映射"""
        if self.color_map == 'fire':
            # 火焰色（黑→红→黄→白）
            r = np.clip(d * 3, 0, 1)
            g = np.clip((d - 0.33) * 3, 0, 1)
            b = np.clip((d - 0.66) * 3, 0, 1)
        elif self.color_map == 'ocean':
            # 海洋色（深蓝→浅蓝→青）
            r = d * 0.1
            g = d * 0.6 + 0.2 * np.sin(d * 15)
            b = d * 0.8 + 0.2
        elif self.color_map == 'rainbow':
            # 彩虹色
            r = 0.5 + 0.5 * np.sin(d * 12)
            g = 0.5 + 0.5 * np.sin(d * 12 + 2.094)
            b = 0.5 + 0.5 * np.sin(d * 12 + 4.189)
        else:
            # 灰度
            r = d
            g = d
            b = d
            
        return r, g, b
        
    def _apply_postprocess(self, img: Image.Image) -> Image.Image:
        """应用后处理效果"""
        for effect in self.postprocess:
            if effect == 'bloom':
                #  Bloom 效果（简单的高斯模糊 + 叠加）
                blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
                img = Image.blend(img, blurred, alpha=0.3)
            elif effect == 'vignette':
                # 暗角效果
                w, h = img.size
                y, x = np.ogrid[:h, :w]
                cx, cy = w / 2, h / 2
                dist = np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2)
                mask = np.clip(1.0 - dist * 0.7, 0.3, 1.0)
                mask = (mask * 255).astype(np.uint8)
                mask_img = Image.fromarray(mask, 'L')
                img = Image.merge('RGB', [Image.fromarray(np.array(img)[:, :, i] * mask // 255) for i in range(3)])
                
        return img
        
    def get_debug_info(self) -> dict:
        """获取调试信息"""
        return {
            'density_min': float(self.density.min()),
            'density_max': float(self.density.max()),
            'velocity_magnitude': float(np.sqrt(self.u**2 + self.v**2).mean())
        }
