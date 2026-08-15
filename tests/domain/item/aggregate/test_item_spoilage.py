"""ItemAggregate.advance_spoilage の腐敗進行ルール検証。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.value_object.spoilage import (
    STATE_KEY_ACQUIRED_AT_TICK,
    STATE_KEY_SPOILED,
    SpoilageAdvanceKind,
)


def _spec(*, spoils_after_ticks=None) -> ItemSpec:
    return ItemSpec(
        item_spec_id=ItemSpecId.create(101),
        name="生の魚",
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description="生の魚",
        max_stack_size=MaxStackSize(1),
        spoils_after_ticks=spoils_after_ticks,
    )


def _aggregate(*, spoils_after_ticks=None, state=None) -> ItemAggregate:
    return ItemAggregate.create(
        item_instance_id=ItemInstanceId(7001),
        item_spec=_spec(spoils_after_ticks=spoils_after_ticks),
        quantity=1,
        state=state,
    )


class TestItemAggregateAdvanceSpoilage:
    """ItemAggregate.advance_spoilage が腐敗進行ルールを集約内で完結させること。"""

    def test_no_spoils_after_ticks_leaves_state_unchanged(self) -> None:
        """spoils_after_ticks 無しなら UNCHANGED で state は空のまま。"""
        item = _aggregate(spoils_after_ticks=None)

        result = item.advance_spoilage(WorldTick(5))

        assert result.kind is SpoilageAdvanceKind.UNCHANGED
        assert item.state == {}

    def test_first_call_records_acquired_at_without_spoiling(self) -> None:
        """初回呼び出しで acquired_at_tick が現在 tick になり NEWLY_SPOILED ではない。"""
        item = _aggregate(spoils_after_ticks=8)

        result = item.advance_spoilage(WorldTick(3))

        assert result.kind is SpoilageAdvanceKind.ACQUIRED_AT_RECORDED
        assert item.state[STATE_KEY_ACQUIRED_AT_TICK] == 3
        assert item.state.get(STATE_KEY_SPOILED) is not True

    def test_existing_acquired_at_tick_is_not_overwritten(self) -> None:
        """既にある acquired_at_tick は上書きしない。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: 10},
        )

        result = item.advance_spoilage(WorldTick(11))

        assert result.kind is SpoilageAdvanceKind.UNCHANGED
        assert item.state[STATE_KEY_ACQUIRED_AT_TICK] == 10
        assert item.state.get(STATE_KEY_SPOILED) is not True

    def test_before_threshold_does_not_spoil(self) -> None:
        """閾値未到達は UNCHANGED で spoiled が立たない。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: 0},
        )

        result = item.advance_spoilage(WorldTick(7))

        assert result.kind is SpoilageAdvanceKind.UNCHANGED
        assert item.state.get(STATE_KEY_SPOILED) is not True

    def test_exact_threshold_marks_newly_spoiled(self) -> None:
        """閾値ちょうどで NEWLY_SPOILED。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: 0},
        )

        result = item.advance_spoilage(WorldTick(8))

        assert result.kind is SpoilageAdvanceKind.NEWLY_SPOILED
        assert item.state[STATE_KEY_SPOILED] is True

    def test_beyond_threshold_marks_newly_spoiled(self) -> None:
        """閾値超過でも NEWLY_SPOILED。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: 0},
        )

        result = item.advance_spoilage(WorldTick(20))

        assert result.kind is SpoilageAdvanceKind.NEWLY_SPOILED
        assert item.state[STATE_KEY_SPOILED] is True

    def test_already_spoiled_is_unchanged(self) -> None:
        """既に spoiled なら UNCHANGED (再マージしない / 二重進行しない)。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: 0, STATE_KEY_SPOILED: True},
        )

        result = item.advance_spoilage(WorldTick(100))

        assert result.kind is SpoilageAdvanceKind.UNCHANGED
        assert item.state[STATE_KEY_SPOILED] is True

    def test_non_int_acquired_at_returns_invalid_without_state_change(self) -> None:
        """acquired_at_tick が int 以外なら INVALID_ACQUIRED_AT で state 不変。"""
        item = _aggregate(
            spoils_after_ticks=8,
            state={STATE_KEY_ACQUIRED_AT_TICK: "bad"},
        )
        original_state = dict(item.state)

        result = item.advance_spoilage(WorldTick(100))

        assert result.kind is SpoilageAdvanceKind.INVALID_ACQUIRED_AT
        assert dict(item.state) == original_state
