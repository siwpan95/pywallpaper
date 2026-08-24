"""
批量效果生成器 — 为低数量分类扩充效果
==========================================
目标分类：
  - 细胞自动机 (2 → ~80)
  - 粒子系统 (2 → ~50)
  - 流体模拟 (3 → ~50)
  - 数学 (14 → ~100)
  - 几何 (13 → ~80)
  - 公式 (1 → ~50)
  - 信息 (1 → ~20)
  - (无分类) (6 → 归入合理分类)

策略：
  A. 细胞自动机：从 recipes/（原 draw/effects）的 140 种规则，每种生成 1 个 CA 效果
  B. 数学/几何/公式：用 formula/curve 原语 + 多样化数学表达式
  C. 粒子系统：多样化发射器配置
  D. 流体模拟：多样化 color_map + 参数组合
  E. 修复无分类效果
"""

import json
import os
import glob
import re
import sys

# ── 路径 ──
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYWALLPAPER_EFFECTS = os.path.join(_ROOT, "effects")
DRAW_EFFECTS = os.path.join(_ROOT, "recipes")

# ── 读取现有最大编号 ──
def get_next_id():
    """扫描现有 JSON 文件，返回下一个可用编号"""
    pattern = os.path.join(PYWALLPAPER_EFFECTS, "*_*.json")
    max_num = 0
    for f in glob.glob(pattern):
        m = re.match(r"(\d+)_", os.path.basename(f))
        if m:
            n = int(m.group(1))
            if n > max_num:
                max_num = n
    return max_num + 1


def load_existing_ids():
    """返回已使用的效果 ID 集合"""
    existing = set()
    pattern = os.path.join(PYWALLPAPER_EFFECTS, "*_*.json")
    for f in glob.glob(pattern):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            eid = data.get("id", "")
            if eid:
                existing.add(eid)
        except Exception:
            pass
    return existing


def get_draw_rule_names():
    """从 recipes/ 提取所有有意义的规则名称（过滤 hash）"""
    import hashlib
    files = glob.glob(os.path.join(DRAW_EFFECTS, "*.json"))
    rule_names = set()
    for f in files:
        name = os.path.basename(f).replace(".json", "")
        parts = name.split("_")
        if len(parts) >= 2:
            rule = parts[1]
            # 过滤掉纯 hash 名称（小写 hex 且长度8-10）
            if re.match(r'^[0-9a-f]{8,10}$', rule):
                continue
            if rule == "custom":
                continue  # 跳过过于通用的名称
            rule_names.add(rule)
    return sorted(rule_names)


def make_effect_id(base, existing_ids):
    """生成不重复的效果 ID"""
    if base not in existing_ids:
        return base
    i = 2
    while f"{base}_{i}" in existing_ids:
        i += 1
    return f"{base}_{i}"


def write_effect(number, config):
    """写入一个效果 JSON 文件"""
    eid = config["id"]
    fname = f"{number:03d}_{eid}.json"
    path = os.path.join(PYWALLPAPER_EFFECTS, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return path


# ============================================================
#  A. 细胞自动机效果 — 每种规则生成一个 effect
# ============================================================
def generate_ca_effects(start_num, existing_ids):
    """为每种 CA 规则生成一个 pywallpaper 效果"""
    rules = get_draw_rule_names()
    print(f"\n{'='*60}")
    print(f"  [A] 细胞自动机效果 — {len(rules)} 种规则")
    print(f"{'='*60}")

    # CA 显示名称映射（为人熟知规则使用友好中文名）
    NAME_MAP = {
        "GameOfLife": "生命游戏（Conway）",
        "HighLife": "HighLife生命游戏",
        "Seeds": "种子爆炸",
        "LifeWithoutDeath": "永生",
        "BZReaction": "Belousov-Zhabotinsky反应",
        "NavierStokes": "Navier-Stokes流体",
        "LatticeBoltzmann": "格子Boltzmann流体",
        "FitzHughNagumo": "FitzHugh-Nagumo神经元",
        "ForestFire": "森林火灾",
        "CahnHilliard": "Cahn-Hilliard相分离",
        "GiererMeinhardt": "Gierer-Meinhardt形态",
        "Meinhardt": "Meinhardt斑图",
        "TuringActivation": "Turing激活-抑制",
        "Schrodinger": "薛定谔方程",
        "WaveEquation2D": "2D波动方程",
        "HeatEquation": "热传导方程",
        "WavePacket": "波包演化",
        "WavePropagate": "波传播",
        "Kuramoto": "Kuramoto同步",
        "NetworkKuramoto": "网络Kuramoto",
        "SmallWorldSync": "小世界同步",
        "LorenzMap": "Lorenz混沌",
        "ChenMap": "Chen混沌",
        "HenonTrajectory": "Henon轨迹",
        "LogisticTrajectory": "Logistic映射轨迹",
        "DuffingTrajectory": "Duffing振子轨迹",
        "RosslerMap": "Rossler混沌",
        "CMLChaotic": "耦合映射混沌",
        "DoubleSlit": "双缝干涉",
        "Interference": "干涉图样",
        "Voronoi": "Voronoi图",
        "EdenGrowth": "Eden生长模型",
        "DiffusionLimited": "DLA扩散限制聚集",
        "StochasticGrowth": "随机生长",
        "ThresholdGrowth": "阈值生长",
        "SmoothLife": "SmoothLife平滑生命",
        "Lenia": "Lenia连续生命",
        "QuantumWalk": "量子行走",
        "PerlinLike": "Perlin噪声",
        "Fractal": "分形迭代",
        "SineField": "正弦场",
        "IsingGlauber": "Ising-Glauber模型",
        "PottsModel": "Potts模型",
        "Schnakenberg": "Schnakenberg反应",
        "Oregonator": "Oregonator反应",
        "ExcitableThreshold": "可激发阈值",
        "AnisotropicDiffusion": "各向异性扩散",
        "PureDiffusion": "纯扩散",
        "NetworkDiffusion": "网络扩散",
        "PhaseSeparation": "相分离",
        "DPProcess": "定向渗流",
        "Laplacian": "Laplacian演化",
        "Gradient2D": "2D梯度场",
        "Gaussian": "高斯场",
        "Noise": "噪声场",
        "Wave": "波动演化",
        "CoupledMap": "耦合映射",
        "XYKosterlitz": "XY-Kosterlitz模型",
        "Quasicrystal": "准晶体",
        "Defect": "拓扑缺陷",
        "Super": "超级通用CA",
        "Spiral": "螺旋波",
        "BS12345": "BZ简化版A",
        "BS678": "BZ简化版B",
        "Move116": "Move116规则",
        "Shape2D": "2D形状场",
        "Polygon": "多边形场",
        "Checker": "棋盘场",
        "2x2": "2x2规则",
        "Slit": "狭缝场",
        "QuantumWalkEvo": "量子行走演化",
    }

    # 颜色方案轮换池
    color_schemes = [
        {"type": "hsv_flow", "hue": [0, 0.8], "speed": 0.1, "sat": 0.8, "val": 0.85},
        {"type": "hsv_flow", "hue": [0.55, 0.75], "speed": 0.12, "sat": 0.7, "val": 0.85},
        {"type": "hsv_flow", "hue": [0.0, 0.3], "speed": 0.08, "sat": 0.6, "val": 0.9},
        {"type": "hsv_flow", "hue": [0.3, 0.5], "speed": 0.15, "sat": 0.7, "val": 0.8},
        {"type": "hsv_flow", "hue": [0.75, 1.0], "speed": 0.1, "sat": 0.6, "val": 0.85},
        {"type": "hsv_flow", "hue": [0.1, 0.4], "speed": 0.06, "sat": 0.8, "val": 0.75},
    ]

    bg_themes = ["无", "星空", "渐变", "极光", "无", "无"]

    generated = 0
    for i, rule in enumerate(rules):
        eid = make_effect_id(f"ca_{rule.lower()}", existing_ids)
        existing_ids.add(eid)

        display_name = NAME_MAP.get(rule, rule)
        number = start_num + i

        config = {
            "id": eid,
            "name": display_name,
            "full_name": f"{number:03d}. {display_name}",
            "category": "细胞自动机",
            "background_theme": bg_themes[i % len(bg_themes)],
            "class": "EngineEffect",
            "params": {
                "layers": [{
                    "type": "ca",
                    "recipe": rule,
                    "grid_size": [80, 45],
                    "steps_per_frame": 2,
                    "use_jit": True,
                    "color": color_schemes[i % len(color_schemes)],
                    "audio": {
                        "source": "band_energy", "target": "color_val",
                        "scale": [0.4, 1.0], "smoothing": 0.85
                    },
                    "audio_modulation": {
                        "color_hue": {"source": "rms", "scale": [0, 0.3]},
                        "steps_per_frame": {"source": "beat", "scale": [1, 5]},
                    },
                }]
            },
        }

        write_effect(number, config)
        generated += 1

    print(f"  生成 {generated} 个细胞自动机效果")
    return start_num + len(rules)


# ============================================================
#  B. 数学 / 几何 / 公式效果
# ============================================================
_HSV_FLOW_RAINBOW = {"type": "hsv_flow", "hue": [0, 1], "speed": 0.1, "sat": 0.8, "val": 0.85}
_HSV_FLOW_WARM = {"type": "hsv_flow", "hue": [0.0, 0.15], "speed": 0.12, "sat": 0.7, "val": 0.85}
_HSV_FLOW_COOL = {"type": "hsv_flow", "hue": [0.5, 0.7], "speed": 0.1, "sat": 0.7, "val": 0.85}
_HSV_FLOW_PURPLE = {"type": "hsv_flow", "hue": [0.7, 0.9], "speed": 0.1, "sat": 0.8, "val": 0.8}
_HSV_FLOW_GREEN = {"type": "hsv_flow", "hue": [0.2, 0.4], "speed": 0.08, "sat": 0.7, "val": 0.85}

def _formula_layer(x_expr, y_expr, t_min, t_max, t_step, color=None, audio=True, line_w=2):
    """创建 formula 原语层"""
    return {
        "type": "formula",
        "formula": {
            "x": x_expr, "y": y_expr,
            "t_min": t_min, "t_max": t_max, "t_step": t_step,
        },
        "color": color or _HSV_FLOW_RAINBOW,
        "line_width": line_w,
        "close_threshold": 4,
        "audio": {"source": "rms", "target": "value", "scale": [0, 1], "smoothing": 0.85} if audio else None,
    }


def _curve_layer(preset, steps=120, layers=3, scale=120, color=None, audio=True):
    """创建 curve 原语层"""
    layer = {
        "type": "curve",
        "preset": preset,
        "steps": steps,
        "layers": layers,
        "scale": scale,
        "line_width": 2,
        "color": color or _HSV_FLOW_RAINBOW,
    }
    if audio:
        layer["audio"] = {"source": "rms", "target": "value", "scale": [0, 1], "smoothing": 0.85}
    return layer


def generate_math_effects(start_num, existing_ids):
    """生成数学类效果"""
    effects = [
        # ── Lissajous 曲线系列 ──
        {
            "id": "lissajous_2_3", "name": "Lissajous曲线(2:3)",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(3*t)*0.85", "sin(2*t)*0.85", 0, "2*pi", 0.005,
                color=_HSV_FLOW_PURPLE,
            )],
        },
        {
            "id": "lissajous_3_5", "name": "Lissajous曲线(3:5)",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(5*t+pi/4)*0.85", "sin(3*t)*0.85", 0, "2*pi", 0.005,
                color=_HSV_FLOW_COOL,
            )],
        },
        {
            "id": "lissajous_5_7", "name": "Lissajous曲线(5:7)",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(7*t)*0.85", "sin(5*t+pi/6)*0.85", 0, "2*pi", 0.005,
                color=_HSV_FLOW_WARM,
            )],
        },
        {
            "id": "lissajous_8_5", "name": "Lissajous曲线(8:5)",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(5*t+pi/3)*0.8", "sin(8*t)*0.8", 0, "2*pi", 0.005,
            )],
        },
        # ── 螺线系列 ──
        {
            "id": "archimedean_spiral", "name": "阿基米德螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "t*cos(8*t)*0.75", "t*sin(8*t)*0.75", 0, "2*pi", 0.003,
                color=_HSV_FLOW_COOL,
            )],
        },
        {
            "id": "log_spiral", "name": "对数螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "exp(t/4-1)*cos(6*t)*0.6", "exp(t/4-1)*sin(6*t)*0.6", 0, "4*pi", 0.003,
                color=_HSV_FLOW_WARM,
            )],
        },
        {
            "id": "fermat_spiral", "name": "费马螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "sqrt(t)*cos(t*8)*0.7", "sqrt(t)*sin(t*8)*0.7", 0, "4*pi", 0.003,
                color=_HSV_FLOW_PURPLE,
            )],
        },
        {
            "id": "parabolic_spiral", "name": "抛物线螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "t*cos(t*12)*0.7", "t*sin(t*12)*0.7", 0, "3*pi", 0.002,
                color=_HSV_FLOW_GREEN,
            )],
        },
        {
            "id": "galactic_spiral", "name": "银河系螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "t*0.5*cos(t*6)*0.8", "t*0.5*sin(t*6)*0.8", 0, "6*pi", 0.004,
                color=_HSV_FLOW_RAINBOW,
            )],
        },
        {
            "id": "hyperbolic_spiral", "name": "双曲螺线",
            "category": "数学",
            "layers": [_formula_layer(
                "cos(8*t)/(t+0.5)*0.8", "sin(8*t)/(t+0.5)*0.8", 0, "3*pi", 0.005,
                color=_HSV_FLOW_COOL,
            )],
        },
        # ── 花瓣曲线 ──
        {
            "id": "rose_6_petal", "name": "六瓣玫瑰线",
            "category": "数学",
            "layers": [_curve_layer("rose", steps=150, layers=4, scale=140, color=_HSV_FLOW_PURPLE)],
        },
        {
            "id": "eight_curve", "name": "8字形曲线",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(t)*0.7", "sin(2*t)*0.6", 0, "2*pi", 0.003,
                color=_HSV_FLOW_COOL,
            )],
        },
        {
            "id": "epitrochoid", "name": "外旋轮线",
            "category": "数学",
            "layers": [_formula_layer(
                "cos(t)+cos(7*t)*0.3", "sin(t)+sin(7*t)*0.3", 0, "2*pi", 0.003,
                color=_HSV_FLOW_WARM,
            )],
        },
        {
            "id": "hypotrochoid", "name": "内旋轮线",
            "category": "数学",
            "layers": [_formula_layer(
                "cos(3*t)+cos(t)*0.4", "sin(3*t)-sin(t)*0.4", 0, "2*pi", 0.003,
                color=_HSV_FLOW_GREEN,
            )],
        },
        {
            "id": "butterfly_curve", "name": "蝴蝶曲线",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(t)*(exp(cos(t))-2*cos(4*t)-pow(sin(t/12),5))*0.25",
                "cos(t)*(exp(cos(t))-2*cos(4*t)-pow(sin(t/12),5))*0.25",
                0, "12*pi", 0.01,
                color=_HSV_FLOW_RAINBOW,
            )],
        },
        # ── 三角函数组合 ──
        {
            "id": "sin_wave_combo", "name": "正弦波组合",
            "category": "数学",
            "layers": [_formula_layer(
                "t-1", "sin(t*10)*0.5", -1, 1, 0.002,
                color=_HSV_FLOW_COOL,
            )],
        },
        {
            "id": "tan_curve", "name": "正切曲线",
            "category": "数学",
            "layers": [_formula_layer(
                "t*0.6", "tan(t*1.5)*0.3", "pi/6", "pi*5/6", 0.003,
                color=_HSV_FLOW_WARM,
            )],
        },
        {
            "id": "cycloid", "name": "摆线",
            "category": "数学",
            "layers": [_formula_layer(
                "t-sin(t)*0.4", "1-cos(t)*0.4", 0, "4*pi", 0.005,
                color=_HSV_FLOW_PURPLE,
            )],
        },
        {
            "id": "astroid", "name": "星形线",
            "category": "数学",
            "layers": [_formula_layer(
                "pow(cos(t),3)*0.8", "pow(sin(t),3)*0.8", 0, "2*pi", 0.005,
                color=_HSV_FLOW_GREEN,
            )],
        },
        {
            "id": "deltoid", "name": "三角线",
            "category": "数学",
            "layers": [_formula_layer(
                "2*cos(t)+cos(2*t)", "2*sin(t)-sin(2*t)", 0, "2*pi", 0.005,
                color=_HSV_FLOW_COOL,
            ), _formula_layer(
                "2*cos(t)+cos(2*t)", "2*sin(t)-sin(2*t)", 0, "2*pi", 0.005,
                color=_HSV_FLOW_WARM, line_w=1,
            )],
            "layers_transform": True,
        },
        # ── 极坐标公式 ──
        {
            "id": "cardioid_polar", "name": "心形线(极坐标)",
            "category": "公式",
            "layers": [_curve_layer("cardioid", steps=120, layers=5, scale=120, color=_HSV_FLOW_WARM)],
        },
        {
            "id": "lemniscate_bernoulli", "name": "Bernoulli双纽线",
            "category": "公式",
            "layers": [_curve_layer("lemniscate", steps=180, layers=4, scale=140, color=_HSV_FLOW_COOL)],
        },
        {
            "id": "limacon", "name": "蚶线",
            "category": "公式",
            "layers": [_formula_layer(
                "(1+2*cos(t))*cos(t)*0.4", "(1+2*cos(t))*sin(t)*0.4", 0, "2*pi", 0.005,
                color=_HSV_FLOW_GREEN,
            )],
        },
        {
            "id": "cassini_oval", "name": "Cassini卵形线",
            "category": "公式",
            "layers": [_formula_layer(
                "cos(t)*sqrt(1+0.8*sin(2*t))*0.7", "sin(t)*sqrt(1+0.8*sin(2*t))*0.7",
                0, "2*pi", 0.005,
                color=_HSV_FLOW_PURPLE,
            )],
        },
        {
            "id": "conchoid", "name": "蚌线",
            "category": "公式",
            "layers": [_formula_layer(
                "(1+1/cos(t))*cos(t)*0.4", "(1+1/cos(t))*sin(t)*0.4",
                "-pi/3", "pi/3", 0.005,
                color=_HSV_FLOW_WARM, audio=False,
            )],
        },
        # ── 参数方程组合 ──
        {
            "id": "parametric_flower", "name": "参数花",
            "category": "公式",
            "layers": [_formula_layer(
                "cos(t)*(1+0.5*cos(8*t))*0.75", "sin(t)*(1+0.5*cos(8*t))*0.75",
                0, "2*pi", 0.003, color=_HSV_FLOW_RAINBOW,
            )],
        },
        {
            "id": "parametric_star", "name": "星芒图案",
            "category": "公式",
            "layers": [_formula_layer(
                "cos(t)*(1+0.3*cos(12*t))*0.7", "sin(t)*(1+0.3*cos(12*t))*0.7",
                0, "2*pi", 0.003, color=_HSV_FLOW_COOL,
            )],
        },
        {
            "id": "mobius_path", "name": "Mobius路径投影",
            "category": "数学",
            "layers": [_formula_layer(
                "cos(t)*(1+t*0.3*cos(t))*0.5", "sin(t)*(1+t*0.3*cos(t))*0.5",
                "pi/4", "3*pi", 0.004, color=_HSV_FLOW_GREEN,
            )],
        },
        # ── 花曲线变体 ──
        {
            "id": "five_petal_flower", "name": "五瓣花",
            "category": "几何",
            "layers": [_formula_layer(
                "cos(5*t)*cos(t)*0.7", "cos(5*t)*sin(t)*0.7",
                0, "2*pi", 0.003, color=_HSV_FLOW_PURPLE,
            )],
        },
        {
            "id": "sunflower_pattern", "name": "向日葵图案",
            "category": "几何",
            "layers": [_formula_layer(
                "cos(t)*(1+0.4*cos(21*t))*0.7", "sin(t)*(1+0.4*cos(21*t))*0.7",
                0, "2*pi", 0.003, color=_HSV_FLOW_WARM,
            )],
        },
        {
            "id": "trefoil_knot_2d", "name": "三叶结(2D投影)",
            "category": "数学",
            "layers": [_formula_layer(
                "sin(t)+2*sin(2*t)", "cos(t)-2*cos(2*t)",
                0, "2*pi", 0.003, color=_HSV_FLOW_COOL,
            )],
        },
    ]

    print(f"\n{'='*60}")
    print(f"  [B] 数学/几何/公式效果 — {len(effects)} 个")
    print(f"{'='*60}")

    generated = 0
    for i, eff in enumerate(effects):
        eid = make_effect_id(eff["id"], existing_ids)
        existing_ids.add(eid)
        number = start_num + i

        config = {
            "id": eid,
            "name": eff["name"],
            "full_name": f"{number:03d}. {eff['name']}",
            "category": eff["category"],
            "background_theme": "无",
            "class": "EngineEffect",
            "params": {"layers": eff["layers"]},
        }
        write_effect(number, config)
        generated += 1

    print(f"  生成 {generated} 个数学/几何/公式效果")
    return start_num + len(effects)


# ============================================================
#  C. 粒子系统效果
# ============================================================
def generate_particle_effects(start_num, existing_ids):
    """生成多样化粒子系统效果"""
    effects = [
        # ── 基础发射器 ──
        {
            "id": "particle_fountain", "name": "粒子喷泉",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.85], "rate": 30, "lifetime": [1.5, 3.0],
                "speed": [100, 250], "direction": [240, 300],
                "color": [100, 200, 255], "size": [2, 6],
            }],
            "forces": [{"type": "gravity", "y": 150}],
            "particle_type": "circle",
        },
        {
            "id": "particle_burst_center", "name": "中心粒子爆发",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 50, "lifetime": [1.0, 2.5],
                "speed": [80, 200], "direction": [0, 360],
                "color": [255, 180, 50], "size": [1, 4],
            }],
            "forces": [],
            "particle_type": "circle",
        },
        {
            "id": "particle_snowfall", "name": "粒子飘雪",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.05], "rate": 15, "lifetime": [3.0, 6.0],
                "speed": [20, 60], "direction": [150, 210],
                "color": [220, 230, 255], "size": [2, 5],
            }],
            "forces": [{"type": "wind", "x": -30}, {"type": "gravity", "y": -10}],
            "particle_type": "circle",
        },
        {
            "id": "particle_rain", "name": "粒子雨",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.0], "rate": 40, "lifetime": [0.5, 1.2],
                "speed": [300, 500], "direction": [85, 95],
                "color": [150, 200, 255], "size": [1, 2],
            }],
            "forces": [{"type": "gravity", "y": 200}],
            "particle_type": "line",
        },
        {
            "id": "particle_sparkle", "name": "粒子闪烁",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 20, "lifetime": [0.5, 1.5],
                "speed": [50, 150], "direction": [0, 360],
                "color": [255, 220, 100], "size": [2, 8],
            }],
            "forces": [],
            "particle_type": "point",
        },
        {
            "id": "particle_vortex_ring", "name": "粒子涡旋环",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 25, "lifetime": [1.0, 2.0],
                "speed": [80, 150], "direction": [0, 360],
                "color": [255, 100, 200], "size": [1, 3],
            }],
            "forces": [{"type": "attract", "position": [0.5, 0.5], "strength": 200}],
            "particle_type": "circle",
        },
        {
            "id": "particle_double_vortex", "name": "双涡旋粒子",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [
                {
                    "position": [0.3, 0.5], "rate": 15, "lifetime": [1.0, 2.5],
                    "speed": [60, 120], "direction": [0, 360],
                    "color": [255, 80, 80], "size": [1, 4],
                },
                {
                    "position": [0.7, 0.5], "rate": 15, "lifetime": [1.0, 2.5],
                    "speed": [60, 120], "direction": [0, 360],
                    "color": [80, 80, 255], "size": [1, 4],
                },
            ],
            "forces": [
                {"type": "attract", "position": [0.3, 0.5], "strength": 300},
                {"type": "attract", "position": [0.7, 0.5], "strength": 300},
            ],
            "particle_type": "circle",
        },
        {
            "id": "particle_trail_lines", "name": "粒子轨迹线",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 10, "lifetime": [1.5, 3.0],
                "speed": [100, 200], "direction": [0, 360],
                "color": [100, 255, 150], "size": [2, 5],
            }],
            "forces": [{"type": "wind", "x": 50}, {"type": "gravity", "y": -20}],
            "particle_type": "trail",
        },
        {
            "id": "particle_rising_sparks", "name": "上升火花",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.9], "rate": 35, "lifetime": [1.0, 2.0],
                "speed": [150, 300], "direction": [230, 310],
                "color": [255, 180, 50], "size": [1, 3],
            }],
            "forces": [{"type": "gravity", "y": 80}],
            "particle_type": "circle",
        },
        {
            "id": "particle_multi_color_burst", "name": "多色粒子爆发",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [
                {
                    "position": [0.3, 0.4], "rate": 12, "lifetime": [0.8, 2.0],
                    "speed": [50, 180], "direction": [0, 360],
                    "color": [255, 60, 60], "size": [2, 6],
                },
                {
                    "position": [0.7, 0.4], "rate": 12, "lifetime": [0.8, 2.0],
                    "speed": [50, 180], "direction": [0, 360],
                    "color": [60, 255, 60], "size": [2, 6],
                },
                {
                    "position": [0.5, 0.7], "rate": 12, "lifetime": [0.8, 2.0],
                    "speed": [50, 180], "direction": [0, 360],
                    "color": [60, 60, 255], "size": [2, 6],
                },
            ],
            "forces": [],
            "particle_type": "circle",
        },
        {
            "id": "particle_galaxy_formation", "name": "银河形成",
            "category": "粒子系统",
            "bg": "星空",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 30, "lifetime": [1.5, 4.0],
                "speed": [30, 100], "direction": [0, 360],
                "color": [180, 200, 255], "size": [1, 3],
            }],
            "forces": [{"type": "attract", "position": [0.5, 0.5], "strength": 500}],
            "particle_type": "point",
        },
        {
            "id": "particle_firework", "name": "粒子烟花",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.5], "rate": 60, "lifetime": [0.5, 1.5],
                "speed": [150, 350], "direction": [0, 360],
                "color": [255, 200, 50], "size": [1, 3],
            }],
            "forces": [{"type": "gravity", "y": 100}],
            "particle_type": "circle",
        },
        {
            "id": "particle_nebula", "name": "粒子星云",
            "category": "粒子系统",
            "bg": "星空",
            "emitters": [
                {
                    "position": [0.35, 0.5], "rate": 8, "lifetime": [3.0, 6.0],
                    "speed": [10, 40], "direction": [0, 360],
                    "color": [255, 100, 200], "size": [3, 8],
                },
                {
                    "position": [0.65, 0.5], "rate": 8, "lifetime": [3.0, 6.0],
                    "speed": [10, 40], "direction": [0, 360],
                    "color": [100, 200, 255], "size": [3, 8],
                },
            ],
            "forces": [
                {"type": "attract", "position": [0.35, 0.5], "strength": 100},
                {"type": "attract", "position": [0.65, 0.5], "strength": 100},
            ],
            "particle_type": "circle",
        },
        {
            "id": "particle_whirlpool", "name": "粒子漩涡",
            "category": "粒子系统",
            "bg": "无",
            "emitters": [{
                "position": [0.5, 0.3], "rate": 20, "lifetime": [2.0, 4.0],
                "speed": [40, 80], "direction": [0, 360],
                "color": [50, 150, 255], "size": [1, 4],
            }],
            "forces": [{"type": "attract", "position": [0.5, 0.5], "strength": 300}, {"type": "gravity", "y": 50}],
            "particle_type": "circle",
        },
        {
            "id": "particle_magnetic_field", "name": "粒子磁场",
            "category": "粒子系统",
            "bg": "星空",
            "emitters": [
                {
                    "position": [0.5, 0.2], "rate": 20, "lifetime": [1.5, 3.0],
                    "speed": [40, 100], "direction": [340, 20],
                    "color": [255, 50, 50], "size": [1, 3],
                },
            ],
            "forces": [
                {"type": "attract", "position": [0.5, 0.8], "strength": 400},
            ],
            "particle_type": "line",
        },
    ]

    print(f"\n{'='*60}")
    print(f"  [C] 粒子系统效果 — {len(effects)} 个")
    print(f"{'='*60}")

    generated = 0
    for i, eff in enumerate(effects):
        eid = make_effect_id(eff["id"], existing_ids)
        existing_ids.add(eid)
        number = start_num + i

        layers_config = {
            "type": "particle",
            "emitters": eff["emitters"],
            "forces": eff.get("forces", []),
            "particle_type": eff.get("particle_type", "circle"),
            "max_particles": 800,
        }
        # 添加音频调制
        layers_config["audio_modulation"] = {
            "rate": {"source": "rms", "scale": [0.5, 2.0]},
            "color_hue": {"source": "band_energy", "scale": [0, 0.3]},
        }

        config = {
            "id": eid,
            "name": eff["name"],
            "full_name": f"{number:03d}. {eff['name']}",
            "category": eff["category"],
            "background_theme": eff.get("bg", "无"),
            "class": "EngineEffect",
            "params": {"layers": [layers_config]},
        }
        write_effect(number, config)
        generated += 1

    print(f"  生成 {generated} 个粒子系统效果")
    return start_num + len(effects)


# ============================================================
#  D. 流体模拟效果
# ============================================================
def generate_fluid_effects(start_num, existing_ids):
    """生成多样化流体模拟效果"""
    effects = [
        # ── 基础颜色映射 ──
        {"id": "fluid_fire_slow", "name": "烈焰慢流", "color_map": "fire",
         "viscosity": 0.000005, "diffusion": 0.00005, "force": 4.0, "bg": "无"},
        {"id": "fluid_fire_fast", "name": "烈焰急流", "color_map": "fire",
         "viscosity": 0.0000005, "diffusion": 0.0002, "force": 8.0, "bg": "无"},
        {"id": "fluid_ocean_calm", "name": "宁静海洋", "color_map": "ocean",
         "viscosity": 0.000002, "diffusion": 0.0001, "force": 3.0, "bg": "无"},
        {"id": "fluid_ocean_storm", "name": "风暴海洋", "color_map": "ocean",
         "viscosity": 0.0000005, "diffusion": 0.0003, "force": 10.0, "bg": "渐变"},
        {"id": "fluid_rainbow_flow", "name": "彩虹流", "color_map": "rainbow",
         "viscosity": 0.000003, "diffusion": 0.00008, "force": 5.0, "bg": "无"},
        {"id": "fluid_rainbow_turbulent", "name": "彩虹湍流", "color_map": "rainbow",
         "viscosity": 0.0000003, "diffusion": 0.0004, "force": 12.0, "bg": "无"},
        # ── 变异参数 ──
        {"id": "fluid_smoke_gentle", "name": "轻烟", "color_map": None,  # grayscale
         "viscosity": 0.00001, "diffusion": 0.00002, "force": 2.0, "bg": "无"},
        {"id": "fluid_lava", "name": "熔岩", "color_map": "fire",
         "viscosity": 0.00005, "diffusion": 0.00001, "force": 3.0, "bg": "无"},
        {"id": "fluid_plasma", "name": "等离子流体", "color_map": "rainbow",
         "viscosity": 0.000001, "diffusion": 0.0001, "force": 7.0, "bg": "星空"},
        {"id": "fluid_deep_ocean", "name": "深海", "color_map": "ocean",
         "viscosity": 0.0001, "diffusion": 0.00005, "force": 2.0, "bg": "无"},
        {"id": "fluid_ethereal", "name": "以太流", "color_map": "rainbow",
         "viscosity": 0.0000001, "diffusion": 0.0005, "force": 6.0, "bg": "极光"},
        {"id": "fluid_magma_flow", "name": "岩浆流", "color_map": "fire",
         "viscosity": 0.00002, "diffusion": 0.00003, "force": 5.0, "bg": "无"},
        {"id": "fluid_crystal_water", "name": "水晶水", "color_map": "ocean",
         "viscosity": 0.000008, "diffusion": 0.00006, "force": 4.0, "bg": "无"},
        {"id": "fluid_aurora_fluid", "name": "极光流体", "color_map": "rainbow",
         "viscosity": 0.0000005, "diffusion": 0.0002, "force": 9.0, "bg": "极光"},
        {"id": "fluid_ink_drop", "name": "墨滴扩散", "color_map": None,
         "viscosity": 0.00005, "diffusion": 0.00003, "force": 1.5, "bg": "无"},
        # ── 不同网格尺寸 ──
        {"id": "fluid_hires_ocean", "name": "高分辨率海洋", "color_map": "ocean",
         "viscosity": 0.000002, "diffusion": 0.00008, "force": 5.0, "bg": "无",
         "grid_size": [128, 128]},
        {"id": "fluid_lores_fire", "name": "低分辨率火焰", "color_map": "fire",
         "viscosity": 0.000008, "diffusion": 0.00006, "force": 6.0, "bg": "无",
         "grid_size": [32, 32]},
        {"id": "fluid_wide_screen", "name": "宽屏流体", "color_map": "rainbow",
         "viscosity": 0.000003, "diffusion": 0.0001, "force": 5.0, "bg": "无",
         "grid_size": [128, 72]},
        # ── 后处理变体 ──
        {"id": "fluid_blooming_fire", "name": "泛光火焰", "color_map": "fire",
         "viscosity": 0.000003, "diffusion": 0.0001, "force": 6.0, "bg": "无",
         "postprocess": ["bloom"]},
        {"id": "fluid_vignette_rainbow", "name": "暗角彩虹流", "color_map": "rainbow",
         "viscosity": 0.000002, "diffusion": 0.00012, "force": 5.0, "bg": "无",
         "postprocess": ["vignette"]},
        {"id": "fluid_dreamscape", "name": "梦境流体", "color_map": "rainbow",
         "viscosity": 0.000001, "diffusion": 0.00015, "force": 4.0, "bg": "渐变",
         "postprocess": ["bloom", "vignette"]},
    ]

    print(f"\n{'='*60}")
    print(f"  [D] 流体模拟效果 — {len(effects)} 个")
    print(f"{'='*60}")

    generated = 0
    for i, eff in enumerate(effects):
        eid = make_effect_id(eff["id"], existing_ids)
        existing_ids.add(eid)
        number = start_num + i

        half_force = eff["force"] * 0.5
        layers_config = {
            "type": "fluid",
            "grid_size": eff.get("grid_size", [64, 64]),
            "viscosity": eff["viscosity"],
            "diffusion": eff["diffusion"],
            "force": eff["force"],
            "color_map": eff["color_map"] or "grayscale",
            "audio_modulation": {
                "source": {"source": "rms", "scale": [0, 2.0]},
            },
        }
        if "postprocess" in eff:
            layers_config["postprocess"] = eff["postprocess"]

        config = {
            "id": eid,
            "name": eff["name"],
            "full_name": f"{number:03d}. {eff['name']}",
            "category": "流体模拟",
            "background_theme": eff.get("bg", "无"),
            "class": "EngineEffect",
            "params": {"layers": [layers_config]},
        }
        write_effect(number, config)
        generated += 1

    print(f"  生成 {generated} 个流体模拟效果")
    return start_num + len(effects)


# ============================================================
#  E. 信息类效果
# ============================================================
def generate_info_effects(start_num, existing_ids):
    """生成信息可视化类效果"""
    effects = [
        {"id": "binary_rain_info", "name": "二进制雨", "category": "信息", "bg": "无",
         "type": "text_rain", "config": {
             "type": "text_rain", "chars": "01", "font_size": 16, "columns": 80,
             "color": {"type": "hsv_flow", "hue": [0.2, 0.4], "speed": 0.05, "sat": 0.8, "val": 0.7},
             "audio": {"source": "band_energy", "target": "speed", "scale": [0.5, 2.0], "smoothing": 0.85},
         }},
        {"id": "hex_stream", "name": "十六进制流", "category": "信息", "bg": "无",
         "type": "text_rain", "config": {
             "type": "text_rain", "chars": "0123456789ABCDEF", "font_size": 14, "columns": 100,
             "color": {"type": "hsv_flow", "hue": [0.0, 0.15], "speed": 0.07, "sat": 0.7, "val": 0.8},
             "audio": {"source": "band_energy", "target": "speed", "scale": [0.3, 2.0], "smoothing": 0.85},
         }},
        {"id": "matrix_code", "name": "矩阵代码", "category": "信息", "bg": "无",
         "type": "text_rain", "config": {
             "type": "text_rain", "chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
             "font_size": 14, "columns": 90,
             "color": {"type": "hsv_flow", "hue": [0.25, 0.4], "speed": 0.06, "sat": 0.9, "val": 0.75},
             "audio": {"source": "rms", "target": "speed", "scale": [0.3, 2.5], "smoothing": 0.85},
         }},
        {"id": "kanji_rain", "name": "汉字雨", "category": "信息", "bg": "无",
         "type": "text_rain", "config": {
             "type": "text_rain",
             "chars": "天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏",
             "font_size": 20, "columns": 50,
             "color": {"type": "hsv_flow", "hue": [0.05, 0.15], "speed": 0.04, "sat": 0.6, "val": 0.85},
             "audio": {"source": "beat", "target": "speed", "scale": [0.5, 2.0], "smoothing": 0.85},
         }},
        {"id": "qr_pattern", "name": "QR图案", "category": "信息", "bg": "无",
         "type": "grid", "config": {
             "type": "grid", "cols": 25, "rows": 25, "cell_size": 20,
             "color": {"type": "hsv_flow", "hue": [0, 0.1], "speed": 0.03, "sat": 0.5, "val": 0.85},
             "audio": {"source": "band_energy", "target": "value", "scale": [0, 1], "smoothing": 0.85},
         }},
        {"id": "barcode_visual", "name": "条形码可视化", "category": "信息", "bg": "无",
         "type": "bars", "config": {
             "type": "bars", "count": 64, "direction": "up",
             "color": {"type": "hsv_flow", "hue": [0.0, 0.1], "speed": 0.05, "sat": 0.5, "val": 0.85},
             "position": {"x": 0, "y": "50%"}, "size": {"width": "100%", "height": "50%"},
             "audio": {"source": "band_energy", "target": "height", "scale": [0, 0.5], "smoothing": 0.85},
         }},
        {"id": "morse_code", "name": "莫尔斯码", "category": "信息", "bg": "无",
         "type": "pulse", "config": {
             "type": "pulse", "count": 6, "radius": 60,
             "color": {"type": "hsv_flow", "hue": [0.0, 0.2], "speed": 0.1, "sat": 0.6, "val": 0.9},
             "audio": {"source": "beat", "target": "value", "scale": [0, 1], "smoothing": 0.85},
         }},
        {"id": "data_stream_viz", "name": "数据流", "category": "信息", "bg": "无",
         "type": "waveform", "config": {
             "type": "waveform", "lines": 8, "points": 120,
             "color": {"type": "hsv_flow", "hue": [0.5, 0.7], "speed": 0.08, "sat": 0.7, "val": 0.85},
             "audio": {"source": "freq_data", "target": "value", "smoothing": 0.85},
         }},
        {"id": "network_packets", "name": "网络数据包", "category": "信息", "bg": "无",
         "type": "spikes", "config": {
             "type": "spikes", "count": 48,
             "color": {"type": "hsv_flow", "hue": [0.5, 0.7], "speed": 0.1, "sat": 0.7, "val": 0.85},
             "audio": {"source": "band_energy", "target": "radius", "scale": [0, 300], "smoothing": 0.85},
         }},
        {"id": "signal_waves", "name": "信号波", "category": "信息", "bg": "无",
         "type": "waveform", "config": {
             "type": "waveform", "lines": 4, "points": 200,
             "color": {"type": "hsv_flow", "hue": [0.0, 0.6], "speed": 0.1, "sat": 0.8, "val": 0.8},
             "audio": {"source": "freq_data", "target": "value", "smoothing": 0.85},
         }},
    ]

    print(f"\n{'='*60}")
    print(f"  [E] 信息类效果 — {len(effects)} 个")
    print(f"{'='*60}")

    generated = 0
    for i, eff in enumerate(effects):
        eid = make_effect_id(eff["id"], existing_ids)
        existing_ids.add(eid)
        number = start_num + i

        config = {
            "id": eid,
            "name": eff["name"],
            "full_name": f"{number:03d}. {eff['name']}",
            "category": eff["category"],
            "background_theme": eff.get("bg", "无"),
            "class": "EngineEffect",
            "params": {"layers": [eff["config"]]},
        }
        write_effect(number, config)
        generated += 1

    print(f"  生成 {generated} 个信息类效果")
    return start_num + len(effects)


# ============================================================
#  F. 修复无分类效果
# ============================================================
def fix_uncategorized_effects(start_num, existing_ids):
    """为无分类的效果添加分类标签"""
    pattern = os.path.join(PYWALLPAPER_EFFECTS, "*_*.json")

    # 猜分类的启发式规则
    def guess_category(config):
        """根据效果配置猜测合理分类"""
        name = config.get("name", "")
        eid = config.get("id", "")
        layers = config.get("params", {}).get("layers", [])
        if not layers:
            return None
        prim_type = layers[0].get("type", "")

        type_map = {
            "bars": "频谱", "spikes": "频谱", "waveform": "波浪",
            "vortex": "圆形", "circle_map": "圆形",
            "particles": "粒子", "particle": "粒子系统",
            "ca": "细胞自动机", "fluid": "流体模拟",
            "texture": "纹理", "grid": "几何", "drawing": "几何",
            "curve": "曲线", "formula": "公式",
            "text_rain": "信息", "wireframe_3d": "3D",
            "pulse": "频谱", "gauge": "仪表",
        }
        return type_map.get(prim_type)

    files = sorted(glob.glob(pattern),
                   key=lambda f: int(re.match(r"(\d+)_", os.path.basename(f)).group(1)))

    fixed = 0
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            config = json.load(fp)

        category = config.get("category", "").strip()
        if category and category != "(无分类)":
            continue  # 已有分类，跳过

        # 猜测分类
        guessed = guess_category(config)
        if not guessed:
            guessed = "组合"

        config["category"] = guessed
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(config, fp, indent=2, ensure_ascii=False)
        print(f"  [FIX] {os.path.basename(f)}: (无分类) → {guessed}")
        fixed += 1

    print(f"\n  修复了 {fixed} 个无分类效果")
    return start_num  # 没有新增编号


# ============================================================
#  MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  批量效果生成器")
    print("  目标：扩充低数量分类效果")
    print("=" * 60)

    # 获取起始编号
    start_num = get_next_id()
    print(f"\n  当前最大编号: {start_num - 1}")
    print(f"  下一个编号:   {start_num}")

    # 加载已有 ID
    existing_ids = load_existing_ids()
    print(f"  已有效果 ID:  {len(existing_ids)}")

    current = start_num

    # A. 细胞自动机 (从 draw 配方库)
    current = generate_ca_effects(current, existing_ids)

    # B. 数学/几何/公式
    current = generate_math_effects(current, existing_ids)

    # C. 粒子系统
    current = generate_particle_effects(current, existing_ids)

    # D. 流体模拟
    current = generate_fluid_effects(current, existing_ids)

    # E. 信息类
    current = generate_info_effects(current, existing_ids)

    # F. 修复无分类
    current = fix_uncategorized_effects(current, existing_ids)

    # ── 统计 ──
    total_new = current - start_num
    print(f"\n{'=' * 60}")
    print(f"  总计新增效果: {total_new}")
    print(f"  编号范围:     {start_num} ~ {current - 1}")
    print(f"{'=' * 60}")

    # ── 最终分类统计 ──
    print(f"\n  运行 auto_registry.py 验证中...")
    sys.path.insert(0, _ROOT)
    os.chdir(_ROOT)
    import subprocess
    result = subprocess.run(
        [sys.executable, "tools/auto_registry.py"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


if __name__ == "__main__":
    main()
