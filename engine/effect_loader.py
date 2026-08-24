"""
效果加载器 — 从 effects/*.json 加载引擎效果

支持:
    - 新引擎效果 (class: "EngineEffect") → 零代码扩展
    - 粒子效果 (含 primitive 字段) → 自动包装为 EngineEffect
    - 旧效果类 (class: "BarsEffect" 等) → 通过内置兼容层桥接
"""
import json
import os
import glob
import re
from engine.core import EngineEffect


def _effect_config_has_key(effect_config: dict, key: str) -> bool:
    """检查效果配置是否包含指定键（非空）"""
    val = effect_config.get(key)
    return val is not None and val != ''


def create_effect(effect_config: dict, drawer, width, height, audio):
    """从效果配置创建效果实例

    effect_config: JSON dict (含 class/primitive/params 字段)
    """
    cls_name = effect_config.get('class', '')

    # 1) 标准引擎效果: class == EngineEffect
    if cls_name == 'EngineEffect':
        return EngineEffect(drawer, width, height, audio, effect_config)

    # 2) 粒子效果: 有 primitive 字段 → 自动包装为 EngineEffect
    if _effect_config_has_key(effect_config, 'primitive'):
        return _create_particle_effect(effect_config, drawer, width, height, audio)

    # 3) 旧效果类 — 尝试通过 render_system 的注册表实例化
    #    注意: 必须直接实例化，不能调用 _make_effect()，否则可能引发循环调用
    try:
        from systems.render_system import EFFECT_REGISTRY as LEGACY_REGISTRY
        full_name = effect_config.get('full_name', effect_config.get('name', ''))
        entry = LEGACY_REGISTRY.get(full_name)
        if entry:
            return _instantiate_legacy_entry(entry, drawer, width, height, audio)
    except ImportError:
        pass

    # 4) 最后的 fallback: 尝试直接导入类名
    try:
        import systems.render_system as rs
        cls = getattr(rs, cls_name, None)
        if cls:
            params = effect_config.get('params', {}) or {}
            return cls(drawer, width, height, audio, params=params)
    except Exception:
        pass

    raise ValueError(
        f"无法创建效果: class='{cls_name}', "
        f"效果={effect_config.get('full_name', effect_config.get('name', '?'))}"
    )


def _instantiate_legacy_entry(entry, drawer, width, height, audio):
    """直接实例化旧格式的效果条目（不会调用回 _make_effect，避免循环）"""
    if isinstance(entry, tuple):
        first = entry[0]
        if isinstance(first, dict):
            # 是新格式的 (config_dict,) 条目（没有 class 字段），无法直接实例化
            name = first.get('full_name', first.get('name', '?'))
            raise ValueError(
                f"效果 '{name}' 缺少 'class' 或 'primitive' 字段，无法实例化"
            )
        else:
            # 旧格式 (EffectClass, params) 或 (EffectClass,)
            cls = first
            params = entry[1] if len(entry) > 1 else {}
            return cls(drawer, width, height, audio, params=params)
    elif isinstance(entry, type):
        # 旧格式: 直接是 EffectClass
        return entry(drawer, width, height, audio)
    else:
        raise ValueError(f"无法识别的效果条目格式: {type(entry)}")


def _create_particle_effect(effect_config: dict, drawer, width, height, audio):
    """从 primitive 格式的配置创建粒子效果"""
    primitive_cfg = effect_config['primitive']

    # 构造 EngineEffect 兼容的 wrapped 配置
    wrapped = {
        'class': 'EngineEffect',
        'params': {
            'layers': [primitive_cfg]
        },
    }
    # 复制元数据字段
    for key in ('name', 'full_name', 'id', 'category', 'description',
                'background_theme', 'tags', 'author', 'version'):
        if key in effect_config:
            wrapped[key] = effect_config[key]

    return EngineEffect(drawer, width, height, audio, wrapped)


def load_engine_effects(effects_dir: str = None) -> dict:
    """从 effects/ 目录加载所有效果，返回 {full_name: effect_config} 注册表

    效果配置可直接传给 create_effect() 实例化。
    """
    if effects_dir is None:
        effects_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'effects')

    registry = {}
    pattern = os.path.join(effects_dir, '*_*.json')
    json_files = sorted(
        glob.glob(pattern),
        key=lambda f: int(re.match(r'(\d+)_', os.path.basename(f)).group(1))
    )

    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[LOAD] 跳过 {os.path.basename(jf)}: {e}")
            continue

        full_name = data.get('full_name', data.get('name', ''))
        if full_name:
            registry[full_name] = data

    print(f"[ENGINE] 从 effects/ 加载了 {len(registry)} 个效果配置")
    return registry


def is_engine_effect(config: dict) -> bool:
    """判断是否为引擎驱动效果（通过 EngineEffect 渲染）"""
    # 标准引擎效果 或 粒子原语效果
    return config.get('class', '') == 'EngineEffect' or 'primitive' in config


# 保持与旧 EFFECT_REGISTRY 兼容的加载接口
def build_compat_registry(effects_dir: str = None) -> dict:
    """构建兼容的 EFFECT_REGISTRY

    返回 {full_name: (factory_func_wrapper,)} 元组，
    供 EffectManager 使用。

    factory_func_wrapper 是一个可调用对象，
    在 _make_effect() 中正确处理。
    """
    if effects_dir is None:
        effects_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'effects')

    # 先加载旧注册表
    from systems.render_system import EFFECT_REGISTRY as legacy_registry
    from systems.render_system import load_effects as load_legacy
    load_legacy(effects_dir)

    # 扫描新增的引擎效果（class == EngineEffect 但不在旧注册表中的）
    engine_configs = load_engine_effects(effects_dir)
    merged = dict(legacy_registry)

    for full_name, config in engine_configs.items():
        if full_name not in merged and is_engine_effect(config):
            # 为引擎效果创建一个工厂元组
            merged[full_name] = (config,)

    return merged
