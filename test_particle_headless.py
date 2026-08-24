"""
粒子原语 headless 测试
使用 PIL 保存渲染结果到 GIF
"""
import sys
import os
import json
import numpy as np
from PIL import Image, ImageDraw

# 添加 pywallpaper 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.formula_engine import FormulaEngine
from engine.primitives.particle import ParticlePrimitive


class MockAudio:
    """模拟音频对象"""
    def __init__(self):
        self._rms = 0.5
        self._band_energy = [0.3, 0.2, 0.1, 0.05]

    def get_rms(self):
        return self._rms

    def get_band_energy(self, idx):
        return self._band_energy[idx] if idx < len(self._band_energy) else 0.0

    def detect_beat(self):
        return False


def test_particle_effect(json_path, output_path, frames=60):
    """
    测试粒子效果

    Args:
        json_path: 效果 JSON 文件路径
        output_path: 输出 GIF 路径
        frames: 渲染帧数
    """
    # 加载效果配置
    with open(json_path, 'r', encoding='utf-8') as f:
        effect_data = json.load(f)

    config = effect_data['primitive']

    # 创建粒子原语
    width, height = 800, 600
    particle = ParticlePrimitive(config, width, height)

    # 创建模拟音频
    audio = MockAudio()

    # 渲染帧
    images = []
    dt = 1.0 / 30  # 30 FPS

    for frame_idx in range(frames):
        # 更新粒子状态
        particle.update(dt, audio, frame_idx * dt)

        # 创建新图片
        img = Image.new('RGB', (width, height), color=(0, 0, 0))
        drawer = ImageDraw.Draw(img)

        # 绘制粒子
        particle.draw(drawer)

        # 添加调试信息
        debug = particle.get_debug_info()
        drawer.text((10, 10), f"Particles: {debug['particle_count']}", fill=(255, 255, 255))

        images.append(img)

        # 打印进度
        if (frame_idx + 1) % 10 == 0:
            print(f"  渲染进度: {frame_idx + 1}/{frames}")

    # 保存为 GIF
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=int(dt * 1000),
        loop=0
    )
    print(f"[OK] 保存到: {output_path}")


if __name__ == '__main__':
    print("=" * 60)
    print("粒子原语 Headless 测试")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    effects_dir = os.path.join(base_dir, 'effects')

    # 测试效果列表
    test_effects = [
        '080_particle_fireworks.json',
        '081_particle_rain.json',
        '082_particle_snow.json'
    ]

    for effect_name in test_effects:
        print(f"\n测试效果: {effect_name}")
        json_path = os.path.join(effects_dir, effect_name)

        if not os.path.exists(json_path):
            print(f"  [ERR] 文件不存在: {json_path}")
            continue

        output_name = effect_name.replace('.json', '.gif')
        output_path = os.path.join(base_dir, output_name)

        try:
            test_particle_effect(json_path, output_path, frames=60)
        except Exception as e:
            print(f"  [ERR] 测试失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
