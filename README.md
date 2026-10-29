# PyWallpaper — 数学公式驱动的动态壁纸引擎

## 仓库角色定位（投资组合分级 ②）

> 本仓在 siwpan 投资组合（D:/projects/repos，共 133 仓）中定级为 **② 保留**，领域 **视频/图像/特效**。
> **角色**：创意库。
> **维护策略**：② 旗舰 / 枢纽仓库打磨保留，作为能力展示或收敛点；② 保留类仓库低优先维持、不主动扩张。
> 投资组合统一分级索引（多机可查）：[组合分级决策索引 · allin 事实源](https://gitee.com/siwpan/allin/blob/master/docs/事实源/组合分级决策索引.md)。

> 仓库：<https://gitee.com/siwpan/pywallpaper> ｜ 许可：MIT（见 [LICENSE](LICENSE)）

ECS 架构的音乐可视化动态壁纸系统，集成了 draw 项目的数学公式引擎和细胞自动机（CA）能力，支持粒子系统、流体模拟等多种效果类型。Python 负责逻辑，JSON 负责内容，通过装饰器 + 子类自动发现实现零硬编码注册。

> 自包含说明：draw 的配方库已收归本项目的 `recipes/` 目录（2026-08-21），CA 原语不再依赖外部 draw 目录，可独立运行。draw 项目保留其自身副本，可随时归档。

---

## 零、三件事 CLI（media_engine 阶段 A，2026-08-24 纯加法）

- 装配自省：`python main.pyw --dump-profile`（effects/primitives/可选依赖清单，agent 审计入口）
- 任务日志审计：`python main.pyw --dump-log [日志路径]`（默认 data/logs/wallpaper.log，JSONL 与 WorldLog 同构）
- 运行日志：启动即写 run_start/run_end 到 data/logs/wallpaper.log；内核 `core/context.py`（注册即回滚）与 `core/world_log.py` 内联自 alloy 引擎（复制优于共享）
- 冒烟：`python test_three_things.py`（3/3）

## 一、项目结构

```
pywallpaper/
├── main.py                          # 入口，命令行参数 → 创建 WallpaperRenderer → 启动循环
├── ecs.py                           # ECS 框架基类（Entity / Component / System / World）
├── data_loader.py                   # 统一 JSON 加载器（config.json / audio.json）
│
├── engine/                          # 新增：数学公式引擎和原语系统
│   ├── formula_engine.py            # 统一公式引擎（结合 draw 的 asteval 系统）
│   └── primitives/                 # 效果原语（可组合的基础效果单元）
│       ├── ca.py                    # 细胞自动机（CA）原语（支持 4973+ 配方）
│       ├── ca_kernel.py             # JIT 编译的 CA 演化核（Numba @njit）
│       ├── curve.py                 # 曲线公式原语（增强版，支持 formula 模式）
│       ├── formula.py               # 通用公式原语（任意数学表达式）
│       ├── particle.py              # 粒子系统原语（发射器+力场+音频驱动）
│       └── fluid.py                # 流体模拟原语（Stable Fluids 简化版）
│
├── systems/
│   ├── audio_system.py              # 音频：AudioSimulator(FFT频谱) + MusicPlaybackSystem(WAV播放)
│   ├── render_system.py             # 核心：VisualEffect 基类 + 48 个效果类 + 自动加载器
│   ├── effect_manager.py            # 效果管理器：轮换调度 + 主题切换
│   └── wallpaper_system.py          # 总控：渲染循环 + Windows 壁纸 API + 性能监控
│
├── effects/                         # 内容层 — 纯 JSON，与逻辑完全解耦
│   ├── 01_bars.json ~ 54_combined_ca_formula.json   # 54 个效果配置
│   ├── themes.json                  # 4 个背景主题配置
│   └── generate.py                  # 自动生成缺失 JSON
│
├── recipes/                         # CA 配方库（原 draw/effects 的 4972 个配方，自包含）
│   ├── *.json                       # {Initial}_{Rule}_{Color}_{hash}.json 配方
│   ├── evolution_rules.py           # 已知规则名单（原 draw/templates/evolution.py 副本）
│   └── super_params.py              # 超级公式参数默认值（p1..p8 / w1..w4 等，33 项）
│
├── templates/                       # 模板层
│   ├── effect.json.tmpl             # 全新效果 JSON 模板
│   ├── effect_class.py.tmpl         # 全新效果 Python 类骨架模板
│   ├── effect_variant.json.tmpl     # 参数化变体 JSON 模板
│   └── README.md                    # 模板使用文档
│
├── tools/
│   ├── new_effect.py                # 模板生成器 CLI（创建新效果入口）
│   ├── auto_registry.py             # 双向对齐检查器（JSON ↔ Python 类）
│   └── effect_editor_v2.py         # 效果编辑器 v2（含效果市场/创意工坊）
│
└── utils/
    └── helpers.py                   # hsv_to_rgb 等工具函数
```

---

## 二、核心新功能

### 2.1 统一公式引擎（FormulaEngine）

结合 draw 项目的 asteval 公式系统和 pywallpaper 的曲线公式能力，支持：
- 安全求值数学表达式（基于 asteval）
- NumPy 向量化计算
- 音频数据驱动（`audio.spectrum`, `audio.energy` 等变量）
- 时间变量（`t` 为运行时间）

```python
from engine.formula_engine import FormulaEngine
engine = FormulaEngine()
result = engine.evaluate("sin(t * 2) * audio.energy", 
                       t=time, audio=audio_data)
```

### 2.2 效果原语系统

将复杂效果分解为可组合的基础单元：

| 原语 | 功能 | 典型应用 |
|------|------|---------|
| `formula` | 通用公式驱动 | 数学艺术、参数化曲线 |
| `curve` | 曲线公式（增强版） | 频谱曲线、Lissajous 图形 |
| `ca` | 细胞自动机 | Game of Life、森林火灾、病毒传播 |
| `particle` | 粒子系统 | 烟花、雨雪、爆炸效果 |
| `fluid` | 流体模拟 | 烟雾、水流、音频可视化 |

### 2.3 CA 引擎集成

- **外置配方加载**：从 draw 的 4973+ 个 JSON 配方动态加载，取代硬编码
- **音频调制**：支持 `color_hue`, `color_sat`, `color_val` 等音频驱动参数
- **性能优化**：
  - NumPy 向量化（`np.roll` 计算邻域和）
  - Numba JIT 编译（性能提升 10-100x）

### 2.4 粒子系统

`particle.py` 原语支持高效的粒子模拟与渲染。

**发射器配置**：
```json
{
  "position": [0.5, 0.8],   // 归一化坐标
  "rate": 50,                // 每秒发射粒子数
  "lifetime": [1.0, 3.0],  // 生命周期范围（秒）
  "speed": [100, 300],       // 速度范围（像素/秒）
  "direction": [260, 280],   // 方向范围（度）
  "color": [255, 200, 50], // 基础颜色
  "size": [2, 5]            // 大小范围
}
```

**力场类型**：
- `gravity`：重力（`"y": 200`）
- `wind`：风力（`"x": 50`）
- `attract`：吸引力（`"position": [0.5, 0.5]`, `"strength": 100`）

**粒子类型**：
- `point`：点
- `circle`：圆
- `line`：线
- `trail`：尾迹

**音频调制**：
```json
{
  "audio_modulation": {
    "rate": "rms * 100 + 20",         // 音量控制发射速率
    "color_hue": "band_energy_0 * 360"  // 低频控制色相
  }
}
```

**内置粒子效果**：
- `080_particle_fireworks.json` — 烟花（向上发射 + 重力）
- `081_particle_rain.json` — 雨水（顶部下落 + 风力）
- `082_particle_snow.json` — 雪花（缓慢飘落 + 音频调制）

### 2.5 流体模拟

实现 Stable Fluids 简化版：
- 密度场和速度场
- 扩散和平流
- 音频驱动（通过 `audio.energy` 影响速度场）

### 2.6 效果编辑器 v2（含效果市场）

GUI 工具，功能包括：
- **效果浏览**：查看所有可用效果
- **参数调整**：实时修改效果参数
- **实时预览**：查看效果变化
- **效果市场**（创意工坊）：
  - 浏览社区效果
  - 导入/导出效果配置
  - 加载效果到编辑器
  - 删除效果

---

## 三、架构总览

### 3.1 分层设计

```
┌──────────────────────────────────────────┐
│              入口层 (main.py)              │
│    命令行解析 → 窗口/全屏模式 → 启动       │
├──────────────────────────────────────────┤
│          原语层 (engine/primitives/)      │
│  FormulaEngine 公式求值                  │
│  CA / Particle / Fluid 等原语           │
├──────────────────────────────────────────┤
│            系统层 (systems/)               │
│  WallpaperRenderer 总控渲染循环           │
│  AudioSimulator FFT 频谱                  │
│  MusicPlaybackSystem WAV 播放             │
│  EffectManager 轮换调度                   │
│  VisualEffect 基类 + 48 效果类            │
├──────────────────────────────────────────┤
│            内容层 (effects/)               │
│  54 个 JSON + themes.json                │
│  仅数据，不含任何逻辑                      │
├──────────────────────────────────────────┤
│            工具层 (tools/ + templates/)    │
│  模板生成器 + 对齐检查器 + 效果编辑器     │
└──────────────────────────────────────────┘
```

### 3.2 ECS 数据流

```
[main.py]
    │
    └→ WallpaperRenderer.__init__()
         │
         ├→ AudioSimulator()              创建 FFT 模拟器
         ├→ MusicPlaybackSystem()          创建 WAV 播放器
         ├→ EffectManager(EFFECT_REGISTRY) 创建效果管理器
         │                                  ↑ EFFECT_REGISTRY 在 import
         │                                    render_system 时自动填充
         └→ run() 渲染循环 ────────────────────────────────────────┐
              │                                                      │
              ├→ audio.update()          FFT 频谱数据                 │
              ├→ music.update()          WAV 音频播放                 │
              ├→ bg.draw()               当前背景主题绘制              │ 每帧
              ├→ effect.update(dt)       更新效果时间/animation        │ 循环
              ├→ effect.draw()           绘制可视化效果               │
              ├→ img.save(PNG)           写出临时 PNG                 │
              ├→ set_wallpaper(PNG)      Windows API 设为壁纸         │
              └→ effect_manager.tick()   检查是否轮换效果 ────────────┘

退出钩子:
  atexit.register(shutdown)  /  KeyboardInterrupt
    → music.stop()          停止 WAV 播放
    → music.shutdown()      释放 pygame.mixer
```

---

## 四、自动注册机制（核心设计）

内容是 JSON，逻辑是 Python，两者通过 **类名字符串** 桥接。注册表完全自动构建，无任何硬编码映射。

### 4.1 两条并行链路

```
链路1: 装饰器收集元数据 (定义时执行)
  @register_effect(id, name, category, background_theme)
       │
       └→ _EFFECT_META[类名] = {id, name, category, background_theme, params}
              │
              └→ get_effect_meta()  ← 供 generate.py / auto_registry.py 读取


链路2: 子类自动发现 (load_effects 时执行)
  VisualEffect.__subclasses__()
       │
       └→ _build_class_map() → {类名: 类对象}
              │
  effects/*.json 扫描 → 读取 class 字段（类名字符串）
       │
       └→ 字符串匹配桥接 → EFFECT_REGISTRY[full_name] = 类对象
```

### 4.2 二元冗余保障

| 机制 | 功能 | 失效后果 |
|------|------|---------|
| `@register_effect` 装饰器 | 收集元数据，供工具链使用 | `generate.py` / `auto_registry.py` 不可用 |
| `__subclasses__()` 自动发现 | 构建类名映射，供运行时加载 | EFFECT_REGISTRY 无法填充 |

两者互不依赖、各自独立工作。任一机制存活即可保证系统正常运行。

---

## 五、运行时流程

### 5.1 启动流程

```
python main.py
  → 解析命令行参数（--size / --fullscreen / --interval 等）
  → 创建 WallpaperRenderer
      → import systems.render_system  ← 触发 @register_effect 执行
      → _auto_load()  ← 扫描 effects/*.json → 填充 EFFECT_REGISTRY + BACKGROUND_THEMES
      → AudioSimulator() ← 初始化 FFT 频谱模拟器
      → MusicPlaybackSystem() ← 初始化 pygame.mixer，加载 music_gen WAV
      → EffectManager() ← 按 JSON 顺序建立效果队列
  → renderer.run()  ← 进入主循环
```

### 5.2 退出流程

```
用户 Ctrl+C / 窗口关闭
  → KeyboardInterrupt → renderer.shutdown()
      → music.stop()         停止并卸载 WAV
      → music.shutdown()     释放 pygame.mixer
      → self.running = False 退出循环

正常退出时 atexit 兜底（双重保险）
```

---

## 六、添加新效果

### 6.1 路径A：全新效果（需 Python 类 + JSON）

```bash
# 步骤1: 生成器创建骨架（自动写入 Python 类 + JSON）
python tools/new_effect.py --full --write --id my_effect --name "我的效果" --category "频谱" --bg "渐变"

# 步骤2: 在 render_system.py 中找到类，实现 draw() 方法

# 步骤3: 验证
python tools/auto_registry.py    # JSON ↔ Python 对齐检查
python effects/generate.py       # 确认无重复

# 完成。无需修改任何注册表或映射字典。
```

**操作文件数**: 0（`--write` 自动完成所有文件操作）

### 6.2 路径B：参数化变体（仅 JSON，复用已有类）

```bash
# 步骤0: 查看哪些类支持参数化，以及各参数的默认值
python tools/new_effect.py --list-params                        # 列出所有支持 params 的类
python tools/new_effect.py --list-params --class VortexEffect   # 查看某类的参数详情+默认值

# 步骤1: 生成器创建 JSON（自动填入类默认参数）
python tools/new_effect.py --variant --class BarsEffect --name "快速条形图" --category "频谱" --bg "渐变" --id fast_bars

# 步骤1-alt: 生成时直接覆盖参数（黄金比例φ=1.618、斐波那契数等数学公式）
python tools/new_effect.py --variant --class VortexEffect --name "漩涡·黄金螺旋" \
    --params "speed=1.618,twist=1.618,r_step=8.09" --bg "渐变" --id vortex_golden

# 步骤2: 如需微调，编辑 JSON 中的 params 字段
#        无需修改任何 Python 代码

# 步骤3: 验证
python tools/auto_registry.py

# 完成。
```

**操作文件数**: 1（仅 json）

### 6.3 路径C：使用效果原语（推荐）

通过组合效果原语创建复杂效果，无需编写 Python 代码：

```json
{
    "id": "my_ca_effect",
    "name": "我的 CA 效果",
    "class": "CAEffect",
    "params": {
        "recipe_name": "game_of_life",
        "width": 128,
        "height": 128,
        "use_jit": true,
        "color_mode": "audio",
        "color_hue": "audio.energy * 360",
        "color_sat": "0.8 + audio.energy * 0.2",
        "color_val": "0.5 + audio.spectrum[0] * 0.5"
    }
}
```

---

## 七、效果 JSON 规范

```json
{
    "id":             "bars",            // 唯一标识，英文小写+下划线
    "name":           "条形图",          // 中文显示名
    "full_name":      "01. 条形图",      // 编号.名称（自动生成）
    "category":        "频谱",           // 分类：频谱/波形/粒子/几何/信息
    "background_theme":"渐变",           // 背景主题：渐变/星空/暗夜/无
    "class":           "BarsEffect",     // Python 类名（字符串桥接）
    "params": {                          // 可选参数，传递给效果类
        "speed": 0.03,
        "n_bars": 64
    }
}
```

### 背景主题 JSON 规范

```json
{
    "id":           "starfield",
    "name":         "星空",
    "class":        "StarFieldTheme",
    "description":  "动态星空背景效果",
    "priority":     10
}
```

### CA 效果 JSON 规范（新增）

```json
{
    "id": "ca_game_of_life",
    "name": "生命游戏",
    "class": "CAEffect",
    "params": {
        "recipe_name": "game_of_life",    // CA 配方名称（从外置 JSON 加载）
        "width": 128,                     // 网格宽度
        "height": 128,                    // 网格高度
        "use_jit": true,                  // 是否使用 JIT 编译（推荐）
        "color_mode": "audio",            // 颜色模式：audio / rainbow / mono
        "color_hue": "audio.energy * 360", // 色调公式（音频驱动）
        "color_sat": "0.8",              // 饱和度
        "color_val": "0.5 + cell * 0.5"  // 亮度公式
    }
}
```

### 粒子效果 JSON 规范（新增）

```json
{
    "id": "particle_fireworks",
    "name": "烟花效果",
    "class": "ParticleEffect",
    "params": {
        "emitters": [{
            "type": "point",
            "x": 0.5,
            "y": 0.5,
            "rate": 50,
            "lifetime": [0.5, 1.5]
        }],
        "forces": [{
            "type": "gravity",
            "gx": 0,
            "gy": -0.1
        }],
        "audio_reactive": true
    }
}
```

---

## 八、工具链

| 工具 | 路径 | 功能 | 典型用法 |
|------|------|------|---------|
| `new_effect.py` | `tools/` | 模板生成器，创建新效果入口 | `python tools/new_effect.py --full --write --id X --name "名称"` |
| `auto_registry.py` | `tools/` | 双向对齐检查 + 自动修复 | `python tools/auto_registry.py [--fix]` |
| `generate.py` | `effects/` | 自动生成缺失 JSON | `python effects/generate.py` |
| `effect_editor_v2.py` | `tools/` | 效果编辑器 + 效果市场 | `python tools/effect_editor_v2.py` |

### 8.1 new_effect.py 全部模式

```
--full        创建全新效果（Python 类骨架 + JSON）  编号自动递增
--variant     创建参数化变体（仅 JSON，复用已有类） class 指向已有类名
              自动从类源码提取参数默认值填充 params
              支持 --params "key1=val1,key2=val2" 命令行覆盖参数
--write       配合 --full 使用，直接写入 render_system.py（无需手工粘贴）
--list-params 列出支持参数化变体的效果类及其参数+默认值
              --class ClassName 查看单个类的参数详情
--preview     预览模式，输出到终端不写文件
--info        显示项目状态（下一个编号、已有分类、所有注册效果）
--help        显示帮助
```

### 8.2 auto_registry.py 检查项

- **多余 JSON**: effects/ 中有但 Python 中无对应类的 JSON
- **缺失 JSON**: Python 中有已注册类但 effects/ 中无对应 JSON
- **类名拼写错误**: JSON 中的 class 字段在 Python 中找不到
- **分类统计**: 各分类下的效果数量
- **主题关联**: 检查每个效果引用的 background_theme 是否存在
- **--fix**: 自动补全缺失的 JSON 文件（编号自动递增）

### 8.3 效果编辑器 v2

GUI 工具，提供：
- **效果浏览**：查看所有可用效果
- **参数调整**：实时修改效果参数（滑块、输入框、颜色选择器）
- **实时预览**：查看效果变化
- **效果市场**（创意工坊）：
  - 浏览社区效果
  - 导入/导出效果配置
  - 加载效果到编辑器
  - 删除效果

启动方式：
```bash
python tools/effect_editor_v2.py
```

### 8.4 完整工作流

```
1. new_effect.py --full --write  创建新效果 → 自动写入 JSON + Python 类
2. 手动实现 draw()               完成视觉效果逻辑
3. auto_registry.py              验证 JSON ↔ Python 对齐
4. generate.py                   确认注册、无重复
5. python main.py                运行测试
```

---

## 九、效果分类体系

| 分类 | 数量 | 典型效果 |
|------|------|---------|
| 频谱 | 15 | 条形图、圆形频谱、瀑布图、3D 频谱 |
| 波形 | 10 | 示波器、心形波、极坐标波、螺旋波 |
| 粒子 | 14 | 粒子雨、烟花、星爆、水晶球 |
| 几何 | 9 | 分形树、六边形网格、超立方体、曼陀罗 |
| 信息 | 1 | 时钟 |
| CA | 5 | 生命游戏、森林火灾、病毒传播、公式螺旋 |
| 公式 | 3 | 公式螺旋、Lissajous 曲线、组合效果 |

---

## 十、背景主题

| 主题 | 类名 | 说明 |
|------|------|------|
| 渐变 | `GradientTheme` | 随音频能量变化的渐变色背景 |
| 星空 | `StarFieldTheme` | 动态星空粒子背景 |
| 暗夜 | `DarkNightTheme` | 深色纯色背景，带细微噪点 |
| 无 | — | 纯黑背景，无额外绘制 |

---

## 十一、设计原则

| 原则 | 实现方式 |
|------|---------|
| **内容与逻辑解耦** | JSON（内容） ↔ Python（逻辑），类名字符串桥接 |
| **零硬编码注册** | `@register_effect` 装饰器 + `__subclasses__()` 二元冗余 |
| **添加 = 追加** | 加文件无需改文件，新 JSON / 新类自动纳入注册表 |
| **编号自增** | `new_effect.py` 和 `generate.py` 均自动找最大编号 +1 |
| **双向验证** | `auto_registry.py` 双向检查，确保 JSON ↔ Python 完全对齐 |
| **模板驱动** | 三套模板覆盖全部场景，生成器消除手工复制粘贴 |
| **配置优先** | Excel → JSON 兜底 → 硬编码默认值 链式加载逻辑 |
| **优雅退出** | atexit 注册 + KeyboardInterrupt 双重保险，确保音乐停止、资源释放 |
| **性能优先** | NumPy 向量化 + Numba JIT 编译，确保实时渲染性能 |
| **可组合性** | 效果原语系统，支持通过 JSON 组合复杂效果 |

---

## 十二、快速开始

```bash
# 运行（窗口模式，800x600）
python main.py

# 全屏模式
python main.py --fullscreen

# 自定义尺寸
python main.py --size 1024 768

# 指定效果轮换间隔（秒）
python main.py --interval 30

# 播放指定音乐
python main.py --music path/to/music.wav

# 启动效果编辑器（含效果市场）
python tools/effect_editor_v2.py

# 检查项目状态
python tools/new_effect.py --info

# 验证文件对齐
python tools/auto_registry.py
```

---

## 十三、示范文件

| 文件 | 说明 |
|------|------|
| `effects/48_demo_crystal.json` | 全新效果示范 JSON |
| `effects/49_demo_crystal_fast.json` | 参数化变体示范 JSON |
| `effects/050_formula_spiral.json` | 公式螺旋效果示范 |
| `effects/051_ca_game_of_life.json` | CA 生命游戏效果示范 |
| `effects/060_particle_fireworks.json` | 粒子烟花效果示范 |
| `effects/061_fluid_smoke.json` | 流体烟雾效果示范 |
| `systems/render_system.py` `DemoCrystalEffect` 类 | 全新效果示范 Python 类 |
| `engine/formula_engine.py` | 统一公式引擎 |
| `engine/primitives/ca.py` | CA 原语（支持 4973+ 配方） |
| `engine/primitives/particle.py` | 粒子系统原语 |
| `engine/primitives/fluid.py` | 流体模拟原语 |
| `tools/effect_editor_v2.py` | 效果编辑器 v2（含效果市场） |
| `templates/demo_crystal_frame0.png` ~ `frame2.png` | 示范效果渲染预览图 |
| `templates/effect.json.tmpl` | 全新效果 JSON 模板 |
| `templates/effect_class.py.tmpl` | Python 类骨架模板 |
| `templates/effect_variant.json.tmpl` | 参数化变体 JSON 模板 |

---

## 十四、性能优化

### 14.1 CA 演化性能

| 优化方法 | 性能提升 | 说明 |
|---------|---------|------|
| NumPy 向量化 | 5-10x | 用 `np.roll` 计算邻域和，替代 SciPy `convolve` |
| Numba JIT 编译 | 10-100x | 使用 `@njit` 编译 CA 演化核函数 |
| 外置配方加载 | - | 从 4973+ 个 JSON 动态加载，取代硬编码 |

### 14.2 公式求值性能

| 优化方法 | 性能提升 | 说明 |
|---------|---------|------|
| asteval 缓存 | 2-5x | 编译后的公式对象缓存，避免重复解析 |
| NumPy 向量化 | 5-10x | 批量计算，避免 Python 循环 |

---

## 十五、依赖

- Python 3.10+
- Pillow（PIL）
- pygame-ce（音频播放，可选 — 无 pygame 时自动跳过音乐功能）
- NumPy（FFT 辅助 + 向量化计算）
- Numba（JIT 编译，可选 — 无 numba 时自动回退到纯 NumPy）
- tkinter（效果编辑器 GUI，Python 内置）

```bash
pip install -r requirements.txt
```

---

## 十六、效果市场（创意工坊）

效果市场是一个本地效果配置管理系统，功能类似创意工坊：

### 16.1 功能

- **浏览**：查看所有可用效果配置
- **导入**：从 JSON 文件导入效果配置
- **导出**：将效果配置导出为 JSON 文件
- **加载**：将效果加载到编辑器进行修改
- **删除**：删除效果配置

### 16.2 文件格式

效果配置文件为 JSON 格式，与 `effects/` 目录下的文件格式相同。

### 16.3 使用流程

```
1. 启动效果编辑器：python tools/effect_editor_v2.py
2. 点击"效果市场"标签
3. 浏览、导入、导出、删除效果
4. 双击效果可加载到编辑器进行修改
```

---

## 十七、常见问题

### 17.1 CA 演化性能问题

**问题**：CA 演化太慢，帧率下降。

**解决方案**：
1. 确保安装了 Numba：`pip install numba`
2. 在效果 JSON 中设置 `"use_jit": true`
3. 减小网格尺寸（`width` 和 `height`）

### 17.2 公式求值错误

**问题**：公式求值失败，效果不显示。

**解决方案**：
1. 检查公式语法（参考 asteval 文档）
2. 确保使用了正确的变量名（`t`, `audio.spectrum`, `audio.energy` 等）
3. 查看控制台错误信息

### 17.3 效果编辑器无法启动

**问题**：效果编辑器启动失败。

**解决方案**：
1. 确保 Python 内置了 tkinter（通常默认安装）
2. 检查是否安装了所有依赖：`pip install -r requirements.txt`
3. 查看控制台错误信息

---

## 十八、贡献指南

欢迎贡献新效果、新原语、新配方！

### 18.1 贡献新效果

1. 使用 `new_effect.py` 创建新效果骨架
2. 实现 `draw()` 方法
3. 测试效果
4. 提交 Pull Request

### 18.2 贡献新原语

1. 在 `engine/primitives/` 下创建新原语文件
2. 实现原语类
3. 添加文档和示例
4. 提交 Pull Request

### 18.3 贡献 CA 配方

1. 在 draw 的 `effects/` 目录下创建新配方 JSON
2. 确保配方格式正确
3. 提交 Pull Request 到 draw 项目

---

## 十九、许可证

[MIT License](LICENSE)

---

## 二十、致谢

- draw 项目（数学公式引擎和 CA 配方）
- pygame-ce（音频播放）
- NumPy（向量化计算）
- Numba（JIT 编译）
- asteval（安全公式求值）
