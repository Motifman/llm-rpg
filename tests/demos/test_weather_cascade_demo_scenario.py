"""環境系 #11 (天候連鎖) の最小デモシナリオの end-to-end 検証。

`data/scenarios/weather_cascade_demo.json` を読み込み、
ReactivePassageBindingStageService が WEATHER_IS predicate を
評価して passage state を切り替えるかを確認する。

新しい primitive は導入していない。既存の ReactivePassageBinding と
WEATHER_IS condition の組み合わせだけで天候連鎖を実現できることを
保証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "weather_cascade_demo.json"
)


@dataclass
class _WeatherHolder:
    """テスト中に天候を切り替えるための可変ホルダ。"""

    state: WeatherState


@pytest.fixture
def weather_cascade():
    """シナリオを読み込んで stage / repo / weather holder を返す。"""
    loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = loaded.graph
    for spawn in loaded.player_spawns:
        graph.place_entity(EntityId.create(spawn.player_id), spawn.spawn_spot_id)
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        interior_repo.save(sid, interior)
    data_store = InMemoryDataStore()
    status_repo = InMemoryPlayerStatusRepository(data_store)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    for spawn in loaded.player_spawns:
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(spawn.player_id)))

    holder = _WeatherHolder(state=loaded.weather_config.initial_state)

    evaluator = ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=interior_repo,
        player_status_repository=status_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        weather_state_provider=lambda: holder.state,
    )
    stage = ReactivePassageBindingStageService(
        bindings=loaded.reactive_passage_bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=evaluator,
    )
    return loaded, spot_graph_repo, stage, holder


def _cid(loaded, string_id: str) -> ConnectionId:
    return ConnectionId.create(loaded.id_mapper.get_int("connection", string_id))


class TestWeatherCascadeDemoScenario:
    """weather_cascade_demo.json が #11 天候連鎖の仕様通りに動く。"""

    def test_initial_clear_weather_keeps_crossing_passable(self, weather_cascade) -> None:
        """初期状態 (CLEAR) では川渡りは INACTIVE（通行可）のまま。"""
        loaded, repo, stage, _ = weather_cascade
        cid = _cid(loaded, "river_crossing")
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "INACTIVE"
        assert repo.find_graph().get_connection(cid).passage.traversable is True

    def test_storm_activates_barrier(self, weather_cascade) -> None:
        """天候が STORM になると次 tick で BARRIER が ACTIVE（通行不可）になる。"""
        loaded, repo, stage, holder = weather_cascade
        cid = _cid(loaded, "river_crossing")
        # 嵐に切り替え
        holder.state = WeatherState(weather_type=WeatherTypeEnum.STORM, intensity=1.0)
        stage.run(WorldTick(2))
        assert repo.find_graph().get_connection(cid).passage.state == "ACTIVE"
        assert repo.find_graph().get_connection(cid).passage.traversable is False

    def test_storm_clears_and_crossing_reopens(self, weather_cascade) -> None:
        """嵐が止めば次 tick で INACTIVE に戻り、再び通行可能になる。"""
        loaded, repo, stage, holder = weather_cascade
        cid = _cid(loaded, "river_crossing")

        holder.state = WeatherState(weather_type=WeatherTypeEnum.STORM, intensity=1.0)
        stage.run(WorldTick(2))
        assert repo.find_graph().get_connection(cid).passage.state == "ACTIVE"

        holder.state = WeatherState(weather_type=WeatherTypeEnum.CLEAR, intensity=0.0)
        stage.run(WorldTick(3))
        assert repo.find_graph().get_connection(cid).passage.state == "INACTIVE"
        assert repo.find_graph().get_connection(cid).passage.traversable is True

    def test_non_storm_weather_does_not_block(self, weather_cascade) -> None:
        """STORM 以外（RAIN など）では BARRIER は ACTIVE にならない。"""
        loaded, repo, stage, holder = weather_cascade
        cid = _cid(loaded, "river_crossing")
        holder.state = WeatherState(weather_type=WeatherTypeEnum.RAIN, intensity=0.5)
        stage.run(WorldTick(2))
        assert repo.find_graph().get_connection(cid).passage.state == "INACTIVE"
