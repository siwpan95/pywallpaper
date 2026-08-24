"""
简单测试 — 只测试 ca_kernel.py 的 JIT 编译函数

不依赖 pywallpaper 项目，直接测试 JIT 编译性能
"""

import time
import numpy as np

# 直接导入 ca_kernel
from engine.primitives.ca_kernel import (
    evolve_game_of_life, evolve_high_life, evolve_seeds,
    evolve_bz_reaction, evolve_pure_diffusion
)


def test_kernel_performance():
    """测试 JIT 编译核函数的性能"""
    print("=" * 60)
    print("CA 演化核性能测试（JIT 编译）")
    print("=" * 60)
    
    # 测试配置
    grid_sizes = [32, 64, 128, 256]
    steps = 100
    
    kernels = [
        ("Game of Life", evolve_game_of_life),
        ("HighLife", evolve_high_life),
        ("Seeds", evolve_seeds),
        ("BZ Reaction", evolve_bz_reaction),
        ("Pure Diffusion", evolve_pure_diffusion),
    ]
    
    for grid_size in grid_sizes:
        print(f"\n网格大小: {grid_size}x{grid_size}")
        print("-" * 40)
        
        for name, kernel in kernels:
            # 创建测试网格
            grid = np.random.random((grid_size, grid_size)).astype(np.float32)
            
            # 预热 JIT（第一次调用会编译）
            kernel(grid)
            
            # 测试性能
            start_time = time.time()
            for _ in range(steps):
                kernel(grid)
            elapsed = time.time() - start_time
            
            fps = steps / elapsed
            print(f"  {name:20s}: {elapsed:.3f}s, {fps:.1f} FPS")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_vs_numpy():
    """对比 JIT 编译和纯 NumPy 实现的性能"""
    print("\n" + "=" * 60)
    print("性能对比：JIT vs NumPy")
    print("=" * 60)
    
    grid_size = 64
    steps = 100
    
    # 创建测试网格
    grid_jit = np.random.random((grid_size, grid_size)).astype(np.float32)
    grid_np = np.random.random((grid_size, grid_size)).astype(np.float32)
    
    # 测试 JIT 版本
    print(f"\n网格大小: {grid_size}x{grid_size}")
    print("-" * 40)
    
    # 预热
    evolve_game_of_life(grid_jit)
    
    start_time = time.time()
    for _ in range(steps):
        evolve_game_of_life(grid_jit)
    jit_time = time.time() - start_time
    
    jit_fps = steps / jit_time
    print(f"  JIT 编译: {jit_time:.3f}s, {jit_fps:.1f} FPS")
    
    # 测试 NumPy 版本
    start_time = time.time()
    for _ in range(steps):
        _step_numpy(grid_np)
    np_time = time.time() - start_time
    
    np_fps = steps / np_time
    print(f"  NumPy 实现: {np_time:.3f}s, {np_fps:.1f} FPS")
    
    # 计算加速比
    speedup = np_time / jit_time
    print(f"\n  加速比: {speedup:.1f}x")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def _step_numpy(grid: np.ndarray):
    """纯 NumPy 实现的 Game of Life"""
    h, w = grid.shape
    new_grid = np.zeros_like(grid)
    
    for i in range(h):
        for j in range(w):
            # 计算活邻居数
            neighbors = (
                grid[(i-1)%h, j] + grid[(i+1)%h, j] +
                grid[i, (j-1)%w] + grid[i, (j+1)%w] +
                grid[(i-1)%h, (j-1)%w] + grid[(i-1)%h, (j+1)%w] +
                grid[(i+1)%h, (j-1)%w] + grid[(i+1)%h, (j+1)%w]
            )
            
            # 应用规则
            if grid[i, j] > 0.5:  # 活细胞
                if 2 <= neighbors <= 3:
                    new_grid[i, j] = 1.0
            else:  # 死细胞
                if neighbors == 3:
                    new_grid[i, j] = 1.0
    
    # 更新网格
    for i in range(h):
        for j in range(w):
            grid[i, j] = new_grid[i, j]


if __name__ == "__main__":
    # 运行测试
    test_kernel_performance()
    test_vs_numpy()
