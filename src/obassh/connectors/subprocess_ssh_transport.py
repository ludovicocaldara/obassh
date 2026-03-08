from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from obassh.domain.errors import SshExecutionError
from obassh.domain.models import ConnectionRequest, ProcessHandle


class SubprocessSshTransport:
    """Builds and runs SSH commands for bastion-backed connections."""

    def build_command(self, request: ConnectionRequest) -> list[str]:
        command = [
            "ssh",
            "-i",
            request.profile.private_key_path,
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=30",
        ]

        for forward in request.forwards:
            command.extend(
                [
                    "-L",
                    f"{forward.local_port}:{forward.remote_host}:{forward.remote_port}",
                ]
            )

        if not request.interactive_shell:
            command.append("-N")

        bastion_host = request.session.ssh_metadata.get("bastion_host", "")
        bastion_port = request.session.ssh_metadata.get("bastion_port", "22")

        if bastion_host:
            command.extend([
                "-o",
                (
                    "ProxyCommand="
                    f"ssh -i {request.profile.private_key_path} -W %h:%p "
                    f"-p {bastion_port} opc@{bastion_host}"
                ),
            ])

        command.append(f"{request.profile.ssh_user}@{request.target.ip_or_fqdn}")
        return command

    def start(self, command: list[str]) -> ProcessHandle:
        try:
            process = subprocess.Popen(command)  # noqa: S603  # pylint: disable=consider-using-with
        except OSError as exc:
            raise SshExecutionError(str(exc)) from exc
        return ProcessHandle(pid=process.pid, started_at=datetime.now(timezone.utc))

    def stop(self, handle: ProcessHandle) -> None:
        try:
            subprocess.run(["kill", str(handle.pid)], check=True)  # noqa: S603
        except subprocess.SubprocessError as exc:
            raise SshExecutionError(f"Failed stopping process {handle.pid}: {exc}") from exc
