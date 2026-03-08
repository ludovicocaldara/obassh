"""Main Textual application shell for obassh."""

from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from typing import cast

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Static,
    TabbedContent,
    TabPane,
)

from obassh.domain.models import OciProfileRef
from obassh.providers.oci.inventory_provider import OciInventoryProvider


class ObasshApp(App[None]):
    """Initial application shell with placeholder tabs."""

    TITLE = "obassh"
    SUB_TITLE = "OCI Bastion SSH orchestrator"
    CSS_PATH = "obassh.tcss"

    def __init__(self) -> None:
        super().__init__()
        self._inventory = OciInventoryProvider()
        self._profiles: list[OciProfileRef] = []
        self._selected_profile_name = ""

    def compose(self) -> ComposeResult:
        """Build the first iterative UI layout."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with TabbedContent(initial="session"):
                with TabPane("Session", id="session"):
                    yield Static("To do", id="session-placeholder")
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
        self._load_target_tables()
        self._load_profiles()

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
            self.query_one("#targets-selection", Static).update(
                f"Selected compute target: {row_values[0]} ({row_values[3]})"
            )
            return

        if event.data_table.id == "targets-db-table":
            self.query_one("#targets-selection", Static).update(
                f"Selected DB node target: {row_values[2]} ({row_values[5]})"
            )

def run() -> None:
    """Run the Textual application."""
    ObasshApp().run()
