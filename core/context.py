"""
可逆装配内核 — Context（注册即回滚）
====================================

[内联自 alloy 引擎的 core/context.py（原仓路径已失效），2026-08-24，复制优于共享]
[media_engine 阶段 A：pywallpaper 三件事升级之一（注册即回滚）]
[2026-11-02 接线改造：补齐 Cordis 语义——事件总线 / 插件生命周期 / inject 校验 / 线程安全]

源自 Cordis 的核心算子，为 pywallpaper 提供声明式装配：

    provide(key, service, *, dispose=None)   注册服务，注册动作压入 dispose 栈
    get(key, default=...)                    依赖查找，缺失即装配期报错
    effect(fn)                               注册可逆副作用，随上下文销毁自动撤销

另外提供插件安装（install）、单服务卸载（unload）、子作用域（child）、事件总线（on/emit）。

设计约定：
    - dispose 栈按注册逆序回滚（后注册先销毁），与 Cordis 语义一致；
    - 重复 provide 同一 key 默认抛 DuplicateServiceError，可用 replace=True 覆盖；
    - install(plugin) 按 name/inject/apply 协议装配，inject 缺失在装配期报错；
    - 事件订阅随 effect 回滚（unsubscribe 与 disposer 同生命周期）；
    - 所有公开方法线程安全（RLock 保护），托盘线程可安全 emit；
    - 纯标准库实现，零第三方依赖。

Cordis 对照（TS 官方版 cordiverse/cordis）：
    TS 版用 Proxy 拦截属性访问 + fiber 树管理插件生命周期；
    本移植用显式 get()/provide() + 扁平 dispose 栈，语义等价但更易读。
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "Context",
    "DuplicateServiceError",
    "MissingDependencyError",
    "PluginHandle",
]

_MISSING = object()


class _Entry:
    """一条注册条目：(key, disposer, owner)。

    key 为 None 表示匿名副作用（effect）。
    owner 是「拥有者令牌」：None 表示根上下文注册，否则为对应 PluginHandle 的令牌；
    插件卸载时按 owner 精确回滚，不误伤其他插件的注册。
    """

    __slots__ = ("key", "dispose", "owner")

    def __init__(self, key: Optional[str], dispose: Optional[Callable[[], Any]],
                 owner: Any = None):
        self.key = key
        self.dispose = dispose
        self.owner = owner


class DuplicateServiceError(RuntimeError):
    """同一上下文内重复提供同名服务。"""

    def __init__(self, key: str):
        super().__init__(f"服务已注册: '{key}'（重复 provide）。如需覆盖请使用 replace=True")


class MissingDependencyError(RuntimeError):
    """插件要求的依赖服务不存在。"""

    def __init__(self, key: str, context: "Context" = None):
        hint = f"（已注册: {sorted(context.keys())}）" if context is not None else ""
        super().__init__(f"缺少依赖服务: '{key}' {hint}")


class PluginHandle:
    """插件安装句柄 —— 持有插件名与其占用的条目集合，支持独立卸载。

    Cordis 用 fiber 树表达插件生命周期；这里用「所有者令牌」近似：
    安装时生成唯一令牌，该插件注册的所有条目打上此标记；
    卸载时只回滚同标记条目，其他插件的注册不受影响。
    """

    __slots__ = ("ctx", "name", "token", "_disposed")

    def __init__(self, ctx: "Context", name: str, token: Any):
        self.ctx = ctx
        self.name = name
        self.token = token
        self._disposed = False

    @property
    def disposed(self) -> bool:
        return self._disposed

    def dispose(self) -> None:
        """卸载该插件：逆序回滚它注册的全部服务与副作用。"""
        if self._disposed:
            return
        self.ctx._uninstall(self)
        self._disposed = True

    def __repr__(self) -> str:
        state = "disposed" if self._disposed else "active"
        return f"<PluginHandle {self.name} {state}>"


class Context:
    """
    服务注册表 + 事件总线 + 可逆副作用栈。

    用法::

        ctx = Context()
        ctx.provide("world", World(), dispose=world.clear)
        ctx.effect(lambda: print("undo"))
        ctx.get("world")          # -> World 实例
        ctx.install(my_plugin)    # 按 name/inject/apply 协议装配
        ctx.on("tick", handler)   # 事件订阅，回滚时自动退订
        ctx.emit("tick", 1)       # 同步派发
        ctx.dispose()             # 逆序回滚全部注册
    """

    def __init__(self, parent: Optional["Context"] = None):
        self._parent = parent
        self._services: Dict[str, Any] = {}
        self._entries: List[_Entry] = []
        self._disposed = False
        self._children: List["Context"] = []
        # 事件总线：event -> [(handler, token)]
        self._listeners: Dict[str, List[Tuple[Callable[..., Any], Any]]] = {}
        # 线程安全：托盘线程与渲染主线程共享同一 Context
        self._lock = threading.RLock()
        # 当前装配的所有者令牌（None = 根上下文；插件装配期间为该插件令牌）
        self._current_owner: Any = None

    # ── 注册 ──────────────────────────────────────────

    def provide(self, key: str, service: Any, *, dispose: Optional[Callable[[], Any]] = None,
                replace: bool = False) -> Any:
        """注册服务；可附带 disposer（卸载/销毁时调用）。返回 service 便于链式赋值。"""
        with self._lock:
            self._ensure_live()
            if key in self._services:
                if not replace:
                    raise DuplicateServiceError(key)
                self.unload(key)
            self._services[key] = service
            self._entries.append(_Entry(key, dispose, self._current_owner))
            return service

    def effect(self, fn: Callable[[], Any]) -> None:
        """注册匿名可逆副作用：上下文销毁时逆序执行。"""
        with self._lock:
            self._ensure_live()
            if not callable(fn):
                raise TypeError("effect 需要可调用对象")
            self._entries.append(_Entry(None, fn, self._current_owner))

    # ── 查找 ──────────────────────────────────────────

    def has(self, key: str) -> bool:
        """本上下文或其父链上是否存在服务。"""
        with self._lock:
            if key in self._services:
                return True
            return self._parent.has(key) if self._parent is not None else False

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """按 key 查找服务：先本层、再父链；缺失且无 default 时抛 MissingDependencyError。"""
        with self._lock:
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
        with self._lock:
            return list(self._services.keys())

    def parent(self) -> Optional["Context"]:
        return self._parent

    # ── 插件 ──────────────────────────────────────────

    def install(self, plugin: Any, config: Any = None) -> "PluginHandle":
        """按插件协议装配：name（标识）+ inject（依赖 key 列表）+ apply(ctx, config)。

        插件三种形态（与 Cordis 对齐）：
            1. 函数插件   def p(ctx, config): ...        —— 返回可选 disposer
            2. 对象插件   带 apply(self, ctx, config) 方法 —— 返回可选 disposer
            3. 类插件     class P: __init__(ctx, config)  —— 不调用 apply

        apply/函数若返回可调用对象，则视为该插件的统一 disposer，随卸载执行。
        返回 PluginHandle，可单独卸载该插件。
        """
        with self._lock:
            self._ensure_live()
            name = self._plugin_name(plugin)
            inject = list(getattr(plugin, "inject", None) or [])
            missing = [k for k in inject if not self.has(k)]
            if missing:
                raise MissingDependencyError(
                    f"插件 '{name}' 缺少依赖: {missing}（已注册: {sorted(self.keys())}）")

            token = object()  # 唯一所有者令牌
            prev_owner = self._current_owner
            self._current_owner = token
            try:
                result = self._invoke_plugin(plugin, config)
            except Exception:
                # 插件体失败：回滚它已经产生的部分注册，不留半成品
                self._rollback_owner(token)
                raise
            finally:
                self._current_owner = prev_owner

            if callable(result):
                self._entries.append(_Entry(None, result, token))
            return PluginHandle(self, name, token)

    def _plugin_name(self, plugin: Any) -> str:
        """取插件标识名：显式 name 属性优先，其次函数 __name__，最后类名。"""
        name = getattr(plugin, "name", None)
        if isinstance(name, str) and name:
            return name
        if not isinstance(plugin, type) and callable(plugin):
            func_name = getattr(plugin, "__name__", "")
            if func_name and func_name != "<lambda>":
                return func_name
        cls = plugin if isinstance(plugin, type) else type(plugin)
        return getattr(cls, "__name__", repr(plugin))

    def _invoke_plugin(self, plugin: Any, config: Any) -> Any:
        """按插件形态分派调用，返回其 disposer（若有）。

        注意：类插件走 __init__(ctx, config) 构造路径，不调用 apply；
        函数插件与对象插件走 (ctx, config) / apply(ctx, config)。
        """
        cfg = {} if config is None else config
        if isinstance(plugin, type):
            # 类插件：实例化，dispose 取实例的 close/stop（若有）
            instance = plugin(self, cfg)
            for attr in ("dispose", "close", "stop", "shutdown"):
                fn = getattr(instance, attr, None)
                if callable(fn):
                    return fn
            return None
        if callable(plugin):
            return plugin(self, cfg)
        apply_fn = getattr(plugin, "apply", None)
        if callable(apply_fn):
            return apply_fn(self, cfg)
        raise TypeError(f"非法插件: {plugin!r}（需为函数、类，或带 apply 方法的对象）")

    def _uninstall(self, handle: "PluginHandle") -> None:
        """回滚某个插件注册的条目（按所有者令牌精确回滚）。"""
        with self._lock:
            self._rollback_owner(handle.token)

    def _rollback_owner(self, token: Any) -> None:
        """逆序回滚属于该 owner 的全部条目（含事件退订），不影响他人注册。"""
        with self._lock:
            owned = [e for e in self._entries if e.owner is token]
            if not owned:
                return
            # 逆序执行 disposer（保持全局注册序的逆序）
            for entry in reversed(self._entries):
                if entry.owner is not token or entry.dispose is None:
                    continue
                try:
                    entry.dispose()
                except Exception:
                    pass  # 容错：单个 disposer 失败不中断其余回滚
            # 移除条目与服务
            removed_keys = {e.key for e in owned if e.key is not None}
            self._entries = [e for e in self._entries if e.owner is not token]
            for key in removed_keys:
                self._services.pop(key, None)

    # ── 事件总线 ──────────────────────────────────────

    def on(self, event: str, handler: Callable[..., Any]) -> Callable[[], None]:
        """订阅事件，返回退订函数（disposer）。

        退订函数随上下文销毁自动执行——即事件订阅是一种可逆副作用。
        订阅归属于当前装配的所有者，插件卸载时随之退订。
        """
        with self._lock:
            self._ensure_live()
            if not callable(handler):
                raise TypeError("事件处理器必须可调用")
            token = object()
            self._listeners.setdefault(event, []).append((handler, token))
            owner = self._current_owner

            def _unsubscribe() -> None:
                self._off(event, handler, token)

            # 订阅也是可逆副作用：登记到 owner，插件卸载/上下文销毁时自动退订
            self._entries.append(_Entry(None, _unsubscribe, owner))
            return _unsubscribe

    def once(self, event: str, handler: Callable[..., Any]) -> Callable[[], None]:
        """订阅一次：首次触发后自动退订。"""
        def _wrapper(*args, **kwargs):
            self._off(event, _wrapper, None)
            return handler(*args, **kwargs)
        return self.on(event, _wrapper)

    def off(self, event: str, handler: Callable[..., Any]) -> bool:
        """退订事件处理器。返回是否确实移除了。"""
        with self._lock:
            return self._off(event, handler, None)

    def _off(self, event: str, handler: Callable[..., Any], token: Any) -> bool:
        """内部退订：token 非 None 时只移除该订阅实例。"""
        with self._lock:
            handlers = self._listeners.get(event)
            if not handlers:
                return False
            for i, (h, t) in enumerate(handlers):
                if h is handler and (token is None or t is token):
                    handlers.pop(i)
                    if not handlers:
                        self._listeners.pop(event, None)
                    return True
            return False

    def emit(self, event: str, *args: Any, **kwargs: Any) -> List[Any]:
        """同步派发事件给全部订阅者，返回各处理器的返回值列表。

        容错：单个处理器抛异常不中断其余处理器（与 disposer 容错口径一致）。
        线程安全：托盘线程与主线程可并发 emit。
        """
        with self._lock:
            handlers = list(self._listeners.get(event, ()))
        results = []
        for handler, _ in handlers:
            try:
                results.append(handler(*args, **kwargs))
            except Exception as exc:
                print(f"[CONTEXT] 事件 '{event}' 处理器异常: {type(exc).__name__}: {exc}")
                results.append(None)
        return results

    def subscribe(self, event: str, handler: Callable[..., Any]) -> Callable[[], None]:
        """on 的别名 —— 兼容 WorldLog.track(bus, ...) 期望的 bus 协议。"""
        return self.on(event, handler)

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> bool:
        """off 的别名 —— 兼容 WorldLog.track(bus, ...) 期望的 bus 协议。"""
        return self.off(event, handler)

    def listener_count(self, event: Optional[str] = None) -> int:
        """统计订阅者数量（指定事件名则只统计该事件）。"""
        with self._lock:
            if event is not None:
                return len(self._listeners.get(event, ()))
            return sum(len(v) for v in self._listeners.values())

    def events(self) -> List[str]:
        """列出当前有订阅者的事件名。"""
        with self._lock:
            return sorted(self._listeners.keys())

    # ── 卸载 / 销毁 ───────────────────────────────────

    def unload(self, key: str) -> bool:
        """只回滚指定 key 的注册：逆序执行其 disposer 并移除服务。未注册返回 False。"""
        with self._lock:
            if key not in self._services:
                return False
            for entry in reversed(self._entries):
                if entry.key == key and entry.dispose is not None:
                    try:
                        entry.dispose()
                    except Exception:
                        pass
            self._entries = [e for e in self._entries if e.key != key]
            del self._services[key]
            return True

    def dispose(self) -> None:
        """销毁本上下文：按注册逆序回滚全部 effect/disposer，并递归销毁子上下文。

        幂等；单个 disposer 抛异常不中断其余回滚（与 EventBus 容错口径一致）。
        """
        with self._lock:
            if self._disposed:
                return
            for child in list(self._children):
                child.dispose()
            for entry in reversed(self._entries):
                if entry.dispose is None:
                    continue
                try:
                    entry.dispose()
                except Exception:
                    pass  # 容错：记录到 debug 日志的责任在调用方
            self._entries.clear()
            self._services.clear()
            self._listeners.clear()
            self._disposed = True

    def child(self) -> "Context":
        """创建子作用域：查找沿父链向上，销毁只回滚自身注册。"""
        with self._lock:
            child = Context(parent=self)
            self._children.append(child)
            return child

    # ── 自省 ──────────────────────────────────────────

    def snapshot(self) -> dict:
        """装配自省快照：服务、插件、事件订阅的真实清单。

        用于 --dump-profile 与审计，取代硬编码的描述文本。
        """
        with self._lock:
            return {
                "services": sorted(self._services.keys()),
                "entries": len(self._entries),
                "events": {e: len(v) for e, v in sorted(self._listeners.items())},
                "total_listeners": sum(len(v) for v in self._listeners.values()),
                "children": len(self._children),
                "disposed": self._disposed,
            }

    # ── 内部 ──────────────────────────────────────────

    def _ensure_live(self) -> None:
        if self._disposed:
            raise RuntimeError("Context 已销毁，不能再注册服务")

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._services)

    def __repr__(self) -> str:
        return f"<Context keys={sorted(self.keys())} parent={'yes' if self._parent else 'no'}>"
