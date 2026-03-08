import socket

import pytest

from obassh.domain.errors import ValidationError
from obassh.domain.models import ForwardSpec
from obassh.services.port_forward_service import PortForwardService


def test_validate_forward_specs_accepts_valid_input() -> None:
    service = PortForwardService()
    forwards = [ForwardSpec(name="db", local_port=15432, remote_host="127.0.0.1", remote_port=5432)]

    service.validate_forward_specs(forwards)


def test_validate_forward_specs_rejects_duplicate_local_port() -> None:
    service = PortForwardService()
    forwards = [
        ForwardSpec(name="db", local_port=15432, remote_host="127.0.0.1", remote_port=5432),
        ForwardSpec(name="app", local_port=15432, remote_host="127.0.0.1", remote_port=8080),
    ]

    with pytest.raises(ValidationError):
        service.validate_forward_specs(forwards)


def test_ensure_ports_available_detects_busy_port() -> None:
    service = PortForwardService()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()

    with pytest.raises(ValidationError):
        service.ensure_ports_available(
            [ForwardSpec(name="busy", local_port=port, remote_host="127.0.0.1", remote_port=80)]
        )

    sock.close()
