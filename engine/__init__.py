"""
渲染引擎 — 声明式壁纸效果系统

通过 JSON 配置组合绘制原语，实现零代码扩展。
新增效果只需创建 effects/*.json，无需修改任何 Python 代码。

用法:
    from engine import EngineEffect, load_engine_effects
    
    # 加载所有 JSON 效果
    registry = load_engine_effects('effects/')
    
    # 创建效果实例
    effect = registry['132. 自定义效果'].create(drawer, w, h, audio)
    effect.update(dt)
    effect.draw()
"""
from engine.core import EngineEffect
from engine.effect_loader import load_engine_effects, create_effect

__all__ = ['EngineEffect', 'load_engine_effects', 'create_effect']
