"""WorldRuntimeの会議入口が専用command serviceだけへ委譲することを保証する。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.meeting_command_service import (
    MeetingCommandService,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "scenarios"
    / "darkened_station.json"
)


def test_runtime_builds_the_meeting_command_service() -> None:
    """通常のruntime生成では会議command serviceが必ず配線される。"""
    runtime = create_world_runtime(_SCENARIO)

    assert isinstance(runtime._meeting_command_service, MeetingCommandService)


def test_runtime_meeting_entrypoints_only_delegate() -> None:
    """緊急招集と死体報告はWorldRuntime内で再実装せず同じserviceへ委譲する。"""
    runtime = create_world_runtime(_SCENARIO)
    service = MagicMock(spec=MeetingCommandService)
    emergency_result = object()
    report_result = object()
    service.call_emergency_meeting.return_value = emergency_result
    service.report_body.return_value = report_result
    runtime._meeting_command_service = service
    initiator = PlayerId(1)
    target = PlayerId(2)

    assert (
        runtime.call_emergency_meeting(initiator, trigger="scenario_alarm")
        is emergency_result
    )
    assert runtime.report_body(initiator, target) is report_result
    service.call_emergency_meeting.assert_called_once_with(
        initiator,
        trigger="scenario_alarm",
    )
    service.report_body.assert_called_once_with(initiator, target)
