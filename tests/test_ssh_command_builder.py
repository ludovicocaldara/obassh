from datetime import datetime
import shlex
from typing import cast

from obassh.app.services.ssh_command_builder import session_command
from obassh.domain.enums import SessionState, SessionType
from obassh.domain.models import BastionSession, OciProfileRef
from obassh.providers.oci import OciBastionSessionProvider


class _Provider:
    def get_session(self, profile: OciProfileRef, session_ocid: str) -> BastionSession:
        _ = profile, session_ocid
        return BastionSession("sid", SessionState.ACTIVE, datetime.now())


def test_session_command_builds_sock5_command_with_bastion_host_and_dynamic_port() -> None:
    session = BastionSession(
        ocid=(
            "ocid1.bastionsession.oc1.uk-london-1."
            "amaaaaaaknuwtjiapxsbqrzrngcg6tmphpdnuwmsrf7uztp2mmwinnbidxrq"
        ),
        state=SessionState.ACTIVE,
        expires_at=datetime.now(),
        session_type=SessionType.SOCKS5,
        target_port=1080,
        ssh_metadata={
            "bastion_host": "host.bastion.uk-london-1.oci.oraclecloud.com",
            "bastion_port": "22",
            "command": (
                "ssh -N -D 127.0.0.1:2022 -p 22 "
                "ignored@host.bastion.uk-london-1.oci.oraclecloud.com"
            ),
        },
    )

    command = session_command(
        session=session,
        private_key_path="/tmp/id_rsa",
        profile=OciProfileRef(
            "DEFAULT",
            "uk-london-1",
            "ocid1.tenancy.oc1..x",
        ),
        provider=cast(OciBastionSessionProvider, _Provider()),
    )

    assert command == (
        "ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 "
        "-o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null "
        "-i /tmp/id_rsa -N -D 127.0.0.1:2022 -p 22 "
        "ocid1.bastionsession.oc1.uk-london-1."
        "amaaaaaaknuwtjiapxsbqrzrngcg6tmphpdnuwmsrf7uztp2mmwinnbidxrq@"
        "host.bastion.uk-london-1.oci.oraclecloud.com"
    )


def test_session_command_injects_default_ssh_options_into_proxy_command() -> None:
    session = BastionSession(
        ocid="ocid1.bastionsession.oc1..x",
        state=SessionState.ACTIVE,
        expires_at=datetime.now(),
        ssh_metadata={
            "command": (
                "ssh -i /tmp/id_rsa -o ProxyCommand='ssh -i /tmp/id_rsa -W %h:%p -p 22 "
                "opc@host.bastion.uk-london-1.oci.oraclecloud.com' opc@10.0.0.10"
            )
        },
    )

    command = session_command(
        session=session,
        private_key_path="/tmp/id_rsa",
        profile=None,
        provider=cast(OciBastionSessionProvider, _Provider()),
    )

    assert "-o StrictHostKeyChecking=accept-new" in command
    assert "-o ServerAliveInterval=30" in command
    assert "-o UserKnownHostsFile=/dev/null" in command
    assert "-o GlobalKnownHostsFile=/dev/null" in command
    parts = shlex.split(command)
    proxy_token = next(
        parts[i + 1]
        for i in range(len(parts) - 1)
        if parts[i] == "-o" and parts[i + 1].startswith("ProxyCommand=")
    )
    proxy_command = proxy_token.split("=", 1)[1]
    assert "-o StrictHostKeyChecking=accept-new" in proxy_command
    assert "-o ServerAliveInterval=30" in proxy_command
    assert "-o UserKnownHostsFile=/dev/null" in proxy_command
    assert "-o GlobalKnownHostsFile=/dev/null" in proxy_command
