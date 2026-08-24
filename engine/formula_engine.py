"""
统一公式引擎 — 结合 draw 的 asteval 公式系统和 pywallpaper 的曲线公式能力

支持：
1. 安全求值数学表达式（基于 asteval）
2. NumPy 向量化计算
3. 音频数据驱动公式参数
4. 内置公式模板库（draw 的 CA 公式 + pywallpaper 的曲线公式）
"""
import re
import builtins
import numpy as np

# asteval 为可选依赖（见 requirements.txt）：缺失时回退到 NumPy 命名空间下的 eval
try:
    from asteval import Interpreter
except ImportError:
    Interpreter = None


class _FallbackEval:
    """无 asteval 时的回退求值器：在受限的 NumPy 命名空间内 exec 公式函数"""
    def __init__(self):
        ns = {k: getattr(np, k) for k in dir(np) if not k.startswith('_')}
        ns['np'] = np
        ns['pi'] = np.pi
        ns['e'] = np.e
        ns['random'] = np.random.random
        ns['__builtins__'] = builtins
        self.ns = ns
        self.symtable = {}

    def eval(self, code):
        exec(code, self.ns, self.symtable)


def _tokenize(text: str) -> list:
    """把公式字符串拆成 token 流 [(kind, value), ...]"""
    toks = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] in ' \t\r\n':
            i += 1
            continue
        m = re.match(r'\d+\.\d*|\.\d+|\d+', text[i:])
        if m:
            toks.append(('num', m.group(0)))
            i += len(m.group(0))
            continue
        m = re.match(r'[A-Za-z_]\w*', text[i:])
        if m:
            toks.append(('name', m.group(0)))
            i += len(m.group(0))
            continue
        m = re.match(r'<=|>=|==|!=|\*\*|[+\-*/%<>()=\[\],]', text[i:])
        if m:
            toks.append(('op', m.group(0)))
            i += len(m.group(0))
            continue
        raise ValueError(f'公式包含无法识别的字符: {text[i:i+12]!r}')
    return toks


class _FormulaParser:
    """把 draw 模板风格的 Python 公式翻译成向量化 NumPy 表达式

    支持: 算术 (+ - * / % **)、比较链 (a<b<c → (a<b)&(b<c))、and/or/not、
          'A if C else B' 三元（可嵌套 → where(C, A, B)）、函数调用。
    """

    _NUMPY_FUNCS = {'sin', 'cos', 'tan', 'exp', 'log', 'log10', 'sqrt', 'abs',
                    'floor', 'ceil', 'minimum', 'maximum', 'clip', 'where',
                    'arctan2', 'sign', 'power', 'mod', 'amin', 'amax', 'sum',
                    'mean', 'round', 'arctan', 'arcsin', 'arccos', 'tanh',
                    'cosh', 'sinh', 'log2'}
    _FUNC_MAP = {'min': 'minimum', 'max': 'maximum', 'random': 'random.random',
                 'int': 'trunc', 'float': 'float64', 'atan2': 'arctan2'}
    _NAME_MAP = {'pi': 'np.pi', 'e': 'np.e'}

    def __init__(self, text: str):
        self.toks = _tokenize(text)
        self.pos = 0

    def parse(self) -> str:
        result = self.ternary()
        if self.pos != len(self.toks):
            raise ValueError(f'公式解析残留 token: {self.toks[self.pos:]}')
        return result

    def _peek(self, kind=None, val=None):
        if self.pos >= len(self.toks):
            return None
        k, v = self.toks[self.pos]
        if kind is not None and k != kind:
            return None
        if val is not None and v != val:
            return None
        return self.toks[self.pos]

    def _advance(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind, val=None):
        if self._peek(kind, val) is None:
            raise ValueError(f'公式语法错误: 期望 {val or kind}，实际 {self.toks[self.pos:self.pos+1]}')
        return self._advance()

    def ternary(self):
        a = self.or_expr()
        if self._peek('name', 'if'):
            self._advance()
            cond = self.or_expr()
            self._expect('name', 'else')
            b = self.ternary()
            return f'where({cond}, {a}, {b})'
        return a

    def or_expr(self):
        parts = [self.and_expr()]
        while self._peek('name', 'or'):
            self._advance()
            parts.append(self.and_expr())
        if len(parts) == 1:
            return parts[0]
        return ' | '.join(f'({p})' for p in parts)

    def and_expr(self):
        parts = [self.not_expr()]
        while self._peek('name', 'and'):
            self._advance()
            parts.append(self.not_expr())
        if len(parts) == 1:
            return parts[0]
        return ' & '.join(f'({p})' for p in parts)

    def not_expr(self):
        if self._peek('name', 'not'):
            self._advance()
            return f'(~({self.not_expr()}))'
        return self.comparison()

    def comparison(self):
        node = self.additive()
        # x in [a, b, ...] → (x==a) | (x==b) | ...
        if self._peek('name', 'in'):
            self._advance()
            rhs = self.additive()
            if rhs.startswith('[') and rhs.endswith(']'):
                items = rhs[1:-1].split(', ')
                return '(' + ' | '.join(f'({node} == {i.strip()})' for i in items) + ')'
            return f'({node} == {rhs})'
        operands = [node]
        ops = []
        while self._peek('op') and self._peek('op')[1] in ('<=', '>=', '<', '>', '==', '!='):
            ops.append(self._advance()[1])
            operands.append(self.additive())
        if not ops:
            return node
        if len(ops) == 1:
            return f'({operands[0]} {ops[0]} {operands[1]})'
        terms = [f'({operands[i]} {op} {operands[i+1]})' for i, op in enumerate(ops)]
        return '(' + ' & '.join(terms) + ')'

    def additive(self):
        node = self.multiplicative()
        while self._peek('op') and self._peek('op')[1] in ('+', '-'):
            op = self._advance()[1]
            node = f'({node} {op} {self.multiplicative()})'
        return node

    def multiplicative(self):
        node = self.power()
        while self._peek('op') and self._peek('op')[1] in ('*', '/', '%'):
            op = self._advance()[1]
            node = f'({node} {op} {self.power()})'
        return node

    def power(self):
        node = self.unary()
        if self._peek('op') and self._peek('op')[1] == '**':
            self._advance()
            node = f'({node} ** {self.power()})'
        return node

    def unary(self):
        if self._peek('op') and self._peek('op')[1] == '-':
            self._advance()
            return f'(-{self.unary()})'
        if self._peek('op') and self._peek('op')[1] == '+':
            self._advance()
            return self.unary()
        return self.primary()

    def primary(self):
        tok = self._advance()
        kind, val = tok
        if kind == 'num':
            return val
        if kind == 'name':
            if self._peek('op') and self._peek('op')[1] == '(':
                self._advance()
                args = []
                if not (self._peek('op') and self._peek('op')[1] == ')'):
                    args.append(self._call_arg())
                    while self._peek('op') and self._peek('op')[1] == ',':
                        self._advance()
                        args.append(self._call_arg())
                self._expect('op', ')')
                return self._call(val, args)
            return self._NAME_MAP.get(val, val)
        if val == '(':
            inner = self.ternary()
            self._expect('op', ')')
            return f'({inner})'
        if val == '[':
            items = []
            if not (self._peek('op') and self._peek('op')[1] == ']'):
                items.append(self.ternary())
                while self._peek('op') and self._peek('op')[1] == ',':
                    self._advance()
                    items.append(self.ternary())
            self._expect('op', ']')
            return '[' + ', '.join(items) + ']'
        raise ValueError(f'公式无法解析 token: {tok!r}')

    def _call_arg(self):
        """函数实参：支持位置参数与 name=value 关键字参数"""
        if (self._peek('name') and self.pos + 1 < len(self.toks)
                and self.toks[self.pos + 1][0] == 'op'
                and self.toks[self.pos + 1][1] == '='):
            name = self._advance()[1]
            self._expect('op', '=')
            value = self.ternary()
            return f'{name}={value}'
        return self.ternary()

    def _call(self, name, args):
        # complex(a, b) → (a + 1j*b)：NumPy 无复数构造函数
        if name == 'complex':
            if len(args) == 2:
                return f'({args[0]} + 1j*{args[1]})'
            return f'({args[0]} + 0j)' if args else '0j'
        if name in self._FUNC_MAP:
            return f'np.{self._FUNC_MAP[name]}({", ".join(args)})'
        if name in self._NUMPY_FUNCS:
            return f'np.{name}({", ".join(args)})'
        return f'{name}({", ".join(args)})'


class FormulaEngine:
    """公式引擎 — 支持 draw 的 CA 公式和 pywallpaper 的曲线公式
    
    使用示例:
        engine = FormulaEngine()
        
        # 编译公式
        func = engine.compile("sin(t) * cos(t)", ['t'])
        
        # 执行公式
        t_vals = np.linspace(0, 2*np.pi, 100)
        result = func(t=t_vals)
        
        # 使用内置模板
        engine.add_template('my_curve', {
            'x': 't * cos(t)',
            'y': 't * sin(t)'
        })
        x_func = engine.compile_template('my_curve', 'x')
        y_func = engine.compile_template('my_curve', 'y')
    """
    
    # 内置公式模板库（合并 draw 的模板和 pywallpaper 的曲线公式）
    TEMPLATES = {
        # ================================================================
        # draw 的初始化模板（精选）
        # ================================================================
        'PureRandom': {
            'type': 'init',
            'expression': 'random()',
            'variables': ['x', 'y', 'i', 'j', 'random']
        },
        'CenterDot': {
            'type': 'init',
            'expression': '1 if (x-0.5)**2 + (y-0.5)**2 < 0.01 else 0',
            'variables': ['x', 'y']
        },
        'CenterCross': {
            'type': 'init',
            'expression': '1 if (abs(x-0.5) < 0.05) or (abs(y-0.5) < 0.05) else 0',
            'variables': ['x', 'y']
        },
        'FilledCircle': {
            'type': 'init',
            'expression': '1 if (x-0.5)**2 + (y-0.5)**2 < 0.25 else 0',
            'variables': ['x', 'y']
        },
        'StripesX': {
            'type': 'init',
            'expression': '1 if int(x * 8) % 2 == 0 else 0',
            'variables': ['x']
        },
        'StripesY': {
            'type': 'init',
            'expression': '1 if int(y * 8) % 2 == 0 else 0',
            'variables': ['y']
        },
        'NoiseSmooth': {
            'type': 'init',
            'expression': 'random() * 0.5 + 0.25',
            'variables': ['random']
        },
        'Mandelbrot': {
            'type': 'init',
            'expression': '1 if (x-0.5)*3-2 + (y-0.5)*3j-2 < 2 else 0',
            'variables': ['x', 'y']
        },
        'Spiral': {
            'type': 'init',
            'expression': '1 if (x-0.5)*cos(10*(x-0.5)) + (y-0.5)*sin(10*(y-0.5)) > 0 else 0',
            'variables': ['x', 'y']
        },
        
        # ================================================================
        # draw 的演化规则模板（精选）
        # ================================================================
        'GameOfLife': {
            'type': 'rule',
            'expression': '1 if (c==1 and 2<=sum_n<=3) or (c==0 and sum_n==3) else 0',
            'variables': ['c', 'sum_n']
        },
        'HighLife': {
            'type': 'rule',
            'expression': '1 if (c==1 and 2<=sum_n<=3) or (sum_n==3 or sum_n==6) else 0',
            'variables': ['c', 'sum_n']
        },
        'Seeds': {
            'type': 'rule',
            'expression': '1 if sum_n==2 else 0',
            'variables': ['c', 'sum_n']
        },
        'LifeWithoutDeath': {
            'type': 'rule',
            'expression': '1 if c==1 or sum_n==3 else 0',
            'variables': ['c', 'sum_n']
        },
        'PureDiffusion': {
            'type': 'rule',
            'expression': 'c + 0.1*(sum_n/len_nb - c)',
            'variables': ['c', 'sum_n', 'len_nb']
        },
        'AnisotropicDiffusion': {
            'type': 'rule',
            'expression': 'c + 0.1*(sum_n/len_nb - c) * (1 + 5*abs(c - avg_n))',
            'variables': ['c', 'sum_n', 'avg_n', 'len_nb']
        },
        'GrayScott_Diffusion': {
            'type': 'rule',
            'expression': 'c + 0.01*(sum_n/len_nb - 2*c + avg_n) - c*(1-c)*0.1',
            'variables': ['c', 'sum_n', 'avg_n', 'len_nb']
        },
        
        # ================================================================
        # draw 的颜色映射模板（精选）
        # ================================================================
        'Color_Grayscale': {
            'type': 'color',
            'expression': 'v',
            'variables': ['v']
        },
        'Color_Fire': {
            'type': 'color',
            'expression': 'minimum(v*3, 1.0)',
            'variables': ['v']
        },
        'Color_Ocean': {
            'type': 'color',
            'expression': 'v*0.8 + 0.2*sin(v*15)',
            'variables': ['v']
        },
        'Color_Rainbow': {
            'type': 'color',
            'expression': '0.5+0.5*sin(v*12)',
            'variables': ['v']
        },
        'Color_Neon': {
            'type': 'color',
            'expression': 'v*0.5 + 0.5*sin(v*25)',
            'variables': ['v']
        },
        
        # ================================================================
        # pywallpaper 的曲线公式
        # ================================================================
        'cardioid': {
            'type': 'curve',
            'x': '16*sin(t)**3 / 16.0',
            'y': '-(13*cos(t)-5*cos(2*t)-2*cos(3*t)-cos(4*t)) / 16.0',
            't_min': 0,
            't_max': '2*pi',
            't_step': 0.1
        },
        'rose': {
            'type': 'curve',
            'r': 'cos(k*t)',
            'x': 'r*cos(t)',
            'y': 'r*sin(t)',
            't_min': 0,
            't_max': '2*pi',
            't_step': 0.05
        },
        'lemniscate': {
            'type': 'curve',
            'x': 'cos(t) / (1 + sin(t)**2)',
            'y': 'sin(t)*cos(t) / (1 + sin(t)**2)',
            't_min': '-pi',
            't_max': 'pi',
            't_step': 0.05
        },
        'spiral': {
            'type': 'curve',
            'x': 't*cos(t) / (2*pi)',
            'y': 't*sin(t) / (2*pi)',
            't_min': 0,
            't_max': '4*pi',
            't_step': 0.1
        },
        'lissajous': {
            'type': 'curve',
            'x': 'sin(a*t + delta)',
            'y': 'sin(b*t)',
            't_min': 0,
            't_max': '2*pi',
            't_step': 0.05
        },
    }
    
    def __init__(self):
        self._aeval = Interpreter() if Interpreter is not None else _FallbackEval()
        if Interpreter is not None:
            # 翻译后的表达式依赖 np.*，注入 numpy 模块符号
            self._aeval.symtable['np'] = np
        self._cache = {}
        
    def compile(self, formula_str: str, variables: list) -> callable:
        """编译公式为可调用函数
        
        参数:
            formula_str: 公式字符串（支持 Python 语法）
            variables: 变量名列表（如 ['x', 'y', 't']）
        
        返回:
            可调用函数 func(**kwargs) -> np.ndarray
        """
        cache_key = (formula_str, tuple(variables))
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 将 Python 语法转换为 NumPy 兼容
        processed = self._translate(formula_str)
        
        # 创建向量化函数
        func_code = f"def _func({','.join(variables)}): return {processed}"
        self._aeval.eval(func_code)
        
        func = self._aeval.symtable['_func']
        
        # 包装：仅传递配方声明的变量，忽略调用方多余的关键字参数
        def _callable(**kwargs):
            filtered = {k: v for k, v in kwargs.items() if k in variables}
            return func(**filtered)
        
        self._cache[cache_key] = _callable
        return _callable
    
    def compile_template(self, template_name: str, var_name: str = None) -> callable:
        """编译内置模板
        
        参数:
            template_name: 模板名称
            var_name: 变量名（对于 curve 类型模板，指定 'x' 或 'y'）
        
        返回:
            可调用函数
        """
        if template_name not in self.TEMPLATES:
            raise ValueError(f"模板 '{template_name}' 不存在")
        
        template = self.TEMPLATES[template_name]
        
        if template['type'] == 'curve':
            if var_name is None:
                raise ValueError("curve 类型模板需要指定 var_name ('x' 或 'y')")
            expr = template[var_name]
            variables = self._extract_variables(expr)
            return self.compile(expr, variables)
        else:
            expr = template['expression']
            variables = template['variables']
            return self.compile(expr, variables)
    
    def evaluate(self, func: callable, **kwargs) -> np.ndarray:
        """执行公式函数
        
        参数:
            func: 编译后的公式函数
            **kwargs: 变量值（可以是标量或 NumPy 数组）
        
        返回:
            NumPy 数组或标量
        """
        try:
            result = func(**kwargs)
            return np.asarray(result, dtype=np.float64)
        except Exception as e:
            print(f"[FormulaEngine] 公式执行错误: {e}")
            return np.float64(0.0)
    
    def evaluate_template(self, template_name: str, var_name: str = None, **kwargs) -> np.ndarray:
        """执行内置模板
        
        参数:
            template_name: 模板名称
            var_name: 变量名（对于 curve 类型模板）
            **kwargs: 变量值
        
        返回:
            NumPy 数组或标量
        """
        func = self.compile_template(template_name, var_name)
        return self.evaluate(func, **kwargs)
    
    def add_template(self, name: str, template: dict):
        """添加自定义模板
        
        参数:
            name: 模板名称
            template: 模板配置（dict）
                - 对于 init/rule/color 类型: {'type': 'init', 'expression': '...', 'variables': [...]}
                - 对于 curve 类型: {'type': 'curve', 'x': '...', 'y': '...', 't_min': 0, 't_max': '2*pi', 't_step': 0.1}
        """
        self.TEMPLATES[name] = template
    
    def _translate(self, expr: str) -> str:
        """将 Python 公式翻译为向量化 NumPy 表达式（递归下降解析）

        转换规则:
            - 'A if C else B' → where(C, A, B)
            - 比较链 a<b<c → (a<b) & (b<c)
            - and/or/not → &/|/~
            - min/max → np.minimum / np.maximum
        """
        return _FormulaParser(expr).parse()
    
    def _extract_variables(self, expr: str) -> list:
        """从公式表达式中提取变量名
        
        注意: 这是一个简化版本，实际应该使用 AST 解析
        这里只提取常见的变量名
        """
        # 常见的数学函数和常量
        math_keywords = {'sin', 'cos', 'tan', 'exp', 'log', 'sqrt', 'abs', 'pi', 'e',
                        'minimum', 'maximum', 'where', 'clip', 'random'}
        
        # 提取所有可能的变量名（由字母、数字、下划线组成）
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr)
        
        # 过滤掉数学关键字
        variables = [t for t in tokens if t not in math_keywords]
        
        # 去重
        seen = set()
        result = []
        for v in variables:
            if v not in seen:
                seen.add(v)
                result.append(v)
        
        return result
    
    def create_audio_modulated_formula(self, base_expr: str, audio_mapping: dict) -> callable:
        """创建音频调制的公式函数
        
        参数:
            base_expr: 基础公式表达式
            audio_mapping: 音频映射配置
                {
                    'variables': {
                        't': 'band_energy(0) * 2',  # 用低频控制 t
                        'scale': 'rms * 0.5 + 0.5'   # 用 RMS 控制缩放
                    }
                }
        
        返回:
            可调用函数 func(audio, **kwargs)
        """
        # 编译基础公式
        base_vars = self._extract_variables(base_expr)
        base_func = self.compile(base_expr, base_vars)
        
        # 编译音频调制公式
        modulated_funcs = {}
        for var_name, audio_expr in audio_mapping.get('variables', {}).items():
            audio_vars = self._extract_variables(audio_expr)
            modulated_funcs[var_name] = (self.compile(audio_expr, audio_vars), audio_vars)
        
        def modulated_func(audio=None, **kwargs):
            """音频调制的公式函数"""
            # 计算音频调制后的变量值
            modulated_kwargs = kwargs.copy()
            
            if audio is not None:
                for var_name, (func, vars) in modulated_funcs.items():
                    # 获取音频数据
                    audio_kwargs = {}
                    for v in vars:
                        if v == 'band_energy':
                            audio_kwargs[v] = audio.get_band_energy(0)  # 默认取第 0 个频段
                        elif v == 'rms':
                            audio_kwargs[v] = audio.get_rms()
                        else:
                            audio_kwargs[v] = kwargs.get(v, 0.0)
                    
                    # 计算调制后的值
                    modulated_kwargs[var_name] = self.evaluate(func, **audio_kwargs)
            
            # 执行基础公式
            return self.evaluate(base_func, **modulated_kwargs)
        
        return modulated_func
