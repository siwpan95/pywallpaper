# 效果模板系统

## 文件说明

| 文件 | 用途 |
|------|------|
| `effect.json.tmpl` | 全新效果JSON模板（含Python类骨架） |
| `effect_class.py.tmpl` | 全新效果Python类骨架模板 |
| `effect_variant.json.tmpl` | 参数化变体JSON模板（复用已有类） |

## 添加新效果的三种方式

### 方式A：全新效果（--full）

自动生成 Python 类骨架 + JSON 文件：

```bash
python tools/new_effect.py --full --id my_effect --name "我的效果" --category "自定义" --bg "渐变"
```

### 方式B：参数化变体（--variant）

复用已有类，仅生成带自定义参数的JSON：

```bash
python tools/new_effect.py --variant --class BarsEffect --name "快速条形图" --category "频谱" --bg "渐变"
```

### 方式C：纯手动

1. 复制 `effect_class.py.tmpl` 内容到 `render_system.py`
2. 复制 `effect.json.tmpl` → `effects/` 目录下创建 JSON
3. 运行 `python tools/auto_registry.py` 验证

## 验证命令

```bash
# 生成缺失的JSON
python effects/generate.py

# 对齐检查
python tools/auto_registry.py

# 强制全部重新生成
python effects/generate.py --force
```
