"""Application-level UI state models."""

from __future__ import annotations

from dataclasses import dataclass, field

from obassh.domain.models import BastionSession, OciProfileRef


@dataclass
class AppState:
    """Mutable UI state for the Textual application."""

    profiles: list[OciProfileRef] = field(default_factory=list)
    selected_profile_name: str = ""
    selected_bastion_ocid: str = ""
    selected_target_ip: str = ""
    preferred_public_key_path: str = ""
    preferred_private_key_path: str = ""
    sessions: list[BastionSession] = field(default_factory=list)
    selected_session_id: str | None = None
