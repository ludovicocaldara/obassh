from __future__ import annotations

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false

import os
from configparser import ConfigParser
from pathlib import Path
from typing import Any, cast

import oci  # type: ignore[import-untyped]

from obassh.domain.errors import OciApiError
from obassh.domain.models import OciProfileRef


class OciInventoryProvider:
    """Read OCI profiles and discover compute / DB System node targets."""

    def __init__(self, config_path: str | None = None, cli_config_path: str | None = None) -> None:
        # .oci/config is used by OCI SDK to read profiles and create clients
        self._config_path = config_path or str(Path.home() / ".oci" / "config")
        # .oci/oci_cli_rc is used by OCI CLI to read compartment for a given profile
        self._cli_config_path = cli_config_path or str(Path.home() / ".oci" / "oci_cli_rc")

    def list_oci_profiles(self) -> list[OciProfileRef]:
        # Source of truth for OCI profile identity data (region/tenancy/user/fingerprint).
        parser = ConfigParser()
        parser.read(self._config_path)
        # Source of truth for default/profile-specific compartment selection.
        cli_parser = ConfigParser()
        cli_parser.read(self._cli_config_path)

        profiles: list[OciProfileRef] = []
        profile_names: list[str] = ["DEFAULT", *list(parser.sections())]

        default_compartment = self._compartment_from_cli_rc(cli_parser, "DEFAULT")

        try:
            for profile_name in profile_names:
                config = cast(
                    dict[str, Any],
                    oci.config.from_file(self._config_path, profile_name),
                )
                # Compartment priority for each profile:
                # 1) COMPID environment variable (highest priority)
                # 2) Profile-specific compartment-id in oci_cli_rc ([PROFILE <name>] or [<name>])
                # 3) DEFAULT compartment-id in oci_cli_rc
                compartment_ocid = (
                    os.getenv("COMPID", "")
                    or self._compartment_from_cli_rc(cli_parser, profile_name)
                    or default_compartment
                )
                profiles.append(
                    OciProfileRef(
                        name=profile_name,
                        region=config.get("region", "unknown"),
                        tenancy_ocid=config.get("tenancy", "unknown"),
                        compartment_ocid=compartment_ocid,
                        user_ocid=config.get("user"),
                        fingerprint=config.get("fingerprint"),
                    )
                )
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to read OCI profiles: {exc}") from exc

        return profiles

    def default_compartment_id(self) -> str:
        """Read compartment from COMPID env var or DEFAULT profile in OCI CLI RC."""
        env_compartment = os.getenv("COMPID", "")
        if env_compartment:
            return env_compartment

        cli_parser = ConfigParser()
        cli_parser.read(self._cli_config_path)
        return self._compartment_from_cli_rc(cli_parser, "DEFAULT")

    def _compartment_from_cli_rc(self, parser: ConfigParser, profile_name: str) -> str:
        for section_name in (profile_name, f"PROFILE {profile_name}"):
            if parser.has_section(section_name):
                compartment_id = parser.get(section_name, "compartment-id", fallback="").strip()
                if compartment_id:
                    return compartment_id
        return ""

    def list_compute_nodes(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        try:
            config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile_name))
            compute_client = oci.core.ComputeClient(config)
            network_client = oci.core.VirtualNetworkClient(config)

            rows: list[dict[str, str]] = []
            instances = cast(
                list[Any],
                compute_client.list_instances(compartment_id=compartment_ocid).data,
            )
            for instance in instances:
                private_ip, dns_name = self._instance_network_info(
                    compute_client,
                    network_client,
                    compartment_ocid,
                    instance.id,
                )
                rows.append(
                    {
                        "name": instance.display_name,
                        "state": str(instance.lifecycle_state),
                        "dns_name": dns_name,
                        "private_ip": private_ip,
                    }
                )
            return rows
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to list compute nodes: {exc}") from exc

    def list_bastions(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        try:
            config = cast(
                dict[str, Any],
                oci.config.from_file(self._config_path, profile_name),
            )
            bastion_client = oci.bastion.BastionClient(config)
            rows: list[dict[str, str]] = []
            bastions = cast(
                list[Any],
                bastion_client.list_bastions(compartment_id=compartment_ocid).data,
            )
            for bastion in bastions:
                rows.append(
                    {
                        "ocid": bastion.id,
                        "name": bastion.name,
                        "state": str(bastion.lifecycle_state),
                    }
                )
            return rows
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to list bastions: {exc}") from exc

    def list_db_system_nodes(
        self,
        profile_name: str,
        compartment_ocid: str,
    ) -> list[dict[str, str]]:
        try:
            config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile_name))
            database_client = oci.database.DatabaseClient(config)
            network_client = oci.core.VirtualNetworkClient(config)

            rows: list[dict[str, str]] = []
            db_systems = cast(
                list[Any],
                database_client.list_db_systems(compartment_id=compartment_ocid).data,
            )
            for db_system in db_systems:
                rows.extend(
                    self._rows_for_db_system(
                        database_client,
                        network_client,
                        compartment_ocid,
                        db_system,
                    )
                )
            return rows
        except Exception as exc:  # pragma: no cover
            raise OciApiError(f"Failed to list DB system nodes: {exc}") from exc

    def _instance_network_info(
        self,
        compute_client: Any,
        network_client: Any,
        compartment_ocid: str,
        instance_id: str,
    ) -> tuple[str, str]:
        private_ip = ""
        dns_name = ""
        vnic_attachments = cast(
            list[Any],
            compute_client.list_vnic_attachments(
                compartment_id=compartment_ocid,
                instance_id=instance_id,
            ).data,
        )
        if vnic_attachments:
            vnic = network_client.get_vnic(vnic_attachments[0].vnic_id).data
            private_ip = vnic.private_ip or ""
            dns_name = vnic.hostname_label or ""
        return private_ip, dns_name

    def _rows_for_db_system(
        self,
        database_client: Any,
        network_client: Any,
        compartment_ocid: str,
        db_system: Any,
    ) -> list[dict[str, str]]:
        db_home = database_client.list_db_homes(
            db_system_id=db_system.id,
            compartment_id=compartment_ocid,
        ).data[0]
        db_nodes = cast(
            list[Any],
            database_client.list_db_nodes(
                compartment_id=compartment_ocid,
                db_system_id=db_system.id,
            ).data,
        )
        rows: list[dict[str, str]] = []
        for index, db_node in enumerate(db_nodes):
            rows.append(
                {
                    "dbsystem": db_system.display_name if index == 0 else "",
                    "version": db_home.db_version if index == 0 else "",
                    "dbnode": db_node.hostname,
                    "state": str(db_node.lifecycle_state),
                    "dns_name": db_node.hostname,
                    "private_ip": self._db_node_private_ip(network_client, db_node),
                }
            )
        return rows

    def _db_node_private_ip(self, network_client: Any, db_node: Any) -> str:
        vnic_id = getattr(db_node, "vnic_id", None)
        if not vnic_id:
            return ""
        vnic = network_client.get_vnic(vnic_id).data
        return vnic.private_ip or ""
