# -*- coding: utf-8 -*-
"""
test_three_things.py —— media_engine 阶段 A 冒烟（Context / WorldLog / dump CLI）
[2026-11-02 接线改造：新增事件总线 / 插件生命周期 / 装配快照 用例]

运行：python test_three_things.py（脚本式，与 test_engine.py 同风格）
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_context():
    from core.context import Context
    ctx = Context()
    order = []
    ctx.provide("svc", 1, dispose=lambda: order.append("undone"))
    ctx.effect(lambda: order.append("effect"))
    assert ctx.get("svc") == 1
    ctx.dispose()
    assert order == ["effect", "undone"]
    print("[OK] Context 注册即回滚")


def test_worldlog():
    from core.world_log import WorldLog
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "log.json")
        log = WorldLog()
        log.append("run_start", {"run_id": "r1", "mode": "normal"})
        log.append("run_end", {"run_id": "r1", "ok": True})
        log.save_to(p)
        loaded = WorldLog.load_from(p)
        assert loaded.seq == 2
        assert loaded.entries()[0]["type"] == "run_start"
    print("[OK] WorldLog 持久化往返")


def test_dump_profile():
    import subprocess
    root = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(root, "main.pyw"), "--dump-profile"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore",
                       cwd=root, timeout=180)
    assert r.returncode == 0, r.stderr[-800:]
    assert "effects:" in r.stdout and "primitives:" in r.stdout
    print("[OK] --dump-profile 自省")


# ── 接线改造新增用例 ──────────────────────────────────


def test_event_bus():
    """事件总线：emit 派发、once 一次性、处理器异常不中断其他处理器。"""
    from core.context import Context

    ctx = Context()
    got = []
    ctx.on("tick", lambda v: got.append(v))
    ctx.emit("tick", 1)
    ctx.emit("tick", 2)
    assert got == [1, 2], got

    # once：只触发一次
    once_got = []
    ctx.once("one", lambda: once_got.append(1))
    ctx.emit("one")
    ctx.emit("one")
    assert once_got == [1], once_got

    # 处理器异常不中断其他处理器
    after = []

    def boom(_v):
        raise ValueError("boom")

    ctx.on("boom", boom)
    ctx.on("boom", lambda v: after.append(v))
    ctx.emit("boom", 42)
    assert after == [42], after

    # 退订
    unsub = ctx.on("temp", lambda: None)
    unsub()
    assert ctx.listener_count("temp") == 0, ctx.listener_count("temp")

    ctx.dispose()
    print("[OK] 事件总线：emit / once / 异常容错 / 退订")


def test_plugin_lifecycle():
    """插件生命周期：三形态安装、inject 校验、独立卸载不误伤他人。"""
    from core.context import Context, PluginHandle, MissingDependencyError

    ctx = Context()

    # 三种插件形态
    def fn_plugin(c, cfg):
        c.on("x", lambda: None)
        return lambda: None

    class ObjPlugin:
        name = "obj_plugin"
        inject = []

        def apply(self, c, cfg):
            return None

    class ClassPlugin:
        def __init__(self, c, cfg):
            self.ctx = c

    h1 = ctx.install(fn_plugin, {})
    h2 = ctx.install(ObjPlugin(), {})
    h3 = ctx.install(ClassPlugin, {})
    assert all(isinstance(h, PluginHandle) for h in (h1, h2, h3))

    # inject 缺失 → 装配期报错
    class NeedsSvc:
        name = "needs"
        inject = ["absent_svc"]

        def apply(self, c, cfg):
            pass

    try:
        ctx.install(NeedsSvc(), {})
        raise AssertionError("inject 缺失应当报错")
    except MissingDependencyError:
        pass

    # 独立卸载不误伤他人
    reg = []

    def p1(c, cfg):
        c.provide("a", 1, dispose=lambda: reg.append("a-disposed"))
        c.on("evt", lambda: reg.append("p1-listener"))
        return lambda: reg.append("p1-done")

    def p2(c, cfg):
        c.provide("b", 2, dispose=lambda: reg.append("b-disposed"))
        c.on("evt", lambda: reg.append("p2-listener"))
        return lambda: reg.append("p2-done")

    hp1 = ctx.install(p1, {})
    ctx.install(p2, {})
    hp1.dispose()
    assert "a" not in ctx.keys(), ctx.keys()
    assert "b" in ctx.keys(), ctx.keys()
    ctx.emit("evt")
    assert "p1-listener" not in reg, reg
    assert "p2-listener" in reg, reg

    # 插件体失败不留半成品
    def bad(c, cfg):
        c.provide("leak", 1)
        raise RuntimeError("boom")

    try:
        ctx.install(bad, {})
    except RuntimeError:
        pass
    assert "leak" not in ctx.keys(), ctx.keys()

    ctx.dispose()
    print("[OK] 插件生命周期：三形态 / inject 校验 / 独立卸载 / 失败回滚")


def test_context_threadsafe():
    """线程安全：托盘线程与主线程并发 emit 不丢事件。"""
    import threading

    from core.context import Context

    ctx = Context()
    count = {"n": 0}
    lock = threading.Lock()

    def handler(_v):
        with lock:
            count["n"] += 1

    ctx.on("e", handler)

    def worker():
        for i in range(300):
            ctx.emit("e", i)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert count["n"] == 3000, count["n"]
    ctx.dispose()
    print("[OK] Context 线程安全：10 线程 × 300 次 emit 无丢失")


def test_world_log_bridge():
    """WorldLog.track 桥接到 Context 事件总线 —— 世界事实自动入日志。"""
    from core.context import Context
    from core.world_log import WorldLog

    ctx = Context()
    log = WorldLog()
    ctx.provide("log", log)
    dispose = log.track(ctx, ["effect:switched"])

    ctx.emit("effect:switched", "极光")
    ctx.emit("effect:switched", "星空")
    types = [e["type"] for e in log.entries()]
    assert types == ["effect:switched", "effect:switched"], types

    dispose()
    ctx.emit("effect:switched", "不应入日志")
    assert len(log.entries()) == 2, log.entries()

    ctx.dispose()
    print("[OK] WorldLog 事件桥：事件入日志 + 退订后不再记录")


def test_assembly_snapshot():
    """装配层：build_context 装出真实服务与事件订阅，snapshot 可自省。"""
    from core.assembly import build_context

    ctx = build_context(silent=True, with_tray=False)
    try:
        snap = ctx.snapshot()
        for key in ("config", "log", "audio", "effect_manager", "renderer"):
            assert key in snap["services"], snap["services"]
        assert snap["total_listeners"] > 0, snap
        # 效果管理器可读
        em = ctx.get("effect_manager")
        assert em.current_name
        # 事件可派发
        ctx.emit("effect:switched", em.current_name)
    finally:
        ctx.dispose()
    print("[OK] 装配层：build_context 装出真实服务 + 事件订阅")


def test_dump_profile_snapshot():
    """--dump-profile 输出真实 Context 注册表快照（非硬编码描述）。"""
    import subprocess
    root = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(root, "main.pyw"), "--dump-profile"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore",
                       cwd=root, timeout=180)
    assert r.returncode == 0, r.stderr[-800:]
    assert "Context 装配快照" in r.stdout, r.stdout[-800:]
    assert "services (" in r.stdout, r.stdout[-800:]
    assert "effect_manager:" in r.stdout, r.stdout[-800:]
    print("[OK] --dump-profile 输出真实装配快照")


def test_tray_event_driven():
    """托盘跨线程事件驱动：菜单动作 → 事件 → 状态变更 + 世界事实入账。"""
    import threading

    from core.assembly import EVENTS, build_context

    ctx = build_context(silent=True, with_tray=True)
    try:
        renderer = ctx.get("renderer")
        log = ctx.get("log")
        manager = ctx.get("effect_manager")

        # 静音：托盘线程 emit → 渲染器状态变更 → 事件入账
        assert renderer.muted is False
        t = threading.Thread(target=lambda: ctx.emit("tray:mute"))
        t.start()
        t.join()
        assert renderer.muted is True, renderer.muted
        assert log.entries()[-1]["type"] == EVENTS.AUDIO_MUTED, log.entries()[-1]

        # 取消静音
        t = threading.Thread(target=lambda: ctx.emit("tray:mute"))
        t.start()
        t.join()
        assert renderer.muted is False, renderer.muted

        # 暂停
        t = threading.Thread(target=lambda: ctx.emit("tray:pause"))
        t.start()
        t.join()
        assert renderer.paused is True, renderer.paused
        assert log.entries()[-1]["type"] == EVENTS.RENDER_PAUSED, log.entries()[-1]

        # 下一个效果
        t = threading.Thread(target=lambda: ctx.emit("tray:next"))
        t.start()
        t.join()
        assert manager.is_transitioning is True, "效果切换未触发"

        # 退出
        renderer.running = True
        t = threading.Thread(target=lambda: ctx.emit("tray:quit"))
        t.start()
        t.join()
        assert renderer.running is False, renderer.running
    finally:
        ctx.dispose()
    print("[OK] 托盘事件驱动：静音/暂停/切换/退出 跨线程全通")


def test_effect_switch_events():
    """效果切换事件链路：请求 → 过渡 → 完成，多载荷正确入账。"""
    from core.assembly import EVENTS, build_context

    ctx = build_context(silent=True, with_tray=False)
    try:
        manager = ctx.get("effect_manager")
        log = ctx.get("log")

        ctx.emit(EVENTS.EFFECT_REQUESTED)
        assert manager.is_transitioning is True, "切换未启动"

        # 推进到过渡结束
        manager.transition_start = 0.0
        manager.transition_duration = 0.001
        manager.update()

        types = [e["type"] for e in log.entries()]
        assert EVENTS.EFFECT_SWITCHING in types, types
        assert EVENTS.EFFECT_SWITCHED in types, types

        # 多载荷事件以列表入账
        switching = [e for e in log.entries() if e["type"] == EVENTS.EFFECT_SWITCHING][-1]
        assert isinstance(switching["payload"], list), switching
        assert len(switching["payload"]) == 2, switching
    finally:
        ctx.dispose()
    print("[OK] 效果切换事件：switching/switched 发布且多载荷入账")


def test_cross_thread_stress():
    """跨线程混合 emit 压力：渲染帧 + 效果切换事件并发无异常。"""
    import threading

    from core.assembly import build_context

    ctx = build_context(silent=True, with_tray=False)
    errs = []

    def worker(n):
        try:
            for i in range(80):
                ctx.emit("render:frame", n * 100 + i)
                ctx.emit("effect:switched", f"e{n}-{i}")
        except Exception as exc:
            errs.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errs, errs[:2]
    ctx.dispose()
    print("[OK] 跨线程压力：8 线程 × 160 次混合 emit 无异常")


# ── 效果热插拔 / HMR 用例 ─────────────────────────────


def _isolate_registry(ctx, em):
    """返回 (registry_snapshot, names_snapshot) 以便测试后恢复全局注册表。"""
    from systems.render_system import EFFECT_REGISTRY
    return dict(EFFECT_REGISTRY), list(em.effect_names)


def _restore_registry(snap, names_snap):
    from systems.render_system import EFFECT_REGISTRY
    EFFECT_REGISTRY.clear()
    EFFECT_REGISTRY.update(snap)
    # effect_names 由调用方在 ctx 外持有的 manager 上恢复


def _minimal_ctx():
    """仅装 config + effect_manager 的极简 Context（避开音频/音乐生成，提速）。

    热重载测试不需要渲染器/音频，reloader 对缺失的 renderer 取 None 即安全。
    """
    from core.context import Context
    from core.assembly import install_config, install_effect_manager

    ctx = Context()
    install_config(ctx)
    install_effect_manager(ctx)
    return ctx


def test_hot_reload_modify():
    """改一个效果 JSON → 注册表热更新，下一帧即生效（无需重启）。"""
    import json
    from core.assembly import EVENTS
    from core.hot_reload import HotReloader
    from systems.render_system import EFFECT_REGISTRY

    ctx = _minimal_ctx()
    em = ctx.get("effect_manager")
    reg_snap, names_snap = _isolate_registry(ctx, em)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "0001_hmr_test.json")
            name = "HMR_TEST_MODIFY"
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect",
                           "params": {"seed": 1}}, f)
            reloader = HotReloader(ctx, tmp, enabled=False)

            reloader._scan_initial()       # 基线（建立快照，不入队）
            assert reloader._queue.empty()

            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect",
                           "params": {"seed": 999}}, f)

            got = []
            unsub = ctx.on(EVENTS.EFFECT_RELOADED, lambda n, k: got.append((n, k)))
            try:
                reloader._scan_once()
                applied = reloader.consume_pending()
                assert applied == 1, applied
                assert EFFECT_REGISTRY.get(name) == (
                    {"full_name": name, "class": "EngineEffect",
                     "params": {"seed": 999}},), EFFECT_REGISTRY.get(name)
                assert got and got[0][0] == name, got
            finally:
                unsub()
    finally:
        _restore_registry(reg_snap, names_snap)
        em.effect_names = names_snap
        ctx.dispose()
    print("[OK] 热重载：修改效果 JSON 即时热更新注册表")


def test_hot_reload_add_remove():
    """新增/删除效果文件 → 热插拔，effect_manager 名列表同步刷新。"""
    import json
    from core.hot_reload import HotReloader
    from systems.render_system import EFFECT_REGISTRY

    ctx = _minimal_ctx()
    em = ctx.get("effect_manager")
    reg_snap, names_snap = _isolate_registry(ctx, em)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            reloader = HotReloader(ctx, tmp, enabled=False)
            reloader._scan_initial()  # 空基线

            # 新增
            name = "HMR_TEST_ADD"
            p = os.path.join(tmp, "0001_add.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect"}, f)
            reloader._scan_once()
            reloader.consume_pending()
            assert name in EFFECT_REGISTRY, list(EFFECT_REGISTRY.keys())[-5:]
            assert name in em.effect_names, em.effect_names[-5:]

            # 删除
            os.remove(p)
            reloader._scan_once()
            reloader.consume_pending()
            assert name not in EFFECT_REGISTRY, name
            assert name not in em.effect_names, name
    finally:
        _restore_registry(reg_snap, names_snap)
        em.effect_names = names_snap
        ctx.dispose()
    print("[OK] 热插拔：新增/删除效果文件 + 名列表刷新")


def test_hot_reload_threaded():
    """监听线程检测变更，主线程 consume_pending 落地（跨线程安全）。"""
    import json
    import time
    from core.hot_reload import HotReloader
    from systems.render_system import EFFECT_REGISTRY

    ctx = _minimal_ctx()
    em = ctx.get("effect_manager")
    reg_snap, names_snap = _isolate_registry(ctx, em)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            name = "HMR_TEST_THREAD"
            p = os.path.join(tmp, "0001_thread.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect",
                           "params": {"v": 1}}, f)
            reloader = HotReloader(ctx, tmp, enabled=True, interval=0.05)
            reloader.start()
            try:
                time.sleep(0.15)  # 基线扫描
                with open(p, "w", encoding="utf-8") as f:
                    json.dump({"full_name": name, "class": "EngineEffect",
                               "params": {"v": 2}}, f)
                time.sleep(0.25)
                assert not reloader._queue.empty(), "监听线程未检测到变更"
                reloader.consume_pending()
                assert EFFECT_REGISTRY.get(name) == (
                    {"full_name": name, "class": "EngineEffect",
                     "params": {"v": 2}},), EFFECT_REGISTRY.get(name)
            finally:
                reloader.stop()
    finally:
        _restore_registry(reg_snap, names_snap)
        em.effect_names = names_snap
        ctx.dispose()
    print("[OK] 热重载：监听线程检测 + 主线程落地（跨线程）")


def test_hot_reload_manual_reload_event():
    """托盘手动重载事件 → 触发全量重扫并经主循环落地（事件驱动、线程安全）。"""
    import json
    from core.assembly import EVENTS
    from core.hot_reload import HotReloader
    from systems.render_system import EFFECT_REGISTRY

    ctx = _minimal_ctx()
    em = ctx.get("effect_manager")
    reg_snap, names_snap = _isolate_registry(ctx, em)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            name = "HMR_TEST_RELOAD"
            p = os.path.join(tmp, "0001_reload.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect", "v": 1}, f)
            reloader = HotReloader(ctx, tmp, enabled=False)
            reloader._scan_initial()  # 基线（记录文件，未入注册表）

            # 用户编辑了效果文件（on-disk 内容变化）
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"full_name": name, "class": "EngineEffect", "v": 2}, f)

            # 模拟 HotReloadPlugin 的接线：手动重载事件 → force_rescan（只入队）
            unsub = ctx.on(EVENTS.EFFECT_RELOAD_REQUESTED,
                           lambda *_: reloader.force_rescan())
            try:
                ctx.emit(EVENTS.EFFECT_RELOAD_REQUESTED)
                reloader.consume_pending()   # 主循环落地
                assert name in EFFECT_REGISTRY, list(EFFECT_REGISTRY.keys())[-5:]
                assert EFFECT_REGISTRY[name] == (
                    {"full_name": name, "class": "EngineEffect", "v": 2},), EFFECT_REGISTRY[name]
            finally:
                unsub()
    finally:
        _restore_registry(reg_snap, names_snap)
        em.effect_names = names_snap
        ctx.dispose()
    print("[OK] 热重载：手动 reload 事件触发全量重扫并落地")


def test_hot_reload_plugin_wiring():
    """install_hot_reload 提供 hot_reloader 服务并订阅手动重载事件。"""
    from core.context import Context
    from core.assembly import (install_config, install_effect_manager,
                               install_hot_reload, EVENTS)

    ctx = Context()
    install_config(ctx)
    install_effect_manager(ctx)
    ctx.provide("audio", object())    # 哑依赖，避免音乐生成
    ctx.provide("renderer", object())
    try:
        assert "hot_reloader" not in ctx, ctx.keys()
        install_hot_reload(ctx, watch=False)
        assert "hot_reloader" in ctx, ctx.keys()
        assert ctx.listener_count(EVENTS.EFFECT_RELOAD_REQUESTED) >= 1
        ctx.emit(EVENTS.EFFECT_RELOAD_REQUESTED)  # 触发不报错
    finally:
        ctx.dispose()
    print("[OK] 热重载插件：提供服务 + 订阅手动重载事件")


# ── 原语类热重载用例（engine/primitives/*.py） ─────────────


def test_primitive_reload_modified():
    """修改既有原语模块后，PRIMITIVE_REGISTRY 类被替换为新对象，
    create_primitive 下一帧即返回新类（无需重启）。"""
    import importlib
    import sys
    from engine.primitives import PRIMITIVE_REGISTRY, create_primitive
    from core.hot_reload import HotReloader

    before = id(PRIMITIVE_REGISTRY["bars"])
    reloader = HotReloader(ctx=None, effects_dir="effects",
                           primitives_dir="engine/primitives", enabled=False)
    try:
        reloader._apply_primitive(
            {"kind": "primitive_modified", "module": "engine.primitives.bars",
             "path": "engine/primitives/bars.py"}, "primitive_modified")
        after = id(PRIMITIVE_REGISTRY["bars"])
        assert before != after, "reload 后类对象应被替换"
        inst = create_primitive({"type": "bars"}, 100, 100)
        assert type(inst).__name__ == "BarsPrimitive"
        assert type(inst).__module__ == "engine.primitives.bars"
    finally:
        # 恢复：重新载入原文件，使运行时回到一致状态（类对象再次刷新但功能等价）
        importlib.reload(sys.modules["engine.primitives.bars"])
    print("[OK] 原语热重载：修改后类对象被替换且 create_primitive 生效")


def test_primitive_reload_dependency_order():
    """ca_kernel 变更应连带 reload 其依赖方 ca，且 ca_kernel 排在 ca 之前。"""
    from core.hot_reload import HotReloader

    r = HotReloader(ctx=None, effects_dir="effects",
                    primitives_dir="engine/primitives", enabled=False)
    affected = r._collect_reload_set("ca_kernel")
    order = r._topo_order(affected)
    assert "ca_kernel" in affected and "ca" in affected, affected
    assert order.index("ca_kernel") < order.index("ca")
    print("[OK] 原语热重载：ca_kernel 变更拓扑连带 ca 且顺序正确")


def test_primitive_hotplug_added():
    """新增原语模块经 HMR 落地注册表，create_primitive 可取实例。"""
    import os
    from engine.primitives import PRIMITIVE_REGISTRY, create_primitive
    from core.hot_reload import HotReloader

    tmp = "engine/primitives/_hmr_tmp_test.py"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(
            "from engine.primitives import register_primitive, RenderPrimitive\n"
            "@register_primitive('_hmr_tmp_test')\n"
            "class Tmp(RenderPrimitive):\n"
            "    def draw(self, d): pass\n"
        )
    reloader = HotReloader(ctx=None, effects_dir="effects",
                           primitives_dir="engine/primitives", enabled=False)
    try:
        reloader._apply_primitive(
            {"kind": "primitive_added", "module": "engine.primitives._hmr_tmp_test",
             "path": tmp}, "primitive_added")
        assert "_hmr_tmp_test" in PRIMITIVE_REGISTRY
        assert create_primitive({"type": "_hmr_tmp_test"}, 10, 10).__class__.__name__ == "Tmp"
    finally:
        reloader._apply_primitive(
            {"kind": "primitive_removed", "module": "engine.primitives._hmr_tmp_test",
             "path": tmp}, "primitive_removed")
        if os.path.exists(tmp):
            os.remove(tmp)
    assert "_hmr_tmp_test" not in PRIMITIVE_REGISTRY
    print("[OK] 原语热插拔：新增模块落地注册表并实例化")


def test_primitive_reload_failure_isolated():
    """语法错误的原语模块重载失败应报错，且不污染注册表其他项。"""
    import os
    from engine.primitives import PRIMITIVE_REGISTRY
    from core.hot_reload import HotReloader

    tmp = "engine/primitives/_hmr_broken.py"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("this is ) not valid python @@@\n")
    reloader = HotReloader(ctx=None, effects_dir="effects",
                           primitives_dir="engine/primitives", enabled=False)
    bars_before = id(PRIMITIVE_REGISTRY["bars"])
    try:
        reloader._apply_primitive(
            {"kind": "primitive_added", "module": "engine.primitives._hmr_broken",
             "path": tmp}, "primitive_added")
        assert "_hmr_broken" not in PRIMITIVE_REGISTRY
        assert id(PRIMITIVE_REGISTRY["bars"]) == bars_before
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("[OK] 原语热重载：坏模块失败隔离，不污染注册表")


def test_primitive_hot_reload_auto_threaded():
    """监听线程自动发现新原语文件并入队，主线程 consume_pending 落地（跨线程）。"""
    import os
    import time
    from engine.primitives import PRIMITIVE_REGISTRY
    from core.hot_reload import HotReloader

    tmp = "engine/primitives/_hmr_auto.py"
    r = HotReloader(ctx=None, effects_dir="effects",
                    primitives_dir="engine/primitives", enabled=True, interval=0.2)
    r.start()  # 先建基线（此时临时文件尚不存在）
    try:
        # 基线之后再创建新原语文件 → 监听线程应检测为「新增」并入队
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(
                "from engine.primitives import register_primitive, RenderPrimitive\n"
                "@register_primitive('_hmr_auto')\n"
                "class A(RenderPrimitive):\n"
                "    def draw(self, d): pass\n"
            )
        for _ in range(50):
            if not r._queue.empty():
                break
            time.sleep(0.1)
        applied = r.consume_pending()
        assert applied >= 1, applied
        assert "_hmr_auto" in PRIMITIVE_REGISTRY
    finally:
        r.stop()
        if "_hmr_auto" in PRIMITIVE_REGISTRY:
            r._apply_primitive(
                {"kind": "primitive_removed", "module": "engine.primitives._hmr_auto",
                 "path": tmp}, "primitive_removed")
        if os.path.exists(tmp):
            os.remove(tmp)
    print("[OK] 原语热重载：监听线程自动发现新文件并落地（跨线程）")


def test_hot_reload_plugin_wires_primitives():
    """install_hot_reload 装配热重载器并暴露原语目录（engine/primitives）。"""
    import os
    from core.context import Context
    from core.assembly import (install_config, install_effect_manager,
                               install_hot_reload)

    ctx = Context()
    install_config(ctx)
    install_effect_manager(ctx)
    ctx.provide("audio", object())
    ctx.provide("renderer", object())
    try:
        install_hot_reload(ctx, watch=False)
        r = ctx.get("hot_reloader")
        assert r is not None
        assert os.path.isdir(r.primitives_dir), r.primitives_dir
        assert os.path.basename(os.path.dirname(r.primitives_dir)) == "engine"
    finally:
        ctx.dispose()
    print("[OK] 热重载插件：装配并暴露 engine/primitives 原语目录")


def test_renderer_shares_assembly_services():
    """渲染器必须复用装配层的 audio / effect_manager / music 同一实例。

    否则事件总线驱动的效果切换作用在「另一个」EffectManager 上，
    真实渲染永远不切换效果（单元测试若只断言 ctx.get('effect_manager') 会漏掉）。
    """
    from core.assembly import EVENTS, build_context

    ctx = build_context(silent=True, with_tray=False)
    try:
        renderer = ctx.get("renderer")
        assert renderer.effect_manager is ctx.get("effect_manager"), "EffectManager 实例不一致"
        assert renderer.audio is ctx.get("audio"), "AudioSimulator 实例不一致"
        assert renderer.music is ctx.get("music"), "MusicPlaybackSystem 实例不一致"

        # 事件驱动的切换必须作用到渲染器实际使用的那个 manager
        ctx.emit(EVENTS.EFFECT_REQUESTED)
        assert renderer.effect_manager.is_transitioning is True, "事件未作用到渲染器的 manager"
        assert renderer.effect_manager.next_effect_name, renderer.effect_manager.next_effect_name
    finally:
        ctx.dispose()
    print("[OK] 渲染器复用装配层服务（audio/effect_manager/music 同一实例）")


if __name__ == "__main__":
    test_context()
    test_worldlog()
    test_event_bus()
    test_plugin_lifecycle()
    test_context_threadsafe()
    test_world_log_bridge()
    test_assembly_snapshot()
    test_dump_profile()
    test_dump_profile_snapshot()
    test_tray_event_driven()
    test_effect_switch_events()
    test_cross_thread_stress()
    test_hot_reload_modify()
    test_hot_reload_add_remove()
    test_hot_reload_threaded()
    test_hot_reload_manual_reload_event()
    test_hot_reload_plugin_wiring()
    test_primitive_reload_modified()
    test_primitive_reload_dependency_order()
    test_primitive_hotplug_added()
    test_primitive_reload_failure_isolated()
    test_primitive_hot_reload_auto_threaded()
    test_hot_reload_plugin_wires_primitives()
    test_renderer_shares_assembly_services()
    print("\n✅ 三件事冒烟 + 接线改造 + 效果/原语热插拔 HMR 用例全过（23/23）")
