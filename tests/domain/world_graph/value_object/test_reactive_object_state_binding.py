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

    def test_keys_only_on_true_rejected(self) -> None:
        """on_true にしかないキーを拒否（False 側で値が固定されないと整合が崩れる）。"""
        with pytest.raises(ReactiveObjectStateBindingValidationException, match="only in on_true"):
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(1),
                predicate=_flag_pred(),
                on_true_state_updates=(("a", 1), ("b", 2)),
                on_false_state_updates=(("a", 0),),  # b が抜けている
            )

    def test_keys_only_on_false_rejected(self) -> None:
        """on_false にしかないキーを拒否。"""
        with pytest.raises(ReactiveObjectStateBindingValidationException, match="only in on_false"):
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(1),
                predicate=_flag_pred(),
                on_true_state_updates=(("a", 1),),
                on_false_state_updates=(("a", 0), ("b", 2)),
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
