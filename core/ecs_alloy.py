"""
ECS 架构核心 — 类型安全版本
==============================

[内联自 alloy 引擎 G:\\games\\alloy\\core\\ecs.py，2026-08-25，J2 S1 唯一 ECS]
[复制优于共享：本副本是引擎 ECS 在媒体引擎内的内联，升级走 engine.patch.yaml + sync]

融合 carimara_py 的 ECS 核心设计与扩展功能：
- 实体使用自增整数 ID 作为主键，字符串 eid 为可选标识
- 全局数据共享（set_data / get_data）
- 组件查询、生成器遍历、链式调用
- TypeVar 泛型类型安全、延迟排序
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Set, Type, TypeVar

T = TypeVar("T")
C = TypeVar("C", bound="Component")

# ─── 实体 ID 分配 ───────────────────────────────────
# World 持有实例级自增计数器（见 World._next_entity_id），
# 保证不同 World 的实体 ID 互相隔离。
# 以下模块级计数器仅作为「脱离 World 直接构造 Entity」时的回退，
# 正式实体务必通过 World.create_entity 创建。

_orphan_entity_id: int = 0


def _next_orphan_id() -> int:
    """脱离 World 直接构造 Entity 时使用的回退 ID（非全局 ECS 计数器）。"""
    global _orphan_entity_id
    _orphan_entity_id += 1
    return _orphan_entity_id


# ─── Component ─────────────────────────────────────────

class Component(ABC):
    """
    所有组件的抽象基类。

    推荐使用 @dataclass 继承以获得类型安全的组件：

        @dataclass
        class Position(Component):
            x: int = 0
            y: int = 0

        @dataclass
        class Health(Component):
            value: int = 100
            max_value: int = 100
    """


def is_component(obj: Any) -> bool:
    """检查对象是否为 Component 实例。"""
    return isinstance(obj, Component)


# ─── Entity ────────────────────────────────────────────

class Entity:
    """
    实体 — 组件的容器。

    使用自增整数 ``id`` 作为主键，字符串 ``eid`` 作为可选逻辑标识。
    支持链式调用和 __slots__ 内存优化。

    属性：
        id: 自增整数主键（全局唯一）
        eid: 可选的字符串标识（如 "player", "door_1"）
        components: 以组件类为键的组件字典
    """

    __slots__ = ("id", "eid", "components")

    def __init__(self, eid: Optional[str] = None, *, entity_id: Optional[int] = None) -> None:
        # id 优先由 World.create_entity 显式传入；脱离 World 直接构造时回退到模块级计数器
        self.id: int = entity_id if entity_id is not None else _next_orphan_id()
        self.eid: Optional[str] = eid
        self.components: Dict[Type[Component], Component] = {}

    def add(self, comp: Component) -> "Entity":
        """添加组件，返回 self 支持链式调用。

        用法：
            entity.add(Position(10, 20)).add(Health(100))
        """
        self.components[type(comp)] = comp
        return self

    def get(self, comp_type: Type[T]) -> Optional[T]:
        """按类型获取组件，类型安全。

        用法：
            pos = entity.get(Position)  # 返回 Optional[Position]
        """
        return self.components.get(comp_type)  # type: ignore[return-value]

    def has(self, comp_type: Type[Component]) -> bool:
        """检查是否拥有指定组件。"""
        return comp_type in self.components

    def has_all(self, *comp_types: Type[Component]) -> bool:
        """检查是否同时拥有所有指定组件。"""
        return all(t in self.components for t in comp_types)

    def has_any(self, *comp_types: Type[Component]) -> bool:
        """检查是否拥有任意一个指定组件。"""
        return any(t in self.components for t in comp_types)

    def remove(self, comp_type: Type[Component]) -> Optional[Component]:
        """移除组件，返回被移除的组件或 None。"""
        return self.components.pop(comp_type, None)

    def clear_components(self) -> None:
        """移除所有组件。"""
        self.components.clear()

    def __repr__(self) -> str:
        comp_names = ", ".join(c.__class__.__name__ for c in self.components.values())
        eid_part = f"{self.eid!r}, " if self.eid else ""
        return f"Entity({eid_part}id={self.id}, [{comp_names}])"


# ─── System ────────────────────────────────────────────

class System(ABC):
    """
    系统基类 — 处理拥有特定组件的实体。

    子类需要实现 ``update()`` 方法。
    可选实现 ``priority`` 类属性控制执行顺序（数值越小越先执行）。
    可选重写 ``enabled()`` 方法控制系统是否启用。

    用法：
        class MovementSystem(System):
            priority = 10  # 高优先级，先执行

            def update(self, world: World, dt: float) -> None:
                for entity in world.each(Position, Velocity):
                    pos = entity.get(Position)
                    vel = entity.get(Velocity)
                    pos.x += vel.dx * dt
    """

    # 类级属性说明：子类可定义 priority 和 required_components
    priority: ClassVar[int] = 100

    @abstractmethod
    def update(self, world: "World", dt: float) -> None:
        """
        系统更新逻辑。由 World.update() 每帧调用。

        参数：
            world: 当前世界实例
            dt: 帧间隔时间（秒）
        """
        ...

    def enabled(self, world: "World") -> bool:
        """可选：控制系统是否启用。默认始终启用。"""
        return True


# ─── World ─────────────────────────────────────────────

class World:
    """
    游戏世界 — 管理所有实体、系统和全局数据。

    核心功能：
        - 实体管理：增删查实体，按 eid 或 id 检索
        - 系统管理：按优先级排序执行
        - 组件查询：类型安全的实体过滤和遍历
        - 全局数据：跨系统的共享状态存储
        - 配置加载：从字典批量设置配置

    用法：
        world = World()
        player = world.create_entity("player")
        player.add(Position(5, 5)).add(Health(100))
        world.add_system(MovementSystem())
        world.update(0.016)
    """

    def __init__(self) -> None:
        # 实体存储：同时维护 eid->entity 和 id->entity 两套索引
        self.entities: Dict[str, Entity] = {}         # 按 eid 索引（主）
        self._entities_by_id: Dict[int, Entity] = {}  # 按 id 索引
        self.systems: List[System] = []
        self._systems_sorted: bool = True

        # 实例级自增实体 ID 计数器（替代原模块级全局计数器）
        self._next_entity_id: int = 0

        # 全局共享数据
        self._data: Dict[str, Any] = {}

    # ── 实体管理 ──────────────────────────────────────

    def create_entity(self, eid: Optional[str] = None) -> Entity:
        """快捷方法：创建实体并自动添加到世界中。

        参数：
            eid: 可选的字符串标识

        返回：
            新创建的 Entity 实例（已添加到世界）

        说明：
            实体 ID 由本 World 实例的 _next_entity_id 计数器分配，
            因此不同 World 的实体 ID 互不影响。
        """
        self._next_entity_id += 1
        entity = Entity(eid, entity_id=self._next_entity_id)
        return self.add_entity(entity)

    def add_entity(self, entity: Entity) -> Entity:
        """添加实体到世界。同名 eid 会被覆盖。返回实体支持链式调用。

        参数：
            entity: 要添加的实体

        返回：
            已添加的实体
        """
        if entity.eid:
            # 如果旧 eid 已存在，先清理 id 索引
            old = self.entities.get(entity.eid)
            if old is not None and old.id != entity.id:
                self._entities_by_id.pop(old.id, None)
            self.entities[entity.eid] = entity
        self._entities_by_id[entity.id] = entity
        return entity

    def reset_id_counter(self, start: int = 0) -> None:
        """重置本 World 的实体 ID 计数器。

        用于测试隔离或需要确定性 ID 的场景。仅影响此 World 实例，
        不影响其他 World（这正是将计数器从模块全局移入实例的目的）。

        参数：
            start: 重置后的起始值（下一个实体 ID 将为 start + 1）
        """
        self._next_entity_id = start

    def get_entity(self, key: str | int) -> Optional[Entity]:
        """按 eid（字符串）或 id（整数）获取实体。

        参数：
            key: 实体的 eid 或 id

        返回：
            匹配的 Entity 或 None
        """
        if isinstance(key, str):
            return self.entities.get(key)
        return self._entities_by_id.get(key)

    def remove_entity(self, key: str | int) -> Optional[Entity]:
        """移除实体。支持 eid 字符串或 id 整数。

        参数：
            key: 实体的 eid 或 id

        返回：
            被移除的实体或 None
        """
        if isinstance(key, str):
            entity = self.entities.pop(key, None)
            if entity is not None:
                self._entities_by_id.pop(entity.id, None)
            return entity
        else:
            entity = self._entities_by_id.pop(key, None)
            if entity is not None and entity.eid is not None:
                self.entities.pop(entity.eid, None)
            return entity

    def entity_count(self) -> int:
        """当前实体总数。"""
        return len(self._entities_by_id)

    def each_entity(self) -> Iterator[Entity]:
        """遍历所有实体。"""
        yield from self._entities_by_id.values()

    def list_entity_ids(self) -> list[str]:
        """列出所有实体的 eid（字符串键）。"""
        return list(self.entities.keys())

    def has_entity(self, eid: str) -> bool:
        """检查指定 eid 的实体是否存在。"""
        return eid in self.entities

    def entity_ids(self) -> Iterator[str]:
        """遍历所有实体 eid。"""
        yield from self.entities.keys()

    # ── 系统管理 ──────────────────────────────────────

    def add_system(self, system: System) -> "World":
        """添加系统，标记需要重新排序。返回 self 支持链式调用。

        用法：
            world.add_system(MovementSystem()).add_system(RenderSystem())
        """
        self.systems.append(system)
        self._systems_sorted = False
        return self

    def get_system(self, system_type: Type[T]) -> Optional[T]:
        """按类型获取系统。

        用法：
            movement = world.get_system(MovementSystem)
        """
        for s in self.systems:
            if isinstance(s, system_type):
                return s  # type: ignore[return-value]
        return None

    def remove_system(self, system_type: Type[System]) -> None:
        """按类型移除系统。"""
        self.systems = [s for s in self.systems if not isinstance(s, system_type)]
        self._systems_sorted = False

    def has_system(self, system_type: Type[System]) -> bool:
        """检查是否存在指定类型的系统。"""
        return any(isinstance(s, system_type) for s in self.systems)

    def _ensure_systems_sorted(self) -> None:
        """延迟排序：仅在需要时才按优先级排序系统列表。"""
        if not self._systems_sorted:
            self.systems.sort(key=lambda s: s.priority)
            self._systems_sorted = True

    # ── 组件查询 ──────────────────────────────────────

    def get_entities_with_components(self, *comp_types: Type[Component]) -> List[Entity]:
        """返回同时拥有所有指定组件的实体列表。

        用法：
            # 获取所有有位置且可交互的实体
            entities = world.get_entities_with_components(Position, Interactable)
        """
        result: List[Entity] = []
        for entity in self._entities_by_id.values():
            if entity.has_all(*comp_types):
                result.append(entity)
        return result

    # 别名，兼容 pywallpaper 风格命名
    find_entities_with = get_entities_with_components

    def get_first_with_components(self, *comp_types: Type[Component]) -> Optional[Entity]:
        """返回第一个匹配所有组件的实体，或 None。"""
        for entity in self._entities_by_id.values():
            if entity.has_all(*comp_types):
                return entity
        return None

    def get_entities_with_any(self, *comp_types: Type[Component]) -> List[Entity]:
        """返回拥有任意一个指定组件的实体列表。"""
        result: List[Entity] = []
        for entity in self._entities_by_id.values():
            if entity.has_any(*comp_types):
                result.append(entity)
        return result

    def each(self, *comp_types: Type[Component]) -> Iterator[Entity]:
        """生成器：遍历所有拥有指定组件的实体。

        用法：
            for entity in world.each(Position, Health):
                pos = entity.get(Position)
                hp = entity.get(Health)
                ...
        """
        for entity in self._entities_by_id.values():
            if entity.has_all(*comp_types):
                yield entity

    def each_any(self, *comp_types: Type[Component]) -> Iterator[Entity]:
        """生成器：遍历拥有任意一个指定组件的实体。"""
        for entity in self._entities_by_id.values():
            if entity.has_any(*comp_types):
                yield entity

    # ── 全局数据共享 ──────────────────────────────────

    def set_data(self, key: str, value: Any) -> None:
        """存储全局共享数据。

        用法：
            world.set_data("current_level", 3)
            world.set_data("player_name", "Alice")
        """
        self._data[key] = value

    def get_data(self, key: str, default: Any = None) -> Any:
        """读取全局共享数据。

        参数：
            key: 数据键名
            default: 键不存在时返回的默认值

        返回：
            存储的数据值
        """
        return self._data.get(key, default)

    def has_data(self, key: str) -> bool:
        """检查是否存在指定的共享数据键。"""
        return key in self._data

    def clear_data(self) -> None:
        """清除所有全局共享数据。"""
        self._data.clear()

    # ── 配置加载 ──────────────────────────────────────

    def load_config(self, config: Dict[str, Any]) -> None:
        """从字典批量加载配置，存入全局数据。

        用法：
            world.load_config({"cell_size": 20, "tilemap": "map_01"})
        """
        self._data.update(config)

    # ── 世界更新 ──────────────────────────────────────

    def update(self, dt: float) -> None:
        """按优先级顺序更新所有启用的系统。

        参数：
            dt: 帧间隔时间（秒）
        """
        self._ensure_systems_sorted()
        for system in self.systems:
            if system.enabled(self):
                system.update(self, dt)

    # ── 调试辅助 ──────────────────────────────────────

    def debug_print(self) -> None:
        """打印世界状态（调试用）。"""
        print(f"[World] {self.entity_count()} entities, {len(self.systems)} systems")
        if self._data:
            print(f"  Data keys: {list(self._data.keys())}")
        for entity in self._entities_by_id.values():
            print(f"  {entity}")
        for s in self.systems:
            status = "ON" if s.enabled(self) else "OFF"
            print(f"  [{status}] {s.__class__.__name__} (priority={s.priority})")

    def reset(self) -> None:
        """重置世界：清除所有实体、系统和数据。

        注意：仅清除内部状态，本 World 的实体 ID 计数器不会重置。
        """
        self.entities.clear()
        self._entities_by_id.clear()
        self.systems.clear()
        self._systems_sorted = True
        self._data.clear()
