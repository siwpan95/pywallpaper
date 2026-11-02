"""
效果热插拔 / HMR（Hot Module Reload）
====================================

两部分能力：

1. 效果 JSON 热插拔（effects/*.json）
   监听 effects/ 目录（及 effects/themes.json）的文件变化，运行时把变更应用到
   运行中的 EFFECT_REGISTRY —— 改一个 JSON 即热替换，无需重启。

2. Python 原语类热重载（engine/primitives/*.py）
   监听原语源文件变化，经 importlib.reload 重新执行模块，其 @register_primitive
   装饰器自动把新类写回 PRIMITIVE_REGISTRY 中央字典。由于 EngineEffect 每帧经
   create_primitive() 按名字 *实时* 查表取类，下一帧即使用新类 —— 注册表就是
   可靠的「重绑点」，不存在被其他模块缓存的悬挂引用问题。

设计要点（线程安全）
--------------------
- 监听线程（daemon）只做文件扫描 + 计算哈希，把变更事件放进 queue.Queue；
- 主渲染循环每帧调用 ``consume_pending()`` 在**主线程**落地注册表变更。
- 因此注册表 dict 永远只在主线程被修改，与渲染读取天然无竞争，无需加锁。

纯标准库（threading / queue / hashlib / os / json / glob / ast / importlib / sys），
零新增第三方依赖。

事件（经 Context.emit 派发，跨线程安全）
----------------------------------------
    effect:reloaded         (full_name, kind)   单个效果配置已热更新
    effect:hotplug_added    (full_name,)        新增效果文件
    effect:hotplug_removed  (full_name,)        删除效果文件
    effect:themes_reloaded  (names,)            背景主题表已热更新
    effect:reload_requested (无参)              请求手动全量重载（托盘菜单触发）
    primitive:reloaded      (module, names)     原语模块已热重载（修改）
    primitive:added         (module, names)     新增原语模块
    primitive:removed       (module, names)     删除原语模块
    primitive:reload_failed (module, error)     原语重载失败（不中断其余）
"""
from __future__ import annotations

import ast
import glob
import hashlib
import importlib
import json
import os
import queue
import sys
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from core.assembly import EVENTS


def _hash_file(path: str) -> Optional[str]:
    """计算文件 md5（读取失败返回 None，便于跳过临时/锁定的文件）。"""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _full_name_of(path: str) -> Tuple[Optional[str], Optional[dict]]:
    """读取效果 JSON，返回 (full_name, data)。解析失败返回 (None, None)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, None
    name = data.get("full_name", data.get("name", ""))
    return (name or None), data


def _primitive_sibling_imports(path: str) -> List[str]:
    """返回某原语模块 *运行时* 依赖的 engine.primitives 兄弟模块名列表。

    用 ast 解析全部 ``from engine.primitives.X`` / ``import engine.primitives.X``
    （含函数体内的延迟导入），自导入（X 导入 X）自动排除。用于拓扑 reload 排序。
    """
    base = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return []
    deps: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "engine.primitives":
                continue  # 来自包的导出名（RenderPrimitive / register_primitive），非子模块依赖
            if mod.startswith("engine.primitives."):
                dep = mod.split(".")[-1]
                if dep != base:
                    deps.add(dep)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("engine.primitives."):
                    dep = alias.name.split(".")[-1]
                    if dep != base:
                        deps.add(dep)
    return sorted(deps)


class HotReloader:
    """效果文件 + 原语类热重载器。

    用法::

        reloader = HotReloader(ctx, effects_dir, primitives_dir=primitives_dir)
        reloader.start()                 # 启动监听线程（daemon）
        # 主循环每帧:
        reloader.consume_pending()       # 在主线程落地变更
        # 退出:
        reloader.stop()
    """

    def __init__(self, ctx, effects_dir: str, *,
                 primitives_dir: Optional[str] = None,
                 watch_themes: bool = True, interval: float = 1.0,
                 enabled: bool = True):
        self.ctx = ctx
        self.effects_dir = effects_dir
        self.themes_path = os.path.join(effects_dir, "themes.json")
        self.watch_themes = watch_themes
        self.interval = interval

        # path -> (hash, full_name)
        self._snapshot: Dict[str, Tuple[str, Optional[str]]] = {}
        # engine.primitives.<base> -> hash
        self._primitive_snapshot: Dict[str, str] = {}
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.enabled = enabled

        self.primitives_dir = primitives_dir

    # ── 生命周期 ──────────────────────────────────────

    def start(self) -> None:
        """启动监听线程（仅 enabled 时）。"""
        if not self.enabled:
            return
        self._scan_initial()
        self._scan_primitives_initial()
        self._thread = threading.Thread(target=self._run, name="hot-reload", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止监听线程。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    # ── 监听线程（只扫描 + 入队，绝不改注册表） ──────────

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_once()
                self._scan_primitives_once()
            except Exception as e:  # 监听线程自身不能崩
                print(f"[HMR] 扫描异常: {e}")
            self._stop.wait(self.interval)

    def _effect_files(self) -> List[str]:
        pattern = os.path.join(self.effects_dir, "*_*.json")
        files = [f for f in glob.glob(pattern)
                 if os.path.basename(f) != "themes.json"]
        return sorted(files, key=os.path.basename)

    def _scan_initial(self) -> None:
        """建立效果基线：记录每个效果文件的 (hash, full_name)。"""
        for path in self._effect_files():
            h = _hash_file(path)
            name, _ = _full_name_of(path)
            if h is not None:
                self._snapshot[path] = (h, name)
        if self.watch_themes and os.path.exists(self.themes_path):
            h = _hash_file(self.themes_path)
            if h is not None:
                self._snapshot[self.themes_path] = (h, None)

    def _scan_once(self) -> None:
        """扫描效果目录一次，把新增/修改/删除变更入队。"""
        current = set(self._effect_files())
        if self.watch_themes and os.path.exists(self.themes_path):
            current.add(self.themes_path)

        # 1) 新增 / 修改
        for path in current:
            h = _hash_file(path)
            if h is None:
                continue
            prev = self._snapshot.get(path)
            if prev is None:
                name, data = _full_name_of(path)
                if name:
                    self._queue.put({"kind": "added", "full_name": name,
                                      "path": path, "data": data,
                                      "is_theme": path == self.themes_path})
                    self._snapshot[path] = (h, name)
            elif prev[0] != h:
                name, data = _full_name_of(path)
                if path == self.themes_path:
                    self._queue.put({"kind": "themes", "full_name": None,
                                      "path": path, "data": None, "is_theme": True})
                elif name:
                    self._queue.put({"kind": "modified", "full_name": name,
                                      "path": path, "data": data, "is_theme": False})
                self._snapshot[path] = (h, name)

        # 2) 删除
        for path in list(self._snapshot.keys()):
            if path not in current:
                prev_name = self._snapshot[path][1]
                is_theme = path == self.themes_path
                self._queue.put({"kind": "removed", "full_name": prev_name,
                                  "path": path, "data": None, "is_theme": is_theme})
                del self._snapshot[path]

    # ── 原语类扫描 ─────────────────────────────────────

    def _primitive_files(self) -> List[str]:
        if not self.primitives_dir or not os.path.isdir(self.primitives_dir):
            return []
        return sorted(
            (os.path.join(self.primitives_dir, f)
             for f in os.listdir(self.primitives_dir)
             if f.endswith(".py") and f != "__init__.py"),
            key=os.path.basename,
        )

    def _scan_primitives_initial(self) -> None:
        for path in self._primitive_files():
            h = _hash_file(path)
            if h is not None:
                full = self._module_full(path)
                self._primitive_snapshot[full] = h

    def _scan_primitives_once(self) -> None:
        if not self.primitives_dir:
            return
        current = set(self._primitive_files())

        # 1) 新增 / 修改
        for path in current:
            h = _hash_file(path)
            if h is None:
                continue
            full = self._module_full(path)
            if full not in self._primitive_snapshot:
                self._queue.put({"kind": "primitive_added", "module": full,
                                  "path": path})
                self._primitive_snapshot[full] = h
            elif self._primitive_snapshot[full] != h:
                self._queue.put({"kind": "primitive_modified", "module": full,
                                  "path": path})
                self._primitive_snapshot[full] = h

        # 2) 删除
        for full in list(self._primitive_snapshot.keys()):
            path = self._path_of(full)
            if path not in current:
                self._queue.put({"kind": "primitive_removed", "module": full,
                                  "path": path})
                del self._primitive_snapshot[full]

    @staticmethod
    def _module_full(path: str) -> str:
        base = os.path.splitext(os.path.basename(path))[0]
        return f"engine.primitives.{base}"

    def _path_of(self, full: str) -> str:
        # 必须与 _primitive_files() 的路径口径一致（均基于 self.primitives_dir），
        # 否则监听线程会把相对/绝对路径不匹配的模块误判为「已删除」而清空注册表。
        base = full.split(".")[-1]
        return os.path.join(self.primitives_dir, base + ".py")

    # ── 手动全量重载（托盘菜单 / 测试触发） ──────────────
    # 注意：只入队，由主循环 consume_pending 落地，保持「注册表只在主线程变更」

    def force_rescan(self) -> None:
        """请求一次全量重扫（效果 + 原语），变更由主循环下一帧落地。"""
        self._scan_once()
        self._scan_primitives_once()

    # ── 主线程落地（每帧调用） ──────────────────────────

    def consume_pending(self) -> int:
        """在主线程应用监听线程发现的变更。返回应用的事件数。"""
        applied = 0
        manager = self.ctx.get("effect_manager", None) if self.ctx else None
        renderer = self.ctx.get("renderer", None) if self.ctx else None
        while not self._queue.empty():
            ev = self._queue.get()
            self._apply(ev, manager, renderer)
            applied += 1
        return applied

    def _apply(self, ev: dict, manager, renderer) -> None:
        kind = ev["kind"]
        try:
            if kind in ("themes", "removed", "added", "modified"):
                if kind == "themes":
                    self._apply_themes(ev, manager, renderer)
                elif kind == "removed":
                    self._apply_effect_removed(ev, manager)
                else:
                    self._apply_effect_upsert(ev, kind, manager)
                return

            # ── 原语类热重载 ──
            if kind in ("primitive_modified", "primitive_added", "primitive_removed"):
                self._apply_primitive(ev, kind)
                return
        except Exception as e:
            print(f"[HMR] 应用变更失败 ({kind}): {e}")

    # ── 效果分支 ──────────────────────────────────────

    def _apply_themes(self, ev, manager, renderer) -> None:
        from systems.render_system import (BACKGROUND_THEMES,
                                            load_background_themes)
        load_background_themes(self.themes_path)
        if manager is not None:
            manager.bg_theme_names = list(BACKGROUND_THEMES.keys())
        if renderer is not None:
            renderer.bg_theme = None  # 强制下一帧重建
        self._emit(EVENTS.EFFECT_THEMES_RELOADED, list(BACKGROUND_THEMES.keys()))
        print(f"[HMR] 背景主题热更新: {len(BACKGROUND_THEMES)} 个")

    def _apply_effect_removed(self, ev, manager) -> None:
        from systems.render_system import EFFECT_REGISTRY
        name = ev["full_name"]
        if name and name in EFFECT_REGISTRY:
            EFFECT_REGISTRY.pop(name, None)
            if manager is not None:
                manager.refresh_names()
                if (manager.current_name == name
                        or manager.next_effect_name == name):
                    if not manager.is_transitioning:
                        manager._start_transition()
            self._emit(EVENTS.EFFECT_HOTPLUG_REMOVED, name)
            print(f"[HMR] 热移除效果: {name}")

    def _apply_effect_upsert(self, ev, kind, manager) -> None:
        from systems.render_system import EFFECT_REGISTRY
        name = ev["full_name"]
        data = ev.get("data")
        if not name or data is None:
            return
        EFFECT_REGISTRY[name] = (data,)
        if kind == "added" and manager is not None:
            manager.refresh_names()
            self._emit(EVENTS.EFFECT_HOTPLUG_ADDED, name)
            print(f"[HMR] 热插拔新增效果: {name}")
        else:
            self._emit(EVENTS.EFFECT_RELOADED, name, "modified")
            print(f"[HMR] 热更新效果: {name}")

    # ── 原语分支 ──────────────────────────────────────

    def _apply_primitive(self, ev: dict, kind: str) -> None:
        full = ev["module"]
        base = full.split(".")[-1]
        if kind == "primitive_removed":
            self._unregister_primitive_module(full)
            self._emit(EVENTS.PRIMITIVE_REMOVED, full, [])
            print(f"[HMR] 原语模块移除: {full}")
            return

        # modified / added：按依赖拓扑 reload 受影响的模块集合
        try:
            affected = self._collect_reload_set(base)
            order = self._topo_order(affected)
        except Exception as e:
            self._emit(EVENTS.PRIMITIVE_RELOAD_FAILED, full, str(e)[:300])
            print(f"[HMR] 原语依赖解析失败 {full}: {e}")
            return

        failed = []
        for mod_base in order:
            mod_full = f"engine.primitives.{mod_base}"
            try:
                if mod_full in sys.modules:
                    importlib.reload(sys.modules[mod_full])
                else:
                    importlib.import_module(mod_full)
            except Exception as e:
                failed.append((mod_base, str(e)))
                self._emit(EVENTS.PRIMITIVE_RELOAD_FAILED, mod_full, str(e)[:300])
                print(f"[HMR] 原语重载失败 {mod_full}: {e}")

        names = self._primitive_names_of(full)
        if failed:
            return
        if kind == "primitive_added":
            self._emit(EVENTS.PRIMITIVE_ADDED, full, names)
            print(f"[HMR] 原语热插拔新增: {full} -> {names}")
        else:
            self._emit(EVENTS.PRIMITIVE_RELOADED, full, names)
            print(f"[HMR] 原语热重载: {full} -> {names}")

    def _primitive_names_of(self, full: str) -> List[str]:
        """扫描 PRIMITIVE_REGISTRY，返回当前由该模块注册的原语名列表。"""
        try:
            import engine.primitives as ep
            return [n for n, c in ep.PRIMITIVE_REGISTRY.items()
                    if getattr(c, "__module__", "") == full]
        except Exception:
            return []

    def _unregister_primitive_module(self, full: str) -> None:
        """从 PRIMITIVE_REGISTRY 移除该模块注册的全部原语，并从 sys.modules 遗忘。"""
        try:
            import engine.primitives as ep
            for n in [n for n, c in ep.PRIMITIVE_REGISTRY.items()
                      if getattr(c, "__module__", "") == full]:
                ep.PRIMITIVE_REGISTRY.pop(n, None)
        except Exception:
            pass
        sys.modules.pop(full, None)

    # ── 原语依赖拓扑 ──────────────────────────────────

    def _dependency_graph(self) -> Dict[str, List[str]]:
        """base 模块名 -> 它依赖的 engine.primitives 兄弟模块名列表。"""
        graph: Dict[str, List[str]] = {}
        for path in self._primitive_files():
            base = os.path.splitext(os.path.basename(path))[0]
            graph[base] = _primitive_sibling_imports(path)
        return graph

    def _collect_reload_set(self, changed: str) -> set:
        """受 changed 影响的模块集合：changed + 所有（传递）依赖它的模块。"""
        graph = self._dependency_graph()
        rev: Dict[str, set] = defaultdict(set)
        for m, deps in graph.items():
            for d in deps:
                rev[d].add(m)
        to_reload: set = set()
        stack = [changed]
        while stack:
            cur = stack.pop()
            if cur in to_reload:
                continue
            to_reload.add(cur)
            for dependent in rev.get(cur, ()):
                stack.append(dependent)
        # 只保留实际存在的模块
        return {m for m in to_reload if os.path.exists(self._path_of(f"engine.primitives.{m}"))}

    def _topo_order(self, modules: set) -> List[str]:
        """依赖优先排序：被依赖者（ca_kernel）先于依赖者（ca）。"""
        graph = self._dependency_graph()
        indeg = {m: 0 for m in modules}
        dependents: Dict[str, List[str]] = defaultdict(list)
        for m in modules:
            for d in graph.get(m, ()):
                if d in modules:
                    indeg[m] += 1
                    dependents[d].append(m)
        # 稳定起点：按字母
        queue_list = sorted([m for m in modules if indeg[m] == 0])
        order: List[str] = []
        while queue_list:
            cur = queue_list.pop(0)
            order.append(cur)
            for nxt in sorted(dependents.get(cur, ())):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue_list.append(nxt)
        # 若图有环（理论不应发生），把剩余补在末尾
        for m in sorted(modules):
            if m not in order:
                order.append(m)
        return order

    # ── 事件派发 ──────────────────────────────────────

    def _emit(self, event: str, *args) -> None:
        if self.ctx is None:
            return
        try:
            self.ctx.emit(event, *args)
        except Exception:
            pass
