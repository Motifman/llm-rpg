"""PR1-5 の主要コンポーネント間の配線検証テスト (端的なスモーク)。

**スコープ限定**: 実 ``SpotGraphSimulationApplicationService`` も
``WorldRuntime`` も使わない。代わりに最小スタブ ``_CountingRuntime`` を
通して、以下のピース群が他コンポーネントなしで正しく連携することだけを
保証する:

1. ``SimulationTickLoop`` が ``GameRuntimeManager`` 経由でランタイムを駆動する
2. ``HeartbeatObservationEmitter`` が idle tick で観測を投入し turn を積む
3. ``IntentResolutionService`` が tool 呼び出しを intent VO 経由で resolve する
4. 失敗 DTO が ``ActionFailedObservationEmitter`` 経由で
   ``type: action_failed`` 観測になる

フル E2E (実 LLM での 2-agent デモ) は ``docs/demos/two_agent_world_issue.md``
を参照。本テストはあくまで PR1-5 のコンポーネント配線の回帰防止が目的。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Mapping

# observation_appender を先に import するのは pre-existing な循環 import を
# 回避するため (他のテストファイルでも同じ workaround)。F401 ではなく実際に
# 下で利用している。
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
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
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
    _SessionState,
)
from ai_rpg_world.presentation.spot_graph_game.tick_loop import (
    SimulationTickLoop,
)


class _AllLlm(ILLMPlayerResolver):
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return True


@dataclass
class _RecordingTrigger(ILlmTurnTrigger):
    scheduled: List[int]

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.scheduled.append(player_id.value)

    def run_scheduled_turns(self) -> None:
        return None


class _CountingRuntime:
    """`advance_tick()` を呼ぶたびに内部 tick を 1 進め、登録された emitter を
    実行するだけの最小ランタイム。

    実際の spot_graph_simulation_application_service は使わず、PR1-5 が
    互いに正しく連携できるかだけを検証する。
    """

    def __init__(self, on_tick) -> None:
        self.tick = 0
        self._on_tick = on_tick

    def advance_tick(self) -> int:
        self.tick += 1
        self._on_tick(WorldTick(self.tick))
        return self.tick


def _build_world() -> tuple[
    _CountingRuntime,
    DefaultObservationContextBuffer,
    _RecordingTrigger,
    IntentResolutionService,
    list[int],
]:
    """PR1-5 の主要コンポーネントを 2 体のプレイヤー用に組み上げる。"""
    buffer = DefaultObservationContextBuffer()
    appender = ObservationAppender(buffer)
    scheduled: list[int] = []
    trigger = _RecordingTrigger(scheduled=scheduled)
    scheduler = ObservationTurnScheduler(
        turn_trigger=trigger,
        llm_player_resolver=_AllLlm(),
    )
    llm_players = [PlayerId(1), PlayerId(2)]
    heartbeat = HeartbeatObservationEmitter(
        observation_appender=appender,
        turn_scheduler=scheduler,
        llm_player_ids_provider=lambda: list(llm_players),
        interval_ticks=2,
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    queue = IntentQueue()
    action_failed = ActionFailedObservationEmitter(
        observation_appender=appender,
        turn_scheduler=scheduler,
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    runtime_holder: dict = {}

    def tick_provider() -> WorldTick:
        return WorldTick(runtime_holder["runtime"].tick)

    # ツールハンドラ: 既存形式 (player_id, args) → DTO
    def attempt_move(player_id: int, args: Mapping[str, Any]) -> LlmCommandResultDto:
        # 同じ目的地を指定したプレイヤーが既にいれば LOST_RACE で失敗
        dest = args.get("dest", "")
        return LlmCommandResultDto(
            success=False,
            message=f"目標 {dest} は既に他のプレイヤーに取られている",
            error_code="LOST_RACE",
            should_reschedule=True,
        )

    service = IntentResolutionService(
        handler_map={"attempt_move": attempt_move},
        intent_queue=queue,
        intent_id_generator=IntentIdGenerator(),
        tick_provider=tick_provider,
        failure_observer=action_failed.on_resolution_failure,
    )

    runtime = _CountingRuntime(on_tick=heartbeat.run)
    runtime_holder["runtime"] = runtime
    return runtime, buffer, trigger, service, scheduled


class TestPr15ComponentIntegration:
    """PR1-5 で追加した主要コンポーネント間の配線回帰防止。

    実ランタイム (``SpotGraphSimulationApplicationService`` 等) は使わない。
    """

    def test_heartbeat_fires_for_both_players_after_interval(self) -> None:
        """tick loop が走ると 2 体それぞれに heartbeat が届きターンが投入される。"""
        runtime, buffer, trigger, _service, scheduled = _build_world()

        # 直接 advance_tick を 4 回呼ぶ (tick 1 anchor, 3 で emit, 4 はまだ)
        # interval_ticks=2 → tick 1 anchor, tick 3 で emit (gap=2)
        runtime.advance_tick()  # tick=1, anchor
        runtime.advance_tick()  # tick=2, gap=1 < 2
        runtime.advance_tick()  # tick=3, gap=2 → emit for both

        # 両プレイヤーに heartbeat 観測が届いている
        p1_obs = buffer.get_observations(PlayerId(1))
        p2_obs = buffer.get_observations(PlayerId(2))
        assert any(
            o.output.structured.get("type") == "heartbeat" for o in p1_obs
        )
        assert any(
            o.output.structured.get("type") == "heartbeat" for o in p2_obs
        )
        # turn も 2 体分積まれている
        assert sorted(set(scheduled)) == [1, 2]

    def test_failed_tool_call_produces_action_failed_observation(self) -> None:
        """ツール失敗時に当該プレイヤーへ action_failed 観測が届きターン投入される。"""
        runtime, buffer, trigger, service, scheduled = _build_world()
        runtime.advance_tick()  # tick=1

        # Player 1 がツールを呼び失敗 (LOST_RACE)
        result = service.submit_and_resolve_immediately(
            player_id=1, tool_name="attempt_move", arguments={"dest": "spot_a"}
        )
        assert result.success is False
        assert result.error_code == "LOST_RACE"

        observations = buffer.get_observations(PlayerId(1))
        types = [o.output.structured.get("type") for o in observations]
        assert "action_failed" in types
        failed = next(
            o
            for o in observations
            if o.output.structured.get("type") == "action_failed"
        )
        assert failed.output.structured["error_code"] == "LOST_RACE"
        # should_reschedule=True なので turn も積まれる
        assert 1 in scheduled

    def test_tick_loop_drives_runtime_in_background(self) -> None:
        """``SimulationTickLoop`` が runtime.advance_tick() を背景で呼び続ける。"""
        runtime, buffer, _trigger, _service, _scheduled = _build_world()

        manager = GameRuntimeManager()
        manager._sessions["demo"] = _SessionState(
            session_id="demo",
            world_id="w",
            world_title="W",
            character_ids=[],
            status="running",
            created_at="now",
            runtime=runtime,
        )

        async def scenario() -> None:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)
            loop.start()
            try:
                # 4 tick 進むまで待つ
                deadline = asyncio.get_event_loop().time() + 2.0
                while runtime.tick < 4 and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.01)
            finally:
                await loop.stop()

        asyncio.run(scenario())
        assert runtime.tick >= 4
        # tick 自走で heartbeat も走っているはず (interval_ticks=2 → tick 3 で emit)
        all_obs = buffer.get_observations(PlayerId(1))
        assert any(
            o.output.structured.get("type") == "heartbeat" for o in all_obs
        )
