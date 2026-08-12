"""協力ギミック #13 (同時操作パズル) の最小デモシナリオの end-to-end 検証。

`tests/fixtures/scenarios/sync_levers_demo.json` を読み込み、registry + resolver stage
が tick 単位で正しく完成 / タイムアウトを判定し、passage 状態が遷移すること
を確認する。LLM ツール呼び出しは経由せず、registry に直接 prepare を投入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "scenarios"
    / "sync_levers_demo.json"
)


@dataclass
class _Harness:
    loaded: object
    spot_graph_repo: InMemorySpotGraphRepository
    registry: SynchronizedActionRegistry
    stage: SynchronizedActionResolverStageService
    world_flags: MutableWorldFlagState
    delivered_messages: list[tuple[str, str, tuple[int, ...], str]]


@pytest.fixture
def sync_levers() -> _Harness:
    loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = loaded.graph
    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        interior_repo.save(sid, interior)
    flags = MutableWorldFlagState()
    registry = SynchronizedActionRegistry(flags)
    delivered_messages: list[tuple[str, str, tuple[int, ...], str]] = []
    stage = SynchronizedActionResolverStageService(
        groups=loaded.synchronized_action_groups,
        registry=registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        world_flag_state=flags,
        on_message=lambda group_id, outcome, recipients, message: delivered_messages.append(
            (group_id, outcome, recipients, message)
        ),
    )
    return _Harness(
        loaded=loaded,
        spot_graph_repo=spot_graph_repo,
        registry=registry,
        stage=stage,
        world_flags=flags,
        delivered_messages=delivered_messages,
    )


def _vault_door_cid(loaded) -> ConnectionId:
    return ConnectionId.create(loaded.id_mapper.get_int("connection", "lever_to_vault"))


class TestSyncLeversDemoScenario:
    """sync_levers_demo.json が #13 仕様通りに動く。"""

    def test_loads_one_synchronized_group(self, sync_levers: _Harness) -> None:
        """シナリオから 1 つの sync group が読み込まれる。"""
        groups = sync_levers.loaded.synchronized_action_groups
        assert len(groups) == 1
        assert groups[0].group_id == "vault_unlock"
        assert groups[0].window_ticks == 2
        assert groups[0].on_prepare_observation_message is not None

    def test_two_prepares_in_same_tick_unlock_vault(self, sync_levers: _Harness) -> None:
        """同 tick に両 prepare が揃えば次の resolver run で扉が OPEN になる。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        sync_levers.registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=3)

        sync_levers.stage.run(WorldTick(3))
        cid = _vault_door_cid(sync_levers.loaded)
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "OPEN"
        assert "vault_unlocked" in sync_levers.world_flags.as_frozen_set()

    def test_partial_prepare_times_out_after_window(self, sync_levers: _Harness) -> None:
        """A だけ prepare して B が来ないと、window=2 経過で reset される。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        # window_ticks=2 なので tick=3 から (3+2)=5 以降で timeout
        sync_levers.stage.run(WorldTick(4))  # まだ pending
        cid = _vault_door_cid(sync_levers.loaded)
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        assert sync_levers.registry.entries_for("pull_lever_left") != []

        sync_levers.stage.run(WorldTick(5))  # timeout
        # passage は LOCKED のまま、prepare はクリアされる
        assert sync_levers.spot_graph_repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        assert sync_levers.registry.entries_for("pull_lever_left") == []
        assert sync_levers.delivered_messages == [
            (
                "vault_unlock",
                "timed_out",
                (1,),
                "レバーが元の位置に戻る音がした。タイミングを合わせ直す必要がある。",
            )
        ]

    def test_one_tick_offset_still_within_window(self, sync_levers: _Harness) -> None:
        """tick 3 と tick 4 の prepare は window=2 内なので完成する。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        sync_levers.registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=4)

        sync_levers.stage.run(WorldTick(4))
        assert "vault_unlocked" in sync_levers.world_flags.as_frozen_set()


class TestSyncLeverMessagesReachRuntimeObservations:
    """同期操作の SHOW_MESSAGE が実 runtime の参加者観測へ届くことを保証する。"""

    @staticmethod
    def _result_messages(runtime, player_id: PlayerId) -> list[str]:
        return [
            entry.output.prose
            for entry in runtime._obs_buffer.get_observations(player_id)
            if entry.output.structured.get("type") == "synchronized_action_result"
        ]

    def test_completion_message_reaches_all_prepared_players(self) -> None:
        """完成文は、準備した二人の観測へ同じ一件として届く。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        stage = runtime._simulation_service._sync_action_resolver_stage
        stage._registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=0)
        stage._registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=0)

        runtime.advance_tick()

        expected = "二つのレバーが噛み合い、金庫扉の錠が外れた。"
        assert self._result_messages(runtime, PlayerId(1)) == [expected]
        assert self._result_messages(runtime, PlayerId(2)) == [expected]

    def test_timeout_message_reaches_the_partial_participant_only(self) -> None:
        """時間切れ文は、準備しなかった相手でなく部分参加者だけへ届く。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        stage = runtime._simulation_service._sync_action_resolver_stage
        stage._registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=0)

        runtime.advance_tick()
        runtime.advance_tick()

        expected = "レバーが元の位置に戻る音がした。タイミングを合わせ直す必要がある。"
        assert self._result_messages(runtime, PlayerId(1)) == [expected]
        assert self._result_messages(runtime, PlayerId(2)) == []
