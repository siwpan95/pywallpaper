"""
Blur — Windows 动态音频可视化壁纸
ECS 架构: py负责逻辑 + json负责内容
入口: python main.py [--auto-start|--remove-auto-start|--status|--silent]
启动后自动最小化到系统托盘，右键托盘图标可控制（静音/暂停/退出等）

[2026-11-02 接线改造：走 Context 装配]
主路径不再裸装各子系统，而是经 core/assembly.py 以插件形式装配到 Context：
每个子系统都有名字、依赖声明与 disposer，退出时按逆序完整回滚。
"""
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(__file__))


def main():
    """主入口 - 组装各系统并启动渲染循环"""
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    # 处理命令行参数
    from systems.wallpaper_system import toggle_auto_start, is_auto_start_enabled

    if '--auto-start' in args:
        toggle_auto_start(True)
        return
    elif '--remove-auto-start' in args:
        toggle_auto_start(False)
        return
    elif '--status' in args:
        status = "已开启" if is_auto_start_enabled() else "未开启"
        print(f"开机自启动: {status}")
        return

    # ── 三件事 CLI（media_engine 阶段 A，纯加法）：装配自省 + 任务日志审计 ──
    if '--dump-profile' in args:
        _dump_profile()
        return
    if '--dump-log' in args:
        idx = args.index('--dump-log')
        path = args[idx + 1] if idx + 1 < len(args) else None
        _dump_log(path)
        return

    silent = '--silent' in args
    # 效果热插拔/HMR：GUI 模式默认开启，可用 --no-hot-reload 关闭
    with_hot_reload = '--no-hot-reload' not in args

    # ── 装配（Context 可逆装配内核） ──
    from core.assembly import build_context

    ctx = build_context(silent=silent, with_hot_reload=with_hot_reload)
    renderer = ctx.get("renderer")

    # 检测屏幕分辨率
    width, height = renderer.get_screen_resolution()
    renderer.width = width
    renderer.height = height
    renderer.render_width = int(width * renderer.resolution_scale)
    renderer.render_height = int(height * renderer.resolution_scale)

    if not silent:
        print("\n提示: 使用以下命令管理开机自启动:")
        print("  --auto-start         开启开机自启动")
        print("  --remove-auto-start  关闭开机自启动")
        print("  --status             查看当前状态")
        print("  --silent             静默模式启动")
        print("  --no-hot-reload     关闭效果热插拔/HMR（默认开启，监听 effects/ 变化）")
        print()

    # 运行
    try:
        renderer.run()
    finally:
        # 逆序回滚：托盘 → 渲染器 → 效果管理 → 音频 → 配置 → 日志落盘
        ctx.dispose()


def _dump_profile() -> None:
    """装配自省：效果/主题/原语/服务清单（agent 审计入口）。"""
    root = os.path.dirname(os.path.abspath(__file__))
    print("pywallpaper 装配自省（media_engine 阶段 A）")
    try:
        from systems.render_system import EFFECT_REGISTRY, load_effects
        load_effects()
        print(f"  effects: {len(EFFECT_REGISTRY)}（effects/*.json 内容层）")
    except Exception as exc:
        print(f"  effects: 加载失败 {exc}")
    try:
        import glob
        prims = glob.glob(os.path.join(root, "engine", "primitives", "*.py"))
        prims = [os.path.basename(p)[:-3] for p in prims if not os.path.basename(p).startswith("_")]
        print(f"  primitives: {len(prims)}（{', '.join(sorted(prims))}）")
    except Exception as exc:
        print(f"  primitives: 读取失败 {exc}")
    try:
        import importlib.util
        mods = {}
        for m in ("numpy", "pygame", "numba", "scipy", "sounddevice"):
            mods[m] = importlib.util.find_spec(m) is not None
        for k, v in mods.items():
            print(f"    {k}={'OK' if v else '缺失'}")
    except Exception:
        pass

    # ── 真实 Context 注册表快照（装配层实际状态，非硬编码描述） ──
    _dump_context_snapshot()


def _dump_context_snapshot() -> None:
    """装配 Context 并输出真实快照：服务、插件、事件订阅。

    与硬编码描述不同 —— 这里反映的是 core/assembly.py 实际装配出的运行时状态。
    """
    print("  --- Context 装配快照 ---")
    try:
        from core.assembly import build_context
        ctx = build_context(silent=True, with_tray=False)
    except Exception as exc:
        print(f"  context: 装配失败 {type(exc).__name__}: {exc}")
        return

    try:
        snap = ctx.snapshot()
        print(f"  services ({len(snap['services'])}): {', '.join(snap['services'])}")
        print(f"  entries: {snap['entries']}  children: {snap['children']}")
        if snap['events']:
            ev = ", ".join(f"{e}×{n}" for e, n in snap['events'].items())
            print(f"  events ({snap['total_listeners']} 订阅): {ev}")
        else:
            print("  events: 无订阅")

        # 各服务的真实类型
        for key in ("config", "log", "audio", "music", "effect_manager", "renderer"):
            try:
                svc = ctx.get(key)
                print(f"    {key}: {type(svc).__name__}")
            except Exception:
                pass

        # 效果管理器实际装载的效果数
        try:
            em = ctx.get("effect_manager")
            print(f"  effect_manager: {len(em.effect_names)} 个效果, 当前 {em.current_name}")
        except Exception as exc:
            print(f"  effect_manager: 读取失败 {exc}")
    finally:
        ctx.dispose()


def _dump_log(path: str | None) -> None:
    """任务日志审计：默认 data/logs/wallpaper.log。"""
    from core.world_log import WorldLog
    root = os.path.dirname(os.path.abspath(__file__))
    log_path = path or os.path.join(root, "data", "logs", "wallpaper.log")
    if not os.path.isfile(log_path):
        print(f"[dump-log] 无日志: {log_path}")
        return
    log = WorldLog.load_from(log_path)
    entries = log.entries()
    print(f"任务日志 {log_path}（{len(entries)} 条）：")
    for e in entries[-20:]:
        print(f"  #{e['seq']} {e.get('ts', '?')} [{e['type']}] {e.get('run_id', '')} {e.get('payload', '')}")


if __name__ == "__main__":
    main()
