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
    ListItem,
    ListView,
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
                    yield Static("Actions", id="session-actions-title")
                    yield Button("Connect", id="session-connect-btn", variant="success")
                    yield Button("Disconnect", id="session-disconnect-btn", variant="error")
                    yield Static("Last action: none", id="session-action-feedback")
                    yield Static("Session State", id="session-state-title")
                    yield Static("Not connected", id="session-state-value")
                    yield Static("Expires In", id="session-expiry-title")
                    yield Static("--:--", id="session-expiry-value")
                    yield Static("Command Preview", id="session-command-title")
                    yield Static(
                        "ssh -i <key> -J <bastion> opc@<target>",
                        id="session-command-value",
                    )
                with TabPane("Targets", id="targets"):
                    yield Static("Compute Nodes", id="targets-compute-title")
                    yield DataTable(id="targets-compute-table")
                    yield Static("DBSystem DB Nodes", id="targets-db-title")
                    yield DataTable(id="targets-db-table")
                    yield Static("No target selected", id="targets-selection")
                with TabPane("Profiles", id="profiles"):
                    yield Static("Select an OCI profile", id="profiles-title")
                    yield ListView(id="profiles-list")
                    yield Static("Hint: ↑/↓ to navigate, Enter to select", id="profiles-hint")
                    yield Static("No profile selected", id="profiles-selection")
        yield Footer()

    def on_mount(self) -> None:
        """Load profiles and initialize target tables."""
        self._setup_target_tables()
        self._load_profiles()

    def _setup_target_tables(self) -> None:
        compute_table = cast(DataTable[str], self.query_one("#targets-compute-table", DataTable))
        compute_table.cursor_type = "row"
        compute_table.add_columns("Name", "State", "DNS Name", "Private IP")

        db_table = cast(DataTable[str], self.query_one("#targets-db-table", DataTable))
        db_table.cursor_type = "row"
        db_table.add_columns("DBSystem", "Version", "DBNode", "State", "DNS Name", "Private IP")

    def _load_profiles(self) -> None:
        profiles_list = self.query_one("#profiles-list", ListView)
        profiles_list.clear()
        self._profiles = []

        try:
            self._profiles = self._inventory.list_oci_profiles()
        except Exception as exc:  # pragma: no cover - runtime environment dependent
            self.query_one("#profiles-selection", Static).update(f"Failed to load profiles: {exc}")
            return

        for profile in self._profiles:
            label = f"{profile.name} | {profile.region} | tenancy={profile.tenancy_ocid}"
            profiles_list.append(ListItem(Label(label), name=profile.name))
            if profile.name == "DEFAULT":
                self._selected_profile_name = "DEFAULT"
                self.query_one("#profiles-selection", Static).update("Selected profile: DEFAULT")
                self._load_targets_for_profile("DEFAULT")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Update selected hints when user activates a list item."""
        if event.list_view.id == "profiles-list":
            selected_profile = event.item.name or "<unknown>"
            self._selected_profile_name = selected_profile
            self.query_one("#profiles-selection", Static).update(
                f"Selected profile: {selected_profile}"
            )
            self._load_targets_for_profile(selected_profile)
            return

    def _load_targets_for_profile(self, profile_name: str) -> None:
        compartment_id = self._inventory.default_compartment_id()
        compute_table = cast(DataTable[str], self.query_one("#targets-compute-table", DataTable))
        db_table = cast(DataTable[str], self.query_one("#targets-db-table", DataTable))
        compute_table.clear(columns=False)
        db_table.clear(columns=False)

        if not compartment_id:
            self.query_one("#targets-selection", Static).update("COMPID env var is not set")
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
        """Handle row selection for both target tables."""
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle placeholder session actions."""
        if event.button.id == "session-connect-btn":
            self.query_one("#session-action-feedback", Static).update("Last action: connect")
            self.query_one("#session-state-value", Static).update("Connecting (placeholder)")
            return

        if event.button.id == "session-disconnect-btn":
            self.query_one("#session-action-feedback", Static).update("Last action: disconnect")
            self.query_one("#session-state-value", Static).update("Disconnected (placeholder)")


def run() -> None:
    """Run the Textual application."""
    ObasshApp().run()
