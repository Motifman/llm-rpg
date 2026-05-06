"""ScenarioConditionEvaluator の動的世界系条件 (WEATHER_IS / OBJECT_STATE_TICK_AT_LEAST)。

#10/#11/#12 で reactive bindings の predicate として再利用するための新条件型。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


@dataclass
class _FakeWeatherType:
    value: str


@dataclass
class _FakeWeatherState:
    weather_type: _FakeWeatherType


def _build_evaluator(weather: _FakeWeatherState | None = None):
    interior_repo = InMemorySpotInteriorRepository()

    class _NoopStatusRepo:
        def find_all(self):
            return []

    class _NoopInventoryRepo:
        def find_by_id(self, *_a, **_kw):
            return None

    class _NoopItemRepo:
        pass

    return ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=interior_repo,
        player_status_repository=_NoopStatusRepo(),
        player_inventory_repository=_NoopInventoryRepo(),
        item_repository=_NoopItemRepo(),
        weather_state_provider=(lambda: weather) if weather is not None else None,
    ), interior_repo


def _build_graph_with_object(state: dict) -> tuple[SpotGraphAggregate, InMemorySpotInteriorRepository, int]:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(SpotNode(
        spot_id=SpotId.create(1),
        name="S1",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    ))
    obj = SpotObject(
        object_id=SpotObjectId.create(7),
        name="berry_bush",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state=dict(state),
        interactions=(),
    )
    interior = SpotInterior((), (obj,), (), ())
    return g, interior, 7


class TestWeatherIsCondition:
    """WEATHER_IS 条件の評価。"""

    def test_matches_when_weather_type_matches(self) -> None:
        """provider が返す weather_type と condition の weather_type が一致なら True。"""
        weather = _FakeWeatherState(weather_type=_FakeWeatherType(value="STORM"))
        evaluator, _ = _build_evaluator(weather)
        cond = ScenarioEventCondition(condition_type="WEATHER_IS", weather_type="STORM")
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        assert evaluator.evaluate(cond, WorldTick(0), graph) is True

    def test_does_not_match_when_weather_differs(self) -> None:
        """天候名が違えば False。"""
        weather = _FakeWeatherState(weather_type=_FakeWeatherType(value="CLEAR"))
        evaluator, _ = _build_evaluator(weather)
        cond = ScenarioEventCondition(condition_type="WEATHER_IS", weather_type="STORM")
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        assert evaluator.evaluate(cond, WorldTick(0), graph) is False

    def test_returns_false_when_provider_missing(self) -> None:
        """weather_state_provider が None なら常に False（後方互換）。"""
        evaluator, _ = _build_evaluator(weather=None)
        cond = ScenarioEventCondition(condition_type="WEATHER_IS", weather_type="STORM")
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        assert evaluator.evaluate(cond, WorldTick(0), graph) is False

    def test_returns_false_when_weather_type_field_missing(self) -> None:
        """condition.weather_type が無ければ常に False。"""
        weather = _FakeWeatherState(weather_type=_FakeWeatherType(value="STORM"))
        evaluator, _ = _build_evaluator(weather)
        cond = ScenarioEventCondition(condition_type="WEATHER_IS")
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        assert evaluator.evaluate(cond, WorldTick(0), graph) is False


class TestObjectStateTickAtLeastCondition:
    """OBJECT_STATE_TICK_AT_LEAST 条件の評価。"""

    def test_returns_true_when_enough_ticks_elapsed(self) -> None:
        """state_key の値 + ticks_offset 以降の current_tick で True。"""
        evaluator, interior_repo = _build_evaluator()
        graph, interior, oid = _build_graph_with_object({"last_harvest_tick": 5})
        interior_repo.save(SpotId.create(1), interior)
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=oid,
            state_key="last_harvest_tick",
            ticks_offset=10,
        )
        # current=15 → 5+10=15 以降なので True
        assert evaluator.evaluate(cond, WorldTick(15), graph) is True
        # current=14 → まだ False
        assert evaluator.evaluate(cond, WorldTick(14), graph) is False

    def test_returns_false_when_state_key_missing(self) -> None:
        """state_key の値が無いと False。"""
        evaluator, interior_repo = _build_evaluator()
        graph, interior, oid = _build_graph_with_object({})
        interior_repo.save(SpotId.create(1), interior)
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=oid,
            state_key="last_harvest_tick",
            ticks_offset=10,
        )
        assert evaluator.evaluate(cond, WorldTick(100), graph) is False

    def test_returns_false_when_state_key_is_not_int(self) -> None:
        """state_key の値が int でなければ False（型不整合）。"""
        evaluator, interior_repo = _build_evaluator()
        graph, interior, oid = _build_graph_with_object({"last_harvest_tick": "not-an-int"})
        interior_repo.save(SpotId.create(1), interior)
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=oid,
            state_key="last_harvest_tick",
            ticks_offset=0,
        )
        assert evaluator.evaluate(cond, WorldTick(100), graph) is False

    def test_returns_false_when_object_not_found(self) -> None:
        """対象 object が graph に存在しない場合 False。"""
        evaluator, _ = _build_evaluator()
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=999,
            state_key="last_harvest_tick",
            ticks_offset=0,
        )
        assert evaluator.evaluate(cond, WorldTick(100), graph) is False
