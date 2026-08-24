"""
曲线原语 — 参数方程曲线绘制

支持的预设:
  cardioid — 心形线: x=16sin^3(t), y=13cos(t)-5cos(2t)-2cos(3t)-cos(4t)
  rose     — 玫瑰线: r=cos(k*t)
  flower   — 花瓣曲线 (带音频驱动的径向变形)
  lemniscate — 双纽线(无穷符号)
  custom   — 自定义参数方程
  formula  — 公式模式: 使用数学表达式定义曲线（新增）

配置:
  preset: str      预设名
  steps: int        点数
  scale: float      缩放
  line_width: int   线宽
  layers: int       层数(仅 rose/flower)
  params: dict      自定义参数 (仅 custom): {x: "expr", y: "expr", t_min, t_max}
  formula: dict     公式模式参数 (仅 formula): {x: "expr", y: "expr", t_min, t_max, t_step}
"""
import math
import numpy as np
from engine.formula_engine import FormulaEngine
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('curve')
class CurvePrimitive(RenderPrimitive):
    """参数曲线

    配置:
        preset: str       'cardioid'/'rose'/'flower'/'lemniscate'/'custom'
        steps: int         点数
        scale: float       缩放
        layers: int        层数
        line_width: int    线宽
    """

    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.preset = config.get('preset', 'cardioid')
        self.steps = config.get('steps', 100)
        self.layer_count = config.get('layers', 3)
        self.line_width = config.get('line_width', 2)
        self.mirror = config.get('mirror', False)
        
        # 根据屏幕分辨率自动计算缩放比例
        # cardioid 公式已归一化到 [-1, 1]，scale 表示距中心的最大像素半径
        screen_scale = int(min(self.width, self.height) * 0.45)
        
        # 新增：formula 模式
        if self.preset == 'formula':
            self._init_formula_mode(config.get('formula', {}))
            return
        
        if self.preset == 'cardioid':
            # 心形线始终根据屏幕自适应，忽略 JSON 中的固定 scale 值
            self.curve_scale = screen_scale
        else:
            self.curve_scale = config.get('scale', screen_scale)
        # 存储基础缩放值，用于心脏跳动效果
        self._base_scale = self.curve_scale

    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)

    def _eval_cardioid(self, t):
        # 归一化到 [-1, 1] 范围，除以 16（原始最大 x 值）
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2*t) -
              2 * math.cos(3*t) - math.cos(4*t))
        return x / 16.0, y / 16.0

    def _eval_rose(self, t):
        n_petals = 6
        k = n_petals
        r = math.cos(k * t)
        return r * math.cos(t), r * math.sin(t)

    def _eval_lemniscate(self, t):
        a = 1.0
        denom = 1 + math.sin(t) ** 2
        x = a * math.cos(t) / denom
        y = a * math.sin(t) * math.cos(t) / denom
        return x, y

    def _eval_flower(self, t, petal_idx, n_petals):
        a = (petal_idx / n_petals) * math.pi * 2
        r = 1.0 + t * 3 + math.sin(t * math.pi * 4) * 0.8
        return r * math.cos(a + t * 0.5), r * math.sin(a + t * 0.5)

    def draw(self, drawer):
        cx, cy = self.cx, self.cy
        t_val = self._time
        sc = self.curve_scale

        if self.preset == 'cardioid':
            for layer in range(self.layer_count):
                ls = sc * (1 - layer * 0.2)
                pts = []
                for i in range(self.steps):
                    t = (i / (self.steps - 1)) * math.pi * 2
                    bx, by = self._eval_cardioid(t)
                    e = self._get_audio_value('value', int(i/self.steps*64))
                    r = ls * (1 + e * 0.3)
                    pts.append((cx + bx * r, cy + by * r))
                color = self._get_color(layer, self.layer_count, 0)
                for pi in range(len(pts) - 1):
                    drawer.line([pts[pi], pts[pi+1]], fill=color, width=self.line_width)
            # 心脏跳动缩放（基于基础缩放值，不再使用硬编码的 80）
            avg_e = sum(self._audio.get_band_energy(i) for i in range(32)) / 32
            target_scale = self._base_scale * (1.0 + avg_e)
            self.curve_scale += (target_scale - self.curve_scale) * 0.3

        elif self.preset == 'rose':
            for layer in range(self.layer_count):
                ls = sc * (1 - layer * 0.2)
                pts = []
                for i in range(self.steps):
                    t = (i / (self.steps - 1)) * math.pi * 2
                    bx, by = self._eval_rose(t + layer * 0.15)
                    e = self._get_audio_value('value', int(i/self.steps*64))
                    r = ls * (0.5 + e * 0.5)
                    pts.append((cx + bx * r, cy + by * r))
                color = self._get_color(layer, self.layer_count, 0)
                for pi in range(len(pts) - 1):
                    drawer.line([pts[pi], pts[pi+1]], fill=color, width=self.line_width)

        elif self.preset == 'lemniscate':
            for layer in range(self.layer_count):
                ls = sc * (1 - layer * 0.15)
                pts = []
                for i in range(self.steps):
                    t = (i / (self.steps - 1) - 0.5) * math.pi * 2
                    bx, by = self._eval_lemniscate(t + layer * 0.2)
                    e = self._get_audio_value('value', int(i/self.steps*64))
                    r = ls * (0.5 + e * 0.5)
                    pts.append((cx + bx * r, cy + by * r))
                color = self._get_color(layer, self.layer_count, 0)
                for pi in range(len(pts) - 1):
                    drawer.line([pts[pi], pts[pi+1]], fill=color, width=self.line_width)

        elif self.preset == 'flower':
            n_petals = 6
            for petal in range(n_petals):
                pts = []
                for i in range(self.steps // 2):
                    t = i / (self.steps // 2 - 1)
                    bx, by = self._eval_flower(t, petal, n_petals)
                    e = self._get_audio_value('value', int(t*64))
                    r = sc * (0.5 + t * 1.5 + e * 0.5)
                    pts.append((cx + bx * r, cy + by * r))
                color = self._get_color(petal, n_petals, 0)
                for pi in range(len(pts) - 1):
                    drawer.line([pts[pi], pts[pi+1]], fill=color, width=self.line_width)
        
        elif self.preset == 'formula':
            # 公式模式：使用数学表达式绘制曲线
            self._draw_formula(drawer)
    
    def _eval_formula_value(self, value):
        """求值公式配置中的单个值（支持数值常量或字符串表达式）"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
            # 字符串表达式 — 用公式引擎求值
            if not hasattr(self, 'engine'):
                self.engine = FormulaEngine()
            try:
                func, _ = self.engine.compile(value, [])
                result = self.engine.evaluate(func)
                return float(result)
            except Exception:
                pass
            # 尝试 eval（支持 pi, e, sin, cos 等简单常量表达式）
            try:
                return float(eval(value, {'pi': math.pi, 'e': math.e, '__builtins__': {}}))
            except Exception:
                pass
        return 2 * math.pi

    def _init_formula_mode(self, formula_config: dict):
        """初始化公式模式"""
        self.engine = FormulaEngine()
        self.formula_config = formula_config
        
        # 获取 t 范围（支持数值和字符串表达式如 "2*pi"）
        self.t_min = self._eval_formula_value(formula_config.get('t_min', 0))
        self.t_max = self._eval_formula_value(formula_config.get('t_max', 2 * math.pi))
        self.t_step = self._eval_formula_value(formula_config.get('t_step', 0.1))
        
        # 编译 x, y 公式
        self.x_func = None
        self.y_func = None
        
        if 'x' in formula_config:
            x_expr = formula_config['x']
            x_vars = self._extract_variables(x_expr)
            self.x_func = self.engine.compile(x_expr, x_vars)
        
        if 'y' in formula_config:
            y_expr = formula_config['y']
            y_vars = self._extract_variables(y_expr)
            self.y_func = self.engine.compile(y_expr, y_vars)
        
        # 设置缩放
        screen_scale = int(min(self.width, self.height) * 0.45)
        self.curve_scale = formula_config.get('scale', screen_scale)
        self._base_scale = self.curve_scale
        
        # 预计算 t 值
        self.t_vals = np.arange(self.t_min, self.t_max, self.t_step)
    
    def _draw_formula(self, drawer):
        """绘制公式曲线"""
        cx, cy = self.cx, self.cy
        sc = self.curve_scale
        
        pts = []
        for t in self.t_vals:
            kwargs = {'t': t, 'time': self._time}
            
            # 计算 x, y
            if self.x_func:
                x = float(self.engine.evaluate(self.x_func, **kwargs))
            else:
                x = math.cos(t)  # 默认：单位圆
            
            if self.y_func:
                y = float(self.engine.evaluate(self.y_func, **kwargs))
            else:
                y = math.sin(t)  # 默认：单位圆
            
            # 坐标变换：归一化坐标 -> 屏幕坐标
            x_pixel = cx + x * sc
            y_pixel = cy + y * sc
            pts.append((x_pixel, y_pixel))
        
        if len(pts) < 2:
            return
        
        # 绘制曲线
        color = self._get_color(0, 1, 0)
        for i in range(len(pts) - 1):
            drawer.line([pts[i], pts[i+1]], fill=color, width=self.line_width)
    
    def _extract_variables(self, expr: str) -> list:
        """从公式表达式中提取变量名"""
        return self.engine._extract_variables(expr)
