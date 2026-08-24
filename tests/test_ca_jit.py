"""
测试 CA 原语的 JIT 编译功能

对比 JIT 编译和 AST 公式计算的性能
"""

import time
import numpy as np
import sys

# 添加项目路径
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from engine.primitives.ca import CAPrimitive, HAS_NUMBA


def test_jit_vs_ast():
    """对比 JIT 编译和 AST 公式计算的性能"""
    print("=" * 60)
    print("CA 演化性能测试：JIT vs AST")
    print("=" * 60)
    
    # 测试配置
    grid_sizes = [32, 64, 128, 256]
    steps = 100
    
    for grid_size in grid_sizes:
        print(f"\n网格大小: {grid_size}x{grid_size}")
        print("-" * 40)
        
        # 测试 JIT 编译版本
        if HAS_NUMBA:
            config_jit = {
                "recipe": "GameOfLife",
                "grid_size": [grid_size, grid_size],
                "use_jit": True,
                "audio_modulation": {},
                "postprocess": []
            }
            
            ca_jit = CAPrimitive(config_jit, 800, 600)
            
            # 预热 JIT（第一次调用会编译）
            ca_jit._step()
            
            # 测试性能
            start_time = time.time()
            for _ in range(steps):
                ca_jit._step()
            jit_time = time.time() - start_time
            
            jit_fps = steps / jit_time
            print(f"  JIT 编译: {jit_time:.3f}s, {jit_fps:.1f} FPS")
        
        # 测试 AST 公式计算版本
        config_ast = {
            "recipe": "GameOfLife",
            "grid_size": [grid_size, grid_size],
            "use_jit": False,
            "audio_modulation": {},
            "postprocess": []
        }
        
        ca_ast = CAPrimitive(config_ast, 800, 600)
        
        # 测试性能
        start_time = time.time()
        for _ in range(steps):
            ca_ast._step()
        ast_time = time.time() - start_time
        
        ast_fps = steps / ast_time
        print(f"  AST 公式: {ast_time:.3f}s, {ast_fps:.1f} FPS")
        
        # 计算加速比
        if HAS_NUMBA:
            speedup = ast_time / jit_time
            print(f"  加速比: {speedup:.1f}x")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_different_rules():
    """测试不同规则的 JIT 编译性能"""
    print("\n" + "=" * 60)
    print("不同规则的 JIT 编译性能测试")
    print("=" * 60)
    
    rules = ["GameOfLife", "HighLife", "Seeds", "BZReaction", "PureDiffusion"]
    grid_size = 64
    steps = 100
    
    for rule in rules:
        print(f"\n规则: {rule}")
        print("-" * 40)
        
        config = {
            "recipe": rule,
            "grid_size": [grid_size, grid_size],
            "use_jit": True,
            "audio_modulation": {},
            "postprocess": []
        }
        
        try:
            ca = CAPrimitive(config, 800, 600)
            
            # 预热
            ca._step()
            
            # 测试性能
            start_time = time.time()
            for _ in range(steps):
                ca._step()
            elapsed = time.time() - start_time
            
            fps = steps / elapsed
            print(f"  JIT 编译: {elapsed:.3f}s, {fps:.1f} FPS")
            
        except Exception as e:
            print(f"  错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    # 检查依赖
    if not HAS_NUMBA:
        print("警告：未安装 Numba，JIT 编译功能不可用")
        print("请运行：pip install numba")
        sys.exit(1)
    
    # 运行测试
    test_jit_vs_ast()
    test_different_rules()
