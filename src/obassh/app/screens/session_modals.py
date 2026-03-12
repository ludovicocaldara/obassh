"""Modal screens used by the session workflow."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from obassh.domain.enums import SessionType


class CreateSessionModal(ModalScreen[dict[str, str] | None]):
    """Modal form for creating session entries."""

    def __init__(self, session_type: SessionType, initial_target_ip: str = "") -> None:
        super().__init__()
        self._session_type = session_type
        self._initial_target_ip = initial_target_ip

    def compose(self) -> ComposeResult:
        with Container(id="session-modal"):
            yield Label(f"Create {self._session_type.value} session", id="session-modal-title")
            yield Input(
                value=self._initial_target_ip,
                placeholder="Target IP / Hostname",
                id="session-target",
            )
            yield Input(value="22", placeholder="Target Port", id="session-port")
            yield Input(value="3600", placeholder="TTL (seconds)", id="session-ttl")
            with Container(id="session-modal-actions"):
                yield Button("Create", variant="primary", id="session-create")
                yield Button("Cancel", id="session-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "session-cancel":
            self.dismiss(None)
            return
        target = self.query_one("#session-target", Input).value.strip()
        port = self.query_one("#session-port", Input).value.strip() or "22"
        ttl = self.query_one("#session-ttl", Input).value.strip() or "3600"
        self.dismiss({"target": target, "port": port, "ttl": ttl})


class CommandEditModal(ModalScreen[str | None]):
    """Modal to view/edit command before execution."""

    def __init__(self, command: str) -> None:
        super().__init__()
        self._command = command

    def compose(self) -> ComposeResult:
        with Container(id="session-modal"):
            yield Label("Edit SSH command", id="session-modal-title")
            yield Input(value=self._command, id="session-command-edit")
            with Container(id="session-modal-actions"):
                yield Button("Execute", variant="primary", id="session-exec")
                yield Button("Cancel", id="session-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "session-cancel":
            self.dismiss(None)
            return
        self.dismiss(self.query_one("#session-command-edit", Input).value.strip())


class PortForwardEditModal(ModalScreen[dict[str, str] | None]):
    """Modal to edit port-forward execution parameters."""

    def __init__(self, local_port: int, remote_port: int, remote_ip: str) -> None:
        super().__init__()
        self._local_port = str(local_port)
        self._remote_port = str(remote_port)
        self._remote_ip = remote_ip

    def compose(self) -> ComposeResult:
        with Container(id="session-modal"):
            yield Label("Edit Port Forward", id="session-modal-title")
            yield Input(value=self._local_port, placeholder="Local Port", id="pf-local-port")
            yield Input(value=self._remote_port, placeholder="Remote Port", id="pf-remote-port")
            yield Input(value=self._remote_ip, placeholder="Remote IP", id="pf-remote-ip")
            with Container(id="session-modal-actions"):
                yield Button("Execute", variant="primary", id="session-exec")
                yield Button("Cancel", id="session-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "session-cancel":
            self.dismiss(None)
            return
        self.dismiss(
            {
                "local_port": self.query_one("#pf-local-port", Input).value.strip(),
                "remote_port": self.query_one("#pf-remote-port", Input).value.strip(),
                "remote_ip": self.query_one("#pf-remote-ip", Input).value.strip(),
            }
        )
