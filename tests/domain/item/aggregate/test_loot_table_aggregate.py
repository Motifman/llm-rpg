import pytest
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate, LootEntry, LootResult
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.exception.item_exception import (
    LootWeightValidationException,
    QuantityValidationException
)


class TestLootTableAggregate:
    """LootTableAggregateの包括的なテストスイート"""

    def test_constructor_success(self):
        """正常なLootTableAggregateのコンストラクタテスト"""
        entry = LootEntry(ItemSpecId(1), weight=10, min_quantity=1, max_quantity=5)
        entries = [entry]
        table = LootTableAggregate("table-1", entries, "Test Table")

        assert table.loot_table_id == "table-1"
        assert table.name == "Test Table"
        assert len(table.entries) == 1
        assert table.entries[0] == entry

    def test_create_method_success(self):
        """create()メソッドの正常動作テスト"""
        entries = [LootEntry(ItemSpecId(1), weight=1)]
        table = LootTableAggregate.create("table-1", entries)
        assert table.loot_table_id == "table-1"

    def test_loot_entry_validation_negative_weight(self):
        """負の重みに対するバリデーションテスト"""
        with pytest.raises(LootWeightValidationException, match="Weight cannot be negative"):
            LootEntry(ItemSpecId(1), weight=-1)

    def test_loot_entry_validation_invalid_quantity(self):
        """不正な数量に対するバリデーションテスト"""
        # min_quantityが0以下
        with pytest.raises(QuantityValidationException, match="Min quantity must be positive"):
            LootEntry(ItemSpecId(1), weight=10, min_quantity=0)
        
        # max_quantityがmin_quantity未満
        with pytest.raises(QuantityValidationException, match="cannot be less than min quantity"):
            LootEntry(ItemSpecId(1), weight=10, min_quantity=5, max_quantity=4)

    def test_aggregate_validation_total_weight_zero(self):
        """合計重みが0の場合のバリデーションテスト"""
        entries = [LootEntry(ItemSpecId(1), weight=0)]
        with pytest.raises(LootWeightValidationException, match="Total weight must be positive"):
            LootTableAggregate("table-1", entries)

    def test_roll_deterministic(self):
        """確定的な抽選のテスト"""
        entry = LootEntry(ItemSpecId(1), weight=100, min_quantity=2, max_quantity=2)
        table = LootTableAggregate("table-1", [entry])
        
        result = table.roll()
        assert result is not None
        assert result.item_spec_id == ItemSpecId(1)
        assert result.quantity == 2

    def test_roll_empty_table_raises_exception(self):
        """空のテーブル作成時に例外が投げられるテスト"""
        from ai_rpg_world.domain.item.exception.item_exception import LootTableValidationException
        with pytest.raises(LootTableValidationException):
            LootTableAggregate("table-empty", [])

    def test_roll_probability_distribution(self):
        """抽選確率の分布テスト"""
        entry1 = LootEntry(ItemSpecId(101), weight=90)
        entry2 = LootEntry(ItemSpecId(102), weight=10)
        table = LootTableAggregate("table-prob", [entry1, entry2])
        
        results = {101: 0, 102: 0}
        iterations = 1000
        for _ in range(iterations):
            res = table.roll()
            results[res.item_spec_id.value] += 1
            
        # 統計的に90:10に近いことを確認（緩めのマージン）
        assert 800 < results[101] < 1000
        assert 0 < results[102] < 200

    def test_entries_immutability(self):
        """entriesプロパティの不変性テスト"""
        entry = LootEntry(ItemSpecId(1), weight=10)
        table = LootTableAggregate("table-1", [entry])
        
        entries = table.entries
        entries.append(LootEntry(ItemSpecId(2), weight=20))
        
        assert len(table.entries) == 1
