from __future__ import annotations

from obassh.domain.enums import NodeType
from obassh.domain.interfaces import CloudInventoryProvider
from obassh.domain.models import BastionRef, OciProfileRef, TargetNode
from obassh.plugins.registry import PluginRegistry


class DiscoveryService:
    def __init__(self, inventory: CloudInventoryProvider, registry: PluginRegistry) -> None:
        self._inventory = inventory
        self._registry = registry

    def list_profiles(self) -> list[OciProfileRef]:
        return self._inventory.list_oci_profiles()

    def list_bastions(self, profile: OciProfileRef, compartment_ocid: str) -> list[BastionRef]:
        return self._inventory.list_bastions(profile, compartment_ocid)

    def list_targets(
        self,
        profile: OciProfileRef,
        compartment_ocid: str,
        node_types: list[NodeType] | None = None,
    ) -> list[TargetNode]:
        plugins = (
            self._registry.all()
            if node_types is None
            else [self._registry.get(nt) for nt in node_types]
        )
        nodes: list[TargetNode] = []
        for plugin in plugins:
            nodes.extend(plugin.discover_nodes(profile, compartment_ocid))
        return nodes
