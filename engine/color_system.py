"""
颜色系统 — 声明式颜色生成

支持的类型:
    solid     — 固定颜色 [r, g, b]
    hsv_flow  — HSV 流动渐变（按元素和时间分配色相）
    energy    — 音频能量映射颜色
    rainbow   — 彩虹循环色
"""
import math
from utils.helpers import hsv_to_rgb, get_energy_color


class ColorGenerator:
    """颜色生成器基类"""

    def get_color(self, index: int, total: int, time: float, energy: float = 0.0) -> tuple:
        """返回 (r, g, b) 元组"""
        raise NotImplementedError

    @staticmethod
    def create(config) -> 'ColorGenerator':
        """从配置创建颜色生成器"""
        if not config or not isinstance(config, dict):
            return HSVFlowColor({})
        t = config.get('type', 'hsv_flow')
        if t == 'solid':
            return SolidColor(config)
        elif t == 'hsv_flow':
            return HSVFlowColor(config)
        elif t == 'energy':
            return EnergyColor(config)
        elif t == 'rainbow':
            return RainbowColor(config)
        else:
            return HSVFlowColor({})


class SolidColor(ColorGenerator):
    """固定颜色"""

    def __init__(self, config: dict):
        val = config.get('value', [255, 255, 255])
        if isinstance(val, str) and val.startswith('#'):
            val = val.lstrip('#')
            self.color = tuple(int(val[i:i+2], 16) for i in (0, 2, 4))
        else:
            self.color = tuple(val[:3])

    def get_color(self, index: int = 0, total: int = 1, time: float = 0.0, energy: float = 0.0) -> tuple:
        return self.color


class HSVFlowColor(ColorGenerator):
    """HSV 流动渐变 — 色相在元素间和时间上流动

    配置:
        hue: [min, max]  色相范围 (0~1 或 0~360)
        speed: float     时间流动速度
        sat: float       饱和度
        val: float        明度
    """

    def __init__(self, config: dict):
        hue_range = config.get('hue', config.get('hue_range', [0, 0.7]))
        self.hue_min = min(hue_range[0], hue_range[1])
        self.hue_max = max(hue_range[0], hue_range[1])
        self.speed = config.get('speed', config.get('color_speed', 0.1))
        self.sat = config.get('sat', config.get('saturation', 0.8))
        self.val = config.get('val', config.get('value', 0.9))

    def get_color(self, index: int = 0, total: int = 1, time: float = 0.0, energy: float = 0.0) -> tuple:
        frac = index / max(total, 1)
        hue = (frac * (self.hue_max - self.hue_min) + self.hue_min + time * self.speed) % 1.0
        return hsv_to_rgb(hue, self.sat, self.val)


class EnergyColor(ColorGenerator):
    """能量颜色 — 根据音频能量级别映射颜色

    配置:
        hue_offset: float  色相偏移
    """

    def __init__(self, config: dict):
        self.hue_offset = config.get('hue_offset', 0.0)

    def get_color(self, index: int = 0, total: int = 1, time: float = 0.0, energy: float = 0.0) -> tuple:
        return get_energy_color(energy, self.hue_offset)


class RainbowColor(ColorGenerator):
    """彩虹色 — 色相循环，所有元素共享同一色相

    配置:
        speed: float  色相循环速度
        sat: float    饱和度
        val: float     明度
    """

    def __init__(self, config: dict):
        self.speed = config.get('speed', 0.05)
        self.sat = config.get('sat', 0.8)
        self.val = config.get('val', 0.9)

    def get_color(self, index: int = 0, total: int = 1, time: float = 0.0, energy: float = 0.0) -> tuple:
        hue = (time * self.speed) % 1.0
        return hsv_to_rgb(hue, self.sat, self.val)
