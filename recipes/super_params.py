"""超级公式参数默认值 & 解析函数."""

SUPER_PARAM_DEFAULTS = {
    "p1": 0.5,
    "p2": 0.5,
    "p3": 0.5,
    "p4": 0.5,
    "p5": 0.2,
    "p6": 0.8,
    "p7": 0.2,
    "p8": 0.8,
    "w1": 0.5,
    "w2": 0.5,
    "w3": 0.1,
    "w4": 0.1,
    "f1": 1.0,
    "f2": 1.0,
    "f3": 1.0,
    "f4": 3.0,
    "f5": 9.0,
    "f6": 27.0,
    "d1": 0.0,
    "d2": 0.0,
    "d3": 0.0,
    "c1": 2.0,
    "c2": 2.0,
    "c3": 2.0,
    "g1": 1.0,
    "g2": 1.0,
    "g3": 1.0,
    "a1": 0.0,
    "a2": 0.0,
    "a3": 0.0,
    "b1": 1.0,
    "b2": 1.0,
    "b3": 1.0,
}

def resolve_super_params(expr: str) -> str:
    """将超级公式参数名替换为默认数值，使表达式可以独立编译执行。"""
    import re
    for name, value in SUPER_PARAM_DEFAULTS.items():
        expr = re.sub(r"\b" + re.escape(name) + r"\b", str(value), expr)
    return expr
