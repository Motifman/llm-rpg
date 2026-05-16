"""``IntentResolutionService`` の failure_observer フック連携テスト。

PR5 で導入した「resolve 失敗時に observer を呼ぶ」フック挙動を検証する。
ActionFailedObservationEmitter と組み合わせた end-to-end 系もここで確認。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.intent_resolution_service import (
    IntentResolutionService,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    ILlmTurnTrigger,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _AllLlm(ILLMPlayerResolver):
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return True


class _RecordingTrigger(ILlmTurnTrigger):
    def __init__(self) -> None:
        self.scheduled: list[int] = []

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.scheduled.append(player_id.value)

    def run_scheduled_turns(self) -> None:
        return None


class TestFailureObserverHook:
    """``failure_observer`` の呼び出し挙動。"""

    def test_observer_called_on_failure(self) -> None:
        """resolve が失敗 DTO を返すと observer が (intent, dto) で呼ばれる。"""
        captured: list[tuple[Intent, LlmCommandResultDto]] = []

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            return LlmCommandResultDto(
                success=False,
                message="x",
                error_code="INVALID_DESTINATION_LABEL",
            )

        service = IntentResolutionService(
            handler_map={"spot_graph_travel_to": handler},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
            failure_observer=lambda intent, dto: captured.append((intent, dto)),
        )

        service.submit_and_resolve_immediately(
            player_id=5, tool_name="spot_graph_travel_to", arguments={}
        )

        assert len(captured) == 1
        intent, dto = captured[0]
        assert intent.tool_name == "spot_graph_travel_to"
        assert dto.error_code == "INVALID_DESTINATION_LABEL"

    def test_observer_not_called_on_success(self) -> None:
        """success=True なら observer は呼ばれない。"""
        captured: list = []

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            return LlmCommandResultDto(success=True, message="ok")

        service = IntentResolutionService(
            handler_map={"tool": handler},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
            failure_observer=lambda intent, dto: captured.append((intent, dto)),
        )
        service.submit_and_resolve_immediately(
            player_id=1, tool_name="tool", arguments={}
        )
        assert captured == []

    def test_observer_exception_does_not_propagate(self, caplog) -> None:
        """observer が例外を投げても resolve 結果は通常通り返り、ログに記録される。"""
        import logging

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            return LlmCommandResultDto(
                success=False, message="x", error_code="LOST_RACE"
            )

        def boom(intent, dto):
            raise RuntimeError("observer crashed")

        service = IntentResolutionService(
            handler_map={"tool": handler},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
            failure_observer=boom,
        )
        with caplog.at_level(
            logging.ERROR,
            logger="ai_rpg_world.application.intent.intent_resolution_service",
        ):
            result = service.submit_and_resolve_immediately(
                player_id=1, tool_name="tool", arguments={}
            )
        assert result.success is False
        assert result.error_code == "LOST_RACE"
        # observer 例外が ERROR レベルでログに残ること (observability 回帰防止)
        assert any(
            "failure_observer raised" in record.message
            for record in caplog.records
        )


class TestEndToEndWithActionFailedEmitter:
    """IntentResolutionService + ActionFailedObservationEmitter を結合した
    end-to-end 挙動。
    """

    def test_failed_tool_call_appends_observation_and_schedules_turn(self) -> None:
        """ツール失敗 → observation buffer に action_failed 追加 → ターン投入。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        trigger = _RecordingTrigger()
        scheduler = ObservationTurnScheduler(
            turn_trigger=trigger,
            llm_player_resolver=_AllLlm(),
        )
        emitter = ActionFailedObservationEmitter(
            observation_appender=appender,
            turn_scheduler=scheduler,
            now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        def handler(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
            return LlmCommandResultDto(
                success=False,
                message="目標が見つからない",
                error_code="TARGET_NO_LONGER_EXISTS",
                should_reschedule=True,  # 再試行可能エラーとして turn 投入する
            )

        service = IntentResolutionService(
            handler_map={"spot_graph_interact": handler},
            intent_queue=IntentQueue(),
            intent_id_generator=IntentIdGenerator(),
            tick_provider=lambda: WorldTick(1),
            failure_observer=emitter.on_resolution_failure,
        )

        service.submit_and_resolve_immediately(
            player_id=11,
            tool_name="spot_graph_interact",
            arguments={"object_label": "ghost"},
        )

        observations = buffer.get_observations(PlayerId(11))
        assert len(observations) == 1
        assert observations[0].output.structured["type"] == "action_failed"
        assert observations[0].output.structured["error_code"] == (
            "TARGET_NO_LONGER_EXISTS"
        )
        assert trigger.scheduled == [11]
