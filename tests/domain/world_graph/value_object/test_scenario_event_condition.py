"""ScenarioEventCondition の合成条件 (NOT/AND/OR) バリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
    ScenarioEventConditionValidationException,
)


class TestNotCondition:
    """NOT 合成条件のバリデーション挙動。"""

    def test_not_with_single_child_is_valid(self) -> None:
        """NOT に子条件 1 個を渡せば構築できる。"""
        flag = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        not_cond = ScenarioEventCondition(condition_type="NOT", children=(flag,))
        assert not_cond.is_composite is True
        assert len(not_cond.children) == 1

    def test_not_with_zero_children_rejected(self) -> None:
        """NOT に子条件 0 個ならバリデーション例外。"""
        with pytest.raises(ScenarioEventConditionValidationException, match="NOT"):
            ScenarioEventCondition(condition_type="NOT", children=())

    def test_not_with_multiple_children_rejected(self) -> None:
        """NOT に子条件 2 個以上はバリデーション例外。"""
        flag1 = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        flag2 = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="y")
        with pytest.raises(ScenarioEventConditionValidationException, match="NOT"):
            ScenarioEventCondition(condition_type="NOT", children=(flag1, flag2))


class TestAndOrCondition:
    """AND/OR 合成条件のバリデーション挙動。"""

    def test_and_with_no_children_is_valid(self) -> None:
        """AND は children 空でも構築可（vacuous truth は評価器側で扱う）。"""
        cond = ScenarioEventCondition(condition_type="AND")
        assert cond.is_composite is True
        assert cond.children == ()

    def test_or_with_no_children_is_valid(self) -> None:
        """OR は children 空でも構築可（評価時は False）。"""
        cond = ScenarioEventCondition(condition_type="OR")
        assert cond.is_composite is True

    def test_and_can_nest_arbitrary_depth(self) -> None:
        """AND の中に NOT、その中に leaf という入れ子が許容される。"""
        flag = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        not_flag = ScenarioEventCondition(condition_type="NOT", children=(flag,))
        and_cond = ScenarioEventCondition(condition_type="AND", children=(not_flag,))
        assert and_cond.children[0].condition_type == "NOT"
        assert and_cond.children[0].children[0].flag_name == "x"


class TestChildrenTupleInvariant:
    """children が tuple 以外なら拒否する（frozen dataclass の hash 不変条件）。"""

    def test_list_children_rejected(self) -> None:
        """children に list を渡すと ValidationException を投げる。"""
        flag = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        with pytest.raises(ScenarioEventConditionValidationException, match="tuple"):
            ScenarioEventCondition(condition_type="NOT", children=[flag])  # type: ignore[arg-type]

    def test_tuple_children_is_hashable(self) -> None:
        """tuple children を持つ条件は hash() 可能で frozen の不変条件を保つ。"""
        flag = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        cond = ScenarioEventCondition(condition_type="NOT", children=(flag,))
        # set に入れられれば hash() が動いている
        assert {cond} == {cond}


class TestLeafCondition:
    """leaf 条件と children の整合性検証。"""

    def test_leaf_with_children_rejected(self) -> None:
        """leaf 条件（FLAG_SET 等）に children を持たせるとバリデーション例外。"""
        child = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        with pytest.raises(ScenarioEventConditionValidationException, match="leaf"):
            ScenarioEventCondition(
                condition_type="FLAG_SET", flag_name="y", children=(child,)
            )

    def test_leaf_without_children_is_valid(self) -> None:
        """普通の leaf は children 無しで構築できて is_composite=False。"""
        cond = ScenarioEventCondition(condition_type="FLAG_SET", flag_name="x")
        assert cond.is_composite is False
        assert cond.children == ()
