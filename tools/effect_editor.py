"""
效果编辑器 — 简化版 GUI 工具

功能:
1. 列出所有可用配方
2. 选择配方并预览
3. 调整基本参数（网格大小、演化步数等）
4. 保存配置

使用方法:
    python effect_editor.py
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import numpy as np

# 配方目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAW_EFFECTS_DIR = os.path.join(_ROOT, "recipes")
PYWALLPAPER_EFFECTS_DIR = os.path.join(_ROOT, "effects")


class SimpleEffectEditor:
    """简化版效果编辑器"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("PyWallpaper 效果编辑器 (简化版)")
        self.root.geometry("600x500")
        
        self.current_recipe = None
        self.config = {}
        
        self._create_ui()
        self._load_recipes()
        
    def _create_ui(self):
        """创建界面"""
        # 顶部：配方选择
        top = ttk.LabelFrame(self.root, text="配方选择")
        top.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top, text="选择 CA 配方:").pack(side=tk.LEFT, padx=5)
        self.recipe_combo = ttk.Combobox(top, width=40, state="readonly")
        self.recipe_combo.pack(side=tk.LEFT, padx=5)
        self.recipe_combo.bind("<<ComboboxSelected>>", self._on_recipe_selected)
        
        ttk.Button(top, text="刷新", command=self._load_recipes).pack(side=tk.LEFT, padx=5)
        
        # 中间：参数调整
        mid = ttk.LabelFrame(self.root, text="参数调整")
        mid.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建参数控件
        self.param_vars = {}
        
        # 网格大小
        frame = ttk.Frame(mid)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="网格宽度:", width=15).pack(side=tk.LEFT)
        self.param_vars['grid_width'] = tk.IntVar(value=64)
        ttk.Scale(frame, from_=8, to=256, variable=self.param_vars['grid_width'], 
                   orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.param_vars['grid_width']).pack(side=tk.LEFT)
        
        frame = ttk.Frame(mid)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="网格高度:", width=15).pack(side=tk.LEFT)
        self.param_vars['grid_height'] = tk.IntVar(value=64)
        ttk.Scale(frame, from_=8, to=256, variable=self.param_vars['grid_height'], 
                   orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.param_vars['grid_height']).pack(side=tk.LEFT)
        
        # 演化步数
        frame = ttk.Frame(mid)
        frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(frame, text="每帧演化步数:", width=15).pack(side=tk.LEFT)
        self.param_vars['steps_per_frame'] = tk.IntVar(value=1)
        ttk.Scale(frame, from_=1, to=20, variable=self.param_vars['steps_per_frame'], 
                   orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(frame, textvariable=self.param_vars['steps_per_frame']).pack(side=tk.LEFT)
        
        # 音频调制
        frame = ttk.Frame(mid)
        frame.pack(fill=tk.X, padx=5, pady=2)
        self.param_vars['enable_audio'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="启用音频调制", variable=self.param_vars['enable_audio']).pack(side=tk.LEFT)
        
        # 底部：按钮
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(bottom, text="生成配置", command=self._generate_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="保存到效果目录", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="预览 (TODO)", command=self._preview).pack(side=tk.LEFT, padx=5)
        
    def _load_recipes(self):
        """加载配方列表"""
        try:
            files = [f for f in os.listdir(DRAW_EFFECTS_DIR) if f.endswith('.json')]
            # 提取规则名称（假设规则是文件名的第二部分）
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
                
        except Exception as e:
            messagebox.showerror("错误", f"加载配方失败: {e}")
            
    def _on_recipe_selected(self, event):
        """配方选择事件"""
        rule_name = self.recipe_combo.get()
        self.current_recipe = rule_name
        
    def _generate_config(self):
        """生成效果配置"""
        if not self.current_recipe:
            messagebox.showwarning("警告", "请先选择配方")
            return
            
        config = {
            "type": "ca",
            "recipe": self.current_recipe,
            "grid_size": [
                self.param_vars['grid_width'].get(),
                self.param_vars['grid_height'].get()
            ],
            "steps_per_frame": self.param_vars['steps_per_frame'].get(),
            "audio_modulation": {},
            "postprocess": []
        }
        
        # 添加音频调制
        if self.param_vars['enable_audio'].get():
            config["audio_modulation"] = {
                "init_seed": "beat",
                "steps_per_frame": "rms * 10 + 1"
            }
        
        self.config = config
        messagebox.showinfo("成功", "配置已生成，请点击保存")
        
    def _save_config(self):
        """保存配置到效果目录"""
        if not self.config:
            messagebox.showwarning("警告", "请先生成配置")
            return
            
        # 生成文件名
        recipe_name = self.config.get('recipe', 'unknown')
        filename = f"ca_{recipe_name.lower()}_{self.config['grid_size'][0]}x{self.config['grid_size'][1]}.json"
        filepath = os.path.join(PYWALLPAPER_EFFECTS_DIR, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("成功", f"配置已保存到:\n{filepath}")
            
            # 尝试在 pywallpaper 中注册这个新效果
            self._register_effect(filename)
            
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
            
    def _register_effect(self, filename):
        """在 pywallpaper 中注册新效果（修改 effects/__init__.py 或主配置）"""
        # 这里需要根据 pywallpaper 的效果注册机制来实现
        # 暂时只保存 JSON 文件，用户可以手动添加到效果切换列表
        pass
        
    def _preview(self):
        """预览效果（TODO）"""
        messagebox.showinfo("提示", "预览功能待实现")
        

def main():
    root = tk.Tk()
    app = SimpleEffectEditor(root)
    root.mainloop()
    

if __name__ == "__main__":
    main()
