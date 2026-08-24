"""
JSON 效果验证器 — 检查 effects/ 下所有 JSON 的格式正确性

用法: python tools/auto_registry.py [--fix]
  --fix: 自动修复重复 ID
"""
import argparse
import json
import os
import sys
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def scan_json_effects(effects_dir):
    """扫描所有效果 JSON"""
    results = {}
    pattern = os.path.join(effects_dir, '*_*.json')
    for jf in sorted(glob.glob(pattern)):
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                results[os.path.basename(jf)] = json.load(f)
        except Exception as e:
            print(f"[WARN] 无法解析 {os.path.basename(jf)}: {e}")
    return results


def validate_engine_json(data):
    """验证引擎效果 JSON 格式"""
    errors = []
    if 'id' not in data:
        errors.append("缺少 'id' 字段")
    if 'name' not in data:
        errors.append("缺少 'name' 字段")
    if data.get('class') != 'EngineEffect':
        errors.append("class 字段必须为 'EngineEffect'")

    params = data.get('params', {})
    layers = params.get('layers', [])
    if not isinstance(layers, list):
        errors.append("params.layers 必须是数组")
        return errors
    if not layers:
        errors.append("至少需要一个 layer")

    valid_primitive_types = {'bars', 'spikes', 'waveform', 'vortex', 'circle_map',
                             'particles', 'grid', 'drawing', 'text_rain', 'script',
                             'formula', 'curve', 'ca', 'particle', 'fluid',
                             'texture', 'pulse', 'wireframe_3d', 'gauge'}
    for i, layer in enumerate(layers):
        ltype = layer.get('type', '')
        if ltype not in valid_primitive_types:
            errors.append(f"layer[{i}]: 未知原语类型 '{ltype}'，可用: {sorted(valid_primitive_types)}")
        if ltype == 'script':
            if 'draw' not in layer:
                errors.append(f"layer[{i}]: script 类型需要 'draw' 字段")

    return errors


def main():
    parser = argparse.ArgumentParser(description='验证 effects/*.json 格式')
    args = parser.parse_args()

    effects_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'effects')
    json_effects = scan_json_effects(effects_dir)

    print("=" * 60)
    print("引擎效果 JSON 验证")
    print(f"  JSON 文件: {len(json_effects)} 个")
    print("=" * 60)

    total_errors = 0
    type_counts = {}
    category_counts = {}

    for fname, data in sorted(json_effects.items()):
        errors = validate_engine_json(data)
        if errors:
            total_errors += len(errors)
            print(f"\n[ERR] {fname}:")
            for e in errors:
                print(f"  - {e}")
        else:
            # 统计
            for layer in data.get('params', {}).get('layers', []):
                ltype = layer.get('type', '?')
                type_counts[ltype] = type_counts.get(ltype, 0) + 1
            cat = data.get('category', '?')
            category_counts[cat] = category_counts.get(cat, 0) + 1

    print()
    if total_errors == 0:
        print("[OK] 所有 JSON 格式正确")
    else:
        print(f"[!!] {total_errors} 个错误")

    print(f"\n[统计] {sum(type_counts.values())} 层，按原语:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:12s}: {c}")

    print(f"\n[分类]")
    for cat, c in sorted(category_counts.items()):
        print(f"  {cat:8s}: {c} 个效果")

    # 检查重复 ID
    id_files = {}
    for fname, data in json_effects.items():
        eid = data.get('id', '')
        if eid:
            id_files.setdefault(eid, []).append(fname)
    dupes = {k: v for k, v in id_files.items() if len(v) > 1}
    if dupes:
        print(f"\n[WARN] 重复 ID:")
        for eid, files in dupes.items():
            print(f"  {eid}: {files}")

    print("=" * 60)


if __name__ == '__main__':
    main()
