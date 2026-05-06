"""ReactivePassageBinding 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
    ReactivePassageBindingValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


def _flag_predicate(name: str = "x") -> ScenarioEventCondition:
    return ScenarioEventCondition(condition_type="FLAG_SET", flag_name=name)


class TestReactivePassageBindingValidation:
    """ReactivePassageBinding の構築バリデーション。"""

    def test_valid_binding_constructs(self) -> None:
        """有効な引数なら構築できる。"""
        b = ReactivePassageBinding(
            target_connection_id=ConnectionId.create(1),
            predicate=_flag_predicate(),
            on_true_state="OPEN",
            on_false_state="LOCKED",
        )
        assert b.on_true_state == "OPEN"
        assert b.on_false_state == "LOCKED"

    def test_empty_on_true_state_rejected(self) -> None:
        """on_true_state が空文字列なら拒否する。"""
        with pytest.raises(ReactivePassageBindingValidationException, match="on_true_state"):
            ReactivePassageBinding(
                target_connection_id=ConnectionId.create(1),
                predicate=_flag_predicate(),
                on_true_state="",
                on_false_state="LOCKED",
            )

    def test_empty_on_false_state_rejected(self) -> None:
        """on_false_state が空文字列なら拒否する。"""
        with pytest.raises(ReactivePassageBindingValidationException, match="on_false_state"):
            ReactivePassageBinding(
                target_connection_id=ConnectionId.create(1),
                predicate=_flag_predicate(),
                on_true_state="OPEN",
                on_false_state="",
            )

    def test_same_states_rejected(self) -> None:
        """on_true と on_false が同じ state なら reactive の意味が無いので拒否する。"""
        with pytest.raises(ReactivePassageBindingValidationException, match="differ"):
            ReactivePassageBinding(
                target_connection_id=ConnectionId.create(1),
                predicate=_flag_predicate(),
                on_true_state="OPEN",
                on_false_state="OPEN",
            )
