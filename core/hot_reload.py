"""
效果热插拔 / HMR（Hot Module Reload）
====================================

监听 effects/ 目录（及 effects/themes.json）的文件变化，在**主渲染线程**
上把变更应用到运行中的 EFFECT_REGISTRY —— 改一个 JSON 即热替换，无需重启。

设计要点（线程安全）
--------------------
- 监听线程（daemon）只做文件扫描 + 计算哈希，把变更事件放进 queue.Queue；
- 主渲染循环每帧调用 ``consume_pending()`` 在**主线程**落地注册表变更。
- 因此注册表 dict 永远只在主线程被修改，与渲染读取天然无竞争，无需加锁。

纯标准库（threading / queue / hashlib / os / json / glob），零新增第三方依赖。

事件（经 Context.emit 派发，跨线程安全）
----------------------------------------
    effect:reloaded         (full_name, kind)   单个效果配置已热更新
    effect:hotplug_added    (full_name,)        新增效果文件
    effect:hotplug_removed  (full_name,)        删除效果文件
    effect:themes_reloaded  (names,)            背景主题表已热更新
    effect:reload_requested (无参)              请求手动全量重载（托盘菜单触发）
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import queue
import re
import threading
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


class HotReloader:
    """效果文件热重载器。

    用法::

        reloader = HotReloader(ctx, effects_dir)
        reloader.start()                 # 启动监听线程（daemon）
        # 主循环每帧:
        reloader.consume_pending()       # 在主线程落地变更
        # 退出:
        reloader.stop()
    """

    def __init__(self, ctx, effects_dir: str, *,
                 watch_themes: bool = True, interval: float = 1.0,
                 enabled: bool = True):
        self.ctx = ctx
        self.effects_dir = effects_dir
        self.themes_path = os.path.join(effects_dir, "themes.json")
        self.watch_themes = watch_themes
        self.interval = interval

        # path -> (hash, full_name)
        self._snapshot: Dict[str, Tuple[str, Optional[str]]] = {}
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.enabled = enabled

    # ── 生命周期 ──────────────────────────────────────

    def start(self) -> None:
        """启动监听线程（仅 enabled 时）。"""
        if not self.enabled:
            return
        self._scan_initial()
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
            except Exception as e:  # 监听线程自身不能崩
                print(f"[HMR] 扫描异常: {e}")
            self._stop.wait(self.interval)

    def _effect_files(self) -> List[str]:
        pattern = os.path.join(self.effects_dir, "*_*.json")
        files = [f for f in glob.glob(pattern)
                 if os.path.basename(f) != "themes.json"]
        return sorted(files, key=os.path.basename)

    def _scan_initial(self) -> None:
        """建立基线：记录每个效果文件的 (hash, full_name)。"""
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
        """扫描一次，把新增/修改/删除变更入队。"""
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

    # ── 手动全量重载（托盘菜单 / 测试触发） ──────────────
    # 注意：只入队，由主循环 consume_pending 落地，保持「注册表只在主线程变更」

    def force_rescan(self) -> None:
        """请求一次全量重扫（变更会由主循环下一帧落地）。"""
        self._scan_once()

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
        name = ev["full_name"]
        try:
            if kind == "themes":
                from systems.render_system import (BACKGROUND_THEMES,
                                                    load_background_themes)
                load_background_themes(self.themes_path)
                if manager is not None:
                    manager.bg_theme_names = list(BACKGROUND_THEMES.keys())
                if renderer is not None:
                    renderer.bg_theme = None  # 强制下一帧重建
                self._emit(EVENTS.EFFECT_THEMES_RELOADED, list(BACKGROUND_THEMES.keys()))
                print(f"[HMR] 背景主题热更新: {len(BACKGROUND_THEMES)} 个")
                return

            if kind == "removed":
                from systems.render_system import EFFECT_REGISTRY
                if name and name in EFFECT_REGISTRY:
                    EFFECT_REGISTRY.pop(name, None)
                    if manager is not None:
                        manager.refresh_names()
                        # 若删的是当前/下一个效果，立即切走
                        if (manager.current_name == name
                                or manager.next_effect_name == name):
                            if not manager.is_transitioning:
                                manager._start_transition()
                    self._emit(EVENTS.EFFECT_HOTPLUG_REMOVED, name)
                    print(f"[HMR] 热移除效果: {name}")
                return

            # added / modified
            data = ev.get("data")
            if not name or data is None:
                return
            from systems.render_system import EFFECT_REGISTRY
            EFFECT_REGISTRY[name] = (data,)
            if kind == "added" and manager is not None:
                manager.refresh_names()
                self._emit(EVENTS.EFFECT_HOTPLUG_ADDED, name)
                print(f"[HMR] 热插拔新增效果: {name}")
            else:
                self._emit(EVENTS.EFFECT_RELOADED, name, "modified")
                print(f"[HMR] 热更新效果: {name}")
        except Exception as e:
            print(f"[HMR] 应用变更失败 ({kind}/{name}): {e}")

    def _emit(self, event: str, *args) -> None:
        if self.ctx is None:
            return
        try:
            self.ctx.emit(event, *args)
        except Exception:
            pass
