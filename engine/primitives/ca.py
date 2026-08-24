"""
CA 原语 — 细胞自动机视觉效果 (v2 - 支持 Numba JIT)

集成 draw 的 CA 引擎，支持：
1. 从 draw 的配方库加载 CA 配方（4973+ 个）
2. 音频驱动 CA 演化（init_seed, steps_per_frame, color_speed 等）
3. 实时渲染到 PIL Image
4. 使用 Numba JIT 编译优化性能（预定义规则）

配置示例:
  {
    "type": "ca",
    "recipe": "BZReaction",  // 可以是完整的文件名，或规则名称（会自动匹配）
    "grid_size": [64, 64],
    "use_jit": true,  // 使用 JIT 编译的核（仅支持预定义规则）
    "audio_modulation": {
      "init_seed": "beat",
      "steps_per_frame": "rms * 10 + 1",
      "color_hue": "band_energy(0) * 360"
    },
    "postprocess": ["bloom", "vignette"]
  }

依赖:
  - numpy (网格计算)
  - asteval (公式编译，当 use_jit=false 时使用)
  - numba (JIT 编译，当 use_jit=true 时使用，可选)
  - PIL (图像渲染，可选)
"""
import os
import json
from pathlib import Path
import numpy as np

# 可选依赖：PIL（用于渲染）
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("[CAPrimitive] 警告：未安装 PIL，渲染功能将不可用")

from engine.formula_engine import FormulaEngine
from engine.primitives import register_primitive, RenderPrimitive

# 尝试导入 JIT 编译的核
HAS_NUMBA = False
try:
    from engine.primitives.ca_kernel import (
        evolve_ca, evolve_game_of_life, evolve_bz_reaction,
        RULE_GAME_OF_LIFE, RULE_BZ_REACTION
    )
    HAS_NUMBA = True
    print("[CAPrimitive] Numba JIT 已启用，CA 演化性能将大幅提升")
except ImportError as e:
    print(f"[CAPrimitive] Numba 未安装，将使用 AST 公式计算（性能较低）: {e}")

# 配方目录：pywallpaper 内置副本（自包含，随项目走；draw 已归档 2026-08-21）
_DRAW_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "recipes",
]
DRAW_EFFECTS_DIR = next((str(p) for p in _DRAW_CANDIDATES if p.is_dir()), str(_DRAW_CANDIDATES[0]))

# 超级公式参数默认值（与 draw/templates/super_params.py 的 SUPER_PARAM_DEFAULTS 保持一致；
# 副本同时存在 pywallpaper/recipes/super_params.py 供参考）
_SUPER_PARAM_DEFAULTS = {
    "p1": 0.5, "p2": 0.5, "p3": 0.5, "p4": 0.5, "p5": 0.2, "p6": 0.8, "p7": 0.2, "p8": 0.8,
    "w1": 0.5, "w2": 0.5, "w3": 0.1, "w4": 0.1,
    "f1": 1.0, "f2": 1.0, "f3": 1.0, "f4": 3.0, "f5": 9.0, "f6": 27.0,
    "d1": 0.0, "d2": 0.0, "d3": 0.0,
    "c1": 2.0, "c2": 2.0, "c3": 2.0,
    "g1": 1.0, "g2": 1.0, "g3": 1.0,
    "a1": 0.0, "a2": 0.0, "a3": 0.0, "b1": 1.0, "b2": 1.0, "b3": 1.0,
}


def _resolve_super_params(expr: str) -> str:
    """将超级公式参数名替换为默认数值（等价 draw 的 resolve_super_params）。"""
    import re as _re
    for name, value in _SUPER_PARAM_DEFAULTS.items():
        expr = _re.sub(r"\b" + _re.escape(name) + r"\b", str(value), expr)
    return expr


class CARecipeLoader:
    """CA 配方加载器 — 从 draw 的配方库加载 JSON 文件"""
    
    def __init__(self, effects_dir: str = DRAW_EFFECTS_DIR):
        self.effects_dir = effects_dir
        self._index = None  # 延迟加载索引
        
    def _build_index(self):
        """构建配方索引 — 映射规则名称到文件名"""
        if self._index is not None:
            return
            
        self._index = {
            'by_name': {},      # 完整名称 -> 文件名
            'by_rule': {},      # 规则名称 -> [文件名列表]
            'by_initial': {},   # 初始化名称 -> [文件名列表]
            'by_color': {},     # 颜色名称 -> [文件名列表]
        }
        
        # 扫描目录
        try:
            files = os.listdir(self.effects_dir)
        except Exception as e:
            print(f"[CARecipeLoader] 无法读取配方目录: {e}")
            return
        
        # 加载已知规则名称（从模板文件）
        known_rules = self._load_known_rules()
        
        for filename in files:
            if not filename.endswith('.json'):
                continue
                
            # 解析文件名：{Initial}_{Rule}_{Color}_{hash}.json
            name_without_ext = filename[:-5]  # 去掉 .json
            parts = name_without_ext.split('_')
            
            # 建立完整名称索引
            self._index['by_name'][name_without_ext] = filename
            
            # 建立规则索引（使用已知规则名称匹配）
            rule_name = self._extract_rule_name(name_without_ext, known_rules)
            if rule_name:
                if rule_name not in self._index['by_rule']:
                    self._index['by_rule'][rule_name] = []
                self._index['by_rule'][rule_name].append(filename)
            
    def load_recipe(self, recipe_name: str) -> dict:
        """
        加载配方
        
        Args:
            recipe_name: 配方名称，可以是：
                - 完整文件名（不带路径）：Annulus_BZReaction_Cool_cd495b9f.json
                - 完整名称（不带 hash）：Annulus_BZReaction_Cool
                - 规则名称：BZReaction（会返回第一个匹配的配方）
                
        Returns:
            配方字典，包含 grid/evolution/color 配置
        """
        self._build_index()
        
        # 归一化：允许带 .json 后缀的完整文件名
        if recipe_name.endswith('.json'):
            recipe_name = recipe_name[:-5]
        
        # 尝试精确匹配文件名
        if recipe_name in self._index['by_name']:
            filename = self._index['by_name'][recipe_name]
            return self._load_json(filename)
        
        # 尝试匹配完整名称（不带 hash）
        for full_name, filename in self._index['by_name'].items():
            if full_name.startswith(recipe_name):
                return self._load_json(filename)
        
        # 尝试匹配规则名称
        if recipe_name in self._index['by_rule']:
            filename = self._index['by_rule'][recipe_name][0]  # 取第一个匹配的
            return self._load_json(filename)
        
        # 没找到，返回默认配方
        print(f"[CARecipeLoader] 未找到配方: {recipe_name}，使用默认配方")
        return self._default_recipe()
    
    def _load_json(self, filename: str) -> dict:
        """加载 JSON 文件"""
        filepath = os.path.join(self.effects_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[CARecipeLoader] 加载配方失败: {filepath}, 错误: {e}")
            return self._default_recipe()
    
    def _default_recipe(self) -> dict:
        """默认配方（Game of Life）"""
        return {
            "name": "Default_GameOfLife",
            "grid": {
                "width": 64,
                "height": 64,
                "wrap": True,
                "initial": {
                    "type": "formula",
                    "expression": "1 if (x-0.5)**2 + (y-0.5)**2 < 0.1 else 0"
                }
            },
            "evolution": {
                "rule": "1 if (c==1 and 2<=sum_n<=3) or (c==0 and sum_n==3) else 0",
                "variables": ["c", "sum_n"]
            },
            "color": {
                "red": "v",
                "green": "v",
                "blue": "v"
            }
        }
    
    def _load_known_rules(self) -> set:
        """加载已知规则名称（优先 pywallpaper/recipes/evolution_rules.py 内置副本）"""
        rules = set()
        candidates = [
            os.path.join(DRAW_EFFECTS_DIR, 'evolution_rules.py'),
            os.path.join(DRAW_EFFECTS_DIR, 'evolution.py'),
            os.path.join(os.path.dirname(DRAW_EFFECTS_DIR), 'templates', 'evolution.py'),
        ]
        evolution_file = next((f for f in candidates if os.path.exists(f)), None)
        
        if evolution_file is None:
            return rules
            
        try:
            with open(evolution_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取所有规则名称（EVOLUTION_TEMPLATES 的 key）
            import re
            matches = re.findall(r'"(\w+)":\s*\{', content)
            rules = set(matches)
        except Exception as e:
            print(f"[CARecipeLoader] 加载规则名称失败: {e}")
            
        return rules
    
    def _extract_rule_name(self, filename_without_ext: str, known_rules: set) -> str:
        """从文件名提取规则名称
        
        Args:
            filename_without_ext: 文件名（不带扩展名和 hash）
            known_rules: 已知规则名称集合
            
        Returns:
            规则名称，或 None（如果无法识别）
        """
        parts = filename_without_ext.split('_')
        
        # 尝试匹配已知规则名称（从长到短）
        for rule in sorted(known_rules, key=len, reverse=True):
            rule_parts = rule.split('_')
            # 检查文件名是否包含此规则的所有部分
            for i in range(len(parts) - len(rule_parts) + 1):
                if parts[i:i+len(rule_parts)] == rule_parts:
                    return rule
                    
        return None
    
    def list_recipes(self, rule_name: str = None) -> list:
        """列出所有配方名称，或按规则名称过滤"""
        self._build_index()
        
        if rule_name:
            return self._index['by_rule'].get(rule_name, [])
        else:
            return list(self._index['by_name'].keys())


@register_primitive('ca')
class CAPrimitive(RenderPrimitive):
    """细胞自动机原语 — 集成 draw 的 CA 引擎
    
    功能:
        - 加载 draw 的 CA 配方（JSON 格式）
        - 执行 CA 演化（支持 JIT 编译优化）
        - 音频驱动参数调制
        - 渲染到 PIL Image
    """
    
    def __init__(self, config: dict, width: int, height: int):
        super().__init__(config, width, height)
        
        # CA 配置
        self.recipe_name = config.get('recipe', 'BZReaction')  # 默认使用 BZReaction
        self.grid_size = config.get('grid_size', [64, 64])
        self.steps_per_frame = config.get('steps_per_frame', 1)
        self.use_jit = config.get('use_jit', True) and HAS_NUMBA  # 是否使用 JIT 编译的核
        
        # 颜色调制状态
        self.color_hue = 0.0    # 色相 (0-360)
        self.color_sat = 1.0    # 饱和度 (0-1)
        self.color_val = 1.0    # 明度 (0-1)
        
        # 音频调制配置
        self.audio_modulation = config.get('audio_modulation', {})
        self.engine = FormulaEngine()
        self.audio_funcs = {}
        
        # 后处理配置
        self.postprocess = config.get('postprocess', [])
        
        # 配方加载器
        self.recipe_loader = CARecipeLoader()
        
        # 加载配方
        self.recipe_data = self.recipe_loader.load_recipe(self.recipe_name)
        
        # 初始化 CA 引擎
        self._init_ca_engine()
        
        # 预分配图像缓冲区
        self._image = Image.new('RGB', (self.grid_size[0], self.grid_size[1]))
        self._pixels = self._image.load()
    
    def _init_ca_engine(self):
        """初始化 CA 引擎"""
        # 创建网格
        self.grid_w, self.grid_h = self.grid_size
        self.grid = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
        
        # 总是编译初始化公式（初始化只执行一次，性能不是问题）
        self._compile_init_formula()
        
        # 根据是否使用 JIT 选择演化方法
        if self.use_jit:
            # 使用 JIT 编译的核函数
            from engine.primitives.ca_kernel import get_kernel_for_recipe
            self.kernel_func, self.rule_id = get_kernel_for_recipe(self.recipe_name)
            self.use_ast_eval = False
            print(f"[CAPrimitive] 使用 JIT 编译的核: {self.kernel_func.__name__}")
        else:
            # 使用 asteval 公式计算
            self.use_ast_eval = True
            self._compile_rule_formula()
            print(f"[CAPrimitive] 使用 AST 公式计算")
        
        # 总是编译颜色公式（颜色计算也需要）
        self._compile_color_formulas()
        
        # 编译音频调制公式
        for param, expr in self.audio_modulation.items():
            variables = self.engine._extract_variables(expr)
            self.audio_funcs[param] = (self.engine.compile(expr, variables), variables)
        
        # 构建坐标系
        self._build_coords()
        
        # 初始化网格
        self._reset_grid()
        
        # 时间步
        self.t = 0
    
    def _compile_init_formula(self):
        """编译初始化公式 — 总是需要"""
        init_config = self.recipe_data.get('grid', {}).get('initial', {})
        if init_config.get('type') == 'formula':
            init_expr = init_config.get('expression', 'random()')
        else:
            init_expr = 'random()'  # 默认随机
        
        self.init_func = self.engine.compile(
            _resolve_super_params(init_expr), ['x', 'y', 'i', 'j', 'random'])
    
    def _compile_rule_formula(self):
        """编译演化规则公式 — 仅当 use_jit=False 时需要"""
        evolution_config = self.recipe_data.get('evolution', {})
        rule_expr = evolution_config.get('rule', '1 if (c==1 and 2<=sum_n<=3) or (c==0 and sum_n==3) else 0')
        rule_vars = evolution_config.get('variables', ['c', 'sum_n'])
        self.rule_func = self.engine.compile(
            _resolve_super_params(rule_expr), rule_vars)
    
    def _compile_color_formulas(self):
        """编译颜色公式 — 总是需要"""
        color_config = self.recipe_data.get('color', {})
        self.color_funcs = {}
        for ch in ['red', 'green', 'blue']:
            if ch in color_config:
                self.color_funcs[ch] = self.engine.compile(
                    _resolve_super_params(color_config[ch]), ['v', 'x', 'y'])
    
    def _build_coords(self):
        """构建归一化坐标网格"""
        self.x_coords = np.broadcast_to(
            np.linspace(0, 1, self.grid_w, endpoint=False, dtype=np.float64).reshape(1, -1),
            (self.grid_h, self.grid_w)
        )
        self.y_coords = np.broadcast_to(
            np.linspace(0, 1, self.grid_h, endpoint=False, dtype=np.float64).reshape(-1, 1),
            (self.grid_h, self.grid_w)
        )
        self.i_grid = self.y_coords * self.grid_h
        self.j_grid = self.x_coords * self.grid_w
    
    def _reset_grid(self):
        """初始化网格 — 总是使用 asteval 公式计算（初始化只执行一次）"""
        try:
            val = self.init_func(
                x=self.x_coords, y=self.y_coords,
                i=self.i_grid, j=self.j_grid,
                random=np.random.random(self.grid.shape)
            )
            val = np.asarray(val, dtype=np.float32)
            if val.shape != (self.grid_h, self.grid_w):
                raise ValueError("shape mismatch")
            self.grid = np.clip(val, 0.0, 1.0).astype(np.float32)
        except Exception as e:
            print(f"[CAPrimitive] 网格初始化错误: {e}")
            self.grid = np.random.random((self.grid_h, self.grid_w)).astype(np.float32)
        
        self.t = 0
    
    def update(self, dt: float, audio, global_time: float):
        super().update(dt, audio, global_time)
        
        # 音频调制参数
        self._apply_audio_modulation(audio)
        
        # 执行 CA 演化
        for _ in range(self.steps_per_frame):
            self._step()
    
    def _apply_audio_modulation(self, audio):
        """应用音频调制"""
        for param, (func, variables) in self.audio_funcs.items():
            try:
                # 构造音频变量字典
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
                
                # 计算调制后的值
                value = float(self.engine.evaluate(func, **kwargs))
                
                # 应用到参数
                if param == 'init_seed' and value > 0.5:
                    self._reset_grid()
                elif param == 'steps_per_frame':
                    self.steps_per_frame = max(1, int(value))
                elif param == 'color_hue':
                    # 调制色相 (0-360)
                    self.color_hue = value % 360.0
                elif param == 'color_sat':
                    # 调制饱和度 (0-1)
                    self.color_sat = max(0.0, min(1.0, value))
                elif param == 'color_val':
                    # 调制明度 (0-1)
                    self.color_val = max(0.0, min(1.0, value))
                elif param == 'grid_size':
                    # 调制网格大小（需要重新初始化引擎）
                    new_size = max(8, min(256, int(value)))
                    if new_size != self.grid_size[0]:
                        self.grid_size = [new_size, new_size]
                        self._init_ca_engine()  # 重新初始化
                    
            except Exception as e:
                print(f"[CAPrimitive] 音频调制错误: {e}")
    
    def _step(self):
        """执行一步演化 — 根据配置选择 JIT 或 AST 方法"""
        if self.use_jit:
            self._step_jit()
        else:
            self._step_ast()
    
    def _step_jit(self):
        """执行一步演化 — 使用 JIT 编译的核函数"""
        # 调用 JIT 编译的核函数
        self.kernel_func(self.grid)
        self.t += 1
    
    def _step_ast(self):
        """执行一步演化 — 使用 asteval 公式计算"""
        # 使用 np.roll 计算 Moore 邻域和（优化性能）
        sum_n = (
            np.roll(self.grid, 1, axis=0) +  # 上
            np.roll(self.grid, -1, axis=0) +  # 下
            np.roll(self.grid, 1, axis=1) +  # 左
            np.roll(self.grid, -1, axis=1) +  # 右
            np.roll(np.roll(self.grid, 1, axis=0), 1, axis=1) +  # 左上
            np.roll(np.roll(self.grid, 1, axis=0), -1, axis=1) +  # 右上
            np.roll(np.roll(self.grid, -1, axis=0), 1, axis=1) +  # 左下
            np.roll(np.roll(self.grid, -1, axis=0), -1, axis=1)  # 右下
        )
        avg_n = sum_n / 8.0  # Moore 邻域有 8 个邻居
        
        # 执行演化规则
        val = self.rule_func(
            c=self.grid, sum_n=sum_n, avg_n=avg_n,
            x=self.x_coords, y=self.y_coords,
            t=np.float64(self.t)
        )
        val = np.asarray(val, dtype=np.float32)
        if val.shape != (self.grid_h, self.grid_w):
            val = np.broadcast_to(val.ravel()[0:1], (self.grid_h, self.grid_w)).astype(np.float32)
        
        self.grid = np.clip(val, 0.0, 1.0)
        self.t += 1
    
    def draw(self, drawer):
        """渲染 CA 网格到 PIL Image"""
        # 计算颜色
        v = self.grid.astype(np.float64)
        r = self._eval_color_channel(self.color_funcs.get('red'), v)
        g = self._eval_color_channel(self.color_funcs.get('green'), v)
        b = self._eval_color_channel(self.color_funcs.get('blue'), v)
        
        # 应用颜色调制（HSV 空间）
        if self.color_hue != 0.0 or self.color_sat != 1.0 or self.color_val != 1.0:
            # 将 RGB 转换为 HSV
            import colorsys
            hsv = np.zeros((self.grid_h, self.grid_w, 3), dtype=np.float64)
            for i in range(self.grid_h):
                for j in range(self.grid_w):
                    h, s, v = colorsys.rgb_to_hsv(r[i, j], g[i, j], b[i, j])
                    # 应用调制
                    h = (h * 360.0 + self.color_hue) % 360.0 / 360.0
                    s = max(0.0, min(1.0, s * self.color_sat))
                    v = max(0.0, min(1.0, v * self.color_val))
                    r[i, j], g[i, j], b[i, j] = colorsys.hsv_to_rgb(h, s, v)
        
        # 创建图像
        img_array = np.zeros((self.grid_h, self.grid_w, 3), dtype=np.uint8)
        img_array[:, :, 0] = (r * 255).astype(np.uint8)
        img_array[:, :, 1] = (g * 255).astype(np.uint8)
        img_array[:, :, 2] = (b * 255).astype(np.uint8)
        
        img = Image.fromarray(img_array, 'RGB')
        
        # 缩放图像到屏幕大小
        img = img.resize((self.width, self.height), Image.NEAREST)
        
        # 后处理
        img = self._apply_postprocess(img)
        
        # 绘制到 drawer
        drawer._image.paste(img, (self.x, self.y))
    
    def _eval_color_channel(self, func, v: np.ndarray) -> np.ndarray:
        """计算颜色通道"""
        if func is None:
            return v
        
        try:
            result = func(v=v, x=self.x_coords, y=self.y_coords)
            return np.clip(result, 0.0, 1.0).astype(np.float64)
        except Exception as e:
            print(f"[CAPrimitive] 颜色计算错误: {e}")
            return v
    
    def _apply_postprocess(self, img: Image.Image) -> Image.Image:
        """应用后处理效果"""
        for effect in self.postprocess:
            if effect == 'bloom':
                # 简单的 bloom 效果：高斯模糊 + 叠加
                blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
                img = Image.blend(img, blurred, alpha=0.3)
            elif effect == 'vignette':
                # 暗角效果
                # 创建渐变蒙版
                # 这里简化为：降低边缘亮度
                pass
            elif effect == 'invert':
                img = ImageOps.invert(img)
        
        return img
    

# 注释：测试代码已移至 test_ca_jit.py
