"""Controller for profile and target related UI flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.widgets import DataTable, Input, Static

from obassh.app.models import AppState
from obassh.domain.models import OciProfileRef
from obassh.providers.oci.inventory_provider import OciInventoryProvider

if TYPE_CHECKING:
    from textual.app import App


class ProfileTargetsController:
    """Manage profile selection, bastion resolution and target tables."""

    def __init__(self, app: App[str | None], state: AppState, inventory: OciInventoryProvider) -> None:
        self._app = app
        self._state = state
        self._inventory = inventory

    def selected_profile(self) -> OciProfileRef | None:
        return next((p for p in self._state.profiles if p.name == self._state.selected_profile_name), None)

    def ensure_single_bastion(self, profile_name: str) -> bool:
        bastion_override = self._app.query_one("#settings-bastion-ocid", Input).value.strip()
        if bastion_override:
            self._state.selected_bastion_ocid = bastion_override
            return True
        compartment_id = self._inventory.default_compartment_id()
        if not compartment_id:
            self._app.query_one("#session-selection", Static).update("No compartment set for bastion discovery")
            return False
        try:
            bastions = self._inventory.list_bastions(profile_name, compartment_id)
        except Exception as exc:  # pragma: no cover
            self._app.query_one("#session-selection", Static).update(f"Failed loading bastions: {exc}")
            return False
        if len(bastions) != 1:
            self._app.query_one("#session-selection", Static).update(f"Expected one bastion, found {len(bastions)}")
            return False
        self._state.selected_bastion_ocid = bastions[0]["ocid"]
        self._app.query_one("#settings-bastion-ocid", Input).value = self._state.selected_bastion_ocid
        return True

    def load_target_tables(self) -> None:
        compute_table = cast(DataTable[str], self._app.query_one("#targets-compute-table", DataTable))
        compute_table.border_title = "Compute Nodes"
        compute_table.cursor_type = "row"
        compute_table.add_columns("Name", "State", "DNS Name", "Private IP")

        db_table = cast(DataTable[str], self._app.query_one("#targets-db-table", DataTable))
        db_table.border_title = "DBSystem DB Nodes"
        db_table.cursor_type = "row"
        db_table.add_columns("DBSystem", "Version", "DBNode", "State", "DNS Name", "Private IP")

    def load_profiles(self) -> None:
        profiles_table = cast(DataTable[str], self._app.query_one("#profiles-table", DataTable))
        profiles_table.border_title = "Select an OCI Profile"
        profiles_table.cursor_type = "row"
        profiles_table.add_columns("Profile", "Region", "Tenancy OCID", "Compartment OCID")

        try:
            self._state.profiles = self._inventory.list_oci_profiles()
        except Exception as exc:  # pragma: no cover
            self._app.query_one("#profiles-selection", Static).update(f"Failed to load profiles: {exc}")
            return

        for profile in self._state.profiles:
            profiles_table.add_row(profile.name, profile.region, profile.tenancy_ocid, profile.compartment_ocid)

    def load_targets_for_profile(self, profile_name: str) -> None:
        compartment_id = self._inventory.default_compartment_id()
        compute_table = cast(DataTable[str], self._app.query_one("#targets-compute-table", DataTable))
        db_table = cast(DataTable[str], self._app.query_one("#targets-db-table", DataTable))
        compute_table.clear(columns=False)
        db_table.clear(columns=False)

        if not compartment_id:
            self._app.query_one("#targets-selection", Static).update("No compartment set. Use COMPID env var or .oci/oci_cli_rc")
            return

        try:
            compute_nodes = self._inventory.list_compute_nodes(profile_name, compartment_id)
            db_nodes = self._inventory.list_db_system_nodes(profile_name, compartment_id)
        except Exception as exc:  # pragma: no cover
            self._app.query_one("#targets-selection", Static).update(f"Failed to load targets: {exc}")
            return

        for row in compute_nodes:
            compute_table.add_row(row["name"], row["state"], row["dns_name"], row["private_ip"])
        for row in db_nodes:
            db_table.add_row(row["dbsystem"], row["version"], row["dbnode"], row["state"], row["dns_name"], row["private_ip"])

        self._app.query_one("#targets-selection", Static).update(
            f"Loaded {len(compute_nodes)} compute nodes and {len(db_nodes)} DB nodes"
        )
