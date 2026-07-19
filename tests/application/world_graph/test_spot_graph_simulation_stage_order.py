"""特性化テスト: SpotGraphSimulationApplicationService の tick stage / post-tick hook 実行順序を固定する。

ドメインイベント配信の一元化リファクタ (docs/refactor_plans/domain_event_dispatch_refactor_plan.md)
の Stage 0b。現状の実行順序は ``_tick_impl`` / ``_run_post_tick_hooks`` の
コメントでしか保証されておらず、14 stage を横断的に固定する回帰テストが無かった
(棚卸し: docs/refactor_plans/domain_event_dispatch_stage0a_inventory.md の穴 6)。

順序が load-bearing な理由:
- needs_decay → status_effects: 空腹発の継続効果を同 tick で連鎖させる。
- outcome_resolution → death_grace: 同 tick で救助確定した player を DEAD で
  上書きしない (grace 期限判定を後に置く)。
- graph_event_flusher → heartbeat → llm_turn_trigger: tick stage が graph に積んだ
  events を観測に流してから heartbeat/turn を走らせないと、turn 実行までに観測が
  buffer に届かない静かな失敗になる。

本テストは挙動を変えない。リファクタで stage/hook の実行順序が動いたら赤くなる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

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


@dataclass
class _RecordingStage:
    """run(current_tick) が呼ばれた順に自分の名前を共有リストへ記録する stage spy。"""

    name: str
    recorder: List[str]

    def run(self, current_tick: WorldTick) -> None:
        self.recorder.append(self.name)


@dataclass
class _RecordingHeartbeat:
    """heartbeat_emitter spy。post-tick で run(current_tick) が呼ばれる。"""

    recorder: List[str]

    def run(self, current_tick: WorldTick) -> None:
        self.recorder.append("heartbeat")


@dataclass
class _RecordingTrigger:
    """llm_turn_trigger spy。post-tick で run_scheduled_turns() が呼ばれる。"""

    recorder: List[str]

    def schedule_turn(self, player_id: PlayerId) -> None:  # 本経路では未使用
        self.recorder.append(f"schedule({player_id.value})")

    def run_scheduled_turns(self) -> None:
        self.recorder.append("llm_turn_trigger")


# _tick_impl (UoW 内) の 14 stage + commit 後の 3 hook を並べた期待順序。
_EXPECTED_ORDER = [
    "travel",
    "scenario_event",
    "reactive_object_state",
    "reactive_binding",
    "sync_action_resolver",
    "environment",
    "day_night",
    "needs_decay",
    "status_effects",
    "monster_spawn",
    "monster_behavior",
    "food_spoilage",
    "outcome_resolution",
    "death_grace",
    # ここから post-tick hook (UoW commit 後)
    "graph_event_flusher",
    "heartbeat",
    "llm_turn_trigger",
]


def _build_service_with_all_stages(
    recorder: List[str],
) -> SpotGraphSimulationApplicationService:
    """全 14 stage + 3 post-tick hook を recording spy で注入したサービスを返す。"""

    def stage(name: str) -> _RecordingStage:
        return _RecordingStage(name=name, recorder=recorder)

    return SpotGraphSimulationApplicationService(
        time_provider=InMemoryGameTimeProvider(),
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=stage("travel"),
        scenario_event_stage=stage("scenario_event"),
        reactive_object_state_stage=stage("reactive_object_state"),
        reactive_binding_stage=stage("reactive_binding"),
        sync_action_resolver_stage=stage("sync_action_resolver"),
        environment_stage=stage("environment"),
        day_night_stage=stage("day_night"),
        needs_decay_stage=stage("needs_decay"),
        status_effects_stage=stage("status_effects"),
        monster_spawn_stage=stage("monster_spawn"),
        monster_behavior_stage=stage("monster_behavior"),
        food_spoilage_stage=stage("food_spoilage"),
        outcome_resolution_stage=stage("outcome_resolution"),
        death_grace_stage=stage("death_grace"),
        heartbeat_emitter=_RecordingHeartbeat(recorder=recorder),
        llm_turn_trigger=_RecordingTrigger(recorder=recorder),
        graph_event_flusher=lambda: recorder.append("graph_event_flusher"),
    )


class TestSpotGraphSimulationStageOrder:
    """1 tick 内の全 stage と post-tick hook が固定順序で実行される。"""

    def test_full_tick_executes_stages_and_hooks_in_fixed_order(self) -> None:
        """全 stage 注入時、14 stage → graph_event_flusher → heartbeat → llm_turn_trigger の順で走る。"""
        recorder: List[str] = []
        service = _build_service_with_all_stages(recorder)

        service.tick()

        assert recorder == _EXPECTED_ORDER

    def test_needs_decay_runs_before_status_effects(self) -> None:
        """継続効果の連鎖のため、needs_decay は同 tick の status_effects より先に走る。"""
        recorder: List[str] = []
        service = _build_service_with_all_stages(recorder)

        service.tick()

        assert recorder.index("needs_decay") < recorder.index("status_effects")

    def test_outcome_resolution_runs_before_death_grace(self) -> None:
        """同 tick 救助を DEAD で上書きしないため、outcome_resolution は death_grace より先に走る。"""
        recorder: List[str] = []
        service = _build_service_with_all_stages(recorder)

        service.tick()

        assert recorder.index("outcome_resolution") < recorder.index("death_grace")

    def test_graph_event_flusher_runs_before_heartbeat_and_turn_trigger(self) -> None:
        """観測が turn 実行までに buffer へ届くよう、graph_event_flusher は heartbeat と llm_turn_trigger より先に走る。"""
        recorder: List[str] = []
        service = _build_service_with_all_stages(recorder)

        service.tick()

        flusher = recorder.index("graph_event_flusher")
        assert flusher < recorder.index("heartbeat")
        assert flusher < recorder.index("llm_turn_trigger")

    def test_all_stages_run_after_unit_of_work_opens(self) -> None:
        """14 stage は post-tick hook より前 (= UoW commit 前) にすべて実行される。"""
        recorder: List[str] = []
        service = _build_service_with_all_stages(recorder)

        service.tick()

        first_post_hook = recorder.index("graph_event_flusher")
        in_uow = recorder[:first_post_hook]
        assert in_uow == _EXPECTED_ORDER[:14]
