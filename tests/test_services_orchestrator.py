from datetime import datetime

from obassh.domain.models import (
    BastionSession,
    ConnectionProfile,
    ConnectionRequest,
    ForwardSpec,
    NodeType,
    ProcessHandle,
    SessionState,
    TargetNode,
)
from obassh.services.orchestrator import ConnectionOrchestrator


class _ConnectionService:
    def __init__(self) -> None:
        self.connected = False

    def connect(self, request: ConnectionRequest) -> ProcessHandle:
        _ = request
        self.connected = True
        return ProcessHandle(pid=1, started_at=datetime.now())

    def disconnect(self, handle: ProcessHandle) -> None:
        _ = handle
        self.connected = False


class _PortForwardService:
    def validate_forward_specs(self, forwards: list[ForwardSpec]) -> None:
        _ = forwards

    def ensure_ports_available(self, forwards: list[ForwardSpec]) -> None:
        _ = forwards


def test_orchestrator_connect_disconnect() -> None:
    connection_service = _ConnectionService()
    pf_service = _PortForwardService()
    orchestrator = ConnectionOrchestrator(connection_service, pf_service)

    profile = ConnectionProfile(
        "n", "p", "c", "b", "t", NodeType.COMPUTE, "opc", "/tmp/k"
    )
    target = TargetNode("id", NodeType.COMPUTE, "name", "c", "10.0.0.1")
    session = BastionSession("sid", SessionState.ACTIVE, datetime.now())
    req = ConnectionRequest(profile, target, session, [ForwardSpec("db", 15432, "127.0.0.1", 5432)])

    handle = orchestrator.connect(req)
    assert handle.pid == 1
    assert connection_service.connected is True

    orchestrator.disconnect(handle)
    assert connection_service.connected is False
