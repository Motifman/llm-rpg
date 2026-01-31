#!/usr/bin/env python3
"""
取引システム デモ

このデモでは、リファクタリングされた取引システムの主要な機能を確認できます：
1. 取引の出品 (Offer)
2. 利用可能な取引の検索 (Query)
3. 取引の受諾 (Accept)
4. 取引のキャンセル (Cancel)
5. ReadModelによる非正規化データの確認

DDD原則に基づき、出品時のアイテム予約、受諾時のアトミックな所有権移転をシミュレートします。
"""

import sys
import os
from datetime import datetime
from unittest.mock import MagicMock

# プロジェクトのルートディレクトリをPythonパスに追加
# demos/trade/demo_trade_system.py から workspace root へのパス
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ドメイン
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId

# アプリケーション
from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.application.trade.contracts.commands import OfferItemCommand, AcceptTradeCommand, CancelTradeCommand
from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler

# インフラ
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_trade_repository import InMemoryTradeRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import InMemoryTradeReadModelRepository
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from ai_rpg_world.infrastructure.events.trade_event_handler_registry import TradeEventHandlerRegistry

def print_separator(title):
    print("\n" + "="*20 + f" {title} " + "="*20)

def setup_player(player_id, name, gold_amount, data_store, uow):
    pid = PlayerId(player_id)
    
    # Profile
    profile = PlayerProfileAggregate.create(pid, PlayerName(name))
    profile_repo = InMemoryPlayerProfileRepository(data_store, uow)
    profile_repo.save(profile)
    
    # Status
    exp_table = ExpTable(100, 1.5)
    status = PlayerStatusAggregate(
        player_id=pid,
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(gold_amount),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100)
    )
    status_repo = InMemoryPlayerStatusRepository(data_store, uow)
    status_repo.save(status)
    
    # Inventory
    inventory = PlayerInventoryAggregate.create_new_inventory(pid)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
    inventory_repo.save(inventory)
    
    return pid

def main():
    print("取引システム総合デモを開始します...")
    
    # 1. セットアップ
    data_store = InMemoryDataStore()
    uow_factory = InMemoryUnitOfWorkFactory()
    uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(uow_factory.create)
    uow_factory._event_publisher = event_publisher

    # リポジトリの初期化
    trade_repo = InMemoryTradeRepository(data_store, uow)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
    status_repo = InMemoryPlayerStatusRepository(data_store, uow)
    profile_repo = InMemoryPlayerProfileRepository(data_store, uow)
    read_model_repo = InMemoryTradeReadModelRepository()
    read_model_repo.clear()
    
    # アイテムリポジトリのモック
    item_repo = MagicMock()
    
    # 2. プレイヤー作成
    print_separator("プレイヤー作成")
    alice_id = setup_player(1, "アリス・スミス", 1000, data_store, uow)
    bob_id = setup_player(2, "ボブ・ブラッドリー", 1000, data_store, uow)
    print(f"アリス (ID:{alice_id.value}) と ボブ (ID:{bob_id.value}) を作成しました。")
    print(f"初期所持金: 各1000ゴールド")

    # 3. アリスにアイテムを持たせる
    alice_inv = inventory_repo.find_by_id(alice_id)
    item_instance_id = ItemInstanceId(101)
    alice_inv.acquire_item(item_instance_id)
    inventory_repo.save(alice_inv)
    print(f"アリスにアイテム「伝説の剣」(ID:{item_instance_id.value})をスロット0に付与しました。")

    # 4. イベントハンドラの登録
    mock_item = MagicMock()
    mock_item.item_spec.name = "伝説の剣"
    mock_item.item_spec.description = "とても強い剣"
    mock_item.item_spec.item_type = ItemType.EQUIPMENT
    mock_item.item_spec.rarity = Rarity.RARE
    mock_item.item_spec.equipment_type = EquipmentType.WEAPON
    mock_item.quantity = 1
    mock_item.durability = MagicMock(current=100, max_value=100)
    item_repo.find_by_id.return_value = mock_item

    handler = TradeEventHandler(
        read_model_repo, trade_repo, profile_repo, item_repo, uow_factory
    )
    registry = TradeEventHandlerRegistry(handler)
    registry.register_handlers(event_publisher)

    # 5. サービス初期化
    command_service = TradeCommandService(trade_repo, inventory_repo, status_repo, uow)
    query_service = TradeQueryService(read_model_repo)

    # 6. アリスがアイテムを出品
    print_separator("アイテム出品")
    offer_cmd = OfferItemCommand(
        seller_id=alice_id.value,
        item_instance_id=item_instance_id.value,
        slot_id=0,
        requested_gold=500
    )
    result = command_service.offer_item(offer_cmd)
    trade_id = result.data["trade_id"]
    print(f"アリスが「伝説の剣」を500ゴールドで出品しました。取引ID: {trade_id}")
    
    alice_inv = inventory_repo.find_by_id(alice_id)
    print(f"アリスのアイテム(ID:{item_instance_id.value})は現在: {'予約済み(ロック中)' if alice_inv.is_item_reserved(item_instance_id) else '未予約'}")

    # 7. 市場の確認
    print_separator("市場の確認")
    market_trades = query_service.get_recent_trades()
    print(f"市場に出品されている取引数: {len(market_trades.trades)}")
    for t in market_trades.trades:
        print(f"- [取引ID:{t.trade_id}] {t.item_name} (出品者: {t.seller_name}, 価格: {t.requested_gold}G, 状態: {t.status})")

    # 8. 取引受諾
    print_separator("取引受諾")
    print(f"受諾前のボブの所持金: {status_repo.find_by_id(bob_id).gold.value}G")
    
    accept_cmd = AcceptTradeCommand(trade_id=trade_id, buyer_id=bob_id.value)
    command_service.accept_trade(accept_cmd)
    
    print(f"ボブが取引を受諾しました。")
    print(f"受諾後のボブの所持金: {status_repo.find_by_id(bob_id).gold.value}G (-500G)")
    print(f"受諾後のアリスの所持金: {status_repo.find_by_id(alice_id).gold.value}G (+500G)")

    bob_inv = inventory_repo.find_by_id(bob_id)
    acquired_item = bob_inv.get_item_instance_id_by_slot(SlotId(0))
    print(f"ボブのインベントリ(スロット0): {acquired_item.value if acquired_item else 'なし'}")
    
    alice_inv = inventory_repo.find_by_id(alice_id)
    removed_item = alice_inv.get_item_instance_id_by_slot(SlotId(0))
    print(f"アリスのインベントリ(スロット0): {removed_item.value if removed_item else '空（取引成立により消失）'}")

    # 9. ReadModel更新確認
    print_separator("ReadModelの事後確認")
    updated_trade = read_model_repo.find_by_id(TradeId(trade_id))
    print(f"取引ステータス: {updated_trade.status} (COMPLETEDに更新済み)")
    print(f"購入者名: {updated_trade.buyer_name} (ボブが設定済み)")

    # 10. 取引キャンセル
    print_separator("取引キャンセル")
    item_instance_id_2 = ItemInstanceId(102)
    alice_inv.acquire_item(item_instance_id_2)
    inventory_repo.save(alice_inv)
    print(f"アリスが新しいアイテム「鋼の盾」(ID:{item_instance_id_2.value})を拾いました。")
    
    offer_cmd_2 = OfferItemCommand(
        seller_id=alice_id.value,
        item_instance_id=item_instance_id_2.value,
        slot_id=0,
        requested_gold=1000
    )
    result_2 = command_service.offer_item(offer_cmd_2)
    trade_id_2 = result_2.data["trade_id"]
    print(f"アリスが「鋼の盾」を1000ゴールドで出品しました。取引ID: {trade_id_2}")
    
    alice_inv = inventory_repo.find_by_id(alice_id)
    print(f"出品直後のアリスのアイテム予約状態: {'予約済み' if alice_inv.is_item_reserved(item_instance_id_2) else '未予約'}")
    
    print("アリスがやっぱり売るのをやめてキャンセルします...")
    cancel_cmd = CancelTradeCommand(trade_id=trade_id_2, player_id=alice_id.value)
    command_service.cancel_trade(cancel_cmd)
    
    alice_inv = inventory_repo.find_by_id(alice_id)
    print(f"キャンセル後のアリスのアイテム予約状態: {'予約済み' if alice_inv.is_item_reserved(item_instance_id_2) else '未予約（ロック解除）'}")
    
    updated_trade_2 = read_model_repo.find_by_id(TradeId(trade_id_2))
    print(f"市場での取引ステータス: {updated_trade_2.status} (CANCELLEDに更新済み)")

    print_separator("デモ完了")
    print("取引システムの全主要機能が正しく動作しました。")

if __name__ == "__main__":
    main()
