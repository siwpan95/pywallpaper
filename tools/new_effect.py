#!/usr/bin/env python
"""
模板生成器 → 模板 → 新效果文件
=================================
从模板生成效果文件（Python类 + JSON），支持全新效果和参数化变体两种模式。

工作流程:
  --full      生成 Python 类骨架 + JSON            （需修改 render_system.py + 生成 JSON）
  --variant   仅生成 JSON，class 指向已有类          （仅需新建 JSON 文件）
  --preview   预览生成内容，不写入文件

示例:
  # 全新效果
  python tools/new_effect.py --full --id ripple --name "涟漪" --category "粒子" --bg "无"

  # 参数化变体
  python tools/new_effect.py --variant --class BarsEffect --name "快速条形图" --category "频谱"

  # 预览不写入
  python tools/new_effect.py --full --id test --name "测试" --preview

自动完成:
  1. 编号自动递增（从已有JSON找最大编号+1）
  2. 基于模板文件填充占位符
  3. Python 类输出到 stdout（手动复制到 render_system.py）
  4. JSON 写入 effects/ 目录
"""
import argparse
import json
import os
import re
import sys
import glob


# ======== 项目根 & 路径 ========
PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(PROJ, 'templates')
EFFECTS_DIR = os.path.join(PROJ, 'effects')
TOOLS_DIR = os.path.join(PROJ, 'tools')

sys.path.insert(0, PROJ)


# ======== 编号 & 类名获取 ========
def _get_existing_effect_ids():
    """扫描 effects/*.json，返回 {effect_id, max_index}"""
    max_idx = 0
    ids = set()
    for f in glob.glob(os.path.join(EFFECTS_DIR, '*_*.json')):
        m = re.match(r'(\d+)_(.+)\.json$', os.path.basename(f))
        if not m:
            continue
        idx = int(m.group(1))
        if idx > max_idx:
            max_idx = idx
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            ids.add(data.get('id', ''))
        except Exception:
            pass
    return ids, max_idx


def _get_registered_class_names():
    """从 render_system 获取已注册的效果类名列表"""
    try:
        from systems.render_system import _EFFECT_META
        return set(_EFFECT_META.keys())
    except Exception:
        return set()


def _get_class_params(class_name: str) -> dict:
    """从效果类 docstring 提取参数定义及默认值
    
    docstring 格式: "01. 条形图  params: n_bars(int), color_speed(float), sat(float)"
    返回: {"n_bars": {"type": "int", "default": 48}, ...}
    
    默认值来源：从类 draw() 中的 self.p('key', default) 提取。
    由于 self.p() 在 draw() 运行时才读取，这里通过实例化一个临时对象来获取。
    """
    import re
    try:
        from systems.render_system import EFFECT_REGISTRY
        from PIL import Image, ImageDraw
        
        # 找到目标类
        entry = None
        for v in EFFECT_REGISTRY.values():
            c = v[0] if isinstance(v, tuple) else v
            if c.__name__ == class_name:
                entry = v
                break
        if entry is None:
            return {}
        
        cls = entry[0] if isinstance(entry, tuple) else entry
        doc = cls.__doc__ or ''
        
        # 提取 "params: xxx" 部分
        m = re.search(r'params:\s*(.+)', doc)
        if not m:
            return {}
        
        params_str = m.group(1).strip()
        param_defs = {}
        for item in params_str.split(','):
            item = item.strip()
            pm = re.match(r'(\w+)\((\w+)\)', item)
            if pm:
                param_defs[pm.group(1)] = pm.group(2)
        
        if not param_defs:
            return {}
        
        # 尝试实例化来获取 self.p() 的默认值
        try:
            class FakeAudio:
                def get_band_energy(self, i): return 0.5
                def get_volume(self): return 0.5
            
            img = Image.new('RGB', (10, 10))
            draw = ImageDraw.Draw(img)
            # 传入空的 params，让 self.p() 回退到默认值
            obj = cls(draw, 10, 10, FakeAudio(), params={})
            result = {}
            for pname, ptype in param_defs.items():
                # 读取 _params 中的值就是 self.p(key, default) 的 default
                # 但空 params 时 _params 为空，所以直接用 getattr 读实例属性不行
                # 更直接的做法：临时设置一个哨兵值，检查 self.p() 的返回
                pass
            
            # 换一个方法：直接从源码的 self.p() 调用提取默认值
            import inspect
            source = inspect.getsource(cls.draw)
            result = {}
            for pname, ptype in param_defs.items():
                # 匹配 self.p('pname', default) 或 self.p("pname", default)
                pattern = rf"self\.p\(['\"]({pname})['\"],\s*([^)]+)\)"
                dm = re.search(pattern, source)
                if dm:
                    default_str = dm.group(2).strip()
                    # 尝试求值
                    try:
                        if ptype == 'int':
                            result[pname] = {"type": ptype, "default": int(eval(default_str))}
                        elif ptype == 'float':
                            result[pname] = {"type": ptype, "default": float(eval(default_str))}
                        elif ptype == 'bool':
                            result[pname] = {"type": ptype, "default": default_str == 'True'}
                        else:
                            result[pname] = {"type": ptype, "default": default_str}
                    except:
                        result[pname] = {"type": ptype, "default": default_str}
                else:
                    result[pname] = {"type": ptype, "default": None}
            return result
            
        except Exception:
            # 实例化失败，返回无默认值
            return {pname: {"type": ptype, "default": None} for pname, ptype in param_defs.items()}
        
    except Exception:
        return {}


def _get_all_parametrized_classes() -> dict:
    """返回所有支持 params 的类及其参数定义"""
    try:
        from systems.render_system import _EFFECT_META, EFFECT_REGISTRY
        result = {}
        seen = set()
        for v in EFFECT_REGISTRY.values():
            c = v[0] if isinstance(v, tuple) else v
            if c.__name__ in seen:
                continue
            seen.add(c.__name__)
            doc = c.__doc__ or ''
            if 'params:' in doc:
                params = _get_class_params(c.__name__)
                if params:
                    result[c.__name__] = params
        return result
    except Exception:
        return {}


def _get_background_themes():
    """从 themes.json 获取有效背景主题名列表"""
    tp = os.path.join(EFFECTS_DIR, 'themes.json')
    try:
        with open(tp, 'r', encoding='utf-8') as f:
            themes = json.load(f)
        return [t['name'] for t in themes]
    except Exception:
        return ['无', '星空', '渐变', '极光']


def _get_categories():
    """从已注册效果收集分类名"""
    try:
        from systems.render_system import _EFFECT_META
        cats = sorted(set(m.get('category', '未分类') for m in _EFFECT_META.values()))
        return cats
    except Exception:
        return ['频谱', '圆形', '波浪', '粒子', '纹理', '文字', '几何', '特殊', '未分类']


# ======== 模板加载 & 填充 ========
def _load_template(filename):
    """加载模板文件"""
    p = os.path.join(TEMPLATES, filename)
    if not os.path.exists(p):
        raise FileNotFoundError(f"模板不存在: {p}")
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()


def _render(template_str, variables):
    """替换模板中的 {{key}} 占位符"""
    result = template_str
    for key, val in variables.items():
        result = result.replace('{{' + key + '}}', str(val))
    return result


# ======== 生成逻辑 ========
def _generate_full(args):
    """--full 模式：生成 Python 类 + JSON"""
    existing_ids, max_idx = _get_existing_effect_ids()
    registered = _get_registered_class_names()

    # --- 校验 ---
    if args.id in existing_ids:
        print(f"[ERROR] effect_id '{args.id}' 已存在！请换一个 id 或删除旧 JSON。")
        sys.exit(1)

    class_name = args.class_name or _id_to_class_name(args.id)
    if class_name in registered:
        print(f"[ERROR] 类名 '{class_name}' 已在 Python 中注册！请换一个 id 或用 --class 指定其他类名。")
        sys.exit(1)

    bg = args.bg or '无'
    valid_bgs = _get_background_themes()
    if bg not in valid_bgs:
        print(f"[WARN] 背景主题 '{bg}' 不在已知列表中: {valid_bgs}，将以原始值写入。")

    cat = args.category or '未分类'

    idx = max_idx + 1
    full_name = f"{idx:02d}. {args.name}"

    # --- 渲染 Python 类模板 ---
    py_vars = {
        "effect_id": args.id,
        "name": args.name,
        "full_name": full_name,
        "category": cat,
        "background_theme": bg,
        "class_name": class_name,
    }
    py_tmpl = _load_template('effect_class.py.tmpl')
    py_code = _render(py_tmpl, py_vars)

    # --- 渲染 JSON 模板 ---
    json_vars = {**py_vars}
    json_tmpl = _load_template('effect.json.tmpl')
    json_content = _render(json_tmpl, json_vars)

    if args.preview:
        print("=" * 60)
        print("预览模式 — 不写入任何文件")
        print("=" * 60)
        print("\n--- Python 类骨架（复制到 render_system.py） ---")
        print(py_code)
        print("\n--- JSON 文件（将写入 effects/） ---")
        print(f"filename: {idx:02d}_{args.id}.json")
        print(json_content)
        print("\n--- 完成后请执行 ---")
        print(f"  python tools/auto_registry.py")
        print(f"  python effects/generate.py")
        return

    # --- 写入 JSON ---
    json_filename = f"{idx:02d}_{args.id}.json"
    json_path = os.path.join(EFFECTS_DIR, json_filename)
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write(json_content)

    # --- 写入 Python 类（如果 --write） ---
    rendered_py_path = None
    if args.write:
        rendered_py_path = os.path.join(PROJ, 'systems', 'render_system.py')
        insert_marker = '# ==================== 效果加载器（自动发现） ===================='
        with open(rendered_py_path, 'r', encoding='utf-8') as f:
            source = f.read()
        if insert_marker in source:
            # 在标记之前插入，前面空两行
            insertion = f'\n\n{py_code.strip()}\n'
            source = source.replace(f'\n{insert_marker}', f'{insertion}\n{insert_marker}', 1)
            with open(rendered_py_path, 'w', encoding='utf-8') as f:
                f.write(source)
        else:
            print(f'\n[WARN] 未找到插入标记 "{insert_marker}"，类代码仅输出到终端')
            args.write = False

    # --- 输出总结 ---
    print("=" * 60)
    print(f"新效果已生成！")
    print("=" * 60)
    print(f"\nJSON 已写入: effects/{json_filename}")
    if args.write and rendered_py_path:
        print(f"Python 类已写入: systems/render_system.py")
        print(f"编号: {idx:02d} | 类名: {class_name} | 背景: {bg}")
        print("\n--- 后续步骤 ---")
        print("  1. 在 render_system.py 中找到类并实现 draw() 方法")
        print("  2. python tools/auto_registry.py   # 验证对齐")
        print("  3. python effects/generate.py       # 确认注册")
    else:
        print(f"编号: {idx:02d} | 类名: {class_name} | 背景: {bg}\n")
        print("--- Python 类骨架（复制到 render_system.py 效果类区域） ---")
        print(py_code)
        print("--- 后续步骤 ---")
        print("  1. 将上方 Python 类代码复制到 render_system.py 的效果类区域")
        print("  2. 实现 draw() 方法")
        print("  3. python tools/auto_registry.py   # 验证对齐")
        print("  4. python effects/generate.py       # 确认注册")


def _generate_variant(args):
    """--variant 模式：仅生成 JSON，复用已有类"""
    existing_ids, max_idx = _get_existing_effect_ids()
    registered = _get_registered_class_names()

    if args.variant_class not in registered:
        print(f"[ERROR] 类名 '{args.variant_class}' 未在 render_system.py 中注册！")
        print(f"  已注册类: {sorted(registered)}")
        sys.exit(1)

    effect_id = args.id or _class_name_to_id(args.variant_class) + '_variant'
    if effect_id in existing_ids:
        print(f"[ERROR] effect_id '{effect_id}' 已存在！请用 --id 指定新 id。")
        sys.exit(1)

    bg = args.bg or '无'
    cat = args.category or '未分类'

    idx = max_idx + 1
    full_name = f"{idx:02d}. {args.name}"

    # 自动提取类的参数定义，生成带真实默认值的 params
    class_params = _get_class_params(args.variant_class)
    if class_params:
        params = {}
        for pname, pinfo in class_params.items():
            d = pinfo.get('default')
            if d is not None:
                params[pname] = d
        if not params:
            params = {"speed": 1.0, "color_speed": 0.1}
    else:
        params = {"speed": 1.0, "color_speed": 0.1}

    # 支持命令行 --params 覆盖
    if args.params:
        for kv in args.params.split(','):
            if '=' in kv:
                k, v = kv.split('=', 1)
                k, v = k.strip(), v.strip()
                try:
                    params[k] = int(v) if v.isdigit() else float(v) if '.' in v else v
                except ValueError:
                    params[k] = v

    data = {
        "id": effect_id,
        "name": args.name,
        "full_name": full_name,
        "category": cat,
        "background_theme": bg,
        "class": args.variant_class,
        "params": params,
    }

    if args.preview:
        print("=" * 60)
        print("预览模式 — 不写入文件")
        print("=" * 60)
        print(f"\n--- JSON 文件 ---")
        print(f"filename: {idx:02d}_{effect_id}.json")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if class_params:
            print(f"\n--- 可用参数 ---")
            for pname, pinfo in class_params.items():
                print(f"  {pname:20s} ({pinfo['type']})  默认={pinfo.get('default', '未知')}")
        return

    json_filename = f"{idx:02d}_{effect_id}.json"
    json_path = os.path.join(EFFECTS_DIR, json_filename)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"参数化变体已生成！")
    print("=" * 60)
    print(f"JSON 已写入: effects/{json_filename}")
    print(f"编号: {idx:02d} | 复用类: {args.variant_class}")
    if class_params:
        print(f"\n可用参数:")
        for pname, pinfo in class_params.items():
            print(f"  {pname:20s} ({pinfo['type']})  默认={pinfo.get('default', '未知')}")
    print(f"\n无需修改 Python 代码，运行以下命令验证:")
    print(f"  python tools/auto_registry.py")


def _list_params(args):
    """--list-params 模式：列出效果类支持的参数"""
    if args.variant_class:
        # 列出指定类的参数
        params = _get_class_params(args.variant_class)
        if not params:
            print(f"[INFO] 类 '{args.variant_class}' 的 docstring 中未声明 params。")
            print(f"       该类可能不支持参数化变体，或尚未添加 self.p() 读取。")
            return
        print(f"类: {args.variant_class}")
        print(f"可用参数:")
        for pname, pinfo in params.items():
            d = pinfo.get('default')
            print(f"  {pname:20s} ({pinfo['type']:6s})  默认值={d}")
    else:
        # 列出所有支持 params 的类
        all_params = _get_all_parametrized_classes()
        if not all_params:
            print("[INFO] 没有效果类声明 params。")
            print("       在类的 docstring 中添加 'params: key(type), ...' 即可被此工具识别。")
            return
        print("支持参数化变体的效果类:")
        print("=" * 70)
        for cls_name, params in sorted(all_params.items()):
            param_str = ', '.join(f'{k}({v["type"]})' for k, v in params.items())
            print(f"  {cls_name:30s} {param_str}")
        print(f"\n使用 --class ClassName --list-params 查看某类参数详情")


def _list_info():
    """--info 模式：列出当前状态"""
    ids, max_idx = _get_existing_effect_ids()
    registered = _get_registered_class_names()
    bgs = _get_background_themes()
    cats = _get_categories()

    print("=" * 60)
    print("当前项目效果状态")
    print("=" * 60)
    print(f"JSON 效果文件: {len(ids)} 个（编号 01~{max_idx:02d}）")
    print(f"Python 注册类: {len(registered)} 个")
    print(f"\n背景主题: {', '.join(bgs)}")
    print(f"\n已有分类: {', '.join(cats)}")
    print(f"\n下一个编号: {max_idx + 1:02d}")

    try:
        from systems.render_system import _EFFECT_META
        print(f"\n已注册效果列表:")
        for cls_name, meta in _EFFECT_META.items():
            bg = meta.get('background', '无')
            cat = meta.get('category', '未分类')
            print(f"  {cls_name:35s} id={meta['id']:20s} [{cat}]  bg={bg}")
    except Exception:
        pass


# ======== 命名工具 ========
def _id_to_class_name(effect_id):
    """'my_effect' → 'MyEffect'"""
    return ''.join(w.capitalize() for w in effect_id.split('_')) + 'Effect'


def _class_name_to_id(class_name):
    """'BarsEffect' → 'bars'"""
    if class_name.endswith('Effect'):
        class_name = class_name[:-6]
    result = re.sub(r'([A-Z])', r'_\1', class_name).lower().strip('_')
    return result


# ======== CLI 入口 ========
def parse_args():
    p = argparse.ArgumentParser(
        description='模板生成器 — 从模板快速生成新效果（Python类 + JSON）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/new_effect.py --full --id ripple --name "涟漪" --category "粒子" --bg "无"
  python tools/new_effect.py --variant --class BarsEffect --name "快速条形图"
  python tools/new_effect.py --full --id test --name "测试" --preview
  python tools/new_effect.py --info
        """
    )

    p.add_argument('--full', action='store_true', help='全新效果模式：生成 Python 类骨架 + JSON')
    p.add_argument('--variant', action='store_true', help='参数化变体模式：仅生成 JSON，class 指向已有类')
    p.add_argument('--info', action='store_true', help='显示当前项目效果状态')
    p.add_argument('--list-params', action='store_true', help='列出效果类支持的参数（--class 指定类名）')

    # 通用参数
    p.add_argument('--id', help='效果标识符（snake_case，如 my_effect）')
    p.add_argument('--name', help='效果中文名（如 "我的效果"）')
    p.add_argument('--category', help='分类名')
    p.add_argument('--bg', help='背景主题名（默认 "无"）')

    # --variant 专用
    p.add_argument('--class', dest='variant_class', help='复用的已有类名（--variant 必需，--list-params 可选）')
    p.add_argument('--params', help='覆盖参数，格式: key1=val1,key2=val2（--variant 模式可选）')

    # 覆盖类名（--full 时可选）
    p.add_argument('--class-name', help='覆盖自动推导的类名（--full 时可选）')

    # 预览
    p.add_argument('--preview', action='store_true', help='仅预览，不写入任何文件')
    p.add_argument('--write', action='store_true', help='将 Python 类代码直接写入 render_system.py（--full 模式）')

    return p.parse_args()


def main():
    args = parse_args()

    if args.info:
        _list_info()
    elif args.list_params:
        _list_params(args)
    elif args.full:
        if not args.id:
            print("[ERROR] --full 模式需要 --id")
            sys.exit(1)
        if not args.name:
            print("[ERROR] --full 模式需要 --name")
            sys.exit(1)
        _generate_full(args)
    elif args.variant:
        if not args.variant_class:
            print("[ERROR] --variant 模式需要 --class")
            sys.exit(1)
        if not args.name:
            print("[ERROR] --variant 模式需要 --name")
            sys.exit(1)
        _generate_variant(args)
    else:
        print("[INFO] 请指定 --full 或 --variant 模式。使用 --info 查看项目状态。")
        print("      示例: python tools/new_effect.py --full --id demo --name '演示'")
        print("      帮助: python tools/new_effect.py --help")
        sys.exit(0)


if __name__ == '__main__':
    main()
