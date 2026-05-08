"""Helpers for building and normalizing SSH commands."""

from __future__ import annotations

import re
import shlex

from obassh.domain.enums import SessionType  # pylint: disable=import-error
from obassh.domain.errors import OciApiError  # pylint: disable=import-error
from obassh.domain.models import BastionSession, OciProfileRef  # pylint: disable=import-error
from obassh.providers.oci import OciBastionSessionProvider  # pylint: disable=import-error


_DEFAULT_SSH_OPTIONS = {
    "StrictHostKeyChecking": "accept-new",
    "ServerAliveInterval": "30",
    "UserKnownHostsFile": "/dev/null",
    "GlobalKnownHostsFile": "/dev/null",
}


def apply_identity_to_command(command: str, private_key_path: str) -> str:
    """Inject or replace -i key argument in ssh commands."""
    if not command:
        return command
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    if not parts:
        return command
    if "-i" in parts:
        idx = parts.index("-i")
        if idx + 1 < len(parts):
            parts[idx + 1] = private_key_path
        else:
            parts.extend(["-i", private_key_path])
    elif parts[0] == "ssh":
        parts = [parts[0], "-i", private_key_path, *parts[1:]]
    return shlex.join(parts)


def extract_local_port(command: str, default_port: int) -> int:
    """Extract local forward port from a -L expression if present."""
    if not command:
        return default_port
    match = re.search(r"-L\s+(\d+):", command)
    if not match:
        return default_port
    try:
        return int(match.group(1))
    except ValueError:
        return default_port


def extract_dynamic_local_port(command: str, default_port: int) -> int:
    """Extract dynamic forward local port from a -D expression if present."""
    if not command:
        return default_port
    match = re.search(r"-D\s+(?:127\.0\.0\.1:)?(\d+)", command)
    if not match:
        return default_port
    try:
        return int(match.group(1))
    except ValueError:
        return default_port


def session_command(
    session: BastionSession,
    private_key_path: str,
    profile: OciProfileRef | None,
    provider: OciBastionSessionProvider,
) -> str:
    """Build the best-effort SSH command for a bastion session."""
    metadata_command = session.ssh_metadata.get("command", "")

    if (
        session.session_type is SessionType.PORT_FORWARDING
        and (not metadata_command or "-L" not in metadata_command)
        and profile is not None
    ):
        try:
            full_session = provider.get_session(profile, session.ocid)
            if full_session.ssh_metadata:
                session.ssh_metadata.update(full_session.ssh_metadata)
                metadata_command = session.ssh_metadata.get("command", metadata_command)
        except OciApiError:
            pass

    if session.session_type is SessionType.PORT_FORWARDING:
        command = _port_forward_command(session, private_key_path, profile, metadata_command)
        return _with_default_ssh_options(command)
    if session.session_type is SessionType.SOCKS5:
        command = _socks5_command(session, private_key_path, profile, metadata_command)
        return _with_default_ssh_options(command)

    command = session.ssh_metadata.get(
        "command", f"ssh -i {private_key_path} opc@{session.target_resource}"
    )
    return _with_default_ssh_options(command)


def _resolve_bastion_host(
    metadata_command: str,
    metadata_host: str,
    profile: OciProfileRef | None,
) -> str:
    bastion_host = metadata_host
    if not bastion_host and metadata_command:
        match = re.search(r"@([^\s]+)", metadata_command)
        if match:
            bastion_host = match.group(1)
    if not bastion_host and profile is not None:
        bastion_host = f"host.bastion.{profile.region}.oci.oraclecloud.com"
    return bastion_host


def _port_forward_command(
    session: BastionSession,
    private_key_path: str,
    profile: OciProfileRef | None,
    metadata_command: str,
) -> str:
    bastion_host = _resolve_bastion_host(
        metadata_command,
        session.ssh_metadata.get("bastion_host", ""),
        profile,
    )
    bastion_port = session.ssh_metadata.get("bastion_port", "22")
    local_port = _safe_int(
        session.ssh_metadata.get("local_port", ""),
        extract_local_port(metadata_command, session.target_port),
    )
    remote_port = _safe_int(
        session.ssh_metadata.get("remote_port", ""),
        session.target_port,
    )
    remote_ip = session.ssh_metadata.get("remote_ip", "") or session.target_resource
    if not bastion_host:
        return session.ssh_metadata.get(
            "command", f"ssh -i {private_key_path} opc@{session.target_resource}"
        )
    return (
        f"ssh -i {shlex.quote(private_key_path)} "
        f"-N -L {local_port}:{remote_ip}:{remote_port} "
        f"-p {bastion_port} {session.ocid}@{bastion_host}"
    )


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _socks5_command(
    session: BastionSession,
    private_key_path: str,
    profile: OciProfileRef | None,
    metadata_command: str,
) -> str:
    bastion_host = _resolve_bastion_host(
        metadata_command,
        session.ssh_metadata.get("bastion_host", ""),
        profile,
    )
    bastion_port = session.ssh_metadata.get("bastion_port", "22")
    local_port = extract_dynamic_local_port(metadata_command, session.target_port)
    if not bastion_host:
        return session.ssh_metadata.get(
            "command", f"ssh -i {private_key_path} opc@{session.target_resource}"
        )
    return (
        f"ssh -i {shlex.quote(private_key_path)} "
        f"-N -D 127.0.0.1:{local_port} "
        f"-p {bastion_port} {session.ocid}@{bastion_host}"
    )


def _with_default_ssh_options(command: str) -> str:
    """Ensure SSH commands auto-accept unknown host fingerprints and avoid known_hosts writes."""
    if not command:
        return command

    try:
        parts = shlex.split(command)
    except ValueError:
        return command

    normalized = _normalize_ssh_parts(parts)
    if normalized is None:
        return command
    return shlex.join(normalized)


def _normalize_ssh_parts(parts: list[str]) -> list[str] | None:
    if not parts or parts[0] != "ssh":
        return None

    normalized = list(parts)
    seen_options: set[str] = set()
    idx = 1
    while idx < len(normalized):
        if normalized[idx] == "-o" and idx + 1 < len(normalized):
            option = normalized[idx + 1]
            if "=" in option:
                key, value = option.split("=", 1)
                seen_options.add(key)
                if key == "ProxyCommand":
                    proxy_command = _with_default_ssh_options(value)
                    normalized[idx + 1] = f"ProxyCommand={proxy_command}"
            idx += 2
            continue
        idx += 1

    insert_at = 1
    for key, value in _DEFAULT_SSH_OPTIONS.items():
        if key not in seen_options:
            normalized[insert_at:insert_at] = ["-o", f"{key}={value}"]
            insert_at += 2
    return normalized
