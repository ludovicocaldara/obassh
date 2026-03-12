"""Controller for session-related UI flows."""

from __future__ import annotations

import os
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast

from textual.widgets import DataTable, Input, Static

from obassh.app.models import AppState
from obassh.app.services.ssh_command_builder import (
    apply_identity_to_command,
    extract_local_port,
    session_command,
)
from obassh.domain.enums import NodeType, SessionState, SessionType
from obassh.domain.errors import OciApiError
from obassh.domain.models import BastionSession, OciProfileRef, TargetNode
from obassh.providers.oci import OciBastionSessionProvider
from obassh.services.session_service import SessionService

if TYPE_CHECKING:
    from textual.app import App


class SessionController:
    """Manage session table, selection and CRUD actions."""

    def __init__(
        self,
        app: App[str | None],
        state: AppState,
        session_service: SessionService,
        provider: OciBastionSessionProvider,
        selected_profile_getter: Callable[[], OciProfileRef | None],
        ensure_single_bastion: Callable[[str], bool],
    ) -> None:
        self._app = app
        self._state = state
        self._session_service = session_service
        self._provider = provider
        self._selected_profile = selected_profile_getter
        self._ensure_single_bastion = ensure_single_bastion

    def load_session_table(self) -> None:
        table = cast(DataTable[str], self._app.query_one("#session-table", DataTable))
        table.border_title = "Bastion Sessions"
        table.cursor_type = "row"
        table.add_columns(
            "Type",
            "Target Resource",
            "Target Port",
            "Local Port",
            "State",
            "SSH session",
            "TTL",
            "Created",
            "PID",
            "Logfile",
        )

    def refresh_sessions_from_oci(self) -> None:
        profile = self._selected_profile()
        if profile is None or not self._state.selected_bastion_ocid:
            return
        try:
            sessions = self._session_service.list_sessions(
                profile,
                self._state.selected_bastion_ocid,
            )
            self._state.sessions = [
                session for session in sessions if session.state != SessionState.DELETED
            ]
        except OciApiError as exc:  # pragma: no cover
            self._app.query_one("#session-selection", Static).update(
                f"Failed loading sessions: {exc}"
            )
            return
        self.refresh_session_rows()

    def refresh_session_rows(self) -> None:
        table = cast(DataTable[str], self._app.query_one("#session-table", DataTable))
        table.clear(columns=False)
        for session in self._state.sessions:
            ssh_running = self._is_ssh_session_running(session.ocid)
            local_port = "-"
            if session.session_type is SessionType.PORT_FORWARDING:
                local_port = str(
                    extract_local_port(
                        session.ssh_metadata.get("command", ""),
                        session.target_port,
                    )
                )
                if session.ssh_metadata.get("local_port"):
                    local_port = session.ssh_metadata["local_port"]
            ttl = max(session.ttl_seconds, 0)
            created = session.started_at
            if created is None:
                created_label = "-"
            else:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                created_label = created.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            table.add_row(
                session.session_type.value,
                session.target_resource,
                str(session.target_port),
                local_port,
                session.state.value,
                "running" if ssh_running else "not running",
                str(ttl),
                created_label,
                str(session.pid) if session.pid else "-",
                session.logfile_path if session.logfile_path else "-",
                key=session.ocid,
            )

    def _is_ssh_session_running(self, session_id: str) -> bool:
        pid = self._state.ssh_processes.get(session_id)
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            self._state.ssh_processes.pop(session_id, None)
            return False
        return True

    def selected_session(self) -> BastionSession | None:
        if self._state.selected_session_id is None:
            return None
        return next(
            (
                session
                for session in self._state.sessions
                if session.ocid == self._state.selected_session_id
            ),
            None,
        )

    def build_session_command(self, session: BastionSession) -> str:
        private_key_path = self._app.query_one("#settings-privkey-path", Input).value.strip()
        return session_command(
            session,
            private_key_path,
            self._selected_profile(),
            self._provider,
        )

    def update_selected_session_label(self, session_id: str) -> None:
        self._state.selected_session_id = session_id
        selected = self.selected_session()
        if selected is None:
            self._app.query_one("#session-selection", Static).update(
                f"Selected session: {session_id}"
            )
            return
        command = self.build_session_command(selected)
        self._app.query_one("#session-selection", Static).update(
            f"Selected session: {session_id}\nSSH command: {command}"
        )

    def create_session_from_form(
        self,
        session_type: SessionType,
        form_data: dict[str, str] | None,
    ) -> None:
        if not form_data:
            return
        profile = self._selected_profile()
        if profile is None:
            self._app.query_one("#session-selection", Static).update("No OCI profile selected")
            return
        target = form_data["target"] or "unknown"
        pubkey_path = self._app.query_one("#settings-pubkey-path", Input).value.strip()
        private_key_path = self._app.query_one("#settings-privkey-path", Input).value.strip()
        if not self._state.selected_bastion_ocid and not self._ensure_single_bastion(profile.name):
            return
        key_validation_error = self._missing_key_message(pubkey_path, private_key_path)
        if key_validation_error is not None:
            self._app.query_one("#session-selection", Static).update(key_validation_error)
            return

        try:
            port = int(form_data["port"] or "22")
            ttl = int(form_data["ttl"] or "7200")
        except ValueError:
            self._app.query_one("#session-selection", Static).update(
                "Invalid numeric input for port/ttl"
            )
            return

        try:
            pub_key = Path(pubkey_path).expanduser().read_text(encoding="utf-8").strip()
            created = self._session_service.open_session(
                profile=profile,
                bastion_ocid=self._state.selected_bastion_ocid,
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
        except OciApiError as exc:  # pragma: no cover
            self._app.query_one("#session-selection", Static).update(
                f"Session creation failed: {exc}"
            )
            return

        command = created.ssh_metadata.get("command", f"ssh opc@{created.target_resource}")
        created.ssh_metadata["command"] = apply_identity_to_command(command, private_key_path)

        self.refresh_sessions_from_oci()
        self.update_selected_session_label(created.ocid)

    def delete_selected_session(self) -> None:
        selected = self.selected_session()
        if selected is None:
            return
        profile = self._selected_profile()
        if profile is None:
            return
        try:
            self._session_service.close_session(profile, selected.ocid)
            self.refresh_sessions_from_oci()
            self._app.query_one("#session-selection", Static).update(
                f"Deleted session: {selected.ocid}"
            )
        except OciApiError as exc:  # pragma: no cover
            self._app.query_one("#session-selection", Static).update(f"Delete failed: {exc}")

    def _missing_key_message(self, public_key: str, private_key: str) -> str | None:
        if not public_key:
            return "SSH public key path is required"
        if not private_key:
            return "SSH private key path is required"
        return None
