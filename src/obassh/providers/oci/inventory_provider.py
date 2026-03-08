from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

import os
from configparser import ConfigParser
from pathlib import Path
from typing import Any, cast

import oci  # type: ignore[import-untyped]

from obassh.domain.models import OciProfileRef


class OciInventoryProvider:
    """Read OCI profiles and discover compute / DB System node targets."""

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path or str(Path.home() / ".oci" / "config")

    def list_oci_profiles(self) -> list[OciProfileRef]:
        parser = ConfigParser()
        parser.read(self._config_path)

        profiles: list[OciProfileRef] = []
        profile_names: list[str] = ["DEFAULT", *list(parser.sections())]
        for profile_name in profile_names:
            config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile_name))
            profiles.append(
                OciProfileRef(
                    name=profile_name,
                    region=config.get("region", "unknown"),
                    tenancy_ocid=config.get("tenancy", "unknown"),
                    user_ocid=config.get("user"),
                    fingerprint=config.get("fingerprint"),
                )
            )
        return profiles

    def default_compartment_id(self) -> str:
        """Read the currently selected compartment from COMPID env var."""
        return os.getenv("COMPID", "")

    def list_compute_nodes(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile_name))
        compute_client = oci.core.ComputeClient(config)
        network_client = oci.core.VirtualNetworkClient(config)

        rows: list[dict[str, str]] = []
        instances = cast(
            list[Any],
            compute_client.list_instances(compartment_id=compartment_ocid).data,
        )
        for instance in instances:
            private_ip = ""
            dns_name = ""
            vnic_attachments = cast(
                list[Any],
                compute_client.list_vnic_attachments(
                compartment_id=compartment_ocid,
                instance_id=instance.id,
                ).data,
            )
            if vnic_attachments:
                vnic = network_client.get_vnic(vnic_attachments[0].vnic_id).data
                private_ip = vnic.private_ip or ""
                dns_name = vnic.hostname_label or ""

            rows.append(
                {
                    "name": instance.display_name,
                    "state": str(instance.lifecycle_state),
                    "dns_name": dns_name,
                    "private_ip": private_ip,
                }
            )
        return rows

    def list_db_system_nodes(self, profile_name: str, compartment_ocid: str) -> list[dict[str, str]]:
        config = cast(dict[str, Any], oci.config.from_file(self._config_path, profile_name))
        database_client = oci.database.DatabaseClient(config)

        rows: list[dict[str, str]] = []
        db_systems = cast(
            list[Any],
            database_client.list_db_systems(compartment_id=compartment_ocid).data,
        )
        for db_system in db_systems:
            db_home = database_client.list_db_homes(
                db_system_id=db_system.id, compartment_id=compartment_ocid).data[0]
            db_nodes = cast(
                list[Any],
                database_client.list_db_nodes(
                    compartment_id=compartment_ocid,
                    db_system_id=db_system.id,
                ).data,
            )
            for index, db_node in enumerate(db_nodes):
                vnic_id = getattr(db_node, "vnic_id", None)
                private_ip = ""
                if vnic_id:
                    network_client = oci.core.VirtualNetworkClient(config)
                    vnic = network_client.get_vnic(vnic_id).data
                    private_ip = vnic.private_ip or ""
                rows.append(
                    {
                        "dbsystem": db_system.display_name if index == 0 else "",
                        "version": db_home.db_version if index == 0 else "",
                        "dbnode": db_node.hostname,
                        "state": str(db_node.lifecycle_state),
                        "dns_name": db_node.hostname,
                        "private_ip": private_ip
                    }
                )
        return rows
