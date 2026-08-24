"""
音频映射系统 — 将音频数据映射到视觉属性

支持的 source:
    band_energy    — 单个频段能量 (index % 64)
    full_spectrum  — 全频谱数据
    rms            — 总体音量 RMS
    beat           — 节拍检测 (简化版: 低频能量)

支持多目标映射：
    一个 AudioMapping 实例映射一个视觉属性。
    多个映射可组合到同一个原语的不同属性上。
"""
import math


class AudioMapping:
    """单个音频→视觉属性映射

    配置:
        source: str      数据源 ('band_energy'/'full_spectrum'/'rms'/'beat')
        target: str      目标属性
        scale: [min, max] 输出范围
        smoothing: float 平滑系数 (0~1, 越大越平滑)
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.source = config.get('source', 'band_energy')
        self.target = config.get('target', 'value')
        scale = config.get('scale', [0.0, 1.0])
        self.scale_min = float(scale[0])
        self.scale_max = float(scale[1])
        self.smoothing = config.get('smoothing', 0.85)
        self._smooth_cache = {}

    def get_value(self, audio, index: int, dt: float = 0.016) -> float:
        """获取元素 index 的映射值"""
        raw = self._get_raw(audio, index)
        key = str(index)
        prev = self._smooth_cache.get(key, raw)
        smoothed = prev * self.smoothing + raw * (1.0 - self.smoothing)
        self._smooth_cache[key] = smoothed
        return self.scale_min + smoothed * (self.scale_max - self.scale_min)

    def get_value_no_smooth(self, audio, index: int) -> float:
        """不经过平滑的原始映射值"""
        raw = self._get_raw(audio, index)
        return self.scale_min + raw * (self.scale_max - self.scale_min)

    def _get_raw(self, audio, index: int) -> float:
        if self.source == 'band_energy':
            return audio.get_band_energy(index % 64)
        elif self.source == 'full_spectrum':
            spectrum = audio.get_full_spectrum()
            if spectrum and index < len(spectrum):
                return spectrum[index]
            return 0.0
        elif self.source == 'rms':
            return audio.get_rms() if hasattr(audio, 'get_rms') else self._calc_rms(audio)
        elif self.source == 'beat':
            # 简化节拍检测: 低频段平均能量
            low_energy = sum(audio.get_band_energy(i) for i in range(4)) / 4.0
            return low_energy
        return 0.0

    def _calc_rms(self, audio) -> float:
        """计算 RMS（如果 AudioSimulator 没有 get_rms）"""
        bands = [audio.get_band_energy(i) for i in range(64)]
        return math.sqrt(sum(b * b for b in bands) / max(len(bands), 1))


class MultiAudioMapping:
    """组合多个音频映射"""

    def __init__(self, configs: list = None):
        self.mappings = {}
        if configs:
            for cfg in configs:
                m = AudioMapping(cfg)
                self.mappings[m.target] = m

    def get(self, target: str, audio, index: int, dt: float = 0.016) -> float:
        """获取指定目标属性的映射值"""
        m = self.mappings.get(target)
        if m:
            return m.get_value(audio, index, dt)
        return None

    def get_or_default(self, target: str, audio, index: int, dt: float = 0.016, default: float = 0.0) -> float:
        val = self.get(target, audio, index, dt)
        return val if val is not None else default

    @staticmethod
    def from_config(config) -> 'MultiAudioMapping':
        """从配置创建 — 支持单个或列表"""
        if not config:
            return MultiAudioMapping()
        if isinstance(config, list):
            return MultiAudioMapping(config)
        if isinstance(config, dict):
            # 单个映射
            return MultiAudioMapping([config])
        return MultiAudioMapping()
