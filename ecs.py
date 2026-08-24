"""
ECS 核心框架 - Entity-Component-System 轻量实现
Entity: 唯一ID标识
Component: 纯数据（从 JSON 加载）
System: 纯逻辑（操作 Component 数据）
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Type, TypeVar, Optional
import json
import os


class Entity:
    """实体 - 只是一个唯一ID的容器"""
    _next_id = 0

    def __init__(self, name: str = ""):
        Entity._next_id += 1
        self.id = Entity._next_id
        self.name = name or f"Entity_{self.id}"
        self._components: Dict[Type, Any] = {}

    def add_component(self, component):
        """添加组件到实体"""
        self._components[type(component)] = component
        component.entity = self

    def get_component(self, component_type: Type) -> Optional[Any]:
        """获取指定类型的组件"""
        return self._components.get(component_type)

    def has_component(self, component_type: Type) -> bool:
        return component_type in self._components

    def remove_component(self, component_type: Type):
        self._components.pop(component_type, None)

    def __repr__(self):
        return f"Entity({self.id}, '{self.name}', components={list(self._components.keys())})"


class Component(ABC):
    """组件基类 - 纯数据容器，从 JSON 加载"""
    entity: Optional[Entity] = None

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建组件（子类可覆盖）"""
        instance = cls()
        instance.__dict__.update(data)
        return instance

    @classmethod
    def from_json(cls, filepath: str):
        """从 JSON 文件加载组件"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != 'entity'}


class System(ABC):
    """系统基类 - 纯逻辑处理器"""
    priority: int = 0  # 执行优先级（越小越先执行）

    @abstractmethod
    def update(self, dt: float, world: 'World'):
        """每帧更新"""
        ...


class World:
    """ECS 世界 - 管理所有实体和系统"""

    def __init__(self):
        self.entities: Dict[int, Entity] = {}
        self.systems: Dict[Type, System] = {}
        self._data: Dict[str, Any] = {}  # 全局共享数据

    def create_entity(self, name: str = "") -> Entity:
        entity = Entity(name)
        self.entities[entity.id] = entity
        return entity

    def destroy_entity(self, entity_id: int):
        self.entities.pop(entity_id, None)

    def add_system(self, system: System):
        self.systems[type(system)] = system
        return system

    def remove_system(self, system_type: Type):
        self.systems.pop(system_type, None)

    def get_system(self, system_type: Type) -> Optional[System]:
        return self.systems.get(system_type)

    def set_data(self, key: str, value: Any):
        self._data[key] = value

    def get_data(self, key: str, default=None) -> Any:
        return self._data.get(key, default)

    def update(self, dt: float):
        """按优先级顺序更新所有系统"""
        sorted_systems = sorted(self.systems.values(), key=lambda s: s.priority)
        for system in sorted_systems:
            system.update(dt, self)

    def find_entities_with(self, *component_types: Type) -> list:
        """查找拥有所有指定组件的实体"""
        result = []
        for entity in self.entities.values():
            if all(entity.has_component(ct) for ct in component_types):
                result.append(entity)
        return result

    def load_config(self, filepath: str) -> dict:
        """加载 JSON 配置文件到世界数据"""
        if not os.path.exists(filepath):
            return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)


class DataLoader:
    """从 JSON 加载数据的工具类"""

    @staticmethod
    def load(filepath: str) -> dict:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"数据文件不存在: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def load_effects(filepath: str) -> list:
        """加载效果定义列表"""
        data = DataLoader.load(filepath)
        return data.get('effects', [])

    @staticmethod
    def load_config(filepath: str) -> dict:
        return DataLoader.load(filepath)

    @staticmethod
    def load_audio_data(filepath: str) -> dict:
        return DataLoader.load(filepath)
