"""
formula 原语 — 通用公式原语，支持用数学表达式定义视觉效果

支持的模式:
  1. 静态公式模式: 用户定义 x, y 表达式
  2. 音频驱动模式: 公式参数由音频数据调制
  3. CA 配方模式: 引用 draw 的 CA 配方

配置示例 1（静态公式）:
  {
    "type": "formula",
    "formula": {
      "x": "t*cos(t)",
      "y": "t*sin(t)",
      "t_min": 0,
      "t_max": 12.56,
      "t_step": 0.1
    }
  }

配置示例 2（音频驱动）:
  {
    "type": "formula",
    "formula": {
      "r": "1 + audio_band(0)*2",
      "theta": "t + audio_band(32)*0.5",
      "x": "r*cos(theta)",
      "y": "r*sin(theta)"
    },
    "audio_vars": ["audio_band(0)", "audio_band(32)"]
  }

配置示例 3（引用内置模板）:
  {
    "type": "formula",
    "template": "spiral",
    "audio_modulation": {
      "t": "t + beat*0.5"
    }
  }
"""
import numpy as np
from engine.formula_engine import FormulaEngine
from engine.primitives import register_primitive, RenderPrimitive


@register_primitive('formula')
class FormulaPrimitive(RenderPrimitive):
    """通用公式原语 — 用数学表达式定义视觉效果
    
    支持的模式:
        - static: 静态公式（x, y 表达式）
        - audio_driven: 音频驱动公式
        - template: 引用内置模板
        - ca_recipe: 引用 draw 的 CA 配方（待实现）
    """
    
    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        self.engine = FormulaEngine()
        self.mode = 'static'
        
        # 加载公式配置
        if 'formula' in config:
            self._init_formula_mode(config['formula'])
        elif 'template' in config:
            self._init_template_mode(config['template'], config.get('audio_modulation', {}))
        elif 'recipe' in config:
            self._init_ca_recipe_mode(config['recipe'])
        else:
            # 默认: 心形线
            self._init_template_mode('cardioid', {})
        
        # 预计算 t 值
        if hasattr(self, 't_min') and hasattr(self, 't_max') and hasattr(self, 't_step'):
            self.t_vals = np.arange(self.t_min, self.t_max, self.t_step)
        else:
            self.t_vals = np.linspace(0, 2*np.pi, 100)
        
        # 点连接的阈值（像素）
        self.close_threshold = config.get('close_threshold', 5)
        self.line_width = config.get('line_width', 2)
        self.fill = config.get('fill', False)
        
    def _init_formula_mode(self, formula_config: dict):
        """初始化公式模式"""
        self.mode = 'formula'
        
        # 编译所有公式
        self.formula_funcs = {}
        for var_name, expr in formula_config.items():
            if var_name in ('t_min', 't_max', 't_step'):
                setattr(self, var_name, eval(expr) if isinstance(expr, str) else expr)
            else:
                variables = self._extract_variables(expr)
                self.formula_funcs[var_name] = self.engine.compile(expr, variables)
        
        # 设置默认值
        if not hasattr(self, 't_min'):
            self.t_min = 0
        if not hasattr(self, 't_max'):
            self.t_max = 2 * np.pi
        if not hasattr(self, 't_step'):
            self.t_step = 0.1
    
    def _init_template_mode(self, template_name: str, audio_modulation: dict):
        """初始化模板模式"""
        self.mode = 'template'
        self.template_name = template_name
        self.audio_modulation = audio_modulation
        
        # 从引擎获取模板配置
        if template_name not in self.engine.TEMPLATES:
            raise ValueError(f"模板 '{template_name}' 不存在")
        
        template = self.engine.TEMPLATES[template_name]
        
        # 设置 t 范围
        self.t_min = template.get('t_min', 0)
        self.t_max = template.get('t_max', 2*np.pi)
        self.t_step = template.get('t_step', 0.1)
        
        # 编译 x, y 公式
        self.formula_funcs = {}
        for var_name in ['x', 'y', 'r', 'theta']:
            if var_name in template:
                expr = template[var_name]
                variables = self.engine._extract_variables(expr)
                self.formula_funcs[var_name] = self.engine.compile(expr, variables)
        
        # 编译音频调制公式
        self.audio_funcs = {}
        for var_name, expr in audio_modulation.items():
            variables = self.engine._extract_variables(expr)
            self.audio_funcs[var_name] = self.engine.compile(expr, variables)
    
    def _init_ca_recipe_mode(self, recipe_name: str):
        """初始化 CA 配方模式（待实现）"""
        self.mode = 'ca_recipe'
        self.recipe_name = recipe_name
        # TODO: 集成 draw 的 CA 引擎
        raise NotImplementedError("CA 配方模式待实现，请先使用其他模式")
    
    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        
        # 更新音频调制参数
        if self.mode == 'template' and self.audio_modulation:
            self._update_audio_modulation(audio)
    
    def _update_audio_modulation(self, audio):
        """更新音频调制参数"""
        # 计算音频调制后的变量值
        self.audio_modulated_values = {}
        
        for var_name, func in self.audio_funcs.items():
            # 获取音频数据
            kwargs = {}
            # 这里需要根据公式中的变量名获取对应的音频数据
            # 简化版本: 假设公式中直接使用 audio.xxx 变量
            # 实际应该解析公式中的音频变量
            kwargs['t'] = self._time
            
            # 执行音频调制公式
            try:
                result = self.engine.evaluate(func, **kwargs)
                self.audio_modulated_values[var_name] = result
            except Exception as e:
                print(f"[FormulaPrimitive] 音频调制错误: {e}")
    
    def draw(self, drawer):
        """绘制公式曲线"""
        if self.mode in ('formula', 'template'):
            points = self._evaluate_formulas()
            
            if len(points) < 2:
                return
            
            # 绘制曲线
            color = self._get_color(0, 1, 0)
            
            if self.fill:
                # 填充模式
                drawer.polygon(points, fill=color)
            else:
                # 线条模式
                for i in range(len(points) - 1):
                    # 检查是否需要断开连接（处理周期性）
                    dist = ((points[i][0] - points[i+1][0])**2 + 
                            (points[i][1] - points[i+1][1])**2)**0.5
                    
                    if dist < self.close_threshold * 10:  # 放宽阈值
                        drawer.line([points[i], points[i+1]], 
                                  fill=color, width=self.line_width)
    
    def _evaluate_formulas(self) -> list:
        """执行所有公式，返回点坐标列表"""
        points = []
        
        for t in self.t_vals:
            # 构造变量字典
            kwargs = {'t': t, 'time': self._time}
            
            # 计算所有公式
            for var_name, func in self.formula_funcs.items():
                try:
                    value = self.engine.evaluate(func, **kwargs)
                    kwargs[var_name] = float(value)
                except Exception as e:
                    print(f"[FormulaPrimitive] 公式计算错误: {e}")
                    kwargs[var_name] = 0.0
            
            # 处理极坐标（如果有 r 和 theta）
            if 'r' in kwargs and 'theta' in kwargs:
                kwargs['x'] = kwargs['r'] * np.cos(kwargs['theta'])
                kwargs['y'] = kwargs['r'] * np.sin(kwargs['theta'])
            
            # 得到 (x, y)
            if 'x' in kwargs and 'y' in kwargs:
                # 坐标变换: 归一化坐标 -> 屏幕坐标
                x = self.cx + kwargs['x'] * self.w * 0.5
                y = self.cy + kwargs['y'] * self.h * 0.5
                points.append((x, y))
        
        return points
    
    def _extract_variables(self, expr: str) -> list:
        """从公式表达式中提取变量名"""
        return self.engine._extract_variables(expr)
