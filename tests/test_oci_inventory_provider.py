import os
from configparser import ConfigParser
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import patch

from obassh.providers.oci.inventory_provider import OciInventoryProvider


def test_list_oci_profiles_uses_profile_specific_cli_rc_compartment(tmp_path: Path) -> None:
    config_path = tmp_path / "config"
    config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "region = eu-zurich-1",
                "[PHX]",
                "region = us-phoenix-1",
                "[MAA]",
                "region = eu-madrid-1",
            ]
        )
    )
    cli_config_path = tmp_path / "oci_cli_rc"
    cli_config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "compartment-id = default-compartment",
                "[PHX]",
                "compartment-id = phx-compartment",
                "[MAA]",
                "compartment-id = maa-compartment",
            ]
        )
    )
    provider = OciInventoryProvider(str(config_path), str(cli_config_path))

    def fake_from_file(_path: str, profile_name: str) -> dict[str, str]:
        return {
            "region": f"region-{profile_name}",
            "tenancy": f"tenancy-{profile_name}",
        }

    with (
        patch.dict(os.environ, {"COMPID": ""}),
        patch(
            "obassh.providers.oci.inventory_provider.oci.config.from_file",
            side_effect=fake_from_file,
        ),
    ):
        profiles = provider.list_oci_profiles()

    compartments_by_profile = {profile.name: profile.compartment_ocid for profile in profiles}
    assert compartments_by_profile == {
        "DEFAULT": "default-compartment",
        "PHX": "phx-compartment",
        "MAA": "maa-compartment",
    }


def test_list_oci_profiles_uses_profile_prefixed_cli_rc_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config"
    config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "region = eu-zurich-1",
                "[PHX]",
                "region = us-phoenix-1",
                "[MAA]",
                "region = eu-madrid-1",
            ]
        )
    )
    cli_config_path = tmp_path / "oci_cli_rc"
    cli_config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "compartment-id = default-compartment",
                "[PROFILE PHX]",
                "compartment-id = phx-compartment",
                "[PROFILE MAA]",
                "compartment-id = maa-compartment",
            ]
        )
    )
    provider = OciInventoryProvider(str(config_path), str(cli_config_path))

    def fake_from_file(_path: str, profile_name: str) -> dict[str, str]:
        return {
            "region": f"region-{profile_name}",
            "tenancy": f"tenancy-{profile_name}",
        }

    with (
        patch.dict(os.environ, {"COMPID": ""}),
        patch(
            "obassh.providers.oci.inventory_provider.oci.config.from_file",
            side_effect=fake_from_file,
        ),
    ):
        profiles = provider.list_oci_profiles()

    compartments_by_profile = {profile.name: profile.compartment_ocid for profile in profiles}
    assert compartments_by_profile == {
        "DEFAULT": "default-compartment",
        "PHX": "phx-compartment",
        "MAA": "maa-compartment",
    }


def test_profile_compartment_lookup_ignores_inherited_default_section_value() -> None:
    cli_parser = ConfigParser()
    cli_parser.read_string(
        "\n".join(
            [
                "[DEFAULT]",
                "compartment-id = default-compartment",
                "[PHX]",
                "region = us-phoenix-1",
            ]
        )
    )
    provider = OciInventoryProvider()
    compartment_from_cli_rc = cast(
        Callable[[ConfigParser, str], str],
        getattr(cast(Any, provider), "_compartment_from_cli_rc"),
    )

    compartment_id = compartment_from_cli_rc(cli_parser, "PHX")

    assert compartment_id == ""


def test_list_oci_profiles_does_not_show_global_compid_for_every_profile(tmp_path: Path) -> None:
    config_path = tmp_path / "config"
    config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "region = eu-zurich-1",
                "[PHX]",
                "region = us-phoenix-1",
                "[MAA]",
                "region = eu-madrid-1",
            ]
        )
    )
    cli_config_path = tmp_path / "oci_cli_rc"
    cli_config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "compartment-id = default-compartment",
                "[PHX]",
                "compartment-id = phx-compartment",
                "[MAA]",
                "compartment-id = maa-compartment",
            ]
        )
    )
    provider = OciInventoryProvider(str(config_path), str(cli_config_path))

    def fake_from_file(_path: str, profile_name: str) -> dict[str, str]:
        return {
            "region": f"region-{profile_name}",
            "tenancy": f"tenancy-{profile_name}",
        }

    with (
        patch.dict(os.environ, {"COMPID": "forced-global-compartment"}),
        patch(
            "obassh.providers.oci.inventory_provider.oci.config.from_file",
            side_effect=fake_from_file,
        ),
    ):
        profiles = provider.list_oci_profiles()

    compartments_by_profile = {profile.name: profile.compartment_ocid for profile in profiles}
    assert compartments_by_profile == {
        "DEFAULT": "default-compartment",
        "PHX": "phx-compartment",
        "MAA": "maa-compartment",
    }


def test_default_compartment_id_reads_configparser_default_section(tmp_path: Path) -> None:
    cli_config_path = tmp_path / "oci_cli_rc"
    cli_config_path.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "compartment-id = default-compartment",
                "[MAA]",
                "compartment-id = maa-compartment",
            ]
        )
    )
    provider = OciInventoryProvider(cli_config_path=str(cli_config_path))

    with patch.dict(os.environ, {"COMPID": ""}):
        assert provider.default_compartment_id() == "default-compartment"


def test_instance_network_info_includes_public_ip_when_set() -> None:
    provider = OciInventoryProvider()

    def list_vnic_attachments(**_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(vnic_id="vnic-1")])

    def get_vnic(_vnic_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            data=SimpleNamespace(
                private_ip="10.0.0.10",
                public_ip="203.0.113.10",
                hostname_label="compute-1",
            )
        )

    compute_client = SimpleNamespace(
        list_vnic_attachments=list_vnic_attachments
    )
    network_client = SimpleNamespace(get_vnic=get_vnic)
    instance_network_info = cast(
        Callable[[Any, Any, str, str], tuple[str, str, str]],
        getattr(cast(Any, provider), "_instance_network_info"),
    )

    private_ip, public_ip, dns_name = instance_network_info(
        compute_client,
        network_client,
        "compartment",
        "instance-1",
    )

    assert private_ip == "10.0.0.10"
    assert public_ip == "203.0.113.10"
    assert dns_name == "compute-1"


def test_db_node_network_info_includes_public_ip_when_set() -> None:
    provider = OciInventoryProvider()
    db_node = SimpleNamespace(vnic_id="vnic-1")

    def get_vnic(_vnic_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            data=SimpleNamespace(private_ip="10.0.1.10", public_ip="203.0.113.20")
        )

    network_client = SimpleNamespace(get_vnic=get_vnic)
    db_node_network_info = cast(
        Callable[[Any, Any], tuple[str, str]],
        getattr(cast(Any, provider), "_db_node_network_info"),
    )

    private_ip, public_ip = db_node_network_info(network_client, db_node)

    assert private_ip == "10.0.1.10"
    assert public_ip == "203.0.113.20"