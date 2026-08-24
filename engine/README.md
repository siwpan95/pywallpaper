# 渲染引擎 — 声明式壁纸效果系统

> 通过 JSON 组合绘制原语，实现零代码扩展。  
> 新增效果 = 创建 `effects/XXX_name.json`，不需要改任何 Python 代码。

---

## 快速开始

### 创建一个新效果（3 步）

**步骤 1**：在 `effects/` 目录创建 JSON 文件，如 `effects/150_my_effect.json`：

```json
{
  "id": "my_effect",
  "name": "我的效果",
  "full_name": "150. 我的效果",
  "category": "频谱",
  "background_theme": "渐变",
  "class": "EngineEffect",
  "params": {
    "layers": [
      {
        "type": "bars",
        "count": 32,
        "direction": "up",
        "position": {"x": 0, "y": "100%"},
        "size": {"width": "100%", "height": "70%"},
        "color": {"type": "hsv_flow", "hue": [0, 0.7], "speed": 0.1},
        "audio": {"source": "band_energy", "target": "height", "scale": [0.02, 1.0]}
      }
    ]
  }
}
```

**步骤 2**：启动程序，效果自动注册。

**步骤 3**：完成。无需编译、无需重启代码、无需 import。

---

## 架构

```
effects/*.json          ← 你只需要关心这里
      ↓
engine/effect_loader.py  →  自动扫描、注册
      ↓
engine/core.py           →  EngineEffect (效果容器)
      ↓
engine/primitives/       →  绘制原语 (可组合的视觉块)
      ├── bars.py        频谱柱状图
      ├── spikes.py      径向尖峰
      ├── waveform.py    波形曲线
      ├── vortex.py      漩涡粒子
      ├── circle_map.py  圆形映射
      ├── particles.py   粒子系统
      ├── grid.py        2D 网格
      ├── drawing.py     自由绘制命令
      └── text_rain.py   文字雨
engine/color_system.py    →  颜色生成器
engine/audio_map.py       →  音频→视觉映射
```

---

## 绘制原语参考

### 1. bars — 频谱柱状图

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"bars"` |
| `count` | int | 64 | 柱数 |
| `direction` | string | `"up"` | `up`/`down`/`left`/`right`/`center_h`/`center_v` |
| `gap` | int | 2 | 柱间距 |
| `round_caps` | bool | false | 圆角 |

**音频目标**: `height` (竖直方向) / `width` (水平方向)

---

### 2. spikes — 径向尖峰

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"spikes"` |
| `count` | int | 64 | 尖峰数 |
| `inner_radius` | float | 30 | 内半径 |
| `outer_radius` | float | 300 | 最大外半径 |
| `line_width` | int | 3 | 线宽 |
| `rotation_speed` | float | 0 | 自转速度 |

**音频目标**: `length`

---

### 3. waveform — 波形曲线

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"waveform"` |
| `lines` | int | 2 | 曲线数量 |
| `points` | int | 200 | 每线点数 |
| `amplitude` | float | 150 | 振幅 |
| `frequency` | float | 0.05 | 空间频率 |
| `line_width` | int | 2 | 线宽 |

**音频目标**: `y`

---

### 4. vortex — 漩涡粒子

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"vortex"` |
| `count` | int | 150 | 粒子数 |
| `radius.min` | float | 50 | 最小半径 |
| `radius.step` | float | 5 | 半径步进 |
| `twist` | float | 1.0 | 扭曲度 |
| `speed` | float | 1.0 | 旋转速度 |
| `element_size` | float | 3 | 粒子大小 |
| `size_scale` | float | 5.0 | 音频缩放 |

**音频目标**: `radius_scale`

---

### 5. circle_map — 圆形映射

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"circle_map"` |
| `rings` | array | - | 环配置数组 |
| `rings[].count` | int | 72 | 每环元素数 |
| `rings[].radius` | float | - | 半径 |
| `rings[].line` | bool | false | 连线模式 |
| `rings[].line_width` | int | 2 | 线宽 |
| `element_size` | float | 4 | 元素大小 |
| `rotation_speed` | float | 0 | 旋转速度 |

**音频目标**: `radius_offset`

---

### 6. particles — 粒子系统

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"particles"` |
| `count` | int | 100 | 粒子数 |
| `particle.behavior` | string | `"drift"` | `drift`/`orbit`/`fall`/`rise`/`bounce` |
| `particle.size` | `{min,max}` | 2~6 | 大小范围 |
| `particle.speed` | `{min,max}` | 10~50 | 速度范围 |
| `particle.lifetime` | `{min,max}` | 2~5 | 生命周期 |
| `connect.enabled` | bool | false | 连线 |
| `connect.max_distance` | float | 100 | 连线距离 |

**音频目标**: `particle_size`

---

### 7. grid — 2D 网格

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"grid"` |
| `cols` | int | 20 | 列数 |
| `rows` | int | 10 | 行数 |
| `element` | string | `"rect"` | `circle`/`rect` |
| `element_ratio` | float | 0.8 | 占格比例 |

**音频目标**: `scale`

---

### 8. drawing — 自由绘制

最灵活的原语。通过命令序列实现任意绘制。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"drawing"` |
| `commands` | array | - | 绘制命令列表 |

**支持的命令**：`circle(x, y, radius)`, `rect(x1, y1, x2, y2)`, `line(x1, y1, x2, y2)`, `polygon(points)`, `ellipse(x1, y1, x2, y2)`, `arc(x, y, radius, start, end)`

每个值可以是固定数值，也可以是音频映射：
```json
{"shape": "circle", "radius": {"audio": "rms", "scale": [10, 100]}}
```

---

### 9. text_rain — 文字雨

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | string | - | `"text_rain"` |
| `chars` | string | - | 字符集 |
| `count` | int | 60 | 列数 |
| `font_size` | int | 16 | 字号 |
| `speed.min/max` | float | 50~150 | 速度 |
| `trail_length` | int | 10 | 拖尾长度 |

**音频目标**: `brightness`

---

## 通用配置

### 位置 (`position`)
```json
{"x": "50%", "y": 0}       // 百分比或像素
{"x": "center", "y": 100}  // 特殊值 center
```

### 尺寸 (`size`)
```json
{"width": "100%", "height": "70%"}  // 百分比
{"width": 300, "height": 200}       // 像素
```

### 中心点 (`center`)
```json
{"x": "50%", "y": "50%"}   // 覆盖默认中心
```

### 颜色系统 (`color`)

| 类型 | 配置 | 说明 |
|------|------|------|
| `hsv_flow` | `hue:[0,0.7], speed:0.1, sat:0.8, val:0.9` | 流动渐变 |
| `rainbow` | `speed:0.05, sat:0.8, val:0.9` | 彩虹循环 |
| `energy` | `hue_offset:0.3` | 能量映射 |
| `solid` | `value:[255,40,40]` | 固定颜色 |

### 音频映射 (`audio`)
```json
{
  "source": "band_energy",   // band_energy / full_spectrum / rms / beat
  "target": "height",        // 目标视觉属性
  "scale": [0.0, 1.0],       // 输出范围
  "smoothing": 0.85          // 平滑系数
}
```

### 多层组合
一个效果可以有多个图层，每个图层使用不同原语：
```json
{
  "layers": [
    {"type": "bars", ...},      // 底层：柱状图
    {"type": "spikes", ...},    // 顶层：尖峰
  ]
}
```

---

## 效果编号约定

- `01~131`: 旧版 Python 类效果（向后兼容，仍可使用）
- `132~199`: 引擎效果（纯 JSON，class: "EngineEffect"）
- `200+`: 预留扩展

---

## 添加新效果 = 三步

1. 复制任意 `132_*.json` 作为模板
2. 修改 `id`、`name`、`full_name`、`layers`
3. 保存，启动程序

**零代码、零编译、零重启。**
