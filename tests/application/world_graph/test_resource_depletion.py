"""採取の枯渇 (#3) — INCREMENT_OBJECT_STATE + OBJECT_STATE_INT_AT_LEAST 検証。

設計:
- 採取するたびに state["harvest_count"] += 1 (INCREMENT_OBJECT_STATE)
- reactive_binding が「count >= N で永久 available=false」を判定
  (OBJECT_STATE_INT_AT_LEAST)

これにより、N 回採取すると永久に枯渇する resource を表現できる。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


SPOT_ID = SpotId.create(1)
OBJECT_ID = SpotObjectId.create(1)


class _StubInteriorRepo:
    """find_by_spot_id だけ実装する最小 interior repo。"""

    def __init__(self, interior: SpotInterior) -> None:
        self._interior = interior

    def find_by_spot_id(self, spot_id):
        if spot_id == SPOT_ID:
            return self._interior
        return None

    def save(self, spot_id, interior):
        self._interior = interior


def _make_graph_with_object(state: dict) -> tuple[SpotGraphAggregate, _StubInteriorRepo]:
    """SPOT_ID に 1 つ OBJECT_ID が置かれた最小 graph + 対応する interior。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(SpotNode(
        spot_id=SPOT_ID, name="採取スポット", description="test",
        category=SpotCategoryEnum.FIELD, parent_id=None,
    ))
    obj = SpotObject(
        object_id=OBJECT_ID,
        name="ベリー茂み",
        description="test",
        object_type=ObjectTypeEnum.RESOURCE,
        state=state,
        interactions=(),
    )
    interior = SpotInterior(sub_locations=(), objects=(obj,), ground_items=(), discoverable_items=())
    return graph, _StubInteriorRepo(interior)


def _evaluator(repo) -> ScenarioConditionEvaluator:
    return ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=repo,
        player_status_repository=MagicMock(),
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
    )


class TestObjectStateIntAtLeast:
    """OBJECT_STATE_INT_AT_LEAST predicate の評価ロジック。"""

    def test_count_が_threshold_に達したら_True(self) -> None:
        graph, repo = _make_graph_with_object({"harvest_count": 5})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            state_key="harvest_count",
            ticks_offset=5,  # threshold (ticks_offset を流用)
        )
        assert _evaluator(repo).evaluate(cond, WorldTick(0), graph) is True

    def test_count_が_threshold_未満なら_False(self) -> None:
        graph, repo = _make_graph_with_object({"harvest_count": 3})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            state_key="harvest_count",
            ticks_offset=5,
        )
        assert _evaluator(repo).evaluate(cond, WorldTick(0), graph) is False

    def test_state_key_不在は_0_扱い_False(self) -> None:
        """まだ採取してないオブジェクトは枯渇判定で False (= まだ枯渇してない)。"""
        graph, repo = _make_graph_with_object({})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            state_key="harvest_count",
            ticks_offset=5,
        )
        assert _evaluator(repo).evaluate(cond, WorldTick(0), graph) is False

    def test_count_と_threshold_が_完全一致なら_True(self) -> None:
        """境界条件: ちょうど threshold に達した瞬間に枯渇判定される。"""
        graph, repo = _make_graph_with_object({"harvest_count": 5})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            state_key="harvest_count",
            ticks_offset=5,
        )
        assert _evaluator(repo).evaluate(cond, WorldTick(0), graph) is True

    def test_必須フィールド不足は_False(self) -> None:
        graph, repo = _make_graph_with_object({"harvest_count": 10})
        # state_key 無し
        cond_no_key = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            ticks_offset=5,
        )
        assert _evaluator(repo).evaluate(cond_no_key, WorldTick(0), graph) is False
        # ticks_offset (threshold) 無し
        cond_no_threshold = ScenarioEventCondition(
            condition_type="OBJECT_STATE_INT_AT_LEAST",
            object_id=OBJECT_ID.value,
            state_key="harvest_count",
        )
        assert _evaluator(repo).evaluate(cond_no_threshold, WorldTick(0), graph) is False
