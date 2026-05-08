from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from obassh.connectors.subprocess_ssh_transport import SubprocessSshTransport
from obassh.domain.enums import NodeType, SessionState
from obassh.domain.errors import SshExecutionError
from obassh.domain.models import (
    BastionSession,
    ConnectionProfile,
    ConnectionRequest,
    ForwardSpec,
    ProcessHandle,
    TargetNode,
)


def _request() -> ConnectionRequest:
    profile = ConnectionProfile(
        name="dev",
        oci_profile_name="DEFAULT",
        compartment_ocid="comp",
        bastion_ocid="bastion",
        target_id="inst",
        target_type=NodeType.COMPUTE,
        ssh_user="opc",
        private_key_path="/tmp/id_rsa",
        forwards=[],
    )
    target = TargetNode(
        id="inst",
        node_type=NodeType.COMPUTE,
        display_name="app",
        compartment_ocid="comp",
        ip_or_fqdn="10.0.0.10",
        metadata={},
    )
    session = BastionSession(
        ocid="session",
        state=SessionState.ACTIVE,
        expires_at=datetime.now(),
        ssh_metadata={"bastion_host": "bastion.example", "bastion_port": "22"},
    )
    return ConnectionRequest(
        profile=profile,
        target=target,
        session=session,
        forwards=[
            ForwardSpec(
                name="db",
                local_port=15432,
                remote_host="127.0.0.1",
                remote_port=5432,
            )
        ],
        interactive_shell=False,
    )


def test_build_command_contains_expected_parts() -> None:
    transport = SubprocessSshTransport()

    command = transport.build_command(_request())

    assert command[0] == "ssh"
    assert "StrictHostKeyChecking=accept-new" in command
    assert "ServerAliveInterval=30" in command
    assert "UserKnownHostsFile=/dev/null" in command
    assert "GlobalKnownHostsFile=/dev/null" in command
    assert "-L" in command
    proxy_command = next(token for token in command if token.startswith("ProxyCommand="))
    assert "StrictHostKeyChecking=accept-new" in proxy_command
    assert "ServerAliveInterval=30" in proxy_command
    assert "UserKnownHostsFile=/dev/null" in proxy_command
    assert "GlobalKnownHostsFile=/dev/null" in proxy_command
    assert command[-1] == "opc@bastion.example"


@patch("obassh.connectors.subprocess_ssh_transport.subprocess.Popen")
def test_start_returns_process_handle(mock_popen: Mock) -> None:
    process = Mock()
    process.pid = 999
    mock_popen.return_value = process
    transport = SubprocessSshTransport()

    handle = transport.start(["ssh", "host"], "/tmp/obassh-test.log", "header")

    assert isinstance(handle, ProcessHandle)
    assert handle.pid == 999


@patch("obassh.connectors.subprocess_ssh_transport.subprocess.Popen", side_effect=OSError("boom"))
def test_start_raises_ssh_execution_error_on_oserror(mock_popen: Mock) -> None:
    transport = SubprocessSshTransport()

    with pytest.raises(SshExecutionError):
        transport.start(["ssh", "host"], "/tmp/obassh-test.log", "header")

    assert mock_popen.called
