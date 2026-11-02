---
name: pywallpaper
description: Maintain pywallpaper the media engine (本 SKILL.md 所在仓库根). ECS audio-visual wallpaper with formula engine, CA recipes and three-things CLI.
agent_created: true
---

# pywallpaper（媒体引擎本体）维护

## 概述
ECS 架构音频可视化动态壁纸 = 事实上的统一媒体引擎：JSON 内容层（4706 效果）与逻辑解耦 + 装饰器自动发现注册 + 公式引擎 + CA(4973 配方) + 粒子/流体。media_engine 的 47/48 效果已迁入本项目（2026-08-21）。

## 结构
- main.pyw：入口（--auto-start/--status/--silent + 三件事 CLI）→ **经 core/assembly.py 装配到 Context**
- core/context.py：可逆装配内核（服务注册表 + 事件总线 + 副作用栈，Cordis 语义）
- core/assembly.py：装配层（各子系统作为插件：name/inject/apply）
- core/hot_reload.py：效果 JSON + 原语类热插拔/HMR（监听线程只扫描入队，主线程每帧 consume_pending 落地，零锁）
- core/world_log.py：WorldLog 日志即事实源（可 track 事件总线自动入账）
- ecs.py：自有 ECS（与 alloy 并存——引擎整合规划 S1 待收敛）
- engine/formula_engine.py + primitives/：公式与效果原语
- systems/render_system.py：EFFECT_REGISTRY + load_effects + 主题
- effects/：JSON 内容层；recipes/：CA 配方库

## 常用命令
- python main.pyw --dump-profile / --dump-log
- python main.pyw --no-hot-reload（关闭效果热插拔监听）
- python test_three_things.py（23/23）；python test_engine.py（需 PYTHONIOENCODING=utf-8，GBK 控制台 ✗ 会崩）
- 验收解释器固定用 `D:\Python314\python.exe`（Python 3.14.7 + pygame-ce 2.5.8 + numba 0.68.1）；WorkBuddy 自带的 python 3.13 环境**不能**作为验收依据
- python selfcheck.py（无头自检）

## 装配约定（2026-11-02 接线改造）
- 新增子系统 → 在 core/assembly.py 写 install_xxx(ctx) 插件，用 inject 声明依赖
- 跨模块通信 → 走 ctx.emit / ctx.on，不要直连对象
- 托盘线程与主线程 → 一律经 Context 事件，勿跨线程直改渲染器状态
- 退出回滚 → ctx.dispose() 逆序回滚，新增插件必须提供 disposer
- 效果热插拔 → `core/hot_reload.py` 的 HotReloader：**监听线程只扫描入队，注册表只在主线程 consume_pending 落地（零锁）**；改 effects/*.json 即热替换，无需重启
- 原语热重载 → HotReloader **同时监听 engine/primitives/*.py**：源文件变更经 importlib.reload 重执行，@register_primitive 自动把新类写回中央 PRIMITIVE_REGISTRY；EngineEffect 每帧按 type 实时查表取类，下一帧即生效。依赖感知拓扑 reload（ca→ca_kernel），失败隔离不污染注册表
- 事件约定：effect:* / primitive:* 两组（详见 README 事件表）

## 已知陷阱
- WorldLog 是 alloy 原版签名：append(type, payload_dict)，不支持 **kwargs
- 壁纸设置类功能请谨慎运行（会改系统壁纸）
- Context 类插件走 __init__(ctx, config)，**不调用 apply**；要 apply 就用对象插件
- 官方 Cordis 是 TypeScript 且 API 未稳定，本项目用自建内核，不引外部 cordis 依赖
- 热插拔覆盖 effects/*.json（数据层）与 engine/primitives/*.py（原语类）；原语类是可靠热重载（注册表即重绑点），非「本期不做」
- 测试套件每次 build_context 会生成约 21s 音乐 WAV，整体偏慢（与 HMR 无关）；HMR 用例已用极简 Context 避开
