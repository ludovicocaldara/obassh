from __future__ import annotations

from obassh.domain.enums import NodeType
from obassh.domain.interfaces import TargetPlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[NodeType, TargetPlugin] = {}

    def register(self, plugin: TargetPlugin) -> None:
        self._plugins[plugin.node_type()] = plugin

    def get(self, node_type: NodeType) -> TargetPlugin:
        return self._plugins[node_type]

    def all(self) -> list[TargetPlugin]:
        return list(self._plugins.values())
