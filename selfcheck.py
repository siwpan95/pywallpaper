#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pywallpaper（数学公式驱动的动态壁纸引擎）无头自检。

只导入无窗口的纯逻辑层：ecs（ECS 框架）、engine.formula_engine（公式引擎）、
engine.primitives.particle（粒子原语），不导入 main / systems.wallpaper_system
（pygame 窗口 + Windows 壁纸 API + 主循环）。

验证点：
  1. ECS 状态推进：实体/组件/系统装配，world.update(dt) 按 priority 顺序推进
     位置组件，组件查询、enabled() 禁用系统被跳过、实体销毁、全局数据读写；
  2. 公式引擎算法结果：向量化表达式求值、`a if cond else b` 到 where 的翻译、
     标量/数组混合求值；
  3. 粒子原语生命周期（纯 numpy + PIL，无音频设备）：发射 -> 绘制出非黑像素 ->
     生命耗尽后粒子数归零，且不超过 max_particles 上限。

numpy / Pillow / asteval 均已在 requirements.txt 中，不新增依赖、不开窗口、不落盘。
"""
import os
import sys
import time
import traceback
from dataclasses import dataclass


def _setup_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class _MockAudio:
    """最小音频桩件：不打开音频设备，返回固定频谱值。"""

    def get_rms(self):
        return 0.5

    def get_band_energy(self, idx):
        return [0.3, 0.2, 0.1, 0.05][idx] if idx < 4 else 0.0

    def detect_beat(self):
        return False


def run_checks():
    import numpy as np

    from ecs import Component, System, World

    checks = []

    # --- 1. ECS 状态推进 -----------------------------------------------------
    @dataclass
    class Position(Component):
        x: float = 0.0
        y: float = 0.0

    @dataclass
    class Velocity(Component):
        dx: float = 0.0
        dy: float = 0.0

    order = []

    class MoveSystem(System):
        priority = 10

        def update(self, world, dt):
            order.append("move")
            for entity in world.each(Position, Velocity):
                pos = entity.get(Position)
                vel = entity.get(Velocity)
                pos.x += vel.dx * dt
                pos.y += vel.dy * dt

    class DisabledSystem(System):
        priority = 20

        def enabled(self, world):
            return False

        def update(self, world, dt):
            order.append("disabled")

    class LateSystem(System):
        priority = 100

        def update(self, world, dt):
            order.append("late")

    world = World()
    ball = world.create_entity("ball").add_component(Position(0.0, 0.0)).add_component(Velocity(10.0, -4.0))
    box = world.create_entity("box").add_component(Position(5.0, 5.0))  # 无 Velocity，不应被系统推进
    world.add_system(LateSystem()).add_system(DisabledSystem()).add_system(MoveSystem())

    if world.entity_count() != 2:
        raise AssertionError(f"实体数错误: {world.entity_count()}")
    if len(world.get_entities_with_components(Position, Velocity)) != 1:
        raise AssertionError("组件查询结果错误")

    world.update(0.5)
    world.update(0.5)
    pos = ball.get(Position)
    if abs(pos.x - 10.0) > 1e-6 or abs(pos.y + 4.0) > 1e-6:
        raise AssertionError(f"MovementSystem 推进错误: ({pos.x}, {pos.y})")
    if (box.get(Position).x, box.get(Position).y) != (5.0, 5.0):
        raise AssertionError("无 Velocity 的实体不应被推进")
    if order != ["move", "late", "move", "late"]:
        raise AssertionError(f"系统优先级/禁用状态错误: {order}")

    world.set_data("frame", 2)
    if world.get_data("frame") != 2 or world.get_data("missing", "d") != "d":
        raise AssertionError("全局数据读写错误")

    world.remove_system(LateSystem)
    order.clear()
    world.update(0.1)
    if order != ["move"]:
        raise AssertionError(f"移除系统后仍在执行: {order}")

    world.destroy_entity(box.id)
    if world.entity_count() != 1 or world.has_entity("box"):
        raise AssertionError("实体销毁失败")
    checks.append("ECS 状态推进：2 帧后位置按 dt 累加，priority 排序、disable/移除生效，实体销毁与全局数据正常")

    # --- 2. 公式引擎算法结果 -------------------------------------------------
    from engine.formula_engine import FormulaEngine

    engine = FormulaEngine()
    fn = engine.compile("x * 2 + 1", ["x"])
    got = engine.evaluate(fn, x=np.array([1.0, 2.0, 3.0]))
    if not np.allclose(got, [3.0, 5.0, 7.0]):
        raise AssertionError(f"向量化求值错误: {got}")

    fn_where = engine.compile("sin(t) if t > 0 else 0", ["t"])
    got_where = engine.evaluate(fn_where, t=np.array([0.0, np.pi / 6]))
    if not np.allclose(got_where, [0.0, 0.5], atol=1e-9):
        raise AssertionError(f"条件表达式未翻译为 where: {got_where}")

    fn_mix = engine.compile("x * 2 + 1", ["x"])
    scalar = engine.evaluate(fn_mix, x=np.float64(10.0))
    if float(scalar) != 21.0:
        raise AssertionError(f"标量求值错误: {scalar}")
    checks.append(f"公式引擎：x*2+1 -> {got.tolist()}，条件式 -> where -> {np.round(got_where, 3).tolist()}")

    # --- 3. 粒子原语生命周期 -------------------------------------------------
    from PIL import Image, ImageDraw

    from engine.primitives.particle import ParticlePrimitive

    config = {
        "emitters": [{
            "position": [0.5, 0.5],
            "rate": 100,
            "lifetime": [0.2, 0.2],
            "speed": [0, 0],
            "direction": [0, 360],
            "color": [255, 255, 255],
            "size": [2, 2],
        }],
        "forces": [],
        "particle_type": "circle",
        "max_particles": 500,
    }
    particle = ParticlePrimitive(config, 160, 120)
    audio = _MockAudio()
    if particle.get_debug_info()["particle_count"] != 0:
        raise AssertionError("新建粒子系统不应已有粒子")

    for frame in range(3):
        particle.update(1.0 / 30, audio, frame / 30.0)
    alive = particle.get_debug_info()["particle_count"]
    if not 0 < alive <= 500:
        raise AssertionError(f"粒子发射数量异常: {alive}")

    canvas = Image.new("RGB", (160, 120), (0, 0, 0))
    particle.draw(ImageDraw.Draw(canvas))
    lit = sum(1 for byte in canvas.tobytes() if byte)  # 非零通道数 > 0 即说明画出了粒子
    if lit == 0:
        raise AssertionError("粒子未绘制出任何像素")

    particle.update(0.5, audio, 0.6)  # 生命周期 0.2s，全部应当过期被压缩移除
    remaining = particle.get_debug_info()["particle_count"]
    if remaining != 0:
        raise AssertionError(f"过期粒子未被移除: {remaining}")

    # 上限：极高发射率下不允许超过 max_particles
    heavy = ParticlePrimitive(dict(config, max_particles=40), 80, 60)
    for frame in range(10):
        heavy.update(0.1, audio, frame * 0.1)
    if heavy.get_debug_info()["particle_count"] > 40:
        raise AssertionError("粒子数超过 max_particles 上限")
    checks.append(f"粒子原语：3 帧发射 {alive} 个粒子并绘出 {lit} 个非零色彩通道，过期后归零，上限 40 生效")

    return checks


def main() -> int:
    _setup_stdout()
    started = time.time()
    try:
        checks = run_checks()
    except Exception as exc:
        print(f"selfcheck FAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    print(f"selfcheck ok: pywallpaper 无头核心逻辑（{'; '.join(checks)}）"
          f" [{time.time() - started:.2f}s]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
