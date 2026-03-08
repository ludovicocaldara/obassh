from __future__ import annotations

import socket

from obassh.domain.errors import ValidationError
from obassh.domain.models import ForwardSpec


class PortForwardService:
    def validate_forward_specs(self, forwards: list[ForwardSpec]) -> None:
        seen: set[int] = set()
        for forward in forwards:
            if not 1 <= forward.local_port <= 65535:
                raise ValidationError(f"Invalid local port: {forward.local_port}")
            if not 1 <= forward.remote_port <= 65535:
                raise ValidationError(f"Invalid remote port: {forward.remote_port}")
            if not forward.remote_host:
                raise ValidationError("Remote host cannot be empty")
            if forward.local_port in seen:
                raise ValidationError(f"Duplicate local port: {forward.local_port}")
            seen.add(forward.local_port)

    def ensure_ports_available(self, forwards: list[ForwardSpec]) -> None:
        for forward in forwards:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", forward.local_port))
                except OSError as exc:
                    raise ValidationError(
                        f"Local port {forward.local_port} is not available"
                    ) from exc
