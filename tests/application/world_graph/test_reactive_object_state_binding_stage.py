"""ReactiveObjectStateBindingStageService の挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
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
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


def _spot(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _build_world_with_object(initial_state: dict):
    """1 spot + 1 object のミニマル世界を組む。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_spot(1))
    obj = SpotObject(
        object_id=SpotObjectId.create(7),
        name="berry_bush",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state=dict(initial_state),
        interactions=(),
    )
    interior = SpotInterior((), (obj,), (), ())
    spot_graph_repo = InMemorySpotGraphRepository(g)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(1), interior)
    flags = MutableWorldFlagState()

    class _NoopStatusRepo:
        def find_all(self):
            return []

    class _NoopInventoryRepo:
        def find_by_id(self, *_a, **_kw):
            return None

    class _NoopItemRepo:
        pass

    evaluator = ScenarioConditionEvaluator(
        world_flag_state=flags,
        spot_interior_repository=interior_repo,
        player_status_repository=_NoopStatusRepo(),
        player_inventory_repository=_NoopInventoryRepo(),
        item_repository=_NoopItemRepo(),
    )
    return spot_graph_repo, interior_repo, flags, evaluator


class TestReactiveObjectStateBindingStage:
    """ReactiveObjectStateBindingStageService.run の挙動。"""

    def test_predicate_true_merges_on_true_state(self) -> None:
        """predicate が True なら on_true_state_updates が object.state にマージされる。"""
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"available": False, "last_harvest_tick": 5}
        )
        flags.add("ready")
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="ready"),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(("available", False),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        stage.run(WorldTick(10))
        interior = interior_repo.find_by_spot_id(SpotId.create(1))
        obj = interior.objects[0]
        # on_true: available=True、他のキー (last_harvest_tick) は保持
        assert obj.state["available"] is True
        assert obj.state["last_harvest_tick"] == 5

    def test_predicate_false_merges_on_false_state(self) -> None:
        """predicate が False なら on_false_state_updates が反映される。"""
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"available": True}
        )
        # ready flag を立てない
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="ready"),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(("available", False),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        stage.run(WorldTick(10))
        obj = interior_repo.find_by_spot_id(SpotId.create(1)).objects[0]
        assert obj.state["available"] is False

    def test_idempotent_when_state_already_matches(self) -> None:
        """state が既に target と一致していれば save は呼ばれない。"""
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"available": False}
        )
        save_count = {"n": 0}
        original_save = interior_repo.save

        def counting_save(sid, interior):
            save_count["n"] += 1
            return original_save(sid, interior)

        interior_repo.save = counting_save  # type: ignore[assignment]

        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="ready"),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(("available", False),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        stage.run(WorldTick(10))
        # state は変わらないので save なし
        assert save_count["n"] == 0

    def test_other_state_keys_are_preserved(self) -> None:
        """binding が管理しないキーは元の値を保持する。"""
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"available": False, "color": "red", "size": 3}
        )
        flags.add("ready")
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="ready"),
            on_true_state_updates=(("available", True),),
            on_false_state_updates=(("available", False),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        stage.run(WorldTick(10))
        obj = interior_repo.find_by_spot_id(SpotId.create(1)).objects[0]
        assert obj.state == {"available": True, "color": "red", "size": 3}

    def test_asymmetric_one_way_write_only_when_predicate_true(self) -> None:
        """on_false_state_updates=() の binding は predicate=True のときだけ state を書き、False では何もしない。

        Phase 2-B: 一方向 lifecycle（例: 「条件成立で phase=ready に推移、
        不成立では phase は触らず作家管理に任せる」）の主要ユースケース。
        """
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"phase": "smelting"}
        )
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="ready_signal"),
            on_true_state_updates=(("phase", "ready"),),
            on_false_state_updates=(),  # 触らない
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        # predicate False: phase は smelting のまま
        stage.run(WorldTick(1))
        assert interior_repo.find_by_spot_id(SpotId.create(1)).objects[0].state["phase"] == "smelting"
        # predicate True に変える
        flags.add("ready_signal")
        stage.run(WorldTick(2))
        assert interior_repo.find_by_spot_id(SpotId.create(1)).objects[0].state["phase"] == "ready"

    def test_asymmetric_disjoint_keys_only_touch_their_side(self) -> None:
        """on_true / on_false が完全に異なるキーを書く場合、各側は自分のキーだけを書き換える。

        旧 same-key-set 制約撤廃後の核心ケース: 「条件 True で a だけ書く、
        False で b だけ書く」が正しく動き、相手側のキーには触らない
        （部分マージ semantics の保証）。
        """
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"a": 0, "b": 0}
        )
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="signal"),
            on_true_state_updates=(("a", 1),),
            on_false_state_updates=(("b", 1),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        # 1 周目: predicate False → b=1, a は変わらない
        stage.run(WorldTick(1))
        s1 = interior_repo.find_by_spot_id(SpotId.create(1)).objects[0].state
        assert s1["a"] == 0
        assert s1["b"] == 1
        # 2 周目: predicate True → a=1, b は前回値を保持
        flags.add("signal")
        stage.run(WorldTick(2))
        s2 = interior_repo.find_by_spot_id(SpotId.create(1)).objects[0].state
        assert s2["a"] == 1
        assert s2["b"] == 1

    def test_asymmetric_no_save_when_updates_empty(self) -> None:
        """空辞書 updates_for は save をトリガーしない（spurious write を避ける）。"""
        repo, interior_repo, flags, evaluator = _build_world_with_object(
            {"phase": "smelting"}
        )
        save_count = {"n": 0}
        original_save = interior_repo.save

        def counting_save(sid, interior):
            save_count["n"] += 1
            return original_save(sid, interior)

        interior_repo.save = counting_save  # type: ignore[assignment]

        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(7),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x"),
            on_true_state_updates=(("phase", "ready"),),
            on_false_state_updates=(),  # False 時は触らない
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        # predicate False (flag が立っていない) → 触らないので save 0 回
        stage.run(WorldTick(1))
        assert save_count["n"] == 0

    def test_missing_target_object_logs_warning_and_continues(self, caplog) -> None:
        """対象 object が見つからない binding は警告ログを出して他に影響しない。"""
        repo, interior_repo, _, evaluator = _build_world_with_object({"available": False})
        binding = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(999),  # 存在しない
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x"),
            on_true_state_updates=(("k", 1),),
            on_false_state_updates=(("k", 0),),
        )
        stage = ReactiveObjectStateBindingStageService(
            bindings=(binding,),
            spot_graph_repository=repo,
            spot_interior_repository=interior_repo,
            condition_evaluator=evaluator,
        )
        with caplog.at_level("WARNING"):
            stage.run(WorldTick(1))
        assert any("999" in r.message for r in caplog.records)
