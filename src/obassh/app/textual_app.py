"""Main Textual application shell for obassh."""

from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from obassh.domain.enums import NodeType, SessionType
from obassh.domain.models import BastionSession, OciProfileRef, TargetNode
from obassh.providers.oci import OciBastionSessionProvider
from obassh.providers.oci.inventory_provider import OciInventoryProvider
from obassh.services.session_service import SessionService


class CreateSessionModal(ModalScreen[dict[str, str] | None]):
    """Modal form for creating session entries."""

    def __init__(self, session_type: SessionType, initial_target_ip: str = "") -> None:
        super().__init__()
        self._session_type = session_type
        self._initial_target_ip = initial_target_ip

    def compose(self) -> ComposeResult:
        with Container(id="session-modal"):
            yield Label(f"Create {self._session_type.value} session", id="session-modal-title")
            yield Input(value=self._initial_target_ip, placeholder="Target IP / Hostname", id="session-target")
            yield Input(value="22", placeholder="Target Port", id="session-port")
            yield Input(value="3600", placeholder="TTL (seconds)", id="session-ttl")
            yield Input(placeholder="Bastion OCID", id="session-bastion-ocid")
            yield Input(placeholder="SSH public key path", id="session-pubkey-path")
            yield Input(placeholder="SSH command (optional override)", id="session-command")
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
        bastion_ocid = self.query_one("#session-bastion-ocid", Input).value.strip()
        pubkey_path = self.query_one("#session-pubkey-path", Input).value.strip()
        command = self.query_one("#session-command", Input).value.strip()
        self.dismiss(
            {
                "target": target,
                "port": port,
                "ttl": ttl,
                "bastion_ocid": bastion_ocid,
                "pubkey_path": pubkey_path,
                "command": command,
            }
        )


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


class ObasshApp(App[str | None]):
    """Initial application shell with placeholder tabs."""

    TITLE = "obassh"
    SUB_TITLE = "OCI Bastion SSH orchestrator"
    CSS_PATH = "obassh.tcss"
    BINDINGS = [
        ("f", "new_port_forward", "New Port-Forward"),
        ("s", "new_managed_ssh", "New Managed SSH"),
        ("S", "new_sock5", "New SOCK5"),
        ("d", "delete_session", "Delete session"),
        ("enter", "edit_and_execute", "Edit+Execute command"),
        ("x", "execute_direct", "Execute command"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._inventory = OciInventoryProvider()
        self._session_service = SessionService(OciBastionSessionProvider())
        self._profiles: list[OciProfileRef] = []
        self._selected_profile_name = ""
        self._selected_bastion_ocid = ""
        self._selected_target_ip = ""
        self._sessions: list[BastionSession] = []
        self._selected_session_id: str | None = None

    def compose(self) -> ComposeResult:
        """Build the first iterative UI layout."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with TabbedContent(initial="session"):
                with TabPane("Session", id="session"):
                    yield DataTable(id="session-table")
                    yield Static(
                        "f: Port-Forward | s: Managed SSH | S: SOCK5 | d: delete | Enter: edit+execute | x: execute",
                        id="session-hint",
                    )
                    yield Static("No session selected", id="session-selection")
                with TabPane("Targets", id="targets"):
                    yield DataTable(id="targets-compute-table")
                    yield DataTable(id="targets-db-table")
                    yield Static("↑/↓ to navigate, Enter to select", id="targets-hint")
                    yield Static("No target selected", id="targets-selection")
                with TabPane("Profiles", id="profiles"):
                    yield DataTable(id="profiles-table")
                    yield Static("↑/↓ to navigate, Enter to select", id="profiles-hint")
                    yield Static("No profile selected", id="profiles-selection")
        yield Footer()

    def on_mount(self) -> None:
        """Load profiles and initialize target tables."""
        self._load_session_table()
        self.set_interval(1.0, self._refresh_session_rows)
        self._load_target_tables()
        self._load_profiles()

    def _selected_profile(self) -> OciProfileRef | None:
        return next((p for p in self._profiles if p.name == self._selected_profile_name), None)

    def _refresh_sessions_from_oci(self) -> None:
        profile = self._selected_profile()
        if profile is None or not self._selected_bastion_ocid:
            return
        try:
            self._sessions = self._session_service.list_sessions(profile, self._selected_bastion_ocid)
        except Exception as exc:  # pragma: no cover - runtime env dependent
            self.query_one("#session-selection", Static).update(f"Failed loading sessions: {exc}")
            return
        self._refresh_session_rows()

    def _load_session_table(self) -> None:
        table = cast(DataTable[str], self.query_one("#session-table", DataTable))
        table.border_title = "Bastion Sessions"
        table.cursor_type = "row"
        table.add_columns("Type", "Target Resource", "Target Port", "State", "TTL", "Remaining time")

    def _load_target_tables(self) -> None:
        compute_table = cast(DataTable[str], self.query_one("#targets-compute-table", DataTable))
        compute_table.border_title = "Compute Nodes"
        compute_table.cursor_type = "row"
        compute_table.add_columns("Name", "State", "DNS Name", "Private IP")

        db_table = cast(DataTable[str], self.query_one("#targets-db-table", DataTable))
        db_table.border_title = "DBSystem DB Nodes"
        db_table.cursor_type = "row"
        db_table.add_columns("DBSystem", "Version", "DBNode", "State", "DNS Name", "Private IP")

    def _load_profiles(self) -> None:
        profiles_table = cast(DataTable[str], self.query_one("#profiles-table", DataTable))
        profiles_table.border_title = "Select an OCI Profile"
        profiles_table.cursor_type = "row"
        profiles_table.add_columns("Profile", "Region", "Tenancy OCID", "Compartment OCID")

        try:
            self._profiles = self._inventory.list_oci_profiles()
        except Exception as exc:  # pragma: no cover - runtime environment dependent
            self.query_one("#profiles-selection", Static).update(f"Failed to load profiles: {exc}")
            return

        for profile in self._profiles:
            profiles_table.add_row(profile.name, profile.region, profile.tenancy_ocid, profile.compartment_ocid)
            if profile.name == "DEFAULT":
                self._selected_profile_name = "DEFAULT"
                self.query_one("#profiles-selection", Static).update("Selected profile: DEFAULT")
                self._load_targets_for_profile("DEFAULT")

    def _load_targets_for_profile(self, profile_name: str) -> None:
        compartment_id = self._inventory.default_compartment_id()
        compute_table = cast(DataTable[str], self.query_one("#targets-compute-table", DataTable))
        db_table = cast(DataTable[str], self.query_one("#targets-db-table", DataTable))
        compute_table.clear(columns=False)
        db_table.clear(columns=False)

        if not compartment_id:
            self.query_one("#targets-selection", Static).update("No compartment set. Use COMPID env var or .oci/oci_cli_rc")
            return

        try:
            compute_nodes = self._inventory.list_compute_nodes(profile_name, compartment_id)
            db_nodes = self._inventory.list_db_system_nodes(profile_name, compartment_id)
        except Exception as exc:  # pragma: no cover - runtime environment dependent
            self.query_one("#targets-selection", Static).update(f"Failed to load targets: {exc}")
            return

        for row in compute_nodes:
            compute_table.add_row(row["name"], row["state"], row["dns_name"], row["private_ip"])

        for row in db_nodes:
            db_table.add_row(
                row["dbsystem"],
                row["version"],
                row["dbnode"],
                row["state"],
                row["dns_name"],
                row["private_ip"],
            )

        self.query_one("#targets-selection", Static).update(
            f"Loaded {len(compute_nodes)} compute nodes and {len(db_nodes)} DB nodes"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection for profiles and target tables."""
        if event.data_table.id == "session-table":
            session_id = event.row_key.value
            if session_id is not None:
                self._update_selected_session_label(session_id)
            return

        if event.data_table.id == "profiles-table":
            row_values = cast(list[str], event.data_table.get_row(event.row_key))
            selected_profile = row_values[0] if row_values else "<unknown>"
            self._selected_profile_name = selected_profile
            self.query_one("#profiles-selection", Static).update(
                f"Selected profile: {selected_profile}"
            )
            self._load_targets_for_profile(selected_profile)
            return

        row_values = cast(list[str], event.data_table.get_row(event.row_key))
        if event.data_table.id == "targets-compute-table":
            self._selected_target_ip = row_values[3]
            self.query_one("#targets-selection", Static).update(
                f"Selected compute target: {row_values[0]} ({row_values[3]})"
            )
            return

        if event.data_table.id == "targets-db-table":
            self._selected_target_ip = row_values[5]
            self.query_one("#targets-selection", Static).update(
                f"Selected DB node target: {row_values[2]} ({row_values[5]})"
            )

    def _refresh_session_rows(self) -> None:
        table = cast(DataTable[str], self.query_one("#session-table", DataTable))
        table.clear(columns=False)
        now = datetime.now(timezone.utc)
        for session in self._sessions:
            started = session.started_at or now
            ttl = max(session.ttl_seconds, 0)
            remaining = max(0, int((started + timedelta(seconds=ttl) - now).total_seconds()))
            rem_mm = remaining // 60
            rem_ss = remaining % 60
            table.add_row(
                session.session_type.value,
                session.target_resource,
                str(session.target_port),
                session.state.value,
                str(ttl),
                f"{rem_mm:02}:{rem_ss:02}",
                key=session.ocid,
            )

    def _selected_session(self) -> BastionSession | None:
        if self._selected_session_id is None:
            return None
        return next((session for session in self._sessions if session.ocid == self._selected_session_id), None)

    def _update_selected_session_label(self, session_id: str) -> None:
        self._selected_session_id = session_id
        self.query_one("#session-selection", Static).update(f"Selected session: {session_id}")

    def _create_session_from_form(self, session_type: SessionType, form_data: dict[str, str] | None) -> None:
        if not form_data:
            return
        profile = self._selected_profile()
        if profile is None:
            self.query_one("#session-selection", Static).update("No OCI profile selected")
            return
        target = form_data["target"] or "unknown"
        bastion_ocid = form_data.get("bastion_ocid", "").strip()
        pubkey_path = form_data.get("pubkey_path", "").strip()
        if not bastion_ocid:
            self.query_one("#session-selection", Static).update("Bastion OCID is required")
            return
        if not pubkey_path:
            self.query_one("#session-selection", Static).update("SSH public key path is required")
            return
        self._selected_bastion_ocid = bastion_ocid
        try:
            port = int(form_data["port"] or "22")
            ttl = int(form_data["ttl"] or "3600")
        except ValueError:
            self.query_one("#session-selection", Static).update("Invalid numeric input for port/ttl")
            return
        try:
            pub_key = Path(pubkey_path).expanduser().read_text(encoding="utf-8").strip()
            created = self._session_service.open_session(
                profile=profile,
                bastion_ocid=bastion_ocid,
                target=TargetNode(
                    id=target,
                    node_type=NodeType.CUSTOM,
                    display_name=target,
                    compartment_ocid=profile.compartment_ocid,
                    ip_or_fqdn=target,
                ),
                ssh_public_key=pub_key,
                ttl_seconds=ttl,
                session_type=session_type,
                target_port=port,
            )
        except Exception as exc:  # pragma: no cover - runtime env dependent
            self.query_one("#session-selection", Static).update(f"Session creation failed: {exc}")
            return

        command = form_data["command"].strip()
        if command:
            created.ssh_metadata["command"] = command

        self._refresh_sessions_from_oci()
        self._update_selected_session_label(created.ocid)

    def action_new_port_forward(self) -> None:
        self.push_screen(
            CreateSessionModal(SessionType.PORT_FORWARDING, self._selected_target_ip),
            lambda data: self._create_session_from_form(SessionType.PORT_FORWARDING, data),
        )

    def action_new_managed_ssh(self) -> None:
        self.push_screen(
            CreateSessionModal(SessionType.MANAGED_SSH, self._selected_target_ip),
            lambda data: self._create_session_from_form(SessionType.MANAGED_SSH, data),
        )

    def action_new_sock5(self) -> None:
        self.push_screen(
            CreateSessionModal(SessionType.SOCK5, self._selected_target_ip),
            lambda data: self._create_session_from_form(SessionType.SOCK5, data),
        )

    def action_delete_session(self) -> None:
        selected = self._selected_session()
        if selected is None:
            return
        profile = self._selected_profile()
        if profile is None:
            return
        try:
            self._session_service.close_session(profile, selected.ocid)
            self._refresh_sessions_from_oci()
            self.query_one("#session-selection", Static).update(f"Deleted session: {selected.ocid}")
        except Exception as exc:  # pragma: no cover - runtime env dependent
            self.query_one("#session-selection", Static).update(f"Delete failed: {exc}")

    def action_edit_and_execute(self) -> None:
        selected = self._selected_session()
        if selected is None:
            return
        command = selected.ssh_metadata.get("command", f"ssh opc@{selected.target_resource}")
        self.push_screen(CommandEditModal(command), self._execute_ssh_command)

    def action_execute_direct(self) -> None:
        selected = self._selected_session()
        if selected is None:
            return
        command = selected.ssh_metadata.get("command", f"ssh opc@{selected.target_resource}")
        self._execute_ssh_command(command)

    def _execute_ssh_command(self, command: str | None) -> None:
        if not command:
            return
        with self.suspend():
            subprocess.run(shlex.split(command), check=False)  # noqa: S603
        self.exit("thanks for using obassh")

def run() -> None:
    """Run the Textual application."""
    result = ObasshApp().run()
    if result:
        print(result)
