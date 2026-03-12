from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import NodeType, SessionState, SessionType


@dataclass(slots=True)
class OciProfileRef:
    name: str
    region: str
    tenancy_ocid: str
    compartment_ocid: str = ""
    user_ocid: str | None = None
    fingerprint: str | None = None


@dataclass(slots=True)
class BastionRef:
    ocid: str
    display_name: str
    compartment_ocid: str
    target_subnet_id: str | None = None


@dataclass(slots=True)
class TargetNode:
    id: str
    node_type: NodeType
    display_name: str
    compartment_ocid: str
    ip_or_fqdn: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ForwardSpec:
    name: str
    local_port: int
    remote_host: str
    remote_port: int


@dataclass(slots=True)
class ConnectionProfile:
    name: str
    oci_profile_name: str
    compartment_ocid: str
    bastion_ocid: str
    target_id: str
    target_type: NodeType
    ssh_user: str
    private_key_path: str
    forwards: list[ForwardSpec] = field(default_factory=list)


@dataclass(slots=True)
class BastionSession:
    ocid: str
    state: SessionState
    expires_at: datetime | None
    session_type: SessionType = SessionType.MANAGED_SSH
    target_resource: str = ""
    target_port: int = 22
    started_at: datetime | None = None
    ttl_seconds: int = 0
    ssh_metadata: dict[str, str] = field(default_factory=lambda: {})
    pid: int | None = None
    logfile_path: str | None = None


@dataclass(slots=True)
class ConnectionRequest:
    profile: ConnectionProfile
    target: TargetNode
    session: BastionSession
    forwards: list[ForwardSpec]
    interactive_shell: bool = False


@dataclass(slots=True)
class ProcessHandle:
    pid: int
    started_at: datetime
