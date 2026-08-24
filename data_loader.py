"""
数据加载器 - 缓存式 JSON 配置加载，供所有系统共享使用
"""
import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
_cache = {}


def _load_json(filename: str) -> dict:
    path = os.path.join(_DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_config() -> dict:
    """获取壁纸配置（缓存）"""
    if 'config' not in _cache:
        _cache['config'] = _load_json('config.json')
    return _cache['config']


def get_effects() -> list:
    """获取效果定义列表（缓存）"""
    if 'effects' not in _cache:
        data = _load_json('effects.json')
        _cache['effects'] = data.get('effects', [])
    return _cache['effects']


def get_audio_data() -> dict:
    """获取音频理论数据（缓存）"""
    if 'audio' not in _cache:
        _cache['audio'] = _load_json('audio.json')
    return _cache['audio']


def reload_all():
    """重新加载所有配置"""
    _cache.clear()
