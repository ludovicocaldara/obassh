from __future__ import annotations

from typing import Protocol

from .enums import NodeType
from .models import (
    BastionRef,
    BastionSession,
    ConnectionProfile,
    ConnectionRequest,
    ForwardSpec,
    OciProfileRef,
    ProcessHandle,
    TargetNode,
)


class CloudInventoryProvider(Protocol):
    def list_oci_profiles(self) -> list[OciProfileRef]: ...

    def list_bastions(
        self, profile: OciProfileRef, compartment_ocid: str
    ) -> list[BastionRef]: ...


class BastionSessionProvider(Protocol):
    def create_managed_ssh_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession: ...

    def get_session(self, profile: OciProfileRef, session_ocid: str) -> BastionSession: ...

    def wait_until_active(
        self, profile: OciProfileRef, session_ocid: str, timeout_s: int = 120
    ) -> BastionSession: ...

    def delete_session(self, profile: OciProfileRef, session_ocid: str) -> None: ...


class TargetPlugin(Protocol):
    def node_type(self) -> NodeType: ...

    def discover_nodes(
        self, profile: OciProfileRef, compartment_ocid: str
    ) -> list[TargetNode]: ...

    def default_forwards(self, node: TargetNode) -> list[ForwardSpec]: ...


class SshTransport(Protocol):
    def build_command(self, request: ConnectionRequest) -> list[str]: ...

    def start(self, command: list[str]) -> ProcessHandle: ...

    def stop(self, handle: ProcessHandle) -> None: ...


class ProfileRepository(Protocol):
    def list_profiles(self) -> list[ConnectionProfile]: ...

    def get_profile(self, name: str) -> ConnectionProfile | None: ...

    def save_profile(self, profile: ConnectionProfile) -> None: ...

    def delete_profile(self, name: str) -> None: ...
