from __future__ import annotations

from obassh.domain.interfaces import BastionSessionProvider
from obassh.domain.models import BastionSession, OciProfileRef, TargetNode


class SessionService:
    def __init__(self, provider: BastionSessionProvider) -> None:
        self._provider = provider

    def open_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target: TargetNode,
        ssh_public_key: str,
        ttl_seconds: int = 3600,
    ) -> BastionSession:
        return self._provider.create_managed_ssh_session(
            profile=profile,
            bastion_ocid=bastion_ocid,
            target_ip=target.ip_or_fqdn,
            ssh_public_key=ssh_public_key,
            ttl_seconds=ttl_seconds,
        )

    def wait_active(
        self,
        profile: OciProfileRef,
        session_ocid: str,
        timeout_s: int = 120,
    ) -> BastionSession:
        return self._provider.wait_until_active(profile, session_ocid, timeout_s)

    def close_session(self, profile: OciProfileRef, session_ocid: str) -> None:
        self._provider.delete_session(profile, session_ocid)
