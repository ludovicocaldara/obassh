from enum import Enum


class NodeType(str, Enum):
    COMPUTE = "compute"
    EXADATA_VM_CLUSTER = "exadata_vm_cluster"
    EXADATA_DB_NODE = "exadata_db_node"
    CUSTOM = "custom"


class SessionState(str, Enum):
    CREATING = "creating"
    ACTIVE = "active"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class SessionType(str, Enum):
    PORT_FORWARDING = "Port-Forwarding"
    MANAGED_SSH = "Managed SSH"
    SOCKS5 = "SOCKS5"
