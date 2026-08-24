"""
CA 演化核 — 使用 Numba JIT 编译优化性能

这个模块提供高性能的 CA 演化函数，使用 Numba JIT 编译。
支持多种预定义规则，性能比纯 NumPy 实现快 10-100 倍。

使用方法:
    from engine.primitives.ca_kernel import evolve_game_of_life
    
    # 创建网格
    grid = np.random.random((64, 64)).astype(np.float32)
    
    # 执行一步演化
    evolve_game_of_life(grid)
    
    # 或者使用通用的演化函数（根据规则 ID 选择）
    from engine.primitives.ca_kernel import evolve_ca
    evolve_ca(grid, rule_id=0)  # 0 = Game of Life
"""

import numpy as np
import numba as nb


# 预定义规则 ID
RULE_GAME_OF_LIFE = 0
RULE_HIGH_LIFE = 1
RULE_SEEDS = 2
RULE_BZ_REACTION = 3
RULE_PURE_DIFFUSION = 4


@nb.jit(nopython=True, cache=True)
def _calc_moore_sum(grid: np.ndarray) -> np.ndarray:
    """计算 Moore 邻域和（8个邻居）— JIT 编译"""
    h, w = grid.shape
    sum_n = np.zeros_like(grid)
    
    for i in range(h):
        for j in range(w):
            # 上
            sum_n[i, j] += grid[(i-1) % h, j]
            # 下
            sum_n[i, j] += grid[(i+1) % h, j]
            # 左
            sum_n[i, j] += grid[i, (j-1) % w]
            # 右
            sum_n[i, j] += grid[i, (j+1) % w]
            # 左上
            sum_n[i, j] += grid[(i-1) % h, (j-1) % w]
            # 右上
            sum_n[i, j] += grid[(i-1) % h, (j+1) % w]
            # 左下
            sum_n[i, j] += grid[(i+1) % h, (j-1) % w]
            # 右下
            sum_n[i, j] += grid[(i+1) % h, (j+1) % w]
    
    return sum_n


@nb.jit(nopython=True, cache=True)
def evolve_game_of_life(grid: np.ndarray):
    """Game of Life 演化规则 — JIT 编译
    
    规则:
        - 活细胞有 2-3 个活邻居时存活
        - 死细胞有恰好 3 个活邻居时复活
    """
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


@nb.jit(nopython=True, cache=True)
def evolve_high_life(grid: np.ndarray):
    """HighLife 演化规则 — JIT 编译
    
    规则:
        - 活细胞有 2-3 个活邻居时存活
        - 死细胞有恰好 3 或 6 个活邻居时复活
    """
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
                if neighbors == 3 or neighbors == 6:
                    new_grid[i, j] = 1.0
    
    # 更新网格
    for i in range(h):
        for j in range(w):
            grid[i, j] = new_grid[i, j]


@nb.jit(nopython=True, cache=True)
def evolve_seeds(grid: np.ndarray):
    """Seeds 演化规则 — JIT 编译
    
    规则:
        - 所有活细胞立即死亡
        - 死细胞有恰好 2 个活邻居时复活
    """
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
            
            # 应用规则（所有活细胞都死亡，只有死细胞可以复活）
            if grid[i, j] < 0.5:  # 死细胞
                if neighbors == 2:
                    new_grid[i, j] = 1.0
    
    # 更新网格
    for i in range(h):
        for j in range(w):
            grid[i, j] = new_grid[i, j]


@nb.jit(nopython=True, cache=True)
def evolve_bz_reaction(grid: np.ndarray, dt=0.1):
    """BZ Reaction 演化规则 — JIT 编译
    
    规则:
        - 使用反应扩散方程模拟 BZ 化学反应
        - grid 值表示激活水平 (0-1)
    """
    h, w = grid.shape
    
    for i in range(h):
        for j in range(w):
            # 计算邻域平均值
            avg = (
                grid[(i-1)%h, j] + grid[(i+1)%h, j] +
                grid[i, (j-1)%w] + grid[i, (j+1)%w] +
                grid[(i-1)%h, (j-1)%w] + grid[(i-1)%h, (j+1)%w] +
                grid[(i+1)%h, (j-1)%w] + grid[(i+1)%h, (j+1)%w]
            ) / 8.0
            
            # BZ Reaction 简化模型
            # 如果激活水平高，保持激活；否则根据邻域扩散
            if grid[i, j] > 0.5:
                grid[i, j] = min(1.0, grid[i, j] + dt * (1.0 - grid[i, j]))
            else:
                grid[i, j] = grid[i, j] + dt * (avg - grid[i, j])


@nb.jit(nopython=True, cache=True)
def evolve_pure_diffusion(grid: np.ndarray, diffusion_rate=0.1):
    """Pure Diffusion 演化规则 — JIT 编译
    
    规则:
        - 使用扩散方程平滑网格值
        - grid 值表示某种物质的浓度
    """
    h, w = grid.shape
    new_grid = np.zeros_like(grid)
    
    for i in range(h):
        for j in range(w):
            # 计算邻域平均值
            avg = (
                grid[(i-1)%h, j] + grid[(i+1)%h, j] +
                grid[i, (j-1)%w] + grid[i, (j+1)%w] +
                grid[(i-1)%h, (j-1)%w] + grid[(i-1)%h, (j+1)%w] +
                grid[(i+1)%h, (j-1)%w] + grid[(i+1)%h, (j+1)%w]
            ) / 8.0
            
            # 扩散方程：新值 = 旧值 + 扩散率 * (邻域平均值 - 旧值)
            new_grid[i, j] = grid[i, j] + diffusion_rate * (avg - grid[i, j])
    
    # 更新网格
    for i in range(h):
        for j in range(w):
            grid[i, j] = new_grid[i, j]


@nb.jit(nopython=True, cache=True)
def evolve_ca(grid: np.ndarray, rule_id: int):
    """通用 CA 演化函数 — 根据 rule_id 选择规则
    
    Args:
        grid: 网格数组 (h, w)，值范围 [0, 1]
        rule_id: 规则 ID（参见上面的预定义常量）
    """
    if rule_id == 0:
        evolve_game_of_life(grid)
    elif rule_id == 1:
        evolve_high_life(grid)
    elif rule_id == 2:
        evolve_seeds(grid)
    elif rule_id == 3:
        evolve_bz_reaction(grid)
    elif rule_id == 4:
        evolve_pure_diffusion(grid)
    else:
        # 默认：Game of Life
        evolve_game_of_life(grid)


def get_kernel_for_recipe(recipe_name: str):
    """根据配方名称返回对应的 JIT 编译核函数
    
    Args:
        recipe_name: 配方名称（如 "GameOfLife", "BZReaction"）
        
    Returns:
        (kernel_func, rule_id) 元组
    """
    # 简单匹配：根据配方名称中的关键字选择规则
    recipe_lower = recipe_name.lower()
    
    if 'gameoflife' in recipe_lower or 'game_of_life' in recipe_lower:
        return evolve_game_of_life, RULE_GAME_OF_LIFE
    elif 'highlife' in recipe_lower:
        return evolve_high_life, RULE_HIGH_LIFE
    elif 'seeds' in recipe_lower:
        return evolve_seeds, RULE_SEEDS
    elif 'bzreaction' in recipe_lower or 'bz_reaction' in recipe_lower:
        return evolve_bz_reaction, RULE_BZ_REACTION
    elif 'purediffusion' in recipe_lower or 'pure_diffusion' in recipe_lower:
        return evolve_pure_diffusion, RULE_PURE_DIFFUSION
    else:
        # 默认：Game of Life
        return evolve_game_of_life, RULE_GAME_OF_LIFE
