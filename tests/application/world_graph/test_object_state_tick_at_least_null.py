"""OBJECT_STATE_TICK_AT_LEAST predicate の null/missing 解釈テスト。

friction #8 の解消。state[state_key] が None / 不在のとき、predicate が
「まだ起きていない」をどちらの真偽値として扱うかを `treat_missing_as_passed`
で明示的に選択できるようにする。

- default (False): 「経過判定不能 → fire しない」 — 安全側
  例: 「採取してから N tick 経った」を判定したい用途で、まだ採取が
  行われていない object に対して binding が誤発火しないようにする。
- True: 「過去無限 → 既に経過済み」 — sentinel マジックナンバー無しで
  「初期から ripe / clean」を表現できる。
"""

from __future__ import annotations

import logging

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


def _build_world_with_object(state: dict):
    """1 spot + 1 object のミニマル世界。"""
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
        name="bush",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state=dict(state),
        interactions=(),
    )
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(1), SpotInterior((), (obj,), (), ()))

    class _NoopStatusRepo:
        def find_all(self):
            return []

    class _NoopInventoryRepo:
        def find_by_id(self, *_a, **_kw):
            return None

    class _NoopItemRepo:
        pass

    evaluator = ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=interior_repo,
        player_status_repository=_NoopStatusRepo(),
        player_inventory_repository=_NoopInventoryRepo(),
        item_repository=_NoopItemRepo(),
    )
    return g, evaluator


class TestNullTickDefaultBehavior:
    """default `treat_missing_as_passed=False`: null/不在は False (経過判定不能)。"""

    def test_state_key_explicitly_null_returns_false(self) -> None:
        """state[key] = None なら predicate False (default)。"""
        graph, evaluator = _build_world_with_object({"last_harvest_tick": None})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
        )
        assert evaluator.evaluate(cond, WorldTick(100), graph) is False

    def test_state_key_missing_returns_false(self) -> None:
        """state に key 自体が無い場合も同じく False。"""
        graph, evaluator = _build_world_with_object({})  # last_harvest_tick 無し
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
        )
        assert evaluator.evaluate(cond, WorldTick(100), graph) is False


class TestNullTickTreatAsPassed:
    """`treat_missing_as_passed=True`: null/不在は True (過去無限とみなす)。"""

    def test_state_key_null_returns_true(self) -> None:
        """state[key] = None でも fire する (sentinel 不要、初期から ripe)。"""
        graph, evaluator = _build_world_with_object({"last_harvest_tick": None})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
            treat_missing_as_passed=True,
        )
        assert evaluator.evaluate(cond, WorldTick(0), graph) is True

    def test_state_key_missing_returns_true(self) -> None:
        """state にキー自体が無くても True。"""
        graph, evaluator = _build_world_with_object({})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
            treat_missing_as_passed=True,
        )
        assert evaluator.evaluate(cond, WorldTick(0), graph) is True

    def test_recorded_tick_still_takes_precedence_over_null_flag(self) -> None:
        """state[key] が int として記録された後は flag の値に関係なく通常評価。

        treat_missing_as_passed は「未記録時の解釈」のみを変える。記録済みの
        値は変わらず int として比較される。
        """
        graph, evaluator = _build_world_with_object({"last_harvest_tick": 50})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
            treat_missing_as_passed=True,
        )
        # 50 + 10 = 60、tick=55 ではまだ False
        assert evaluator.evaluate(cond, WorldTick(55), graph) is False
        # tick=60 で True
        assert evaluator.evaluate(cond, WorldTick(60), graph) is True


class TestObjectNotFoundFallback:
    """object 自体が graph に存在しない場合は flag に関係なく False。"""

    def test_object_not_found_with_flag_true_still_returns_false(self) -> None:
        """treat_missing_as_passed=True でも object_id が graph に無ければ False。

        flag は「object は存在するが state[key] が未記録」のときのみ意味を
        持つ。「object が見つからない」は別の失敗モードであり、混同しない。
        """
        graph, evaluator = _build_world_with_object({"last_harvest_tick": None})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=999,  # 存在しない object
            state_key="last_harvest_tick",
            ticks_offset=10,
            treat_missing_as_passed=True,
        )
        assert evaluator.evaluate(cond, WorldTick(0), graph) is False


class TestNonStrictBooleanRejection:
    """scenario_loader が `treat_missing_as_passed` の暗黙 coercion を拒否する。"""

    def test_loader_treats_truthy_string_as_false(self) -> None:
        """JSON の `"true"` (文字列) は厳格 boolean ではないので False に倒す。

        `bool(...)` で coerce すると非空文字列が True になってしまうが、
        `is True` 判定で「JSON 真偽値以外は default の False」を保つ。
        """
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = {
            "scenario_format_version": "1.0",
            "metadata": {
                "id": "x", "title": "x", "description": "x",
                "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
                "author": "x", "tags": [],
            },
            "item_specs": [],
            "environment": {
                "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                            "update_interval_ticks": 100, "announce_changes": False},
            },
            "spots": [{
                "id": "s", "name": "S", "description": "d", "category": "OTHER",
                "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
                "interior": {"objects": [{
                    "id": "bush", "name": "bush", "description": "d", "object_type": "OTHER",
                    "state": {}, "interactions": [],
                }]},
            }],
            "connections": [],
            "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
            "game_end_conditions": {"win": [], "lose": []},
            "scenario_events": [{
                "id": "ev", "trigger": "ON_TICK", "once": True,
                "conditions": [{
                    "condition_type": "OBJECT_STATE_TICK_AT_LEAST",
                    "target_object": "bush",
                    "state_key": "last_harvest_tick",
                    "ticks_offset": 10,
                    "treat_missing_as_passed": "true",  # 文字列 (作家ミス)
                }],
                "effects": [],
            }],
        }
        cond = ScenarioLoader().load_from_dict(scenario).scenario_events[0].conditions[0]
        # 厳格 boolean ではないので default の False に倒れる
        assert cond.treat_missing_as_passed is False


class TestNonIntNonNullValue:
    """int でも None でもない値（文字列など）は警告 + False のまま。"""

    def test_string_value_logs_warning_and_returns_false(self, caplog) -> None:
        """state[key] が文字列等の場合は警告ログを出し False を返す（既存挙動の維持）。"""
        graph, evaluator = _build_world_with_object({"last_harvest_tick": "five"})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
        )
        with caplog.at_level(logging.WARNING):
            result = evaluator.evaluate(cond, WorldTick(100), graph)
        assert result is False
        assert any("not int" in r.message for r in caplog.records)

    def test_string_value_with_treat_missing_flag_still_false(self, caplog) -> None:
        """型不整合は flag の値に関係なく False（true/false 解釈を二段階に分ける）。"""
        graph, evaluator = _build_world_with_object({"last_harvest_tick": "five"})
        cond = ScenarioEventCondition(
            condition_type="OBJECT_STATE_TICK_AT_LEAST",
            object_id=7,
            state_key="last_harvest_tick",
            ticks_offset=10,
            treat_missing_as_passed=True,
        )
        with caplog.at_level(logging.WARNING):
            assert evaluator.evaluate(cond, WorldTick(0), graph) is False


class TestScenarioLoaderIntegration:
    """scenario_loader が `treat_missing_as_passed` を正しく parse する。"""

    def test_loader_propagates_treat_missing_as_passed(self) -> None:
        """JSON 側の `treat_missing_as_passed: true` が AST のフィールドに反映される。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = {
            "scenario_format_version": "1.0",
            "metadata": {
                "id": "x", "title": "x", "description": "x",
                "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
                "author": "x", "tags": [],
            },
            "item_specs": [],
            "environment": {
                "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                            "update_interval_ticks": 100, "announce_changes": False},
            },
            "spots": [{
                "id": "s", "name": "S", "description": "d", "category": "OTHER",
                "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
                "interior": {"objects": [{
                    "id": "bush", "name": "bush", "description": "d", "object_type": "OTHER",
                    "state": {"last_harvest_tick": None},
                    "interactions": [],
                }]},
            }],
            "connections": [],
            "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
            "game_end_conditions": {"win": [], "lose": []},
            "scenario_events": [{
                "id": "ev", "trigger": "ON_TICK", "once": True,
                "conditions": [{
                    "condition_type": "OBJECT_STATE_TICK_AT_LEAST",
                    "target_object": "bush",
                    "state_key": "last_harvest_tick",
                    "ticks_offset": 10,
                    "treat_missing_as_passed": True,
                }],
                "effects": [],
            }],
        }
        result = ScenarioLoader().load_from_dict(scenario)
        cond = result.scenario_events[0].conditions[0]
        assert cond.condition_type == "OBJECT_STATE_TICK_AT_LEAST"
        assert cond.treat_missing_as_passed is True

    def test_loader_default_treat_missing_as_passed_false(self) -> None:
        """flag を JSON で省略すると default の False になる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = {
            "scenario_format_version": "1.0",
            "metadata": {
                "id": "x", "title": "x", "description": "x",
                "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
                "author": "x", "tags": [],
            },
            "item_specs": [],
            "environment": {
                "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                            "update_interval_ticks": 100, "announce_changes": False},
            },
            "spots": [{
                "id": "s", "name": "S", "description": "d", "category": "OTHER",
                "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
                "interior": {"objects": [{
                    "id": "bush", "name": "bush", "description": "d", "object_type": "OTHER",
                    "state": {},
                    "interactions": [],
                }]},
            }],
            "connections": [],
            "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
            "game_end_conditions": {"win": [], "lose": []},
            "scenario_events": [{
                "id": "ev", "trigger": "ON_TICK", "once": True,
                "conditions": [{
                    "condition_type": "OBJECT_STATE_TICK_AT_LEAST",
                    "target_object": "bush",
                    "state_key": "last_harvest_tick",
                    "ticks_offset": 10,
                }],
                "effects": [],
            }],
        }
        cond = ScenarioLoader().load_from_dict(scenario).scenario_events[0].conditions[0]
        assert cond.treat_missing_as_passed is False
