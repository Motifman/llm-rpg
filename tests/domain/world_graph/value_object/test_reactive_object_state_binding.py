"""ReactiveObjectStateBinding のバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ReactiveObjectStateBindingValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _flag_pred(name: str = "x") -> ScenarioEventCondition:
    return ScenarioEventCondition(condition_type="FLAG_SET", flag_name=name)


class TestReactiveObjectStateBindingValidation:
    """構築バリデーション。"""

    def test_minimal_binding_constructs(self) -> None:
        """両 updates が同じキーで揃っていれば構築できる。"""
        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=_flag_pred(),
            on_true_state_updates=(("rust_level", "high"),),
            on_false_state_updates=(("rust_level", "low"),),
        )
        assert b.managed_state_keys == ("rust_level",)

    def test_both_updates_empty_rejected(self) -> None:
        """on_true / on_false の両方が空なら拒否（binding として機能しない）。"""
        with pytest.raises(ReactiveObjectStateBindingValidationException):
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(1),
                predicate=_flag_pred(),
                on_true_state_updates=(),
                on_false_state_updates=(),
            )

    def test_asymmetric_keys_allowed_for_one_way_lifecycle(self) -> None:
        """Phase 2-B: on_true / on_false で異なるキー集合を許容する。

        旧仕様では同じキーを両側に書く必要があったが、一方向 lifecycle
        （例: 「条件を満たした時だけ phase=ready に遷移、満たさない時は
        触らない」）を表現するためにこの制約を撤廃した。
        """
        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=_flag_pred(),
            on_true_state_updates=(("phase", "ready"),),
            on_false_state_updates=(),  # 触らない
        )
        assert b.updates_for(True) == {"phase": "ready"}
        assert b.updates_for(False) == {}
        # managed_state_keys は両側の和集合
        assert b.managed_state_keys == ("phase",)

    def test_asymmetric_with_both_sides_disjoint(self) -> None:
        """両側で別々のキーを書く asymmetric 構成も許容される。"""
        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=_flag_pred(),
            on_true_state_updates=(("a", 1),),
            on_false_state_updates=(("b", 2),),
        )
        assert b.updates_for(True) == {"a": 1}
        assert b.updates_for(False) == {"b": 2}
        assert set(b.managed_state_keys) == {"a", "b"}

    def test_duplicate_key_within_on_true_rejected(self) -> None:
        """on_true_state_updates 内で同一キーが重複している場合は拒否。"""
        with pytest.raises(ReactiveObjectStateBindingValidationException, match="duplicate key"):
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(1),
                predicate=_flag_pred(),
                on_true_state_updates=(("a", 1), ("a", 2)),
                on_false_state_updates=(("a", 0),),
            )

    def test_duplicate_key_within_on_false_rejected(self) -> None:
        """on_false_state_updates 内で同一キーが重複している場合も同じく拒否（対称チェック）。"""
        with pytest.raises(
            ReactiveObjectStateBindingValidationException,
            match="duplicate key.*on_false_state_updates",
        ):
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(1),
                predicate=_flag_pred(),
                on_true_state_updates=(("a", 1),),
                on_false_state_updates=(("a", 0), ("a", 9)),
            )

    def test_updates_for_returns_correct_dict(self) -> None:
        """updates_for は predicate_value に応じた dict を返す。"""
        b = ReactiveObjectStateBinding(
            target_object_id=SpotObjectId.create(1),
            predicate=_flag_pred(),
            on_true_state_updates=(("k", "T"),),
            on_false_state_updates=(("k", "F"),),
        )
        assert b.updates_for(True) == {"k": "T"}
        assert b.updates_for(False) == {"k": "F"}
