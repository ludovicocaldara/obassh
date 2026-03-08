from datetime import datetime

from obassh.domain.enums import NodeType, SessionState
from obassh.domain.models import (
    BastionSession,
    ConnectionProfile,
    ForwardSpec,
    ProcessHandle,
    TargetNode,
)


def test_forward_spec_and_connection_profile_creation() -> None:
    forward = ForwardSpec(name="db", local_port=15432, remote_host="10.0.0.10", remote_port=5432)
    profile = ConnectionProfile(
        name="dev-db",
        oci_profile_name="DEFAULT",
        compartment_ocid="ocid1.compartment.oc1..example",
        bastion_ocid="ocid1.bastion.oc1..example",
        target_id="ocid1.instance.oc1..example",
        target_type=NodeType.COMPUTE,
        ssh_user="opc",
        private_key_path="/tmp/id_rsa",
        forwards=[forward],
    )

    assert profile.forwards[0].name == "db"
    assert profile.target_type is NodeType.COMPUTE


def test_bastion_session_and_process_handle() -> None:
    now = datetime.now()
    session = BastionSession(
        ocid="ocid1.bastionsession.oc1..example",
        state=SessionState.ACTIVE,
        expires_at=now,
        ssh_metadata={"bastion_host": "host.example"},
    )
    handle = ProcessHandle(pid=1234, started_at=now)

    assert session.state is SessionState.ACTIVE
    assert handle.pid == 1234


def test_target_node_metadata() -> None:
    node = TargetNode(
        id="instance-id",
        node_type=NodeType.COMPUTE,
        display_name="app-01",
        compartment_ocid="comp",
        ip_or_fqdn="10.0.0.5",
        metadata={"shape": "VM.Standard.E4.Flex"},
    )

    assert node.metadata["shape"] == "VM.Standard.E4.Flex"
