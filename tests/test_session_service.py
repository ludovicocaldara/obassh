from datetime import datetime

from obassh.domain.enums import NodeType, SessionState, SessionType
from obassh.domain.models import BastionSession, OciProfileRef, TargetNode
from obassh.services.session_service import SessionService


class _Provider:
    def __init__(self) -> None:
        self.called = ""

    def create_managed_ssh_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        _ = profile, bastion_ocid, target_ip, ssh_public_key, ttl_seconds
        self.called = "managed"
        return BastionSession("sid", SessionState.ACTIVE, datetime.now(), session_type=SessionType.MANAGED_SSH)

    def create_port_forward_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        target_port: int,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        _ = profile, bastion_ocid, target_ip, target_port, ssh_public_key, ttl_seconds
        self.called = "pf"
        return BastionSession("sid", SessionState.ACTIVE, datetime.now(), session_type=SessionType.PORT_FORWARDING)

    def create_dynamic_port_forward_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        _ = profile, bastion_ocid, target_ip, ssh_public_key, ttl_seconds
        self.called = "socks5"
        return BastionSession("sid", SessionState.ACTIVE, datetime.now(), session_type=SessionType.SOCKS5)

    def list_sessions(self, profile: OciProfileRef, bastion_ocid: str) -> list[BastionSession]:
        _ = profile, bastion_ocid
        return [BastionSession("sid", SessionState.ACTIVE, datetime.now())]

    def get_session(self, profile: OciProfileRef, session_ocid: str) -> BastionSession:
        _ = profile, session_ocid
        return BastionSession("sid", SessionState.ACTIVE, datetime.now())

    def wait_until_active(self, profile: OciProfileRef, session_ocid: str, timeout_s: int = 120) -> BastionSession:
        _ = profile, session_ocid, timeout_s
        return BastionSession("sid", SessionState.ACTIVE, datetime.now())

    def delete_session(self, profile: OciProfileRef, session_ocid: str) -> None:
        _ = profile, session_ocid


def _profile() -> OciProfileRef:
    return OciProfileRef("DEFAULT", "eu-zurich-1", "tenancy")


def _target() -> TargetNode:
    return TargetNode("id", NodeType.COMPUTE, "target", "comp", "10.0.0.5")


def test_open_session_uses_managed_ssh_provider_call_by_default() -> None:
    provider = _Provider()
    service = SessionService(provider)

    session = service.open_session(_profile(), "bastion", _target(), "ssh-rsa ...")

    assert provider.called == "managed"
    assert session.session_type is SessionType.MANAGED_SSH


def test_open_session_uses_port_forward_provider_call() -> None:
    provider = _Provider()
    service = SessionService(provider)

    session = service.open_session(
        _profile(), "bastion", _target(), "ssh-rsa ...", session_type=SessionType.PORT_FORWARDING
    )

    assert provider.called == "pf"
    assert session.session_type is SessionType.PORT_FORWARDING


def test_open_session_uses_sock5_provider_call() -> None:
    provider = _Provider()
    service = SessionService(provider)

    session = service.open_session(
        _profile(), "bastion", _target(), "ssh-rsa ...", session_type=SessionType.SOCKS5
    )

    assert provider.called == "socks5"
    assert session.session_type is SessionType.SOCKS5
