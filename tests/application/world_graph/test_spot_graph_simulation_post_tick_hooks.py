"""``SpotGraphSimulationApplicationService`` の post-tick hook 連鎖を検証。

heartbeat → llm_turn_trigger の順序が守られ、heartbeat が enqueue した
ターンが同 tick 内で turn_trigger により実行されることを保証する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ai_rpg_world.application.common.services.game_time_provider import (
    GameTimeProvider,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
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
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class _AllLlmResolver:
    """テスト用に全プレイヤーを LLM 制御扱いする resolver。"""

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return True


@dataclass
class _RecordingTrigger(ILlmTurnTrigger):
    """schedule_turn と run_scheduled_turns の呼び出し履歴を記録する。

    記録順を見ることで heartbeat → turn_trigger.run の順序を検証できる。
    """

    events: List[str] = field(default_factory=list)
    scheduled_during_run: List[int] = field(default_factory=list)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.events.append(f"schedule({player_id.value})")

    def run_scheduled_turns(self) -> None:
        # 直前に enqueue されたものをここで読み出す体で記録する。
        self.events.append("run")


class TestSpotGraphSimulationPostTickHooks:
    """post-tick hook の連携挙動。"""

    def _build_service(
        self,
        emitter: HeartbeatObservationEmitter | None,
        trigger: _RecordingTrigger | None,
    ) -> SpotGraphSimulationApplicationService:
        return SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            unit_of_work=InMemoryUnitOfWork(),
            heartbeat_emitter=emitter,
            llm_turn_trigger=trigger,
        )

    def test_heartbeat_runs_before_llm_turn_trigger(self) -> None:
        """同一 post-tick で heartbeat → turn_trigger.run の順に実行される。"""
        buffer = DefaultObservationContextBuffer()
        trigger = _RecordingTrigger()
        scheduler = ObservationTurnScheduler(
            turn_trigger=trigger,
            llm_player_resolver=_AllLlmResolver(),
        )
        emitter = HeartbeatObservationEmitter(
            observation_appender=ObservationAppender(buffer),
            turn_scheduler=scheduler,
            llm_player_ids_provider=lambda: [PlayerId(1)],
            interval_ticks=1,
        )

        service = self._build_service(emitter, trigger)
        service.tick()  # tick=1, anchor (no emit) → events: ['run']
        events_before_emit = list(trigger.events)
        service.tick()  # tick=2, emit + schedule + run

        # 1 tick 目では heartbeat が anchor のみで schedule_turn は呼ばれない
        assert events_before_emit == ["run"]
        # 2 tick 目で schedule → run の順に積まれる
        new_events = trigger.events[len(events_before_emit):]
        assert new_events == ["schedule(1)", "run"]

    def test_heartbeat_can_be_absent(self) -> None:
        """heartbeat_emitter が None でも tick は正常に進む。"""
        trigger = _RecordingTrigger()
        service = self._build_service(emitter=None, trigger=trigger)
        service.tick()
        assert "run" in trigger.events
