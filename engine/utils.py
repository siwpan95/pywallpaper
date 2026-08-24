"""
引擎工具函数 — 坐标解析等
"""
import math


def parse_position(pos_config, width, height):
    """解析位置配置，支持像素值和百分比

    配置格式:
        {"x": "50%", "y": 100} 或 {"x": 0, "y": 0}
    """
    x = pos_config.get('x', 0) if pos_config else 0
    y = pos_config.get('y', 0) if pos_config else 0

    def _parse(val, total):
        if isinstance(val, str):
            val = val.strip()
            if val.endswith('%'):
                return int(total * float(val.rstrip('%')) / 100)
            if val == 'center':
                return total // 2
        return int(val)

    return _parse(x, width), _parse(y, height)


def parse_size(size_config, width, height):
    """解析尺寸配置

    配置格式:
        {"width": "100%", "height": "70%"} 或 {"width": 300, "height": 200}
    """
    w = size_config.get('width', width) if size_config else width
    h = size_config.get('height', height) if size_config else height

    def _parse(val, total):
        if isinstance(val, str) and val.endswith('%'):
            return int(total * float(val.rstrip('%')) / 100)
        return int(val)

    return _parse(w, width), _parse(h, height)
