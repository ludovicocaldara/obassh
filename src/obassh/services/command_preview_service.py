from __future__ import annotations

import shlex

from obassh.domain.models import ConnectionRequest
from obassh.domain.interfaces import SshTransport


class CommandPreviewService:
    def __init__(self, transport: SshTransport) -> None:
        self._transport = transport

    def preview_command(self, request: ConnectionRequest) -> str:
        command = self._transport.build_command(request)
        return shlex.join(command)
