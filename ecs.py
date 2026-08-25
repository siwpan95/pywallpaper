# -*- coding: utf-8 -*-
"""
ecs.py —— ECS 兼容 shim（J2 S1，2026-08-25）

pywallpaper 自有 ECS（150 行）已退役，本文件是面向 alloy 唯一 ECS
（内联副本 core/ecs_alloy.py）的兼容层，保持 pywallpaper 旧 API 不变：

- Entity：旧命名 add_component/get_component/has_component/remove_component +
          name 属性 + component.entity 回引用
- Component：补 from_dict/from_json/to_dict
- System：兼容旧 update(dt, world) 签名（World.update 按签名自动分派）
- World：补 clear() 别名（→ reset）、destroy_entity、create_entity(name=)
- DataLoader：JSON 工具保留原实现（非 ECS）

内联记录见 engine.patch.yaml；升级走 alloy sync 流程。
"""
import inspect
import json
import os
from typing import Any, Dict, Optional, Type, TypeVar

from core.ecs_alloy import (
    Component as _AlloyComponent,
    Entity as _AlloyEntity,
    System as _AlloySystem,
    World as _AlloyWorld,
    is_component,
)

T = TypeVar("T")


class Component(_AlloyComponent):
    """组件基类：alloy Component + pywallpaper 序列化/回引用兼容。"""

    entity: Optional["Entity"] = None

    @classmethod
    def from_dict(cls, data: dict):
        instance = cls()
        instance.__dict__.update(data)
        return instance

    @classmethod
    def from_json(cls, filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "entity"}


class Entity(_AlloyEntity):
    """实体：alloy Entity + pywallpaper 旧命名与 name 属性。"""

    def __init__(self, name: str = "", *, entity_id=None):
        super().__init__(eid=name or None, entity_id=entity_id)
        self.name = name or f"Entity_{self.id}"
        self._components: Dict[Type, Any] = {}

    def add_component(self, component):
        self.add(component)
        component.entity = self
        return self

    def get_component(self, component_type: Type) -> Optional[Any]:
        return self.get(component_type)

    def has_component(self, component_type: Type) -> bool:
        return self.has(component_type)

    def remove_component(self, component_type: Type):
        return self.remove(component_type)


class System(_AlloySystem):
    """系统基类：alloy System + pywallpaper 旧 update(dt, world) 签名兼容。

    pywallpaper 旧系统子类若覆盖 update(self, dt, world)，World.update
    会按签名自动以旧顺序调用；未覆盖则使用本类默认空操作（旧系统
    普遍不实现 update，如 MusicPlaybackSystem）。
    """

    priority: Any = 0

    def update(self, world, dt):
        pass


class World(_AlloyWorld):
    """世界：alloy World + pywallpaper 兼容面。"""

    def __init__(self):
        super().__init__()
        self._legacy_systems: Dict[int, bool] = {}

    def create_entity(self, name: str = ""):
        self._next_entity_id += 1
        entity = Entity(name, entity_id=self._next_entity_id)
        return self.add_entity(entity)

    def add_system(self, system):
        params = list(inspect.signature(type(system).update).parameters)
        self._legacy_systems[id(system)] = (len(params) >= 3 and params[1] == "dt")
        return super().add_system(system)

    def remove_system(self, system_type: Type):
        s = self.get_system(system_type)
        if s is not None:
            self._legacy_systems.pop(id(s), None)
        return super().remove_system(system_type)

    def update(self, dt: float):
        self._ensure_systems_sorted()
        for system in self.systems:
            if system.enabled(self):
                if self._legacy_systems.get(id(system)):
                    system.update(dt, self)
                else:
                    system.update(self, dt)

    def destroy_entity(self, entity_id: int):
        return self.remove_entity(entity_id)

    def clear(self):
        self.reset()


class DataLoader:
    """从 JSON 加载数据的工具类（原实现保留）。"""

    @staticmethod
    def load(filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"数据文件不存在: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def load_effects(filepath: str) -> list:
        return DataLoader.load(filepath).get("effects", [])

    @staticmethod
    def load_config(filepath: str) -> dict:
        return DataLoader.load(filepath)

    @staticmethod
    def load_audio_data(filepath: str) -> dict:
        return DataLoader.load(filepath)


