from obassh.domain.enums import NodeType
from obassh.domain.models import ForwardSpec, OciProfileRef, TargetNode
from obassh.plugins.registry import PluginRegistry


class _Plugin:
    def node_type(self) -> NodeType:
        return NodeType.COMPUTE

    def discover_nodes(
        self,
        profile: OciProfileRef,
        compartment_ocid: str,
    ) -> list[TargetNode]:
        _ = (profile, compartment_ocid)
        return []

    def default_forwards(self, node: TargetNode) -> list[ForwardSpec]:
        _ = node
        return []


def test_registry_register_and_get() -> None:
    registry = PluginRegistry()
    plugin = _Plugin()
    registry.register(plugin)

    assert registry.get(NodeType.COMPUTE) is plugin
    assert registry.all() == [plugin]
