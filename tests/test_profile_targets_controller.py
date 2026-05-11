from typing import Any, cast

from textual.app import App

from obassh.app.controllers.profile_targets_controller import ProfileTargetsController
from obassh.app.models import AppState
from obassh.domain.models import OciProfileRef
from obassh.providers.oci.inventory_provider import OciInventoryProvider


class _DummyApp:
    pass


class _DummyInventory:
    def default_compartment_id(self) -> str:
        return "default-compartment"


class _FakeTable:
    def __init__(self) -> None:
        self.border_title = ""
        self.cursor_type = ""
        self.columns: list[tuple[str, ...]] = []
        self.rows: list[tuple[str, ...]] = []
        self.clear_calls = 0

    def add_columns(self, *columns: str) -> None:
        self.columns.append(columns)

    def add_row(self, *values: str) -> None:
        self.rows.append(values)

    def clear(self, *, columns: bool) -> None:
        assert columns is False
        self.clear_calls += 1


class _FakeStatic:
    def __init__(self) -> None:
        self.value = ""

    def update(self, value: str) -> None:
        self.value = value


class _TargetsApp:
    def __init__(self) -> None:
        self.compute_table = _FakeTable()
        self.db_table = _FakeTable()
        self.targets_selection = _FakeStatic()

    def query_one(self, selector: str, _widget_type: object) -> object:
        widgets: dict[str, object] = {
            "#targets-compute-table": self.compute_table,
            "#targets-db-table": self.db_table,
            "#targets-selection": self.targets_selection,
        }
        return widgets[selector]


class _TargetsInventory:
    def default_compartment_id(self) -> str:
        return "default-compartment"

    def list_compute_nodes(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        assert profile_name == "DEFAULT"
        assert compartment_ocid == "profile-compartment"
        return [
            {
                "name": "compute-1",
                "state": "RUNNING",
                "dns_name": "compute-1",
                "private_ip": "10.0.0.10",
                "public_ip": "203.0.113.10",
            }
        ]

    def list_db_system_nodes(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        assert profile_name == "DEFAULT"
        assert compartment_ocid == "profile-compartment"
        return [
            {
                "dbsystem": "db-system-1",
                "version": "19c",
                "dbnode": "db-node-1",
                "state": "AVAILABLE",
                "dns_name": "db-node-1",
                "private_ip": "10.0.1.10",
                "public_ip": "203.0.113.20",
            }
        ]


def test_compartment_id_for_profile_uses_selected_profile_compartment() -> None:
    state = AppState(
        profiles=[
            OciProfileRef("DEFAULT", "eu-zurich-1", "tenancy", "default-compartment"),
            OciProfileRef("MAA", "eu-madrid-1", "tenancy", "maa-compartment"),
        ],
        selected_profile_name="MAA",
    )
    controller = ProfileTargetsController(
        app=cast(App[str | None], _DummyApp()),
        state=state,
        inventory=cast(OciInventoryProvider, _DummyInventory()),
    )

    compartment_id = cast(Any, controller)._compartment_id_for_profile("MAA")

    assert compartment_id == "maa-compartment"


def test_compartment_id_for_profile_falls_back_to_default_compartment() -> None:
    state = AppState(
        profiles=[OciProfileRef("MAA", "eu-madrid-1", "tenancy")],
        selected_profile_name="MAA",
    )
    controller = ProfileTargetsController(
        app=cast(App[str | None], _DummyApp()),
        state=state,
        inventory=cast(OciInventoryProvider, _DummyInventory()),
    )

    compartment_id = cast(Any, controller)._compartment_id_for_profile("MAA")

    assert compartment_id == "default-compartment"


def test_load_target_tables_adds_public_ip_columns() -> None:
    app = _TargetsApp()
    controller = ProfileTargetsController(
        app=cast(App[str | None], app),
        state=AppState(),
        inventory=cast(OciInventoryProvider, _TargetsInventory()),
    )

    controller.load_target_tables()

    assert app.compute_table.columns == [
        ("Name", "State", "DNS Name", "Private IP", "Public IP")
    ]
    assert app.db_table.columns == [
        ("DBSystem", "Version", "DBNode", "State", "DNS Name", "Private IP", "Public IP")
    ]


def test_load_targets_for_profile_prints_public_ips_when_set() -> None:
    app = _TargetsApp()
    state = AppState(
        profiles=[OciProfileRef("DEFAULT", "eu-zurich-1", "tenancy", "profile-compartment")]
    )
    controller = ProfileTargetsController(
        app=cast(App[str | None], app),
        state=state,
        inventory=cast(OciInventoryProvider, _TargetsInventory()),
    )

    controller.load_targets_for_profile("DEFAULT")

    assert app.compute_table.rows == [
        ("compute-1", "RUNNING", "compute-1", "10.0.0.10", "203.0.113.10")
    ]
    assert app.db_table.rows == [
        (
            "db-system-1",
            "19c",
            "db-node-1",
            "AVAILABLE",
            "db-node-1",
            "10.0.1.10",
            "203.0.113.20",
        )
    ]
    assert app.targets_selection.value == "Loaded 1 compute nodes and 1 DB nodes"