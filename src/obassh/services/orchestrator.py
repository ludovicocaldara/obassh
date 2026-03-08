from __future__ import annotations

from typing import Protocol

from obassh.domain.models import ConnectionRequest, ForwardSpec, ProcessHandle


class ConnectionRunner(Protocol):
    def connect(self, request: ConnectionRequest) -> ProcessHandle: ...

    def disconnect(self, handle: ProcessHandle) -> None: ...


class ForwardValidator(Protocol):
    def validate_forward_specs(self, forwards: list[ForwardSpec]) -> None: ...

    def ensure_ports_available(self, forwards: list[ForwardSpec]) -> None: ...


class ConnectionOrchestrator:
    def __init__(
        self,
        connection_service: ConnectionRunner,
        port_forward_service: ForwardValidator,
    ) -> None:
        self._connection_service = connection_service
        self._port_forward_service = port_forward_service

    def connect(self, request: ConnectionRequest) -> ProcessHandle:
        self._port_forward_service.validate_forward_specs(request.forwards)
        self._port_forward_service.ensure_ports_available(request.forwards)
        return self._connection_service.connect(request)

    def disconnect(self, handle: ProcessHandle) -> None:
        self._connection_service.disconnect(handle)
