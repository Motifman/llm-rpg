"""主体を知らない受け手に届けなかった観測が、ターンも積まず移動も止めないことを保証する (#1531)。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    WithheldFromStrangers,
)
from ai_rpg_world.application.observation.handlers.observation_event_handler import (
    ObservationEventHandler,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.world_runtime.pipeline_event_publisher import (
    PipelineEventPublisher,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_RECIPIENT = PlayerId(7)


def _remote_revive() -> ObservationOutput:
    return ObservationOutput(
        prose="遠くで誰かが動けるようになった気配がした。",
        structured={"type": "player_revived", "actor": "ノア"},
        observation_category="social",
        schedules_turn=True,
        breaks_movement=True,
        subject_name="ノア",
        if_subject_unknown=WithheldFromStrangers(),
    )


def _withholding_appender(buffer: DefaultObservationContextBuffer) -> ObservationAppender:
    return ObservationAppender(buffer=buffer, recipient_view=lambda _pid, out: out.as_subject_unknown())


class TestObservationEventHandler:
    """ObservationEventHandler が、届けなかった観測ではターンを積まず移動を止めないことを保証する。"""

    def test_withheld_observation_neither_schedules_nor_interrupts(self) -> None:
        """受け手に届けなかった観測では、turn_scheduler も movement_interruption も呼ばれない。"""
        pipeline = MagicMock()
        pipeline.run.return_value = [(_RECIPIENT, _remote_revive())]
        scheduler = MagicMock()
        movement = MagicMock()
        buffer = DefaultObservationContextBuffer()
        handler = ObservationEventHandler(
            pipeline=pipeline,
            appender=_withholding_appender(buffer),
            timestamp_resolver=MagicMock(**{"resolve_occurred_at.return_value": datetime.now()}),
            movement_interruption=movement,
            turn_scheduler=scheduler,
            unit_of_work_factory=MagicMock(),
        )

        handler._handle_impl(object())

        assert buffer.get_observations(_RECIPIENT) == []
        scheduler.maybe_schedule.assert_not_called()
        movement.maybe_cancel.assert_not_called()


class _Runtime:
    def __init__(self, appender: ObservationAppender, scheduler: MagicMock, output: ObservationOutput) -> None:
        self._obs_pipeline = MagicMock(**{"run.return_value": [(_RECIPIENT, output)]})
        self._observation_appender = appender
        self._observation_turn_scheduler = scheduler

    def _time_label(self) -> str:
        return "朝"


class TestPipelineEventPublisher:
    """PipelineEventPublisher が、届けなかった観測ではターンを積まないことを保証する。"""

    def test_withheld_observation_does_not_schedule(self) -> None:
        """受け手に届けなかった観測では maybe_schedule が呼ばれず、届けた観測では呼ばれる。"""
        scheduler = MagicMock()
        buffer = DefaultObservationContextBuffer()
        publisher = PipelineEventPublisher(_Runtime(_withholding_appender(buffer), scheduler, _remote_revive()))

        publisher.publish(object())

        scheduler.maybe_schedule.assert_not_called()

    def test_delivered_observation_schedules(self) -> None:
        """届けた観測では、これまでどおり maybe_schedule が呼ばれる。"""
        scheduler = MagicMock()
        plain = ObservationOutput(prose="雨が降り出した。", structured={"type": "weather"}, schedules_turn=True)
        publisher = PipelineEventPublisher(
            _Runtime(_withholding_appender(DefaultObservationContextBuffer()), scheduler, plain)
        )

        publisher.publish(object())

        scheduler.maybe_schedule.assert_called_once()


class TestEmitObservationDirectly:
    """runtime が届け先を決めて直接届ける経路でも、届けなかった観測ではターンを積まないことを保証する。"""

    def test_withheld_observation_does_not_schedule(self) -> None:
        """会っていない相手を主体にした届けない観測を直接届けても、受け手のバッファは空のままで maybe_schedule は呼ばれない。"""
        from pathlib import Path

        from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
            DefaultActionResultStore,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        scenario = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios" / "two_teams_unaware.json"
        runtime = create_world_runtime(scenario)
        ids = {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}
        scheduler = MagicMock()
        runtime._observation_turn_scheduler = scheduler
        output = ObservationOutput(
            prose="ゲンジは救助された。",
            structured={"type": "player_outcome_resolved"},
            observation_category="environment",
            schedules_turn=True,
            subject_name="ゲンジ",
            if_subject_unknown=WithheldFromStrangers(),
        )

        runtime._emit_observation_directly(ids["ミナト"], output)

        assert runtime._obs_buffer.get_observations(ids["ミナト"]) == []
        scheduler.maybe_schedule.assert_not_called()
