from __future__ import annotations

from obassh.domain.interfaces import SshTransport
from obassh.domain.models import ConnectionRequest, ProcessHandle


class ConnectionService:
    def __init__(self, transport: SshTransport) -> None:
        self._transport = transport

    def preview_command(self, request: ConnectionRequest) -> str:
        return " ".join(self._transport.build_command(request))

    def connect(self, request: ConnectionRequest) -> ProcessHandle:
        command = self._transport.build_command(request)
        return self._transport.start(command)

    def disconnect(self, handle: ProcessHandle) -> None:
        self._transport.stop(handle)
