"""
追加式世界事件日志（WorldLog）—— 日志即事实源
================================================

[内联自 alloy 引擎 G:\\games\\alloy\\core\\world_log.py，2026-08-24，复制优于共享]
[media_engine 阶段 A：pywallpaper 三件事升级之二（日志即事实源）]

对应 harness 的事件源纪律（"Model-visible means logged"）的引擎版：

    "凡影响世界状态的事实必须先入 WorldLog"。

特性：
    - 追加式事件流：条目 {seq, ts, type, payload}，seq 单调递增；
    - 快照点（checkpoint）：标记"此 seq 之前的世界状态已被快照"，
      存档 = 快照 + 快照之后的日志增量；
    - 投影（projection）：register_projection(key, init, fold) 注册纯函数折叠，
      由日志推导任意派生状态（HUD/审计/重建），三方永不矛盾；
    - 事件总线桥（track）：把 bus.emit 的指定事件类型自动追加进日志；
    - JSON 持久化（save_to/load_from）；
    - 确定性：同一种子/输入下事件流逐字节一致（ts 可选，便于回放比对）。

纯标准库实现，零第三方依赖。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

__all__ = ["WorldLog", "WorldLogEntry"]


class WorldLogEntry(dict):
    """单条日志条目：seq / ts / type / payload。"""


class WorldLog:
    """追加式世界事件日志。"""

    def __init__(self, source: str = "world", max_entries: Optional[int] = None):
        self.source = source
        self.max_entries = max_entries  # None = 不限
        self._entries: List[dict] = []
        self._seq = 0
        self._projections: Dict[str, dict] = {}

    # ── 运行 id ────────────────────────────────────────

    @classmethod
    def new_run_id(cls) -> str:
        """生成新的运行 id（每次进程启动唯一，供任务日志按次审计）。"""
        return f"run-{time.time_ns()}"

    # ── 追加 ──────────────────────────────────────────

    @property
    def seq(self) -> int:
        """当前序号（下一条事件的 seq）。"""
        return self._seq

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, event_type: str, payload: Any = None, ts: Optional[float] = None) -> dict:
        """追加一条世界事实事件，返回条目。

        ts 默认取 time.time()；测试/回放可传固定值或 None（None 时省略，
        保证确定性比对不依赖时钟）。
        """
        self._seq += 1
        entry: dict = {"seq": self._seq, "type": event_type, "payload": payload}
        if ts is not None:
            entry["ts"] = ts
        self._entries.append(entry)
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        for key, proj in self._projections.items():
            proj["state"] = proj["fold"](proj["state"], entry)
        return entry

    # ── 读取 ──────────────────────────────────────────

    def entries(self) -> List[dict]:
        """返回全部条目（浅拷贝列表）。"""
        return list(self._entries)

    def entries_since(self, seq: int) -> List[dict]:
        """返回 seq 之后（不含）的条目——即"快照之后的增量"。"""
        return [e for e in self._entries if e["seq"] > seq]

    # ── 快照点 ────────────────────────────────────────

    def checkpoint(self) -> int:
        """标记快照点，返回当前 seq（快照应包含 <= 此 seq 的事实）。"""
        return self._seq

    # ── 投影 ──────────────────────────────────────────

    def register_projection(self, key: str, init: Any, fold: Callable[[Any, dict], Any]) -> None:
        """注册投影：init 为初始状态，fold(state, entry) -> 新状态。

        投影会随每条新事件即时折叠；也可用 rebuild_projection 全量重算。
        """
        if key in self._projections:
            raise ValueError(f"投影已注册: '{key}'")
        self._projections[key] = {"init": init, "fold": fold, "state": init}

    def get_projection(self, key: str) -> Any:
        """读取投影当前状态。"""
        if key not in self._projections:
            raise KeyError(f"未注册的投影: '{key}'（已注册: {sorted(self._projections)}）")
        return self._projections[key]["state"]

    def rebuild_projection(self, key: str) -> Any:
        """从日志头重算某个投影（热修复/审计用），返回状态。"""
        proj = self._projections[key]
        state = proj["init"]
        for entry in self._entries:
            state = proj["fold"](state, entry)
        proj["state"] = state
        return state

    def rebuild_all(self) -> None:
        """从日志头重算全部投影。"""
        for key in list(self._projections):
            self.rebuild_projection(key)

    # ── 事件总线桥 ────────────────────────────────────

    def track(self, bus: Any, event_types: List[str]) -> Callable[[], None]:
        """把总线事件自动追加进日志（世界事实类事件）。

        返回 disposer：调用即取消桥接（可交给 Context.effect 随作用域回滚）。
        """

        def _handler(event_type: str) -> Callable[[Any], None]:
            def handler(data: Any) -> None:
                self.append(event_type, data)
            return handler

        handlers = [(et, _handler(et)) for et in event_types]
        for et, h in handlers:
            bus.subscribe(et, h)

        def _dispose() -> None:
            for et, h in handlers:
                bus.unsubscribe(et, h)

        return _dispose

    # ── 持久化 ────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"version": 1, "source": self.source, "seq": self._seq, "entries": self._entries}

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save_to(self, path: str) -> None:
        Path(path).write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "WorldLog":
        log = cls(source=data.get("source", "world"))
        for entry in data.get("entries", []):
            # 绕过 append 的投影折叠与 max_entries 截断，原样装载
            log._seq = max(log._seq, int(entry["seq"]))
            log._entries.append({
                "seq": int(entry["seq"]),
                "type": str(entry["type"]),
                "payload": entry.get("payload"),
                **({"ts": entry["ts"]} if "ts" in entry else {}),
            })
        return log

    @classmethod
    def load_from(cls, path: str) -> "WorldLog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ── 确定性比对 ────────────────────────────────────

    def deterministic_dump(self) -> str:
        """不含 ts 的确定性转储（同一种子下应逐字节一致）。"""
        return json.dumps(
            [{"seq": e["seq"], "type": e["type"], "payload": e.get("payload")} for e in self._entries],
            ensure_ascii=False, sort_keys=True,
        )

    def __repr__(self) -> str:
        return f"<WorldLog source={self.source!r} entries={len(self._entries)} seq={self._seq}>"
