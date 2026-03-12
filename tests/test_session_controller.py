from typing import Any, cast

from textual.app import App

from obassh.app.controllers.session_controller import SessionController
from obassh.app.models import AppState
from obassh.domain.enums import SessionState, SessionType
from obassh.domain.models import BastionSession
from obassh.providers.oci import OciBastionSessionProvider
from obassh.services.session_service import SessionService


class _DummyApp:
    pass


class _DummySessionService:
    pass


class _DummyProvider:
    pass


def _controller_with_state(state: AppState) -> SessionController:
    return SessionController(
        app=cast(App[str | None], _DummyApp()),
        state=state,
        session_service=cast(SessionService, _DummySessionService()),
        provider=cast(OciBastionSessionProvider, _DummyProvider()),
        selected_profile_getter=lambda: None,
        ensure_single_bastion=lambda _: False,
    )


def test_merge_runtime_session_data_preserves_runtime_fields() -> None:
    previous = BastionSession(
        ocid="s1",
        state=SessionState.ACTIVE,
        expires_at=None,
        session_type=SessionType.PORT_FORWARDING,
        target_resource="10.0.0.10",
        target_port=22,
        ssh_metadata={
            "local_port": "15432",
            "remote_port": "5432",
            "remote_ip": "10.0.0.10",
            "command": "ssh -N -L 15432:10.0.0.10:5432 session@bastion",
            "bastion_host": "host.bastion.example",
        },
        pid=9991,
        logfile_path="/tmp/obassh-s1.log",
    )
    state = AppState(sessions=[previous], ssh_processes={"s1": 9991})
    controller = _controller_with_state(state)

    fresh = BastionSession(
        ocid="s1",
        state=SessionState.ACTIVE,
        expires_at=None,
        session_type=SessionType.PORT_FORWARDING,
        target_resource="10.0.0.10",
        target_port=22,
        ssh_metadata={},
    )

    merged = cast(Any, controller)._merge_runtime_session_data([fresh])

    assert len(merged) == 1
    session = merged[0]
    assert session.ssh_metadata["local_port"] == "15432"
    assert session.ssh_metadata["remote_port"] == "5432"
    assert session.ssh_metadata["remote_ip"] == "10.0.0.10"
    assert session.ssh_metadata["command"].startswith("ssh -N -L 15432")
    assert session.pid == 9991
    assert session.logfile_path == "/tmp/obassh-s1.log"


def test_merge_runtime_session_data_uses_pid_from_runtime_map_for_new_session() -> None:
    state = AppState(sessions=[], ssh_processes={"s2": 7777})
    controller = _controller_with_state(state)

    fresh = BastionSession(
        ocid="s2",
        state=SessionState.ACTIVE,
        expires_at=None,
        session_type=SessionType.MANAGED_SSH,
        ssh_metadata={},
    )

    merged = cast(Any, controller)._merge_runtime_session_data([fresh])

    assert merged[0].pid == 7777
