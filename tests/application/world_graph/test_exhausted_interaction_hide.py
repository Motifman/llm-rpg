"""永続失敗 (= 取り尽くした) interaction を snapshot から落とす挙動 (#343)。

第24回実験 OFF run で `search_cockpit` を 19 回 retry した silent failure に
対する構造的修正の単体テスト。OBJECT_STATE precondition が現在失敗している
interaction は available_actions から落ちる。HAS_ITEM 等のプレイヤー / 環境
依存条件は隠さない (探索の手掛かりを残す)。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    _has_failing_object_state_precondition,
)
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
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


COCKPIT_ID = SpotObjectId.create(1)


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


def _make_interaction(condition_type, **kwargs) -> InteractionDef:
    cond = InteractionCondition(condition_type=condition_type, **kwargs)
    return InteractionDef(
        action_name="search_cockpit",
        display_label="漁る",
        preconditions=(cond,),
        effects=(),
    )


class TestObjectStatePreconditionFailureHidesInteraction:
    """OBJECT_STATE が現在失敗 → interaction は隠す (= cockpit retry の停止)。"""

    def test_OBJECT_STATE_が現在の値と一致しないなら_true(self) -> None:
        interior = _make_interior({"opened": True})
        interaction = _make_interaction(
            InteractionConditionTypeEnum.OBJECT_STATE,
            target_object_id=COCKPIT_ID,
            required_state={"opened": False},
        )
        assert _has_failing_object_state_precondition(interaction, interior) is True

    def test_OBJECT_STATE_が現在の値と一致するなら_false(self) -> None:
        interior = _make_interior({"opened": False})
        interaction = _make_interaction(
            InteractionConditionTypeEnum.OBJECT_STATE,
            target_object_id=COCKPIT_ID,
            required_state={"opened": False},
        )
        assert _has_failing_object_state_precondition(interaction, interior) is False


class TestNonObjectStateConditionsAreNotHidden:
    """HAS_ITEM / ALWAYS / FLAG_SET 等は OBJECT_STATE ではないので落とさない。"""

    def test_HAS_ITEM_は_対象外_常に_false(self) -> None:
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionConditionTypeEnum.HAS_ITEM,
            target_item_spec_id=ItemSpecId.create(42),
        )
        # HAS_ITEM の充足は player 状態 (snapshot builder の外) で判定するので、
        # ここでは「OBJECT_STATE による永続失敗ではない」と判断 = false。
        assert _has_failing_object_state_precondition(interaction, interior) is False

    def test_ALWAYS_は_対象外_常に_false(self) -> None:
        interior = _make_interior({})
        interaction = _make_interaction(InteractionConditionTypeEnum.ALWAYS)
        assert _has_failing_object_state_precondition(interaction, interior) is False


class TestEdgeCases:
    """target_object_id 無効 / required_state 空のときは hide しない (安全側)。"""

    def test_target_object_id_未指定なら_false(self) -> None:
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionConditionTypeEnum.OBJECT_STATE,
            target_object_id=None,
            required_state={"opened": False},
        )
        assert _has_failing_object_state_precondition(interaction, interior) is False

    def test_対象_object_が_interior_に無いなら_false(self) -> None:
        interior = _make_interior({})
        interaction = _make_interaction(
            InteractionConditionTypeEnum.OBJECT_STATE,
            target_object_id=SpotObjectId.create(999),  # 存在しない
            required_state={"opened": False},
        )
        assert _has_failing_object_state_precondition(interaction, interior) is False
