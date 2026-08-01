"""所持品を object.state へ数量一致で投入し、複数人で蓄積できることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


FIRE_PIT_ID = SpotObjectId.create(10)
DRIFTWOOD_ID = ItemSpecId.create(100)


def _fire_pit(*, stacked: object = 0) -> SpotObject:
    deposit = InteractionDef(
        action_name="add_driftwood",
        display_label="流木を狼煙台に積む",
        preconditions=(),
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
                parameters={
                    "item_spec_id": DRIFTWOOD_ID.value,
                    "state_key": "driftwood_stacked",
                    "quantity": "all",
                },
            ),
        ),
    )
    light = InteractionDef(
        action_name="light_signal",
        display_label="狼煙を上げる",
        preconditions=(
            InteractionCondition(
                condition_type=(
                    InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST
                ),
                target_object_id=FIRE_PIT_ID,
                state_key="driftwood_stacked",
                required_quantity=3,
            ),
        ),
        effects=(),
    )
    return SpotObject(
        object_id=FIRE_PIT_ID,
        name="狼煙台",
        description="材料を積んでおける。",
        object_type=SpotObjectTypeEnum.OTHER,
        state={"driftwood_stacked": stacked},
        interactions=(deposit, light),
    )


def _interior(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestDistributedDeposit:
    """材料を一人へ集約せず、object.state に順次持ち寄れることを保証する。"""

    def test_two_players_deposit_two_plus_one_then_light_condition_passes(self) -> None:
        """別々の所持 2 本と 1 本を積むと合計 3 本になり、点火条件が成立する。"""
        service = SpotInteractionService()
        first = service.execute_interaction(
            _interior(_fire_pit()),
            FIRE_PIT_ID,
            "add_driftwood",
            frozenset({DRIFTWOOD_ID}),
            frozenset(),
            owned_item_spec_counts={DRIFTWOOD_ID: 2},
        )
        second = service.execute_interaction(
            first.new_interior,
            FIRE_PIT_ID,
            "add_driftwood",
            frozenset({DRIFTWOOD_ID}),
            frozenset(),
            owned_item_spec_counts={DRIFTWOOD_ID: 1},
        )

        lit = service.execute_interaction(
            second.new_interior,
            FIRE_PIT_ID,
            "light_signal",
            frozenset(),
            frozenset(),
            owned_item_spec_counts={},
        )

        assert len(first.item_spec_ids_to_remove) == 2
        assert len(second.item_spec_ids_to_remove) == 1
        assert (
            second.new_interior.get_object(FIRE_PIT_ID).state["driftwood_stacked"]
            == 3
        )
        assert lit.new_interior.get_object(FIRE_PIT_ID) is not None

    def test_holding_three_without_deposit_does_not_satisfy_light_condition(self) -> None:
        """流木を 3 本持っていても狼煙台が空なら、旧 HAS_ITEM 経路では点火できない。"""
        service = SpotInteractionService()

        with pytest.raises(InteractionNotAllowedException, match="必要: 3, いま: 0"):
            service.execute_interaction(
                _interior(_fire_pit()),
                FIRE_PIT_ID,
                "light_signal",
                frozenset({DRIFTWOOD_ID}),
                frozenset(),
                owned_item_spec_counts={DRIFTWOOD_ID: 3},
            )


class TestDepositQuantityConsistency:
    """所持品から取る数と object.state へ足す数が同一 effect 内で一致する。"""

    def test_requested_three_with_two_owned_removes_and_increments_two(self) -> None:
        """quantity=3 でも所持 2 個なら、減算予約と state 加算はともに 2 個になる。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": DRIFTWOOD_ID.value,
                "state_key": "driftwood_stacked",
                "quantity": 3,
            },
        )
        pit = _fire_pit()

        result = WorldGraphEffectService().apply_effects(
            interior=_interior(pit),
            acting_object=pit,
            effects=(effect,),
            world_flags=frozenset(),
            owned_item_spec_counts={DRIFTWOOD_ID: 2},
        )

        assert result.item_spec_ids_to_remove == (DRIFTWOOD_ID, DRIFTWOOD_ID)
        assert (
            result.new_interior.get_object(FIRE_PIT_ID).state["driftwood_stacked"]
            == 2
        )

    def test_all_moves_every_owned_item_and_leaves_no_remainder(self) -> None:
        """quantity=all は所持 4 個すべてを減算予約し、state にも 4 加える。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": DRIFTWOOD_ID.value,
                "state_key": "driftwood_stacked",
                "quantity": "all",
            },
        )
        pit = _fire_pit(stacked=1)

        result = WorldGraphEffectService().apply_effects(
            interior=_interior(pit),
            acting_object=pit,
            effects=(effect,),
            world_flags=frozenset(),
            owned_item_spec_counts={DRIFTWOOD_ID: 4},
        )

        assert result.item_spec_ids_to_remove == (DRIFTWOOD_ID,) * 4
        assert (
            result.new_interior.get_object(FIRE_PIT_ID).state["driftwood_stacked"]
            == 5
        )

    def test_missing_state_key_starts_from_zero(self) -> None:
        """対象 state にキーが無い場合は 0 起点で、投入数と同じ値を新設する。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": DRIFTWOOD_ID.value,
                "state_key": "new_material_stacked",
                "quantity": "all",
            },
        )
        pit = _fire_pit()

        result = WorldGraphEffectService().apply_effects(
            interior=_interior(pit),
            acting_object=pit,
            effects=(effect,),
            world_flags=frozenset(),
            owned_item_spec_counts={DRIFTWOOD_ID: 2},
        )

        assert result.new_interior.get_object(FIRE_PIT_ID).state == {
            "driftwood_stacked": 0,
            "new_material_stacked": 2,
        }

    def test_zero_owned_does_not_touch_object_state(self) -> None:
        """所持 0 個の単体 effect 実行は、remove 予約も state 変更も発生させない。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT,
            parameters={
                "item_spec_id": DRIFTWOOD_ID.value,
                "state_key": "driftwood_stacked",
                "quantity": "all",
            },
        )
        pit = _fire_pit(stacked=2)

        result = WorldGraphEffectService().apply_effects(
            interior=_interior(pit),
            acting_object=pit,
            effects=(effect,),
            world_flags=frozenset(),
            owned_item_spec_counts={},
        )

        assert result.item_spec_ids_to_remove == ()
        assert result.new_interior.get_object(FIRE_PIT_ID).state == {
            "driftwood_stacked": 2
        }


class TestObjectStateIntAtLeast:
    """整数 state の下限条件が ScenarioEventCondition と同じ 0 扱いをする。"""

    @pytest.mark.parametrize(
        ("state", "expected", "expected_message"),
        [
            ({"driftwood_stacked": 3}, True, None),
            (
                {"driftwood_stacked": 2},
                False,
                "必要な量が足りません (必要: 3, いま: 2)",
            ),
            ({}, False, "必要な量が足りません (必要: 3, いま: 0)"),
            (
                {"driftwood_stacked": "3"},
                False,
                "必要な量が足りません (必要: 3, いま: 0)",
            ),
        ],
    )
    def test_threshold_missing_and_non_int_semantics(
        self,
        state: dict[str, object],
        expected: bool,
        expected_message: str | None,
    ) -> None:
        """閾値ちょうどは成立し、1不足・キー不在・非整数は現在値0として不成立になる。"""
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST,
            target_object_id=FIRE_PIT_ID,
            state_key="driftwood_stacked",
            required_quantity=3,
        )
        interaction = InteractionDef(
            action_name="light_signal",
            display_label="狼煙を上げる",
            preconditions=(condition,),
            effects=(),
        )
        pit = SpotObject(
            object_id=FIRE_PIT_ID,
            name="狼煙台",
            description="材料を積んでおける。",
            object_type=SpotObjectTypeEnum.OTHER,
            state=state,
            interactions=(interaction,),
        )

        actual, message = SpotInteractionService().can_interact(
            interaction,
            pit,
            frozenset(),
            frozenset(),
            owned_item_spec_counts={},
            interior=_interior(pit),
        )

        assert actual is expected
        assert message == expected_message
