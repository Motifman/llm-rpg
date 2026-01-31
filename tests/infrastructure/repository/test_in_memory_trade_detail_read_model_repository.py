"""
InMemoryTradeDetailReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime

from ai_rpg_world.infrastructure.repository.in_memory_trade_detail_read_model_repository import InMemoryTradeDetailReadModelRepository
from ai_rpg_world.domain.trade.read_model.trade_detail_read_model import TradeDetailReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus


class TestInMemoryTradeDetailReadModelRepository:
    """InMemoryTradeDetailReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryTradeDetailReadModelRepository()

    def test_find_by_id_existing_detail(self):
        """存在する取引詳細をIDで検索できる"""
        detail = self.repository.find_by_id(TradeId(1))
        assert detail is not None
        assert detail.trade_id == TradeId(1)
        assert detail.item_name == "鋼の剣"
        assert detail.seller_name == "勇者"

    def test_find_by_id_non_existing_detail(self):
        """存在しない取引詳細をIDで検索するとNoneが返る"""
        detail = self.repository.find_by_id(TradeId(999))
        assert detail is None

    def test_find_by_ids_multiple_details(self):
        """複数の取引詳細をIDリストで検索できる"""
        detail_ids = [TradeId(1), TradeId(2), TradeId(999)]
        details = self.repository.find_by_ids(detail_ids)

        assert len(details) == 2
        assert details[0].trade_id == TradeId(1)
        assert details[1].trade_id == TradeId(2)

    def test_find_all_returns_all_details(self):
        """find_allですべての取引詳細を取得できる"""
        all_details = self.repository.find_all()
        assert len(all_details) >= 6  # サンプルデータが6件以上あるはず

        # 取引IDがユニークであることを確認
        detail_ids = [detail.trade_id for detail in all_details]
        assert len(detail_ids) == len(set(detail_ids))

    def test_save_and_find_new_detail(self):
        """新しい取引詳細を保存して検索できる"""
        # 新しい取引詳細を作成
        new_detail = TradeDetailReadModel.create_from_trade_data(
            trade_id=TradeId(100),
            item_spec_id=ItemSpecId(100),
            item_instance_id=ItemInstanceId(100),
            item_name="テストアイテム",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            item_description="テスト用のアイテム",
            durability_current=100,
            durability_max=100,
            requested_gold=1000,
            seller_name="テスト出品者",
            buyer_name=None,
            status=TradeStatus.ACTIVE.value
        )

        # 保存
        saved_detail = self.repository.save(new_detail)

        # 検索して確認
        found_detail = self.repository.find_by_id(TradeId(100))
        assert found_detail is not None
        assert found_detail.trade_id == TradeId(100)
        assert found_detail.item_name == "テストアイテム"
        assert found_detail.requested_gold == 1000
        assert found_detail.seller_name == "テスト出品者"

    def test_delete_existing_detail(self):
        """存在する取引詳細を削除できる"""
        # 削除前に存在することを確認
        detail_before = self.repository.find_by_id(TradeId(1))
        assert detail_before is not None

        # 削除
        result = self.repository.delete(TradeId(1))
        assert result is True

        # 削除後に存在しないことを確認
        detail_after = self.repository.find_by_id(TradeId(1))
        assert detail_after is None

    def test_delete_non_existing_detail(self):
        """存在しない取引詳細を削除しようとするとFalseが返る"""
        result = self.repository.delete(TradeId(999))
        assert result is False

    def test_find_detail_existing_trade(self):
        """find_detailで存在する取引の詳細を取得できる"""
        detail = self.repository.find_detail(TradeId(1))
        assert detail is not None
        assert detail.trade_id == TradeId(1)
        assert detail.item_name == "鋼の剣"
        assert detail.status == TradeStatus.ACTIVE.value

    def test_find_detail_non_existing_trade(self):
        """find_detailで存在しない取引の詳細を取得しようとするとNoneが返る"""
        detail = self.repository.find_detail(TradeId(999))
        assert detail is None

    def test_find_detail_completed_trade(self):
        """find_detailで完了した取引の詳細を取得できる"""
        detail = self.repository.find_detail(TradeId(4))  # ドラゴンスケールアーマー
        assert detail is not None
        assert detail.status == TradeStatus.COMPLETED.value
        assert detail.buyer_name == "騎士団長"

    def test_find_detail_cancelled_trade(self):
        """find_detailでキャンセルされた取引の詳細を取得できる"""
        detail = self.repository.find_detail(TradeId(5))  # 鉄の盾
        assert detail is not None
        assert detail.status == TradeStatus.CANCELLED.value
        assert detail.buyer_name is None

    def test_clear_removes_all_details(self):
        """clearですべての取引詳細が削除される"""
        # 削除前に取引詳細が存在することを確認
        assert self.repository.get_detail_count() > 0

        # クリア
        self.repository.clear()

        # 削除後に出品が存在しないことを確認
        assert self.repository.get_detail_count() == 0
        all_details = self.repository.find_all()
        assert len(all_details) == 0

    def test_get_detail_count_returns_correct_count(self):
        """get_detail_countで正しい取引詳細数を取得できる"""
        count = self.repository.get_detail_count()
        all_details = self.repository.find_all()
        assert count == len(all_details)

    def test_sample_data_has_various_trade_statuses(self):
        """サンプルデータに様々な取引ステータスが含まれている"""
        all_details = self.repository.find_all()

        statuses = set(detail.status for detail in all_details)
        assert TradeStatus.ACTIVE.value in statuses
        assert TradeStatus.COMPLETED.value in statuses
        assert TradeStatus.CANCELLED.value in statuses

    def test_sample_data_has_various_item_types(self):
        """サンプルデータに様々なアイテムタイプが含まれている"""
        all_details = self.repository.find_all()

        item_types = set(detail.item_type for detail in all_details)
        assert ItemType.EQUIPMENT in item_types
        assert ItemType.CONSUMABLE in item_types
        assert ItemType.MATERIAL in item_types

    def test_sample_data_has_equipment_with_durability(self):
        """サンプルデータに耐久度を持つ装備が含まれている"""
        all_details = self.repository.find_all()

        equipment_with_durability = [
            detail for detail in all_details
            if detail.is_equipment and detail.has_durability
        ]
        assert len(equipment_with_durability) > 0

        # 耐久度の割合計算が正しいことを確認
        for detail in equipment_with_durability:
            expected_percentage = detail.durability_current / detail.durability_max
            assert detail.durability_percentage == expected_percentage

    def test_sample_data_has_consumables_without_durability(self):
        """サンプルデータに耐久度を持たない消耗品が含まれている"""
        all_details = self.repository.find_all()

        consumables_without_durability = [
            detail for detail in all_details
            if detail.item_type == ItemType.CONSUMABLE and not detail.has_durability
        ]
        assert len(consumables_without_durability) > 0

    def test_sample_data_has_completed_trades_with_buyers(self):
        """サンプルデータに購入者が設定された完了した取引が含まれている"""
        all_details = self.repository.find_all()

        completed_trades_with_buyers = [
            detail for detail in all_details
            if detail.is_completed and detail.buyer_name is not None
        ]
        assert len(completed_trades_with_buyers) > 0

    def test_durability_percentage_calculation_edge_cases(self):
        """耐久度の割合計算のエッジケースが正しく処理される"""
        # 新しいアイテムを作成してテスト
        item_with_zero_max = TradeDetailReadModel.create_from_trade_data(
            trade_id=TradeId(200),
            item_spec_id=ItemSpecId(200),
            item_instance_id=ItemInstanceId(200),
            item_name="壊れたアイテム",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            item_description="耐久度が0のアイテム",
            durability_current=0,
            durability_max=0,
            requested_gold=100,
            seller_name="テスト出品者",
            buyer_name=None,
            status=TradeStatus.ACTIVE.value
        )

        # 保存
        self.repository.save(item_with_zero_max)

        # 検索して確認
        found_item = self.repository.find_by_id(TradeId(200))
        assert found_item is not None
        assert found_item.durability_percentage is None  # maxが0なのでNone

    def test_item_properties_calculations(self):
        """アイテムのプロパティ計算が正しく機能する"""
        all_details = self.repository.find_all()

        # 装備品の確認
        equipment_items = [detail for detail in all_details if detail.is_equipment]
        for item in equipment_items:
            assert item.item_equipment_type is not None

        # アクティブな取引の確認
        active_trades = [detail for detail in all_details if detail.is_active]
        for trade in active_trades:
            assert trade.status == TradeStatus.ACTIVE.value

        # 完了した取引の確認
        completed_trades = [detail for detail in all_details if detail.is_completed]
        for trade in completed_trades:
            assert trade.status == TradeStatus.COMPLETED.value
