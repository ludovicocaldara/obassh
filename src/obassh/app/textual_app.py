"""Main Textual application shell for obassh."""

from __future__ import annotations

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false

import shlex
import subprocess
from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Static,
    TabbedContent,
    TabPane,
)

from obassh.app.controllers.profile_targets_controller import ProfileTargetsController
from obassh.app.controllers.session_controller import SessionController
from obassh.app.models import AppState
from obassh.app.screens.session_modals import CommandEditModal, CreateSessionModal
from obassh.domain.enums import SessionState, SessionType
from obassh.providers.oci import OciBastionSessionProvider
from obassh.providers.oci.inventory_provider import OciInventoryProvider
from obassh.services.session_service import SessionService


class ObasshApp(App[str | None]):
    """Initial application shell with placeholder tabs."""

    TITLE = "obassh"
    SUB_TITLE = "OCI Bastion SSH orchestrator"
    CSS_PATH = "obassh.tcss"
    BINDINGS = [
        ("f", "new_port_forward", "New Port Forward"),
        ("s", "new_managed_ssh", "New Managed SSH"),
        ("S", "new_socks5", "New SOCKS5"),
        ("d", "delete_session", "Delete session"),
        ("r", "refresh", "Refresh"),
        ("enter", "edit_and_execute", "Edit+Execute command"),
        ("x", "execute_direct", "Execute command"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._inventory = OciInventoryProvider()
        self._provider = OciBastionSessionProvider()
        self._session_service = SessionService(self._provider)
        pubkey, privkey = self._default_key_paths()
        self._state = AppState(preferred_public_key_path=pubkey, preferred_private_key_path=privkey)
        self._profile_targets = ProfileTargetsController(self, self._state, self._inventory)
        self._sessions = SessionController(
            app=self,
            state=self._state,
            session_service=self._session_service,
            provider=self._provider,
            selected_profile_getter=self._profile_targets.selected_profile,
            ensure_single_bastion=self._profile_targets.ensure_single_bastion,
        )

    def compose(self) -> ComposeResult:
        """Build the first iterative UI layout."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with TabbedContent(initial="session"):
                with TabPane("Session", id="session"):
                    yield DataTable(id="session-table")
                    yield Static("No session selected", id="session-selection")
                with TabPane("Targets", id="targets"):
                    yield DataTable(id="targets-compute-table")
                    yield DataTable(id="targets-db-table")
                    yield Static("No target selected", id="targets-selection")
                with TabPane("Profiles", id="profiles"):
                    yield DataTable(id="profiles-table")
                    yield Static("No profile selected", id="profiles-selection")
                with TabPane("Settings", id="settings"):
                    yield Input(placeholder="Bastion OCID override", id="settings-bastion-ocid")
                    yield Input(
                        value=self._state.preferred_public_key_path,
                        placeholder="SSH public key path",
                        id="settings-pubkey-path",
                    )
                    yield Input(
                        value=self._state.preferred_private_key_path,
                        placeholder="SSH private key path",
                        id="settings-privkey-path",
                    )
                    with Container(id="session-modal-actions"):
                        yield Button("Apply", variant="primary", id="settings-apply")
                    yield Static("Configure bastion/key defaults", id="settings-selection")
        yield Footer()

    def on_mount(self) -> None:
        """Load profiles and initialize target tables."""
        self._sessions.load_session_table()
        self._profile_targets.load_target_tables()
        self._profile_targets.load_profiles()
        if any(p.name == "DEFAULT" for p in self._state.profiles):
            self._state.selected_profile_name = "DEFAULT"
            self.query_one("#profiles-selection", Static).update("Selected profile: DEFAULT")
            self._profile_targets.load_targets_for_profile("DEFAULT")
            if self._profile_targets.ensure_single_bastion("DEFAULT"):
                self._sessions.refresh_sessions_from_oci()

    def _default_key_paths(self) -> tuple[str, str]:
        ssh_dir = Path.home() / ".ssh"
        preferred = ["id_ed25519", "id_rsa"]
        for key_name in preferred:
            pub = ssh_dir / f"{key_name}.pub"
            prv = ssh_dir / key_name
            if pub.exists() and prv.exists():
                return (str(pub), str(prv))
        return (str(ssh_dir / "id_ed25519.pub"), str(ssh_dir / "id_ed25519"))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection for profiles and target tables."""
        if event.data_table.id == "session-table":
            session_id = event.row_key.value
            if session_id is not None:
                self._sessions.update_selected_session_label(session_id)
            return

        if event.data_table.id == "profiles-table":
            row_values = cast(list[str], event.data_table.get_row(event.row_key))
            selected_profile = row_values[0] if row_values else "<unknown>"
            self._state.selected_profile_name = selected_profile
            self.query_one("#profiles-selection", Static).update(
                f"Selected profile: {selected_profile}"
            )
            self._profile_targets.load_targets_for_profile(selected_profile)
            if self._profile_targets.ensure_single_bastion(selected_profile):
                self._sessions.refresh_sessions_from_oci()
            return

        row_values = cast(list[str], event.data_table.get_row(event.row_key))
        if event.data_table.id == "targets-compute-table":
            self._state.selected_target_ip = row_values[3]
            self.query_one("#targets-selection", Static).update(
                f"Selected compute target: {row_values[0]} ({row_values[3]})"
            )
            return

        if event.data_table.id == "targets-db-table":
            self._state.selected_target_ip = row_values[5]
            self.query_one("#targets-selection", Static).update(
                f"Selected DB node target: {row_values[2]} ({row_values[5]})"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "settings-apply":
            return
        self._state.selected_bastion_ocid = self.query_one(
            "#settings-bastion-ocid", Input
        ).value.strip()
        self._state.preferred_public_key_path = self.query_one(
            "#settings-pubkey-path", Input
        ).value.strip()
        self._state.preferred_private_key_path = self.query_one(
            "#settings-privkey-path", Input
        ).value.strip()
        self.query_one("#settings-selection", Static).update("Settings applied")
        self._sessions.refresh_sessions_from_oci()

    def action_new_port_forward(self) -> None:
        self.push_screen(
            CreateSessionModal(
                SessionType.PORT_FORWARDING,
                self._state.selected_target_ip,
            ),
            lambda data: self._sessions.create_session_from_form(
                SessionType.PORT_FORWARDING, data
            ),
        )

    def action_new_managed_ssh(self) -> None:
        self.push_screen(
            CreateSessionModal(
                SessionType.MANAGED_SSH,
                self._state.selected_target_ip,
            ),
            lambda data: self._sessions.create_session_from_form(
                SessionType.MANAGED_SSH,
                data,
            ),
        )

    def action_new_socks5(self) -> None:
        self.push_screen(
            CreateSessionModal(SessionType.SOCKS5, self._state.selected_target_ip),
            lambda data: self._sessions.create_session_from_form(SessionType.SOCKS5, data),
        )

    def action_delete_session(self) -> None:
        self._sessions.delete_selected_session()

    def action_refresh(self) -> None:
        selected_profile = self._state.selected_profile_name
        if not selected_profile:
            self.query_one("#session-selection", Static).update(
                "Select a profile before refreshing"
            )
            return

        self._profile_targets.load_targets_for_profile(selected_profile)
        if self._profile_targets.ensure_single_bastion(selected_profile):
            self._sessions.refresh_sessions_from_oci()

    def action_edit_and_execute(self) -> None:
        selected = self._sessions.selected_session()
        if selected is None:
            return
        if selected.state != SessionState.ACTIVE:
            self.query_one("#session-selection", Static).update(
                f"Session {selected.ocid} is not ACTIVE ({selected.state.value})"
            )
            return
        command = self._sessions.build_session_command(selected)
        self.push_screen(CommandEditModal(command), self._execute_ssh_command)

    def action_execute_direct(self) -> None:
        selected = self._sessions.selected_session()
        if selected is None:
            return
        if selected.state != SessionState.ACTIVE:
            self.query_one("#session-selection", Static).update(
                f"Session {selected.ocid} is not ACTIVE ({selected.state.value})"
            )
            return
        command = self._sessions.build_session_command(selected)
        self.push_screen(CommandEditModal(command), self._execute_ssh_command)

    def _execute_ssh_command(self, command: str | None) -> None:
        if not command:
            return
        print(f"Executing SSH command: {command}")
        with self.suspend():
            subprocess.run(shlex.split(command), check=False)  # noqa: S603
        print(f"SSH command: {command}")
        self.exit("thanks for using obassh")



def run() -> None:
    """Run the Textual application."""
    result = ObasshApp().run()
    if result:
        print(result)
