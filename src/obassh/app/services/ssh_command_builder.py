"""Helpers for building and normalizing SSH commands."""

from __future__ import annotations

import re
import shlex

from obassh.domain.enums import SessionType
from obassh.domain.models import BastionSession, OciProfileRef
from obassh.providers.oci import OciBastionSessionProvider


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
        except Exception:
            pass

    if session.session_type is SessionType.PORT_FORWARDING:
        bastion_host = session.ssh_metadata.get("bastion_host", "")
        bastion_port = session.ssh_metadata.get("bastion_port", "22")

        if not bastion_host and metadata_command:
            match = re.search(r"@([^\s]+)", metadata_command)
            if match:
                bastion_host = match.group(1)

        local_port = extract_local_port(metadata_command, session.target_port)

        if not bastion_host and profile is not None:
            bastion_host = f"host.bastion.{profile.region}.oci.oraclecloud.com"

        if bastion_host:
            return (
                f"ssh -i {shlex.quote(private_key_path)} "
                f"-N -L {local_port}:{session.target_resource}:{session.target_port} "
                f"-p {bastion_port} {session.ocid}@{bastion_host}"
            )

    if session.session_type is SessionType.SOCKS5:
        bastion_host = session.ssh_metadata.get("bastion_host", "")
        bastion_port = session.ssh_metadata.get("bastion_port", "22")

        if not bastion_host and metadata_command:
            match = re.search(r"@([^\s]+)", metadata_command)
            if match:
                bastion_host = match.group(1)

        local_port = extract_dynamic_local_port(metadata_command, session.target_port)

        if not bastion_host and profile is not None:
            bastion_host = f"host.bastion.{profile.region}.oci.oraclecloud.com"

        if bastion_host:
            return (
                f"ssh -i {shlex.quote(private_key_path)} "
                f"-N -D 127.0.0.1:{local_port} "
                f"-p {bastion_port} {session.ocid}@{bastion_host}"
            )

    return session.ssh_metadata.get("command", f"ssh -i {private_key_path} opc@{session.target_resource}")
