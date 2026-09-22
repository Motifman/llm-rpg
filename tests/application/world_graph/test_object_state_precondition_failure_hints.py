"""OBJECT_STATE precondition の失敗理由ヒント生成の挙動。

第24回実験 OFF run で `search_cockpit` を 19 回 retry した静かな失敗に対する
構造的修正の単体テスト。OBJECT_STATE precondition が現在失敗している
interaction は、action を隠さず失敗理由ヒントを添えて表示する。このファイルは
そのヒント本文が条件の failure_message から作られることを保証する。
HAS_ITEM 等のプレイヤー / 環境依存条件は対象外。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    _object_state_precondition_failure_hints,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import (
    InteractionDef,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
    SpotObjectId,
)

COCKPIT_ID = SpotObjectId.create(1)
DEFAULT_HINT = "現在は条件を満たしていない"


def _make_interior(state: dict) -> SpotInterior:
    cockpit = SpotObject(
        object_id=COCKPIT_ID,
        name="cockpit",
        description="d",
        object_type=ObjectTypeEnum.RESOURCE,
        state=state,
        interactions=(),
    )
    return SpotInterior(
        sub_locations=(),
        objects=(cockpit,),
        ground_items=(),
        discoverable_items=(),
    )


def _make_interaction(*conditions: InteractionCondition) -> InteractionDef:
    return InteractionDef(
        action_name="search_cockpit",
        display_label="漁る",
        preconditions=conditions,
        effects=(),
    )


class TestFailingObjectStateProducesHint:
    """OBJECT_STATE が現在の値と一致しないとき、条件の failure_message を返す。"""

    def test_mismatched_state_returns_failure_message(self) -> None:
        """required_state が現在値と一致しないとき、その条件の failure_message を 1 件返す。"""
        interior = _make_interior({"opened": True})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False},
                failure_message="もう漁り尽くした",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == (
            "もう漁り尽くした",
        )

    def test_empty_failure_message_falls_back_to_default_hint(self) -> None:
        """failure_message が空文字のとき、既定文でヒントを埋める。"""
        interior = _make_interior({"opened": True})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False},
                failure_message="",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == (
            DEFAULT_HINT,
        )

    def test_blank_failure_message_falls_back_to_default_hint(self) -> None:
        """failure_message が空白だけのとき、既定文でヒントを埋める。"""
        interior = _make_interior({"opened": True})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False},
                failure_message="   ",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == (
            DEFAULT_HINT,
        )

    def test_multiple_mismatched_keys_in_one_condition_return_single_hint(self) -> None:
        """1 つの条件で複数の key が不一致でも、ヒントは条件あたり 1 件にまとめる。"""
        interior = _make_interior({"opened": True, "empty": True})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False, "empty": False},
                failure_message="もう漁り尽くした",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == (
            "もう漁り尽くした",
        )

    def test_multiple_failing_conditions_return_hints_in_declared_order(self) -> None:
        """失敗している条件が複数あるとき、宣言順に failure_message を並べて返す。"""
        interior = _make_interior({"opened": True, "powered": False})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False},
                failure_message="もう漁り尽くした",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"powered": True},
                failure_message="電源が入っていない",
            ),
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == (
            "もう漁り尽くした",
            "電源が入っていない",
        )


class TestSatisfiedObjectStateProducesNoHint:
    """OBJECT_STATE が満たされているときはヒントを出さない。"""

    def test_matching_state_returns_empty(self) -> None:
        """required_state が現在値と一致するとき、ヒントは空になる。"""
        interior = _make_interior({"opened": False})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={"opened": False},
                failure_message="もう漁り尽くした",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()


class TestNonObjectStateConditionsProduceNoHint:
    """HAS_ITEM / ALWAYS は OBJECT_STATE ではないので、この関数はヒントを出さない。"""

    def test_has_item_returns_empty(self) -> None:
        """HAS_ITEM の充足はプレイヤー状態で決まるので、ここではヒントを出さない。"""
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=ItemSpecId.create(42),
                failure_message="道具が足りない",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()

    def test_always_returns_empty(self) -> None:
        """ALWAYS は失敗しないので、ヒントを出さない。"""
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.ALWAYS,
                failure_message="出てはいけない",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()


class TestIncompleteConditionsProduceNoHint:
    """条件の指定が不足しているときは、判定できないのでヒントを出さない。"""

    def test_target_object_id_unspecified_returns_empty(self) -> None:
        """target_object_id が未指定のとき、対象を特定できないのでヒントを出さない。"""
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=None,
                required_state={"opened": False},
                failure_message="出てはいけない",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()

    def test_required_state_empty_returns_empty(self) -> None:
        """required_state が空のとき、比較する値が無いのでヒントを出さない。"""
        interior = _make_interior({"opened": True})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=COCKPIT_ID,
                required_state={},
                failure_message="出てはいけない",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()

    def test_target_object_missing_from_interior_returns_empty(self) -> None:
        """対象 object が interior に無いとき、状態を読めないのでヒントを出さない。"""
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=SpotObjectId.create(999),
                required_state={"opened": False},
                failure_message="出てはいけない",
            )
        )
        assert _object_state_precondition_failure_hints(interaction, interior) == ()
