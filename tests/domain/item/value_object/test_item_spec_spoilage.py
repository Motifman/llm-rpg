"""ItemSpec.spoils_after_ticks のバリデーション検証 (Phase D-2)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.exception import ItemSpecValidationException
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize


def _make(spoils_after_ticks=None) -> ItemSpec:
    """テスト用に最低限のフィールドだけ埋めた ItemSpec を作る。"""
    return ItemSpec(
        item_spec_id=ItemSpecId.create(1),
        name="生の魚",
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description="釣り上げたばかりの魚。",
        max_stack_size=MaxStackSize(1),
        spoils_after_ticks=spoils_after_ticks,
    )


class TestItemSpecSpoilsAfterTicks:
    """spoils_after_ticks のバリデーション挙動。"""

    def test_None_は_腐らないアイテムとして受理される(self) -> None:
        spec = _make(spoils_after_ticks=None)
        assert spec.spoils_after_ticks is None

    def test_正の整数なら受理される(self) -> None:
        spec = _make(spoils_after_ticks=8)
        assert spec.spoils_after_ticks == 8

    def test_0_は無意味なので弾く(self) -> None:
        with pytest.raises(ItemSpecValidationException):
            _make(spoils_after_ticks=0)

    def test_負の値は弾く(self) -> None:
        with pytest.raises(ItemSpecValidationException):
            _make(spoils_after_ticks=-1)
