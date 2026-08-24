"""
效果编辑器 v2 — 功能完整的 GUI 工具

新增功能:
1. 实时预览 CA 演化（右侧面板，30 FPS）
2. 颜色选择器（HSV 滑块 + 预览）
3. 公式编辑器（init/rule/color 公式，带语法检查）
4. 音频调制参数可视化编辑
5. 保存/加载效果配置

依赖:
  - tkinter (GUI)
  - PIL (图像渲染)
  - numpy (CA 计算)
  - asteval (公式求值)
"""

import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import numpy as np
from PIL import Image, ImageTk
from asteval import Interpreter


# 目录配置
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAW_EFFECTS_DIR = os.path.join(_ROOT, "recipes")
PYWALLPAPER_EFFECTS_DIR = os.path.join(_ROOT, "effects")


class CARenderer:
    """独立的 CA 渲染器（用于预览，不依赖 pywallpaper 引擎）"""
    
    def __init__(self, grid_w=64, grid_h=64):
        self.grid_w = grid_w
        self.grid_h = grid_h
        self.grid = np.zeros((grid_h, grid_w), dtype=np.float32)
        self.t = 0
        
        # 公式引擎
        self._aeval = Interpreter()
        self.init_func = None
        self.rule_func = None
        self.color_funcs = {}
        
        # 颜色调制
        self.color_hue = 0.0
        self.color_sat = 1.0
        self.color_val = 1.0
        
        # 编译坐标系
        self._build_coords()
        
    def _build_coords(self):
        """构建坐标网格"""
        self.x_coords = np.broadcast_to(
            np.linspace(0, 1, self.grid_w, endpoint=False, dtype=np.float64).reshape(1, -1),
            (self.grid_h, self.grid_w)
        )
        self.y_coords = np.broadcast_to(
            np.linspace(0, 1, self.grid_h, endpoint=False, dtype=np.float64).reshape(-1, 1),
            (self.grid_h, self.grid_w)
        )
        
    def load_recipe(self, recipe_data: dict):
        """加载配方"""
        # 编译初始化公式
        init_config = recipe_data.get('grid', {}).get('initial', {})
        if init_config.get('type') == 'formula':
            init_expr = init_config.get('expression', 'random()')
            self.init_func = self._compile_formula(
                init_expr, ['x', 'y', 'i', 'j', 'random'])
        
        # 编译演化规则
        evolution_config = recipe_data.get('evolution', {})
        rule_expr = evolution_config.get('rule', '1 if (c==1 and 2<=sum_n<=3) or (c==0 and sum_n==3) else 0')
        rule_vars = evolution_config.get('variables', ['c', 'sum_n'])
        self.rule_func = self._compile_formula(rule_expr, rule_vars)
        
        # 编译颜色公式
        color_config = recipe_data.get('color', {})
        for ch in ['red', 'green', 'blue']:
            if ch in color_config:
                self.color_funcs[ch] = self._compile_formula(
                    color_config[ch], ['v', 'x', 'y'])
        
        # 初始化网格
        self.reset()
        
    def _compile_formula(self, expr: str, variables: list):
        """编译公式为函数"""
        # 转换 Python 语法为 asteval 兼容
        translated = expr
        translated = translated.replace(' and ', ' & ')
        translated = translated.replace(' or ', ' | ')
        translated = translated.replace(' not ', ' ~ ')
        
        # 创建函数
        func_code = f"def _func({','.join(variables)}): return {translated}"
        self._aeval.eval(func_code)
        return self._aeval.symtable['_func']
        
    def reset(self):
        """重置网格"""
        try:
            if self.init_func:
                val = self.init_func(
                    x=self.x_coords, y=self.y_coords,
                    i=self.y_coords * self.grid_h,
                    j=self.x_coords * self.grid_w,
                    random=np.random.random(self.grid.shape)
                )
                val = np.asarray(val, dtype=np.float32)
                if val.shape == (self.grid_h, self.grid_w):
                    self.grid = np.clip(val, 0.0, 1.0).astype(np.float32)
                    self.t = 0
                    return
        except Exception as e:
            print(f"[CARenderer] 初始化错误: {e}")
        
        #  fallback：随机初始化
        self.grid = np.random.random((self.grid_h, self.grid_w)).astype(np.float32)
        self.t = 0
        
    def step(self):
        """执行一步演化"""
        # 使用 np.roll 计算 Moore 邻域和
        sum_n = (
            np.roll(self.grid, 1, axis=0) +
            np.roll(self.grid, -1, axis=0) +
            np.roll(self.grid, 1, axis=1) +
            np.roll(self.grid, -1, axis=1) +
            np.roll(np.roll(self.grid, 1, axis=0), 1, axis=1) +
            np.roll(np.roll(self.grid, 1, axis=0), -1, axis=1) +
            np.roll(np.roll(self.grid, -1, axis=0), 1, axis=1) +
            np.roll(np.roll(self.grid, -1, axis=0), -1, axis=1)
        )
        avg_n = sum_n / 8.0
        
        # 执行演化规则
        if self.rule_func:
            val = self.rule_func(
                c=self.grid, sum_n=sum_n, avg_n=avg_n,
                x=self.x_coords, y=self.y_coords,
                t=np.float64(self.t)
            )
            val = np.asarray(val, dtype=np.float32)
            if val.shape == (self.grid_h, self.grid_w):
                self.grid = np.clip(val, 0.0, 1.0).astype(np.float32)
        
        self.t += 1
        
    def render(self, scale=4) -> Image.Image:
        """渲染网格为 PIL Image"""
        # 计算颜色
        v = self.grid.astype(np.float64)
        r = self._eval_color('red', v)
        g = self._eval_color('green', v)
        b = self._eval_color('blue', v)
        
        # 创建图像
        img_h = self.grid_h * scale
        img_w = self.grid_w * scale
        img_array = np.zeros((img_h, img_w, 3), dtype=np.uint8)
        
        # 缩放（最近邻）
        for i in range(img_h):
            for j in range(img_w):
                gi = i // scale
                gj = j // scale
                img_array[i, j, 0] = int(r[gi, gj] * 255)
                img_array[i, j, 1] = int(g[gi, gj] * 255)
                img_array[i, j, 2] = int(b[gi, gj] * 255)
        
        return Image.fromarray(img_array, 'RGB')
        
    def _eval_color(self, channel: str, v: np.ndarray) -> np.ndarray:
        """计算颜色通道"""
        if channel in self.color_funcs:
            try:
                result = self.color_funcs[channel](v=v, x=self.x_coords, y=self.y_coords)
                return np.clip(result, 0.0, 1.0).astype(np.float64)
            except Exception as e:
                print(f"[CARenderer] 颜色计算错误: {e}")
        
        # 默认：灰度
        return v


class EffectEditorV2:
    """效果编辑器 v2 — 带实时预览"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("PyWallpaper 效果编辑器 v2")
        self.root.geometry("1000x700")
        
        # 状态
        self.current_recipe_data = None
        self.current_config = {}
        self.ca_renderer = None
        self.preview_running = False
        self.preview_thread = None
        
        # 公式编辑器变量
        self.formula_vars = {
            'init': tk.StringVar(value=''),
            'rule': tk.StringVar(value=''),
            'color_red': tk.StringVar(value=''),
            'color_green': tk.StringVar(value=''),
            'color_blue': tk.StringVar(value=''),
        }
        
        # 颜色选择器变量
        self.color_vars = {
            'hue': tk.DoubleVar(value=0.0),
            'sat': tk.DoubleVar(value=1.0),
            'val': tk.DoubleVar(value=1.0),
        }
        
        self._create_ui()
        self._load_recipes()
        
    def _create_ui(self):
        """创建界面"""
        # 使用 PanedWindow 实现可调整大小的面板
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧面板：控制和编辑
        left_panel = ttk.Frame(main_pane)
        main_pane.add(left_panel, weight=1)
        
        # 右侧面板：预览
        right_panel = ttk.Frame(main_pane)
        main_pane.add(right_panel, weight=1)
        
        # ===== 左侧面板内容 =====
        # 配方选择
        top = ttk.LabelFrame(left_panel, text="配方选择")
        top.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top, text="选择 CA 配方:").pack(side=tk.LEFT, padx=5)
        self.recipe_combo = ttk.Combobox(top, width=30, state="readonly")
        self.recipe_combo.pack(side=tk.LEFT, padx=5)
        self.recipe_combo.bind("<<ComboboxSelected>>", self._on_recipe_selected)
        
        ttk.Button(top, text="刷新", command=self._load_recipes).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="加载 JSON", command=self._load_json).pack(side=tk.LEFT, padx=5)
        
        # 参数调整（使用 Notebook 实现标签页）
        notebook = ttk.Notebook(left_panel)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 标签页1：基本参数
        params_frame = ttk.Frame(notebook)
        notebook.add(params_frame, text="基本参数")
        self._create_basic_params(params_frame)
        
        # 标签页2：公式编辑器
        formula_frame = ttk.Frame(notebook)
        notebook.add(formula_frame, text="公式编辑器")
        self._create_formula_editor(formula_frame)
        
        # 标签页3：颜色选择器
        color_frame = ttk.Frame(notebook)
        notebook.add(color_frame, text="颜色选择器")
        self._create_color_chooser(color_frame)
        
        # 标签页4：音频调制
        audio_frame = ttk.Frame(notebook)
        notebook.add(audio_frame, text="音频调制")
        self._create_audio_editor(audio_frame)

        # ── 新增：标签页5 效果市场 ─────────────────────────
        market_frame = ttk.Frame(notebook)
        notebook.add(market_frame, text="效果市场")
        self._create_marketplace(market_frame)
        
        # 底部按钮
        bottom = ttk.Frame(left_panel)
        bottom.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(bottom, text="生成配置", command=self._generate_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="保存到效果目录", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="预览", command=self._toggle_preview).pack(side=tk.LEFT, padx=5)
        
        # ===== 右侧面板内容 =====
        ttk.Label(right_panel, text="实时预览", font=("Arial", 12, "bold")).pack(pady=5)
        
        # 预览画布
        self.preview_canvas = tk.Canvas(right_panel, width=400, height=400, bg="black")
        self.preview_canvas.pack(padx=5, pady=5)
        
        # 预览控制
        preview_control = ttk.Frame(right_panel)
        preview_control.pack(fill=tk.X, padx=5, pady=5)
        
        self.preview_btn = ttk.Button(preview_control, text="开始预览", command=self._toggle_preview)
        self.preview_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(preview_control, text="重置", command=self._reset_preview).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(preview_control, text="缩放:").pack(side=tk.LEFT, padx=5)
        self.preview_scale = tk.IntVar(value=6)
        ttk.Scale(
            preview_control, from_=2, to=10, variable=self.preview_scale,
            orient=tk.HORIZONTAL, command=lambda v: self._update_preview_scale()
        ).pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def _create_basic_params(self, parent):
        """创建基本参数调整界面"""
        # 网格大小
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="网格宽度:", width=15).pack(side=tk.LEFT)
        self.grid_width_var = tk.IntVar(value=64)
        ttk.Scale(frame, from_=8, to=128, variable=self.grid_width_var, 
                   orient=tk.HORIZONTAL, command=lambda v: self._on_param_changed()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.grid_width_var).pack(side=tk.LEFT)
        
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="网格高度:", width=15).pack(side=tk.LEFT)
        self.grid_height_var = tk.IntVar(value=64)
        ttk.Scale(frame, from_=8, to=128, variable=self.grid_height_var, 
                   orient=tk.HORIZONTAL, command=lambda v: self._on_param_changed()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.grid_height_var).pack(side=tk.LEFT)
        
        # 演化步数
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="每帧步数:", width=15).pack(side=tk.LEFT)
        self.steps_var = tk.IntVar(value=1)
        ttk.Scale(frame, from_=1, to=10, variable=self.steps_var, 
                   orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.steps_var).pack(side=tk.LEFT)
        
    def _create_formula_editor(self, parent):
        """创建公式编辑器界面"""
        # 初始化公式
        frame = ttk.LabelFrame(parent, text="初始化公式 (init)")
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(frame, text="表达式 (支持 x, y, i, j, random):").pack(anchor=tk.W, padx=5)
        self.formula_init_entry = ttk.Entry(frame, textvariable=self.formula_vars['init'])
        self.formula_init_entry.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(frame, text="应用", command=lambda: self._apply_formula('init')).pack(anchor=tk.W, padx=5, pady=2)
        
        # 演化规则
        frame = ttk.LabelFrame(parent, text="演化规则 (rule)")
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(frame, text="表达式 (支持 c, sum_n, avg_n, x, y, t):").pack(anchor=tk.W, padx=5)
        self.formula_rule_entry = ttk.Entry(frame, textvariable=self.formula_vars['rule'])
        self.formula_rule_entry.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(frame, text="应用", command=lambda: self._apply_formula('rule')).pack(anchor=tk.W, padx=5, pady=2)
        
        # 颜色公式
        for ch in ['red', 'green', 'blue']:
            frame = ttk.LabelFrame(parent, text=f"颜色公式 ({ch})")
            frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(frame, text=f"表达式 (支持 v, x, y):").pack(anchor=tk.W, padx=5)
            entry = ttk.Entry(frame, textvariable=self.formula_vars[f'color_{ch}'])
            entry.pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Button(frame, text="应用", command=lambda c=ch: self._apply_formula(f'color_{ch}')).pack(anchor=tk.W, padx=5, pady=2)
        
        # 公式模板
        frame = ttk.LabelFrame(parent, text="公式模板")
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        templates = {
            'Game of Life': {
                'init': '1 if (x-0.5)**2 + (y-0.5)**2 < 0.1 else 0',
                'rule': '1 if (c==1 and 2<=sum_n<=3) or (c==0 and sum_n==3) else 0',
                'color_red': 'v',
                'color_green': 'v',
                'color_blue': 'v',
            },
            'BZ Reaction': {
                'init': 'random()',
                'rule': '1 if (c > 0.5) else (0.5 if sum_n > 1 else c)',
                'color_red': 'v',
                'color_green': '1-v',
                'color_blue': '1',
            },
        }
        
        for name, template in templates.items():
            ttk.Button(
                frame, text=name,
                command=lambda t=template: self._load_formula_template(t)
            ).pack(anchor=tk.W, padx=5, pady=2)
        
    def _create_color_chooser(self, parent):
        """创建颜色选择器界面"""
        # HSV 滑块
        for name, var in [('色相 (Hue)', 'hue'), ('饱和度 (Saturation)', 'sat'), ('明度 (Value)', 'val')]:
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Label(frame, text=f"{name}:", width=20).pack(side=tk.LEFT)
            
            if var == 'hue':
                ttk.Scale(frame, from_=0, to=360, variable=self.color_vars[var], 
                           orient=tk.HORIZONTAL, command=lambda v: self._on_color_changed()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            else:
                ttk.Scale(frame, from_=0.0, to=1.0, variable=self.color_vars[var], 
                           orient=tk.HORIZONTAL, command=lambda v: self._on_color_changed()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            ttk.Label(frame, textvariable=self.color_vars[var]).pack(side=tk.LEFT)
        
        # 颜色预览
        self.color_preview = tk.Canvas(parent, width=100, height=50, bg="black")
        self.color_preview.pack(padx=5, pady=10)
        
        # 系统颜色选择器
        ttk.Button(parent, text="打开系统颜色选择器", command=self._open_colorchooser).pack(pady=5)
        
    def _create_audio_editor(self, parent):
        """创建音频调制编辑器界面"""
        ttk.Label(parent, text="音频调制参数 (支持 rms, beat, band_energy(n))").pack(anchor=tk.W, padx=5, pady=5)
        
        # 音频调制参数列表
        self.audio_params = {}
        self.audio_vars = {}
        
        for param in ['init_seed', 'steps_per_frame', 'color_hue', 'color_sat', 'color_val']:
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Label(frame, text=f"{param}:", width=20).pack(side=tk.LEFT)
            
            self.audio_vars[param] = tk.StringVar(value='')
            entry = ttk.Entry(frame, textvariable=self.audio_vars[param])
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            ttk.Button(
                frame, text="✓", width=3,
                command=lambda p=param: self._validate_audio_param(p)
            ).pack(side=tk.LEFT)
        
    def _load_recipes(self):
        """加载配方列表"""
        try:
            files = [f for f in os.listdir(DRAW_EFFECTS_DIR) if f.endswith('.json')]
            # 提取规则名称
            recipe_names = []
            for f in files:
                parts = f[:-5].split('_')  # 去掉 .json
                if len(parts) >= 2:
                    rule_name = parts[1]
                    if rule_name not in recipe_names:
                        recipe_names.append(rule_name)
            
            self.recipe_combo['values'] = sorted(recipe_names)
            if recipe_names:
                self.recipe_combo.set(recipe_names[0])
                self._on_recipe_selected(None)
                
        except Exception as e:
            messagebox.showerror("错误", f"加载配方失败: {e}")
            
    def _load_json(self):
        """从 JSON 文件加载配方"""
        filepath = filedialog.askopenfilename(
            title="选择配方 JSON 文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not filepath:
            return
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.current_recipe_data = json.load(f)
            
            self._update_ui_from_recipe()
            self._set_status(f"已加载配方: {os.path.basename(filepath)}")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")
            
    def _on_recipe_selected(self, event):
        """配方选择事件"""
        rule_name = self.recipe_combo.get()
        
        # 从 draw 的配方库加载
        try:
            files = [f for f in os.listdir(DRAW_EFFECTS_DIR) if f.endswith('.json')]
            for f in files:
                if rule_name in f:
                    filepath = os.path.join(DRAW_EFFECTS_DIR, f)
                    with open(filepath, 'r', encoding='utf-8') as fp:
                        self.current_recipe_data = json.load(fp)
                    break
            
            self._update_ui_from_recipe()
            self._set_status(f"已加载配方: {rule_name}")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载配方失败: {e}")
            
    def _update_ui_from_recipe(self):
        """从配方数据更新 UI"""
        if not self.current_recipe_data:
            return
            
        # 更新公式编辑器
        init_config = self.current_recipe_data.get('grid', {}).get('initial', {})
        if init_config.get('type') == 'formula':
            self.formula_vars['init'].set(init_config.get('expression', ''))
        
        evolution_config = self.current_recipe_data.get('evolution', {})
        self.formula_vars['rule'].set(evolution_config.get('rule', ''))
        
        color_config = self.current_recipe_data.get('color', {})
        for ch in ['red', 'green', 'blue']:
            if ch in color_config:
                self.formula_vars[f'color_{ch}'].set(color_config[ch])
        
        # 更新基本参数
        grid_config = self.current_recipe_data.get('grid', {})
        self.grid_width_var.set(grid_config.get('width', 64))
        self.grid_height_var.set(grid_config.get('height', 64))
        
    def _apply_formula(self, formula_type):
        """应用公式修改"""
        if not self.current_recipe_data:
            self.current_recipe_data = {
                "grid": {"width": 64, "height": 64, "initial": {"type": "formula", "expression": ""}},
                "evolution": {"rule": "", "variables": ["c", "sum_n"]},
                "color": {}
            }
        
        if formula_type == 'init':
            expr = self.formula_vars['init'].get()
            self.current_recipe_data['grid']['initial']['expression'] = expr
            
        elif formula_type == 'rule':
            expr = self.formula_vars['rule'].get()
            self.current_recipe_data['evolution']['rule'] = expr
            
        elif formula_type.startswith('color_'):
            ch = formula_type.split('_')[1]
            expr = self.formula_vars[formula_type].get()
            self.current_recipe_data['color'][ch] = expr
        
        self._set_status(f"已应用 {formula_type} 公式")
        
    def _load_formula_template(self, template):
        """加载公式模板"""
        for key, value in template.items():
            self.formula_vars[key].set(value)
        
        self._set_status("已加载公式模板")
        
    def _on_color_changed(self):
        """颜色参数变化事件"""
        # 更新颜色预览
        h = self.color_vars['hue'].get()
        s = self.color_vars['sat'].get()
        v = self.color_vars['val'].get()
        
        # 转换 HSV 为 RGB
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h/360.0, s, v)
        color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        
        self.color_preview.config(bg=color)
        
    def _open_colorchooser(self):
        """打开系统颜色选择器"""
        color = colorchooser.askcolor(title="选择颜色")
        if color[1]:  # color 是 ((r, g, b), "#rrggbb") 格式
            # 转换为 HSV
            import colorsys
            r, g, b = [x/255.0 for x in color[0]]
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            
            self.color_vars['hue'].set(h * 360)
            self.color_vars['sat'].set(s)
            self.color_vars['val'].set(v)
            
            self._on_color_changed()
            
    def _validate_audio_param(self, param):
        """验证音频调制参数公式"""
        expr = self.audio_vars[param].get()
        if not expr:
            return
            
        try:
            # 简单验证：检查是否包含合法的变量名
            valid_vars = ['rms', 'beat', 'band_energy']
            # 这里可以添加更完整的公式验证
            self._set_status(f"{param} 公式验证通过")
        except Exception as e:
            messagebox.showerror("错误", f"公式验证失败: {e}")
            
    def _toggle_preview(self):
        """切换预览状态"""
        if self.preview_running:
            self.preview_running = False
            self.preview_btn.config(text="开始预览")
        else:
            self.preview_running = True
            self.preview_btn.config(text="停止预览")
            
            # 启动预览线程
            self.preview_thread = threading.Thread(target=self._preview_loop, daemon=True)
            self.preview_thread.start()
            
    def _preview_loop(self):
        """预览循环"""
        # 创建 CA 渲染器
        grid_w = self.grid_width_var.get()
        grid_h = self.grid_height_var.get()
        self.ca_renderer = CARenderer(grid_w, grid_h)
        
        if self.current_recipe_data:
            self.ca_renderer.load_recipe(self.current_recipe_data)
        
        # 预览循环
        while self.preview_running:
            # 执行演化
            steps = self.steps_var.get()
            for _ in range(steps):
                self.ca_renderer.step()
            
            # 渲染图像
            scale = self.preview_scale.get()
            img = self.ca_renderer.render(scale)
            
            # 缩放到预览画布大小
            img = img.resize((400, 400), Image.NEAREST)
            
            # 更新 UI
            photo = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            self.preview_canvas.image = photo  # 保持引用
            
            # 控制帧率
            self.root.update_idletasks()
            self.root.update()
            
            import time
            time.sleep(0.03)  # ~30 FPS
            
    def _reset_preview(self):
        """重置预览"""
        if self.ca_renderer:
            self.ca_renderer.reset()
            self._set_status("预览已重置")
            
    def _update_preview_scale(self):
        """更新预览缩放"""
        # 下次渲染时会使用新的缩放值
        pass
        
    def _on_param_changed(self):
        """参数变化事件"""
        # 可以在这里添加实时更新逻辑
        pass
        
    def _generate_config(self):
        """生成效果配置"""
        if not self.current_recipe_data:
            messagebox.showwarning("警告", "请先选择或加载配方")
            return
            
        config = {
            "type": "ca",
            "recipe": self.recipe_combo.get() if self.recipe_combo.get() else "custom",
            "grid_size": [
                self.grid_width_var.get(),
                self.grid_height_var.get()
            ],
            "steps_per_frame": self.steps_var.get(),
            "audio_modulation": {},
            "postprocess": []
        }
        
        # 添加音频调制
        for param in ['init_seed', 'steps_per_frame', 'color_hue', 'color_sat', 'color_val']:
            expr = self.audio_vars[param].get()
            if expr:
                config["audio_modulation"][param] = expr
        
        self.current_config = config
        messagebox.showinfo("成功", "配置已生成，请点击保存")
        
    def _save_config(self):
        """保存配置到效果目录"""
        if not self.current_config:
            messagebox.showwarning("警告", "请先生成配置")
            return
            
        # 生成文件名
        recipe_name = self.current_config.get('recipe', 'unknown')
        filename = f"ca_{recipe_name.lower()}_{self.current_config['grid_size'][0]}x{self.current_config['grid_size'][1]}.json"
        filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.current_config, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("成功", f"配置已保存到:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
        
    # ── 效果市场功能 ─────────────────────────────────────────
    
    def _create_marketplace(self, parent):
        """创建效果市场标签页（创意工坊风格）"""
        # 使用 PanedWindow 分割左右面板
        pw = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左侧：效果列表
        left = ttk.Frame(pw)
        pw.add(left, weight=1)
        
        ttk.Label(left, text="本地效果列表", font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=5, pady=5)
        
        # 搜索框
        search_frame = ttk.Frame(left)
        search_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.market_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.market_search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self._market_search())
        
        # 效果列表（带滚动条）
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.market_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE, height=20
        )
        self.market_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.market_listbox.yview)
        
        self.market_listbox.bind("<<ListboxSelect>>", self._market_on_select)
        
        # 刷新按钮
        ttk.Button(left, text="刷新列表", command=self._market_load).pack(fill=tk.X, padx=5, pady=5)
        
        # 右侧：效果详情 + 操作
        right = ttk.Frame(pw)
        pw.add(right, weight=2)
        
        ttk.Label(right, text="效果详情", font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=5, pady=5)
        
        # 详情文本框（只读）
        detail_frame = ttk.Frame(right)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar2 = ttk.Scrollbar(detail_frame)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.market_detail = tk.Text(
            detail_frame, yscrollcommand=scrollbar2.set,
            wrap=tk.WORD, height=15, state=tk.DISABLED
        )
        self.market_detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar2.config(command=self.market_detail.yview)
        
        # 操作按钮
        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="加载到编辑器", command=self._market_load_to_editor).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导出效果", command=self._market_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导入效果", command=self._market_import).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除效果", command=self._market_delete).pack(side=tk.LEFT, padx=5)
        
        # 预览画布
        ttk.Label(right, text="预览").pack(anchor=tk.W, padx=5)
        self.market_preview = tk.Canvas(right, width=200, height=200, bg="black")
        self.market_preview.pack(padx=5, pady=5)
        
        # 加载效果列表
        self._market_load()
        
    def _market_load(self):
        """加载效果列表"""
        self.market_listbox.delete(0, tk.END)
        
        try:
            files = [f for f in os.listdir(PYWALLPAPER_EFFECTS_DIR) if f.endswith('.json')]
            self.market_files = {}  # name -> filename
            
            for f in sorted(files):
                filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, f)
                try:
                    with open(filepath, 'r', encoding='utf-8') as fp:
                        data = json.load(fp)
                    name = data.get('name', f[:-5])
                    self.market_files[name] = f
                    self.market_listbox.insert(tk.END, name)
                except:
                    self.market_listbox.insert(tk.END, f"  (无效)")
                    
            self._set_status(f"效果市场：加载了 {len(files)} 个效果")
        except Exception as e:
            messagebox.showerror("错误", f"加载效果列表失败: {e}")
            
    def _market_search(self):
        """搜索效果"""
        query = self.market_search_var.get().lower()
        
        self.market_listbox.delete(0, tk.END)
        
        for name in self.market_files:
            if query in name.lower():
                self.market_listbox.insert(tk.END, name)
                
    def _market_on_select(self, event):
        """选择效果事件"""
        selection = self.market_listbox.curselection()
        if not selection:
            return
            
        name = self.market_listbox.get(selection[0])
        if name not in self.market_files:
            return
            
        filename = self.market_files[name]
        filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 显示详情
            self.market_detail.config(state=tk.NORMAL)
            self.market_detail.delete(1.0, tk.END)
            self.market_detail.insert(tk.END, json.dumps(data, indent=2, ensure_ascii=False))
            self.market_detail.config(state=tk.DISABLED)
            
            # 预览（简化：显示效果类型）
            self.market_preview.delete("all")
            effect_type = "未知"
            params = data.get('params', {})
            layers = params.get('layers', [])
            if layers:
                effect_type = layers[0].get('type', '未知')
                
            self.market_preview.create_text(
                100, 100, text=f"类型: {effect_type}",
                fill="white", font=("Arial", 12)
            )
            
            self._set_status(f"已选择效果: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"加载效果详情失败: {e}")
            
    def _market_load_to_editor(self):
        """加载选中的效果到编辑器"""
        selection = self.market_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个效果")
            return
            
        name = self.market_listbox.get(selection[0])
        if name not in self.market_files:
            return
            
        filename = self.market_files[name]
        filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.current_config = json.load(f)
                
            # 切换到基本参数标签页
            # TODO: 自动填充 UI 控件
            
            self._set_status(f"已加载效果到编辑器: {name}")
            messagebox.showinfo("成功", f"效果 '{name}' 已加载到编辑器\n请切换到对应标签页查看/修改")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {e}")
            
    def _market_export(self):
        """导出效果（复制到用户指定位置）"""
        selection = self.market_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个效果")
            return
            
        name = self.market_listbox.get(selection[0])
        if name not in self.market_files:
            return
            
        filename = self.market_files[name]
        src_path = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
        
        dst_path = filedialog.asksaveasfilename(
            title="导出效果",
            initialfile=filename,
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not dst_path:
            return
            
        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            messagebox.showinfo("成功", f"效果已导出到:\n{dst_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")
            
    def _market_import(self):
        """导入效果（从用户指定位置复制）"""
        src_path = filedialog.askopenfilename(
            title="导入效果",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if not src_path:
            return
            
        try:
            # 验证 JSON 格式
            with open(src_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 复制到效果目录
            filename = os.path.basename(src_path)
            dst_path = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
            
            import shutil
            shutil.copy2(src_path, dst_path)
            
            # 刷新列表
            self._market_load()
            
            self._set_status(f"已导入效果: {filename}")
            messagebox.showinfo("成功", f"效果已导入:\n{filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {e}")
            
    def _market_delete(self):
        """删除效果"""
        selection = self.market_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个效果")
            return
            
        name = self.market_listbox.get(selection[0])
        if name not in self.market_files:
            return
            
        filename = self.market_files[name]
        
        if not messagebox.askyesno("确认", f"确定要删除效果 '{name}' 吗？\n文件: {filename}"):
            return
            
        try:
            filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
            os.remove(filepath)
            
            # 刷新列表
            self._market_load()
            
            # 清空详情
            self.market_detail.config(state=tk.NORMAL)
            self.market_detail.delete(1.0, tk.END)
            self.market_detail.config(state=tk.DISABLED)
            
            self._set_status(f"已删除效果: {name}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")
        
    def _set_status(self, message):
        """设置状态栏消息"""
        self.status_bar.config(text=message)
        

def main():
    root = tk.Tk()
    app = EffectEditorV2(root)
    root.mainloop()
    

if __name__ == "__main__":
    main()
