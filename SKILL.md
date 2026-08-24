---
name: pywallpaper
description: Maintain pywallpaper the media engine (G:/media/pywallpaper). ECS audio-visual wallpaper with formula engine, CA recipes and three-things CLI.
agent_created: true
---

# pywallpaper（媒体引擎本体）维护

## 概述
ECS 架构音频可视化动态壁纸 = 事实上的统一媒体引擎：JSON 内容层（4706 效果）与逻辑解耦 + 装饰器自动发现注册 + 公式引擎 + CA(4973 配方) + 粒子/流体。media_engine 的 47/48 效果已迁入本项目（2026-08-21）。

## 结构
- main.pyw：入口（--auto-start/--status/--silent + 三件事 CLI）
- ecs.py：自有 ECS（与 alloy 并存——引擎整合规划 S1 待收敛）
- engine/formula_engine.py + primitives/：公式与效果原语
- systems/render_system.py：EFFECT_REGISTRY + load_effects + 主题
- effects/：JSON 内容层；recipes/：CA 配方库
- core/context.py + core/world_log.py：内联自 alloy（三件事，2026-08-24）

## 常用命令
- python main.pyw --dump-profile / --dump-log
- python test_three_things.py（3/3）；python test_engine.py（需 PYTHONIOENCODING=utf-8，GBK 控制台 ✗ 会崩）

## 已知陷阱
- WorldLog 是 alloy 原版签名：append(type, payload_dict)，不支持 **kwargs
- 壁纸设置类功能请谨慎运行（会改系统壁纸）
