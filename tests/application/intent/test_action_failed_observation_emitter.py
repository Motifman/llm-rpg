"""``ActionFailedObservationEmitter`` の挙動を検証する単体テスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
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
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase
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


def _make_intent(
    intent_id: int = 1,
    player_id: int = 42,
    tool_name: str = "spot_graph_travel_to",
) -> Intent:
    return Intent(
        intent_id=IntentId(intent_id),
        player_id=PlayerId(player_id),
        tool_name=tool_name,
        arguments={"destination_label": "X"},
        phase=IntentPhase.MOVEMENT,
        submitted_at_tick=WorldTick(1),
        complete_at_tick=WorldTick(1),
    )


def _build_emitter() -> tuple[
    ActionFailedObservationEmitter,
    DefaultObservationContextBuffer,
    _RecordingTrigger,
]:
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
    return emitter, buffer, trigger


class TestActionFailedObservationEmitter:
    """resolve 失敗時の観測投入挙動。"""

    def test_success_dto_is_ignored(self) -> None:
        """success=True の DTO では何も投入しない。"""
        emitter, buffer, trigger = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(),
            LlmCommandResultDto(success=True, message="ok"),
        )
        assert buffer.get_observations(PlayerId(42)) == []
        assert trigger.scheduled == []

    def test_action_failure_with_reschedule_emits_and_schedules_turn(self) -> None:
        """should_reschedule=True の失敗は observation 投入 + turn schedule。"""
        emitter, buffer, trigger = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(player_id=7, tool_name="spot_graph_travel_to"),
            LlmCommandResultDto(
                success=False,
                message="移動先が見つかりません",
                error_code="INVALID_DESTINATION_LABEL",
                remediation="現在の状況に表示されたラベルを指定してください。",
                should_reschedule=True,
            ),
        )
        observations = buffer.get_observations(PlayerId(7))
        assert len(observations) == 1
        structured = observations[0].output.structured
        assert structured["type"] == "action_failed"
        assert structured["tool_name"] == "spot_graph_travel_to"
        assert structured["error_code"] == "INVALID_DESTINATION_LABEL"
        assert observations[0].output.schedules_turn is True
        assert trigger.scheduled == [7]

    def test_action_failure_without_reschedule_emits_but_does_not_schedule(self) -> None:
        """should_reschedule=False の失敗は観測投入のみ、turn は積まない (ループ抑止)。"""
        emitter, buffer, trigger = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(player_id=8),
            LlmCommandResultDto(
                success=False,
                message="目標が見つからない",
                error_code="TARGET_NO_LONGER_EXISTS",
                should_reschedule=False,
            ),
        )
        # 観測は届く (LLM が次の自発的ターンで参照可能)
        assert len(buffer.get_observations(PlayerId(8))) == 1
        # ただしターンは積まれない
        assert trigger.scheduled == []

    def test_llm_api_failure_is_excluded(self) -> None:
        """LLM API レベルの失敗 (NO_TOOL_CALL 等) は観測化しない。"""
        emitter, buffer, trigger = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(),
            LlmCommandResultDto(
                success=False,
                message="ツール未選択",
                error_code="NO_TOOL_CALL",
            ),
        )
        assert buffer.get_observations(PlayerId(42)) == []
        assert trigger.scheduled == []

    def test_internal_error_codes_are_excluded(self) -> None:
        """配線・内部エラー (UNKNOWN_TOOL / INTENT_HANDLER_RAISED 等) も観測化しない。

        LLM 側でリカバー不能な内部エラーを「行動失敗」として伝えると、
        同じツール呼び出しを再試行するループの素になる。
        """
        emitter, buffer, trigger = _build_emitter()
        for code in (
            "UNKNOWN_TOOL",
            "INTENT_HANDLER_RAISED",
            "INTENT_SUBMISSION_REJECTED",
            "INTENT_RESOLVE_INTERNAL",
        ):
            emitter.on_resolution_failure(
                _make_intent(),
                LlmCommandResultDto(
                    success=False,
                    message="internal",
                    error_code=code,
                    should_reschedule=True,
                ),
            )
        assert buffer.get_observations(PlayerId(42)) == []
        assert trigger.scheduled == []

    def test_failure_without_error_code_is_still_emitted(self) -> None:
        """error_code が None でも安全側で観測投入する (should_reschedule に従う)。"""
        emitter, buffer, trigger = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(),
            LlmCommandResultDto(
                success=False,
                message="原因不明の失敗",
                should_reschedule=True,
            ),
        )
        assert len(buffer.get_observations(PlayerId(42))) == 1
        assert trigger.scheduled == [42]

    def test_intent_id_is_in_structured_payload(self) -> None:
        """observation の structured に intent_id が含まれる。"""
        emitter, buffer, _ = _build_emitter()
        emitter.on_resolution_failure(
            _make_intent(intent_id=777),
            LlmCommandResultDto(
                success=False, message="x", error_code="LOST_RACE"
            ),
        )
        out = buffer.get_observations(PlayerId(42))[0].output
        assert out.structured["intent_id"] == 777
