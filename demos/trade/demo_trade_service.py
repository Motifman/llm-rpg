"""
取引アプリケーションサービスのデモ

このデモでは、DTOとコマンドパターンを使用した取引システムの使用例を示します。
"""

from datetime import datetime
from src.application.trade.contracts.commands import (
    CreateTradeCommand,
    ExecuteTradeCommand,
    CancelTradeCommand,
    GetPlayerTradesCommand,
    GetGlobalTradesCommand
)
from src.application.trade.services.trade_service import TradeApplicationService
from src.domain.trade.trade_service import TradeService
from src.domain.player.player_repository import PlayerRepository
from src.domain.trade.trade_repository import TradeRepository
from src.domain.trade.trade_event_dispatcher import TradeEventDispatcher
from src.domain.trade.trade_event_handler import NotificationTradeEventHandler, LoggingTradeEventHandler
from src.domain.player.player import Player
from src.domain.trade.trade import TradeOffer
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.trade.trade_enum import TradeType
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.item.item_enum import ItemType, Rarity


class MockPlayerRepository(PlayerRepository):
    """モックプレイヤーリポジトリ"""
    
    def __init__(self):
        self._players = {}
    
    def find_by_id(self, player_id: int):
        return self._players.get(player_id)
    
    def save(self, player: Player):
        self._players[player.player_id] = player
        return player
    
    def delete(self, player_id: int):
        if player_id in self._players:
            del self._players[player_id]
            return True
        return False
    
    def find_all(self):
        return list(self._players.values())
    
    def find_by_name(self, name: str):
        for player in self._players.values():
            if player.name == name:
                return player
        return None
    
    def find_by_spot_id(self, spot_id: int):
        return [player for player in self._players.values() if player.current_spot_id == spot_id]
    
    def find_by_role(self, role):
        return [player for player in self._players.values() if player.role == role]


class MockTradeRepository(TradeRepository):
    """モック取引リポジトリ"""
    
    def __init__(self):
        self._trades = {}
        self._next_id = 1
    
    def find_by_id(self, trade_id: int):
        return self._trades.get(trade_id)
    
    def save(self, trade_offer: TradeOffer):
        self._trades[trade_offer.trade_id] = trade_offer
        return trade_offer
    
    def delete(self, trade_id: int):
        if trade_id in self._trades:
            del self._trades[trade_id]
            return True
        return False
    
    def find_all(self):
        return list(self._trades.values())
    
    def find_by_seller_id(self, seller_id: int):
        return [t for t in self._trades.values() if t.seller_id == seller_id]
    
    def find_by_buyer_id(self, buyer_id: int):
        return [t for t in self._trades.values() if t.buyer_id == buyer_id]
    
    def find_by_target_player_id(self, target_player_id: int):
        return [t for t in self._trades.values() if t.target_player_id == target_player_id]
    
    def find_active_trades(self):
        return [t for t in self._trades.values() if t.status.value == "active"]
    
    def find_global_trades(self):
        return [t for t in self._trades.values() if t.trade_type == TradeType.GLOBAL]
    
    def find_by_item_id(self, item_id: int):
        return [t for t in self._trades.values() if t.offered_item.item_id == item_id]
    
    def find_by_price_range(self, min_price: int, max_price: int):
        return [t for t in self._trades.values() if min_price <= t.requested_gold <= max_price]
    
    def find_recent_trades(self, limit: int = 10):
        sorted_trades = sorted(self._trades.values(), key=lambda t: t.created_at, reverse=True)
        return sorted_trades[:limit]
    
    def generate_trade_id(self) -> int:
        """取引IDを生成（簡易実装）"""
        import time
        import random
        # タイムスタンプ + ランダム値で一意性を確保
        return int(time.time() * 1000) + random.randint(1, 999)


def create_sample_data():
    """サンプルデータを作成"""
    
    # プレイヤーリポジトリ
    player_repo = MockPlayerRepository()
    
    # 取引リポジトリ
    trade_repo = MockTradeRepository()
    
    # アイテムを作成
    potion = Item(
        item_id=1,
        name="回復ポーション",
        description="HPを回復するポーション",
        price=50,
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON
    )
    
    sword = Item(
        item_id=2,
        name="鉄の剣",
        description="基本的な鉄製の剣",
        price=200,
        item_type=ItemType.WEAPON,
        rarity=Rarity.COMMON
    )
    
    # プレイヤーを作成
    base_status1 = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dynamic_status1 = DynamicStatus(hp=100, mp=50, max_hp=100, max_mp=50, exp=0, level=1, gold=1000)
    inventory1 = Inventory()
    equipment_set1 = EquipmentSet()
    message_box1 = MessageBox()
    
    player1 = Player(
        player_id=1,
        name="商人",
        role=Role.MERCHANT,
        current_spot_id=1,
        base_status=base_status1,
        dynamic_status=dynamic_status1,
        inventory=inventory1,
        equipment_set=equipment_set1,
        message_box=message_box1
    )
    
    # プレイヤー1にアイテムを追加
    player1.add_item(potion, 5)  # ポーション5個
    unique_sword = UniqueItem(id=1, item=sword, durability=100, attack=15)
    player1.add_item(unique_sword)  # ユニークな剣
    
    base_status2 = BaseStatus(attack=8, defense=3, speed=9, critical_rate=0.15, evasion_rate=0.1)
    dynamic_status2 = DynamicStatus(hp=80, mp=40, max_hp=80, max_mp=40, exp=0, level=1, gold=500)
    inventory2 = Inventory()
    equipment_set2 = EquipmentSet()
    message_box2 = MessageBox()
    
    player2 = Player(
        player_id=2,
        name="冒険者",
        role=Role.ADVENTURER,
        current_spot_id=1,
        base_status=base_status2,
        dynamic_status=dynamic_status2,
        inventory=inventory2,
        equipment_set=equipment_set2,
        message_box=message_box2
    )
    
    # プレイヤーをリポジトリに保存
    player_repo.save(player1)
    player_repo.save(player2)
    
    return player_repo, trade_repo


def demo_trade_service():
    """取引サービスのデモ"""
    print("=== 取引アプリケーションサービスのデモ ===\n")
    
    # サンプルデータを作成
    player_repo, trade_repo = create_sample_data()
    
    # イベントシステムを設定
    event_dispatcher = TradeEventDispatcher()
    notification_handler = NotificationTradeEventHandler(player_repo)
    logging_handler = LoggingTradeEventHandler()
    
    event_dispatcher.register_handler(notification_handler)
    event_dispatcher.register_handler(logging_handler)
    
    # 取引サービスを作成
    trade_service = TradeService(event_dispatcher)
    trade_app_service = TradeApplicationService(trade_service, player_repo, trade_repo, event_dispatcher)
    
    # 1. グローバル取引を作成
    print("1. グローバル取引を作成")
    create_cmd = CreateTradeCommand(
        seller_id=1,
        requested_gold=100,
        offered_item_id=1,
        offered_item_count=2,
        trade_type=TradeType.GLOBAL
    )
    result = trade_app_service.create_trade(create_cmd)
    
    print(f"取引作成結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.error_message:
        print(f"エラー: {result.error_message}")
    print()
    
    # 2. ユニークアイテムの取引を作成
    print("2. ユニークアイテムの取引を作成")
    create_unique_cmd = CreateTradeCommand(
        seller_id=1,
        requested_gold=300,
        offered_item_id=2,
        offered_unique_id=1,
        trade_type=TradeType.GLOBAL
    )
    result = trade_app_service.create_trade(create_unique_cmd)
    
    print(f"取引作成結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.error_message:
        print(f"エラー: {result.error_message}")
    print()
    
    # 3. 直接取引を作成
    print("3. 直接取引を作成")
    create_direct_cmd = CreateTradeCommand(
        seller_id=1,
        requested_gold=50,
        offered_item_id=1,
        offered_item_count=1,
        trade_type=TradeType.DIRECT,
        target_player_id=2
    )
    result = trade_app_service.create_trade(create_direct_cmd)
    
    print(f"取引作成結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.error_message:
        print(f"エラー: {result.error_message}")
    print()
    
    # 4. グローバル取引一覧を取得
    print("4. グローバル取引一覧を取得")
    global_cmd = GetGlobalTradesCommand(limit=5)
    global_trades = trade_app_service.get_global_trades(global_cmd)
    
    print(f"総取引数: {global_trades.total_count}")
    print(f"フィルター適用後: {global_trades.filtered_count}")
    print("取引一覧:")
    for trade in global_trades.trades:
        print(f"  - ID:{trade.trade_id} {trade.seller_name} → {trade.offered_item.item_id}x{trade.offered_item.count} ⇄ {trade.requested_gold}G")
    print()
    
    # 5. 取引を実行
    print("5. 取引を実行")
    if global_trades.trades:
        first_trade = global_trades.trades[0]
        execute_cmd = ExecuteTradeCommand(
            trade_id=first_trade.trade_id,
            buyer_id=2
        )
        result = trade_app_service.execute_trade(execute_cmd)
        
        print(f"取引実行結果: {'成功' if result.success else '失敗'}")
        print(f"メッセージ: {result.message}")
        if result.error_message:
            print(f"エラー: {result.error_message}")
    print()
    
    # 6. プレイヤーの取引履歴を取得
    print("6. プレイヤーの取引履歴を取得")
    player_trades_cmd = GetPlayerTradesCommand(player_id=1)
    player_trades = trade_app_service.get_player_trades(player_trades_cmd)
    
    if player_trades:
        print(f"プレイヤー: {player_trades.player_name}")
        print(f"アクティブ取引: {len(player_trades.active_trades)}件")
        print(f"成立取引: {len(player_trades.completed_trades)}件")
        print(f"キャンセル取引: {len(player_trades.cancelled_trades)}件")
        print(f"総取引数: {player_trades.total_trades}件")
    print()
    
    # 7. 取引をキャンセル
    print("7. 取引をキャンセル")
    if player_trades and player_trades.active_trades:
        first_active = player_trades.active_trades[0]
        cancel_cmd = CancelTradeCommand(
            trade_id=first_active.trade_id,
            player_id=1
        )
        result = trade_app_service.cancel_trade(cancel_cmd)
        
        print(f"取引キャンセル結果: {'成功' if result.success else '失敗'}")
        print(f"メッセージ: {result.message}")
        if result.error_message:
            print(f"エラー: {result.error_message}")
    print()
    
    # 8. 価格フィルター付きで取引一覧を取得
    print("8. 価格フィルター付きで取引一覧を取得")
    filter_cmd = GetGlobalTradesCommand(min_price=50, max_price=200, limit=3)
    filtered_trades = trade_app_service.get_global_trades(filter_cmd)
    
    print(f"価格50-200Gの取引: {filtered_trades.filtered_count}件")
    print("取引一覧:")
    for trade in filtered_trades.trades:
        print(f"  - ID:{trade.trade_id} {trade.seller_name} → {trade.offered_item.item_id}x{trade.offered_item.count} ⇄ {trade.requested_gold}G")
    
    # 9. プレイヤーのメッセージを確認
    print("\n9. プレイヤーのメッセージを確認")
    for player in player_repo.find_all():
        print(f"\n{player.name}のメッセージ:")
        for message in player._message_box.messages:
            print(f"  - {message.display()}")
    
    print("\n=== デモ完了 ===")


if __name__ == "__main__":
    demo_trade_service()
