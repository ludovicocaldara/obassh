from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import oci  # type: ignore[import-untyped]

from obassh.domain.enums import SessionState, SessionType
from obassh.domain.errors import OciApiError, SessionTimeoutError
from obassh.domain.models import BastionSession, OciProfileRef


class OciBastionSessionProvider:
    """OCI SDK-backed bastion session provider."""

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path

    def _client(self, profile: OciProfileRef) -> Any:
        if self._config_path:
            config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile.name))
        else:
            config = cast(dict[str, Any], oci.config.from_file(profile_name=profile.name))
        return oci.bastion.BastionClient(config)

    def create_managed_ssh_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        return self._create_session(
            profile,
            bastion_ocid,
            session_type="MANAGED_SSH",
            target_ip=target_ip,
            target_port=22,
            ssh_public_key=ssh_public_key,
            ttl_seconds=ttl_seconds,
        )

    def create_port_forward_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        target_port: int,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        return self._create_session(
            profile,
            bastion_ocid,
            session_type="PORT_FORWARDING",
            target_ip=target_ip,
            target_port=target_port,
            ssh_public_key=ssh_public_key,
            ttl_seconds=ttl_seconds,
        )

    def create_dynamic_port_forward_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        target_ip: str,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        return self._create_session(
            profile,
            bastion_ocid,
            session_type="DYNAMIC_PORT_FORWARDING",
            target_ip=target_ip,
            target_port=1080,
            ssh_public_key=ssh_public_key,
            ttl_seconds=ttl_seconds,
        )

    def _create_session(
        self,
        profile: OciProfileRef,
        bastion_ocid: str,
        session_type: str,
        target_ip: str,
        target_port: int,
        ssh_public_key: str,
        ttl_seconds: int,
    ) -> BastionSession:
        client = self._client(profile)
        details = {
            "bastionId": bastion_ocid,
            "keyDetails": {"publicKeyContent": ssh_public_key},
            "targetResourceDetails": {
                "sessionType": session_type,
                "targetResourcePort": target_port,
                "targetResourcePrivateIpAddress": target_ip,
            },
            "sessionTtlInSeconds": ttl_seconds,
            "displayName": f"obassh-{session_type.lower()}",
        }
        try:
            response = client.create_session(create_session_details=details)
            return self._map_session(response.data)
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to create OCI bastion session: {exc}") from exc

    def list_sessions(self, profile: OciProfileRef, bastion_ocid: str) -> list[BastionSession]:
        client = self._client(profile)
        try:
            response = client.list_sessions(bastion_id=bastion_ocid)
            return [self._map_session(item) for item in cast(list[Any], response.data)]
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to list OCI bastion sessions: {exc}") from exc

    def get_session(self, profile: OciProfileRef, session_ocid: str) -> BastionSession:
        client = self._client(profile)
        try:
            return self._map_session(client.get_session(session_ocid).data)
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to get OCI bastion session {session_ocid}: {exc}") from exc

    def wait_until_active(
        self,
        profile: OciProfileRef,
        session_ocid: str,
        timeout_s: int = 120,
    ) -> BastionSession:
        client = self._client(profile)
        try:
            response = cast(
                Any,
                oci.wait_until(
                client,
                client.get_session(session_ocid),
                evaluate_response=lambda r: cast(str, cast(Any, r).data.lifecycle_state).upper() == "ACTIVE",  # type: ignore[reportUnknownLambdaType]
                max_wait_seconds=timeout_s,
                ),
            )
            return self._map_session(response.data)
        except Exception as exc:  # pragma: no cover
            raise SessionTimeoutError(f"Timed out waiting for session ACTIVE: {exc}") from exc

    def delete_session(self, profile: OciProfileRef, session_ocid: str) -> None:
        client = self._client(profile)
        try:
            client.delete_session(session_ocid)
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to delete OCI bastion session {session_ocid}: {exc}") from exc

    def _map_session(self, item: Any) -> BastionSession:
        lifecycle = cast(str, getattr(item, "lifecycle_state", "UNKNOWN") or "UNKNOWN").upper()
        state_map = {
            "CREATING": SessionState.CREATING,
            "ACTIVE": SessionState.ACTIVE,
            "FAILED": SessionState.FAILED,
            "DELETING": SessionState.DELETING,
            "DELETED": SessionState.DELETED,
        }
        target_details = getattr(item, "target_resource_details", None)
        session_type_raw = cast(str, getattr(target_details, "session_type", "MANAGED_SSH") or "MANAGED_SSH")
        session_type = {
            "PORT_FORWARDING": SessionType.PORT_FORWARDING,
            "DYNAMIC_PORT_FORWARDING": SessionType.SOCK5,
            "MANAGED_SSH": SessionType.MANAGED_SSH,
        }.get(session_type_raw.upper(), SessionType.MANAGED_SSH)

        target_ip = cast(str, getattr(target_details, "target_resource_private_ip_address", "") or "")
        target_fqdn = cast(str, getattr(target_details, "target_resource_fqdn", "") or "")
        target_resource = target_fqdn or target_ip
        target_port = int(getattr(target_details, "target_resource_port", 22) or 22)
        ttl_seconds = int(getattr(item, "session_ttl_in_seconds", 0) or 0)
        started_at = cast(datetime | None, getattr(item, "time_created", None))
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        expires_at = None
        if started_at and ttl_seconds > 0:
            expires_at = started_at + timedelta(seconds=ttl_seconds)

        ssh_metadata: dict[str, str] = {}
        ssh_meta_obj = getattr(item, "ssh_metadata", None)
        if ssh_meta_obj is not None:
            command = cast(str, getattr(ssh_meta_obj, "command", "") or "")
            bastion_host = cast(str, getattr(ssh_meta_obj, "bastion_host", "") or "")
            bastion_port = cast(str, getattr(ssh_meta_obj, "bastion_port", "") or "")
            if command:
                ssh_metadata["command"] = command
            if bastion_host:
                ssh_metadata["bastion_host"] = bastion_host
            if bastion_port:
                ssh_metadata["bastion_port"] = bastion_port

        return BastionSession(
            ocid=cast(str, getattr(item, "id", "")),
            state=state_map.get(lifecycle, SessionState.UNKNOWN),
            expires_at=expires_at,
            session_type=session_type,
            target_resource=target_resource,
            target_port=target_port,
            started_at=started_at,
            ttl_seconds=ttl_seconds,
            ssh_metadata=ssh_metadata,
        )
