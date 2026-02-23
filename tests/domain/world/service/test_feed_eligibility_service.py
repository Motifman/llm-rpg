"""餌適合性判定 is_feed_for_monster のテスト。"""

import pytest
from ai_rpg_world.domain.world.service.feed_eligibility_service import is_feed_for_monster
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootEntry
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class TestFeedEligibilityService:
    """is_feed_for_monster の正常・境界・例外ケース"""

    def test_returns_true_when_entries_contain_preferred_id(self):
        """LootTable の entries に preferred の item_spec_id が含まれるとき True"""
        entries = [
            LootEntry(ItemSpecId(1), weight=50),
            LootEntry(ItemSpecId(2), weight=50),
        ]
        preferred = {ItemSpecId(2)}
        assert is_feed_for_monster(entries, preferred) is True

    def test_returns_false_when_no_overlap(self):
        """entries と preferred に共通の item_spec_id がないとき False"""
        entries = [LootEntry(ItemSpecId(1), weight=100)]
        preferred = {ItemSpecId(2), ItemSpecId(3)}
        assert is_feed_for_monster(entries, preferred) is False

    def test_returns_false_when_preferred_none(self):
        """preferred_feed_item_spec_ids が None のとき False"""
        entries = [LootEntry(ItemSpecId(1), weight=100)]
        assert is_feed_for_monster(entries, None) is False

    def test_returns_false_when_preferred_empty_set(self):
        """preferred が空集合のとき False"""
        entries = [LootEntry(ItemSpecId(1), weight=100)]
        assert is_feed_for_monster(entries, set()) is False

    def test_returns_true_when_multiple_preferred_match(self):
        """複数の preferred のうちいずれかが entries に含まれるとき True"""
        entries = [LootEntry(ItemSpecId(2), weight=100)]
        preferred = {ItemSpecId(1), ItemSpecId(2), ItemSpecId(3)}
        assert is_feed_for_monster(entries, preferred) is True

    def test_returns_false_when_entries_empty(self):
        """entries が空のとき False"""
        preferred = {ItemSpecId(1)}
        assert is_feed_for_monster([], preferred) is False
