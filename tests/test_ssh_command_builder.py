from datetime import datetime
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
        "ssh -i /tmp/id_rsa -N -D 127.0.0.1:2022 -p 22 "
        "ocid1.bastionsession.oc1.uk-london-1."
        "amaaaaaaknuwtjiapxsbqrzrngcg6tmphpdnuwmsrf7uztp2mmwinnbidxrq@"
        "host.bastion.uk-london-1.oci.oraclecloud.com"
    )
