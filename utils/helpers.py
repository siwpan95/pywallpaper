"""
工具函数 - HSV颜色转换、数学辅助等
"""
import math


def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """HSV 转 RGB，h/s/v 范围 [0, 1]，返回 (R, G, B) 0-255"""
    h = h * 6.0
    i = int(h)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return (int(r * 255), int(g * 255), int(b * 255))


def get_energy_color(energy: float, hue_offset: float = 0.0) -> tuple:
    """根据音频能量获取颜色"""
    hue = (0.7 - energy * 0.5 + hue_offset) % 1.0
    saturation = 0.8
    value = 0.3 + energy * 0.7
    return hsv_to_rgb(hue, saturation, value)


def map_freq_to_band(freq: float, num_bands: int = 64) -> int:
    """将频率 (Hz) 映射到频谱带索引 (0 ~ num_bands-1)，使用对数刻度"""
    if freq <= 0:
        return -1
    freq = max(20.0, min(20000.0, freq))
    log_low = math.log2(20.0)
    log_high = math.log2(20000.0)
    log_f = math.log2(freq)
    ratio = (log_f - log_low) / (log_high - log_low)
    return max(0, min(num_bands - 1, int(ratio * num_bands)))


def lerp(a: float, b: float, t: float) -> float:
    """线性插值"""
    return a + (b - a) * t


def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def smooth_damp(current: float, target: float, current_velocity: float, smooth_time: float, max_speed: float = float('inf'), dt: float = 0.016) -> tuple:
    """平滑阻尼过渡 (Unity-like SmoothDamp)"""
    smooth_time = max(0.0001, smooth_time)
    omega = 2.0 / smooth_time
    x = omega * dt
    exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
    change = current - target
    max_change = max_speed * smooth_time
    change = max(-max_change, min(max_change, change))
    target_new = current - change
    temp = (current_velocity + omega * change) * dt
    current_velocity = (current_velocity - omega * temp) * exp
    output = target_new + (change + temp) * exp
    if target_new - current > 0 == output > target_new:
        output = target_new
        current_velocity = (output - target_new) / dt
    return output, current_velocity
