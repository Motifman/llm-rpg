"""協力ギミック #13 (同時操作パズル) の最小デモシナリオの end-to-end 検証。

`data/scenarios/sync_levers_demo.json` を読み込み、registry + resolver stage
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
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "sync_levers_demo.json"
)


@dataclass
class _Harness:
    loaded: object
    spot_graph_repo: InMemorySpotGraphRepository
    registry: SynchronizedActionRegistry
    stage: SynchronizedActionResolverStageService
    world_flags: MutableWorldFlagState


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
    stage = SynchronizedActionResolverStageService(
        groups=loaded.synchronized_action_groups,
        registry=registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        world_flag_state=flags,
    )
    return _Harness(
        loaded=loaded,
        spot_graph_repo=spot_graph_repo,
        registry=registry,
        stage=stage,
        world_flags=flags,
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

    def test_one_tick_offset_still_within_window(self, sync_levers: _Harness) -> None:
        """tick 3 と tick 4 の prepare は window=2 内なので完成する。"""
        sync_levers.registry.prepare(action_id="pull_lever_left", player_id=1, current_tick=3)
        sync_levers.registry.prepare(action_id="pull_lever_right", player_id=2, current_tick=4)

        sync_levers.stage.run(WorldTick(4))
        assert "vault_unlocked" in sync_levers.world_flags.as_frozen_set()
