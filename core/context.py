"""
可逆装配内核 — Context（注册即回滚）
====================================

[内联自 alloy 引擎的 core/context.py（原仓路径已失效），2026-08-24，复制优于共享]
[media_engine 阶段 A：pywallpaper 三件事升级之一（注册即回滚）]

源自 Cordis 的三个核心算子，为 alloy 提供声明式装配：

    provide(key, service, *, dispose=None)   注册服务，注册动作压入 dispose 栈
    get(key, default=...)                    依赖查找，缺失即装配期报错
    effect(fn)                               注册可逆副作用，随上下文销毁自动撤销

另外提供插件安装（install）、单服务卸载（unload）、子作用域（child）。

设计约定：
    - dispose 栈按注册逆序回滚（后注册先销毁），与 Cordis 语义一致；
    - 重复 provide 同一 key 默认抛 DuplicateServiceError，可用 replace=True 覆盖；
    - install(plugin) 按 name/inject/apply 协议装配，inject 缺失在装配期报错；
    - 纯标准库实现，零第三方依赖。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "Context",
    "DuplicateServiceError",
    "MissingDependencyError",
]

_MISSING = object()

# 条目类型：(key, disposer)；key 为 None 表示匿名副作用（effect）
_Entry = Tuple[Optional[str], Optional[Callable[[], Any]]]


class DuplicateServiceError(RuntimeError):
    """同一上下文内重复提供同名服务。"""

    def __init__(self, key: str):
        super().__init__(f"服务已注册: '{key}'（重复 provide）。如需覆盖请使用 replace=True")


class MissingDependencyError(RuntimeError):
    """插件要求的依赖服务不存在。"""

    def __init__(self, key: str, context: "Context" = None):
        hint = f"（已注册: {sorted(context.keys())}）" if context is not None else ""
        super().__init__(f"缺少依赖服务: '{key}' {hint}")


class Context:
    """
    服务注册表 + 可逆副作用栈。

    用法::

        ctx = Context()
        ctx.provide("world", World(), dispose=world.clear)
        ctx.effect(lambda: print("undo"))
        ctx.get("world")          # -> World 实例
        ctx.install(my_plugin)    # 按 name/inject/apply 协议装配
        ctx.dispose()             # 逆序回滚全部注册
    """

    def __init__(self, parent: Optional["Context"] = None):
        self._parent = parent
        self._services: Dict[str, Any] = {}
        self._entries: List[_Entry] = []
        self._disposed = False
        self._children: List["Context"] = []

    # ── 注册 ──────────────────────────────────────────

    def provide(self, key: str, service: Any, *, dispose: Optional[Callable[[], Any]] = None,
                replace: bool = False) -> Any:
        """注册服务；可附带 disposer（卸载/销毁时调用）。返回 service 便于链式赋值。"""
        self._ensure_live()
        if key in self._services and not replace:
            raise DuplicateServiceError(key)
        if key in self._services and replace:
            self.unload(key)
        self._services[key] = service
        self._entries.append((key, dispose))
        return service

    def effect(self, fn: Callable[[], Any]) -> None:
        """注册匿名可逆副作用：上下文销毁时逆序执行。"""
        self._ensure_live()
        if not callable(fn):
            raise TypeError("effect 需要可调用对象")
        self._entries.append((None, fn))

    # ── 查找 ──────────────────────────────────────────

    def has(self, key: str) -> bool:
        """本上下文或其父链上是否存在服务。"""
        if key in self._services:
            return True
        return self._parent.has(key) if self._parent is not None else False

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """按 key 查找服务：先本层、再父链；缺失且无 default 时抛 MissingDependencyError。"""
        if key in self._services:
            return self._services[key]
        if self._parent is not None:
            value = self._parent.get(key, _MISSING)
            if value is not _MISSING:
                return value
        if default is _MISSING:
            raise MissingDependencyError(key, self)
        return default

    def keys(self) -> List[str]:
        """本层注册的所有 key（不含父链）。"""
        return list(self._services.keys())

    def parent(self) -> Optional["Context"]:
        return self._parent

    # ── 插件 ──────────────────────────────────────────

    def install(self, plugin: Any, config: Any = None) -> "Context":
        """按插件协议装配：name（标识）+ inject（依赖 key 列表）+ apply(ctx, config)。

        apply 若返回可调用对象，则视为该插件的统一 disposer，随上下文销毁执行。
        """
        self._ensure_live()
        name = getattr(plugin, "name", None) or plugin.__class__.__name__
        inject = list(getattr(plugin, "inject", None) or [])
        missing = [k for k in inject if not self.has(k)]
        if missing:
            raise MissingDependencyError(
                f"插件 '{name}' 缺少依赖: {missing}（已注册: {sorted(self.keys())}）")
        result = plugin.apply(self, {} if config is None else config)
        if callable(result):
            self.effect(result)
        return self

    # ── 卸载 / 销毁 ───────────────────────────────────

    def unload(self, key: str) -> bool:
        """只回滚指定 key 的注册：逆序执行其 disposer 并移除服务。未注册返回 False。"""
        if key not in self._services:
            return False
        for k, disp in reversed(self._entries):
            if k == key and disp is not None:
                disp()
        self._entries = [(k, d) for k, d in self._entries if k != key]
        del self._services[key]
        return True

    def dispose(self) -> None:
        """销毁本上下文：按注册逆序回滚全部 effect/disposer，并递归销毁子上下文。

        幂等；单个 disposer 抛异常不中断其余回滚（与 EventBus 容错口径一致）。
        """
        if self._disposed:
            return
        for child in list(self._children):
            child.dispose()
        for _, disp in reversed(self._entries):
            if disp is None:
                continue
            try:
                disp()
            except Exception:
                pass  # 容错：记录到 debug 日志的责任在调用方
        self._entries.clear()
        self._services.clear()
        self._disposed = True

    def child(self) -> "Context":
        """创建子作用域：查找沿父链向上，销毁只回滚自身注册。"""
        child = Context(parent=self)
        self._children.append(child)
        return child

    # ── 内部 ──────────────────────────────────────────

    def _ensure_live(self) -> None:
        if self._disposed:
            raise RuntimeError("Context 已销毁，不能再注册服务")

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __repr__(self) -> str:
        return f"<Context keys={sorted(self.keys())} parent={'yes' if self._parent else 'no'}>"
