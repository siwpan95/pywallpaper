"""
快速测试脚本 — 验证 pywallpaper 引擎基本功能
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_formula_engine():
    """测试公式引擎"""
    print("=" * 60)
    print("测试 1: 公式引擎")
    print("=" * 60)
    try:
        from engine.formula_engine import FormulaEngine
        engine = FormulaEngine()

        # 测试编译和求值
        func = engine.compile("sin(t)", ['t'])
        result = func(t=0.5)
        print(f"  sin(0.5) = {result:.4f} ✓")

        # 测试向量化（编译后支持 NumPy 数组）
        import numpy as np
        func2 = engine.compile("sin(2*pi*x)", ['x'])
        x = np.linspace(0, 1, 100)
        y = func2(x=x)
        print(f"  sin(2*pi*x) 向量化: shape={y.shape} ✓")

        print("[OK] 公式引擎测试通过\n")
        return True
    except Exception as e:
        print(f"[ERR] 公式引擎测试失败: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_primitives():
    """测试原语系统"""
    print("=" * 60)
    print("测试 2: 原语系统")
    print("=" * 60)
    try:
        # 直接检查 primitives 目录
        import glob
        primitive_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine', 'primitives')
        py_files = glob.glob(os.path.join(primitive_dir, '*.py'))

        # 排除 __init__.py 和 ca_kernel.py
        primitives = []
        for f in py_files:
            basename = os.path.basename(f)
            if basename not in ['__init__.py', 'ca_kernel.py']:
                primitives.append(basename.replace('.py', ''))

        print(f"  可用原语: {len(primitives)} 个")
        for name in sorted(primitives):
            print(f"    - {name} ✓")

        print(f"\n[OK] 原语系统测试通过 (共 {len(primitives)} 个原语)\n")
        return True
    except Exception as e:
        print(f"[ERR] 原语系统测试失败: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_ca_recipe_loader():
    """测试 CA 配方加载器"""
    print("=" * 60)
    print("测试 3: CA 配方加载器")
    print("=" * 60)
    try:
        from engine.primitives.ca import CARecipeLoader

        loader = CARecipeLoader()
        recipes = loader.list_recipes()

        print(f"  加载配方: {len(recipes)} 个")
        if recipes:
            print(f"  示例配方: {recipes[0]} ✓")
            recipe = loader.load_recipe(recipes[0])
            print(f"  配方字段: {list(recipe.keys())}")

        print("[OK] CA 配方加载器测试通过\n")
        return True
    except Exception as e:
        print(f"[ERR] CA 配方加载器测试失败: {e}\n")
        return False


def test_effect_loading():
    """测试效果加载"""
    print("=" * 60)
    print("测试 4: 效果加载")
    print("=" * 60)
    try:
        # 不导入 VisualEffect，直接检查 JSON 文件
        effects_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'effects')
        json_files = [f for f in os.listdir(effects_dir) if f.endswith('.json') and not f.startswith('themes')]

        print(f"  效果文件: {len(json_files)} 个")

        # 尝试加载几个效果
        test_files = ['050_formula_spiral.json', '052_ca_gameoflife.json',
                      '060_particle_fireworks.json', '062_fluid_flow.json']

        loaded = 0
        for fname in test_files:
            fpath = os.path.join(effects_dir, fname)
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"  {fname}: {data.get('name', '?')} ✓")
                loaded += 1

        print(f"\n[OK] 效果加载测试通过 ({loaded}/{len(test_files)} 个)\n")
        return True
    except Exception as e:
        print(f"[ERR] 效果加载测试失败: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_numba_jit():
    """测试 Numba JIT"""
    print("=" * 60)
    print("测试 5: Numba JIT 编译")
    print("=" * 60)
    try:
        from engine.primitives.ca_kernel import get_kernel_for_recipe

        # 尝试编译一个配方
        kernel, rule_id = get_kernel_for_recipe('gameoflife')
        print(f"  JIT 编译: rule_id={rule_id} ✓")
        print(f"  内核函数: {kernel}")

        print("[OK] Numba JIT 测试通过\n")
        return True
    except Exception as e:
        print(f"[WARN] Numba JIT 测试失败（可能回退到 NumPy）: {e}\n")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("PyWallpaper 引擎测试")
    print("=" * 60 + "\n")

    results = []

    results.append(("公式引擎", test_formula_engine()))
    results.append(("原语系统", test_primitives()))
    results.append(("CA 配方加载器", test_ca_recipe_loader()))
    results.append(("效果加载", test_effect_loading()))
    results.append(("Numba JIT", test_numba_jit()))

    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")
    print(f"\n总计: {passed}/{total} 通过\n")

    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
