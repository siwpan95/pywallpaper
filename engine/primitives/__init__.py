"""
绘制原语基类 + 原语注册表

所有原语继承 RenderPrimitive，实现 update() 和 draw()。
通过 PRIMITIVE_REGISTRY 按名称查找和实例化。
"""
import math
from PIL import ImageDraw

from engine.color_system import ColorGenerator
from engine.audio_map import MultiAudioMapping
from engine.utils import parse_position, parse_size


class RenderPrimitive:
    """绘制原语基类"""

    def __init__(self, config: dict, width: int, height: int):
        self.config = config
        self.width = width
        self.height = height
        self.cx = width // 2
        self.cy = height // 2

        # 位置和尺寸
        pos_cfg = config.get('position', {})
        size_cfg = config.get('size', {})
        self.x, self.y = parse_position(pos_cfg, width, height)
        self.w, self.h = parse_size(size_cfg, width, height)

        # 距中心的最大安全距离（留 5% 边距，防止任何效果超出渲染区域）
        self._max_safe_radius = min(width, height) * 0.475

        # 颜色系统
        color_cfg = config.get('color', {})
        self.color_gen = ColorGenerator.create(color_cfg)

        # 音频映射
        audio_cfg = config.get('audio', {})
        self.audio_map = MultiAudioMapping.from_config(audio_cfg)

        # 中心点（可覆盖）
        center = config.get('center', {})
        if center:
            self.cx, self.cy = parse_position(center, width, height)

        # 旋转
        rotation = config.get('rotation', {})
        self.rotation_enabled = bool(rotation)
        self.rotation_speed = rotation.get('speed', 0.0) if self.rotation_enabled else 0.0
        self.rotation_angle = rotation.get('angle', 0.0) if self.rotation_enabled else 0.0

        # 预设的音频引用和全局时间
        self._audio = None
        self._time = 0.0

    def update(self, dt: float, audio, global_time: float):
        """更新原语状态"""
        self._audio = audio
        self._time = global_time
        if self.rotation_enabled:
            self.rotation_angle += self.rotation_speed * dt

    def draw(self, drawer: ImageDraw.ImageDraw):
        """绘制原语 — 子类必须实现"""
        raise NotImplementedError

    def _get_audio_value(self, target: str, index: int, dt: float = 0.016, default: float = 0.0) -> float:
        """获取音频映射值"""
        return self.audio_map.get_or_default(target, self._audio, index, dt, default)

    def _get_color(self, index: int = 0, total: int = 1, energy: float = 0.0) -> tuple:
        """获取颜色"""
        return self.color_gen.get_color(index, total, self._time, energy)

    def _rotated_point(self, x: float, y: float, cx: float = None, cy: float = None) -> tuple:
        """绕中心旋转点"""
        if not self.rotation_enabled or self.rotation_angle == 0:
            return x, y
        cx = cx if cx is not None else self.cx
        cy = cy if cy is not None else self.cy
        cos_a = math.cos(self.rotation_angle)
        sin_a = math.sin(self.rotation_angle)
        dx, dy = x - cx, y - cy
        return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


# ==================== 原语注册表 ====================
PRIMITIVE_REGISTRY = {}


def register_primitive(name: str):
    """装饰器：注册原语类"""
    def decorator(cls):
        PRIMITIVE_REGISTRY[name] = cls
        return cls
    return decorator


def create_primitive(config: dict, width: int, height: int) -> RenderPrimitive:
    """从配置创建原语实例"""
    ptype = config.get('type', '')
    cls = PRIMITIVE_REGISTRY.get(ptype)
    if cls is None:
        raise ValueError(f"未知原语类型: '{ptype}'，可用: {list(PRIMITIVE_REGISTRY.keys())}")
    return cls(config, width, height)


# ==================== 导入所有原语以触发注册 ====================
from engine.primitives.bars import BarsPrimitive
from engine.primitives.spikes import SpikesPrimitive
from engine.primitives.waveform import WaveformPrimitive
from engine.primitives.vortex import VortexPrimitive
from engine.primitives.circle_map import CircleMapPrimitive
from engine.primitives.particles import ParticlesPrimitive
from engine.primitives.grid import GridPrimitive
from engine.primitives.drawing import DrawingPrimitive
from engine.primitives.text_rain import TextRainPrimitive
from engine.primitives.script import ScriptPrimitive
from engine.primitives.wireframe_3d import Wireframe3DPrimitive
from engine.primitives.texture import TexturePrimitive
from engine.primitives.curve import CurvePrimitive
from engine.primitives.cellular import CellularPrimitive
from engine.primitives.pulse import PulsePrimitive
from engine.primitives.gauge import GaugePrimitive
from engine.primitives.ca import CAPrimitive
from engine.primitives.particle import ParticlePrimitive
from engine.primitives.fluid import FluidPrimitive
from engine.primitives.formula import FormulaPrimitive
