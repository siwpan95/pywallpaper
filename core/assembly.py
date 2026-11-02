"""
装配层 — 把壁纸引擎的各子系统抽象为可注册插件
==============================================

[2026-11-02 接线改造：media_engine 阶段 B]

把 `core/context.py` 的可逆装配内核真正接到生产路径上：
main.pyw 不再裸装 AudioSimulator / EffectManager / WallpaperRenderer，
而是通过插件装配到 Context —— 每个子系统都是「有名字、有依赖声明、有 disposer」
的插件，可独立启停、可被审计。

分层::

    core/context.py    可逆装配内核（服务 + 事件总线 + 副作用栈）
    core/assembly.py   本文件：壁纸引擎的插件定义与装配工厂
    core/world_log.py  日志即事实源（WorldLog）
    systems/*.py       各子系统实现（被包装成插件）

事件约定（全部经 Context.emit 派发，跨线程安全）::

    effect:switching   效果开始过渡   (prev_name, next_name)
    effect:switched    效果切换完成   (name)
    effect:requested   请求切换下一个效果 (无参)
    render:frame       每帧渲染完成   (frame_index)
    render:resized     渲染分辨率变化 (width, height)
    audio:muted        静音状态变化   (muted: bool)
    render:paused      暂停状态变化   (paused: bool)
    app:quit           请求退出程序   (无参)

纯标准库 + 项目内模块，零新增第三方依赖。
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from core.context import Context, PluginHandle
from core.world_log import WorldLog

__all__ = [
    "EVENTS",
    "build_context",
    "install_logging",
    "install_config",
    "install_audio",
    "install_effect_manager",
    "install_renderer",
    "install_tray",
    "install_hot_reload",
    "install_world_log_bridge",
]


class EVENTS:
    """事件名常量集中定义 —— 避免字符串散落各处。"""

    EFFECT_SWITCHING = "effect:switching"
    EFFECT_SWITCHED = "effect:switched"
    EFFECT_REQUESTED = "effect:requested"
    RENDER_FRAME = "render:frame"
    RENDER_RESIZED = "render:resized"
    AUDIO_MUTED = "audio:muted"
    RENDER_PAUSED = "render:paused"
    APP_QUIT = "app:quit"
    # 效果热插拔 / HMR
    EFFECT_RELOADED = "effect:reloaded"
    EFFECT_HOTPLUG_ADDED = "effect:hotplug_added"
    EFFECT_HOTPLUG_REMOVED = "effect:hotplug_removed"
    EFFECT_THEMES_RELOADED = "effect:themes_reloaded"
    EFFECT_RELOAD_REQUESTED = "effect:reload_requested"


# ── 各子系统插件 ──────────────────────────────────────


def install_logging(ctx: Context, *, silent: bool = False) -> PluginHandle:
    """装配 WorldLog —— 日志即事实源。

    提供 "log" 服务；退出时落盘到 data/logs/wallpaper.log。
    """
    log = WorldLog()
    run_id = WorldLog.new_run_id()

    def _save() -> None:
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "data", "logs", "wallpaper.log")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            log.save_to(path)
        except OSError:
            pass  # 日志落盘失败不阻断退出

    ctx.provide("log", log, dispose=_save)
    ctx.provide("run_id", run_id)
    log.append("run_start", {"run_id": run_id, "mode": ("silent" if silent else "normal")})
    return ctx.install(lambda c, cfg: (lambda: log.append("run_end", {"run_id": run_id, "ok": True})),
                       {"name": "run_end_marker"})


def install_config(ctx: Context) -> PluginHandle:
    """装配全局配置 —— 提供 "config" 服务。"""
    from data_loader import get_config
    config = get_config()
    ctx.provide("config", config)
    return ctx.install(lambda c, cfg: None, {"name": "config_provider"})


def install_audio(ctx: Context) -> PluginHandle:
    """装配音频系统 —— 提供 "audio"（AudioSimulator）服务。

    依赖 "config"（音频参数）。
    """
    config = ctx.get("config")

    class AudioPlugin:
        name = "audio"
        inject = ["config"]

        def apply(self, c, cfg):
            from systems.audio_system import AudioSimulator, MusicPlaybackSystem
            audio = AudioSimulator()
            c.provide("audio", audio)

            music = MusicPlaybackSystem(audio)
            c.provide("music", music)

            def _dispose() -> None:
                try:
                    music.shutdown()
                except Exception:
                    pass

            return _dispose

    return ctx.install(AudioPlugin(), {})


def install_effect_manager(ctx: Context) -> PluginHandle:
    """装配效果管理器 —— 提供 "effect_manager" 服务，并把切换过程事件化。"""

    class EffectManagerPlugin:
        name = "effect_manager"
        inject = ["config"]

        def apply(self, c, cfg):
            from systems.render_system import EFFECT_REGISTRY
            from systems.effect_manager import EffectManager
            config = c.get("config")
            manager = EffectManager(EFFECT_REGISTRY, config, ctx=c)
            c.provide("effect_manager", manager)

            # 切换请求 → 执行切换（托盘线程 emit，主循环或托盘线程均可触发）
            def _on_requested(*_args):
                if manager.is_transitioning:
                    return
                manager._start_transition()

            c.on(EVENTS.EFFECT_REQUESTED, _on_requested)
            return None

    return ctx.install(EffectManagerPlugin(), {})


def install_renderer(ctx: Context, *, width: Optional[int] = None,
                     height: Optional[int] = None) -> PluginHandle:
    """装配渲染器 —— 提供 "renderer" 服务。

    依赖 "config" / "audio" / "effect_manager"。
    """

    class RendererPlugin:
        name = "renderer"
        inject = ["config", "audio", "effect_manager"]

        def apply(self, c, cfg):
            from systems.wallpaper_system import WallpaperRenderer
            config = c.get("config")
            renderer = WallpaperRenderer(
                width=width or config["wallpaper"]["default_width"],
                height=height or config["wallpaper"]["default_height"],
                ctx=c,
            )
            c.provide("renderer", renderer)

            # 托盘的静音/暂停动作在此执行，并发布状态变化事件供日志与订阅者感知
            def _on_mute(*_args):
                renderer.set_muted(not renderer.muted)
                c.emit(EVENTS.AUDIO_MUTED, renderer.muted)

            def _on_pause(*_args):
                renderer.set_paused(not renderer.paused)
                c.emit(EVENTS.RENDER_PAUSED, renderer.paused)

            c.on("tray:mute", _on_mute)
            c.on("tray:pause", _on_pause)

            # 退出请求 → 停止渲染循环
            c.on(EVENTS.APP_QUIT, lambda *_: setattr(renderer, "running", False))

            def _dispose() -> None:
                try:
                    renderer.shutdown()
                except Exception:
                    pass

            return _dispose

    return ctx.install(RendererPlugin(), {})


def install_tray(ctx: Context) -> PluginHandle:
    """装配系统托盘 —— 事件驱动的菜单回调。

    依赖 "renderer"。托盘在独立线程运行，通过 Context.emit 与主线程通信
    （Context 的锁保证跨线程安全）。
    """

    class TrayPlugin:
        name = "tray"
        inject = ["renderer"]

        def apply(self, c, cfg):
            from systems.tray_system import SystemTrayManager
            renderer = c.get("renderer")
            tray = SystemTrayManager(renderer, ctx=c)
            c.provide("tray", tray)

            # 托盘菜单 → 事件。
            # 静音/暂停的实际执行由 renderer 插件订阅 tray:mute / tray:pause 完成，
            # 此处只转发渲染器不关心的两个动作。
            c.on("tray:next", lambda *_: c.emit(EVENTS.EFFECT_REQUESTED))
            c.on("tray:quit", lambda *_: c.emit(EVENTS.APP_QUIT))

            return None

    return ctx.install(TrayPlugin(), {})


def install_hot_reload(ctx: Context, *, watch: bool = True,
                       interval: float = 1.0) -> PluginHandle:
    """装配效果热重载器 —— 提供 "hot_reloader" 服务（core/hot_reload.py）。

    依赖 "config" / "effect_manager" / "renderer"。
    监听线程在 apply 中启动（daemon），dispose 时停止；注册表变更只在主渲染
    线程通过 consume_pending() 落地，跨线程安全。
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    effects_dir = os.path.join(project_root, "effects")

    class HotReloadPlugin:
        name = "hot_reloader"
        inject = ["effect_manager", "renderer"]

        def apply(self, c, cfg):
            from core.hot_reload import HotReloader
            reloader = HotReloader(c, effects_dir, interval=interval, enabled=watch)
            reloader.start()
            c.provide("hot_reloader", reloader)

            # 托盘/外部请求手动全量重载（只入队，由主循环落地）
            def _on_reload_requested(*_args):
                try:
                    reloader.force_rescan()
                except Exception as e:
                    print(f"[HMR] 手动重载请求失败: {e}")

            c.on(EVENTS.EFFECT_RELOAD_REQUESTED, _on_reload_requested)

            def _dispose() -> None:
                reloader.stop()

            return _dispose

    return ctx.install(HotReloadPlugin(), {})


def install_world_log_bridge(ctx: Context, event_types: Optional[List[str]] = None) -> PluginHandle:
    """把 Context 事件桥接进 WorldLog —— 世界事实自动入日志。

    依赖 "log"。返回的插件句柄 dispose 时取消桥接。
    """
    log = ctx.get("log")
    types = event_types if event_types is not None else [
        EVENTS.EFFECT_SWITCHING,
        EVENTS.EFFECT_SWITCHED,
        EVENTS.EFFECT_RELOADED,
        EVENTS.EFFECT_HOTPLUG_ADDED,
        EVENTS.EFFECT_HOTPLUG_REMOVED,
        EVENTS.EFFECT_THEMES_RELOADED,
        EVENTS.RENDER_RESIZED,
        EVENTS.AUDIO_MUTED,
        EVENTS.RENDER_PAUSED,
        EVENTS.APP_QUIT,
    ]
    dispose = log.track(ctx, types)
    return ctx.install(lambda c, cfg: dispose, {"name": "world_log_bridge"})


# ── 装配工厂 ──────────────────────────────────────────


def build_context(*, silent: bool = False, with_tray: bool = True,
                  with_hot_reload: bool = False,
                  width: Optional[int] = None,
                  height: Optional[int] = None) -> Context:
    """装配完整 Context —— 生产路径的统一入口。

    装配顺序即依赖顺序：
        config → audio → effect_manager → renderer → tray → hot_reloader
        log 先行（WorldLog 是事实源），事件桥最后挂上。

    返回的 Context 已完成全部插件安装，可直接 .get("renderer") 取用。

    with_hot_reload: 开启 effects/ 目录文件监听，支持运行时热插拔/HMR。
    """
    ctx = Context()

    install_logging(ctx, silent=silent)
    install_config(ctx)
    install_audio(ctx)
    install_effect_manager(ctx)
    install_renderer(ctx, width=width, height=height)
    if with_tray:
        install_tray(ctx)
    if with_hot_reload:
        install_hot_reload(ctx, watch=True)
    install_world_log_bridge(ctx)

    return ctx
