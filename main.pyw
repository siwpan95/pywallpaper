"""
Blur — Windows 动态音频可视化壁纸
ECS 架构: py负责逻辑 + json负责内容
入口: python main.py [--auto-start|--remove-auto-start|--status|--silent]
启动后自动最小化到系统托盘，右键托盘图标可控制（静音/暂停/退出等）
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

    # ── 运行级任务日志（日志即事实源，<项目>/data/logs/wallpaper.log） ──
    from core.context import Context
    from core.world_log import WorldLog
    ctx = Context()
    log = WorldLog()
    ctx.provide("log", log)
    _run_id = WorldLog.new_run_id()
    log.append("run_start", {"run_id": _run_id, "mode": ("silent" if '--silent' in args else "normal")})

    silent = '--silent' in args

    # 创建渲染器（自动检测屏幕分辨率）
    from systems.wallpaper_system import WallpaperRenderer
    renderer = WallpaperRenderer()

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
        print()

    # 运行
    try:
        renderer.run()
    finally:
        log.append("run_end", {"run_id": _run_id, "ok": True})
        try:
            log.save_to(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "data", "logs", "wallpaper.log"))
        except OSError:
            pass  # 日志落盘失败不阻断退出


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
    print("  services: log(WorldLog) + effects 注册表（EFFECT_REGISTRY）")


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
