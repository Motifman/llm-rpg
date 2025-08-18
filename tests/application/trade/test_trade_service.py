import pytest
from datetime import datetime
from src.application.trade.commands import (
    CreateTradeCommand,
    ExecuteTradeCommand,
    CancelTradeCommand,
    GetPlayerTradesCommand,
    GetGlobalTradesCommand
)
from src.application.trade.trade_service import TradeApplicationService
from src.application.trade.dtos import (
    CreateTradeResultDto,
    ExecuteTradeResultDto,
    CancelTradeResultDto,
    PlayerTradesDto,
    GlobalTradesDto
)
from src.domain.trade.trade_service import TradeService
from src.domain.player.player_repository import PlayerRepository
from src.domain.trade.trade_repository import TradeRepository
from src.domain.trade.trade_event_dispatcher import TradeEventDispatcher
from src.domain.trade.trade_event_handler import LoggingTradeEventHandler
from src.domain.player.player import Player
from src.domain.trade.trade import TradeOffer
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.trade.trade_enum import TradeType, TradeStatus
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


@pytest.fixture
def sample_data():
    """テスト用のサンプルデータを作成"""
    player_repo = MockPlayerRepository()
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
    
    # プレイヤーを作成
    base_status = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dynamic_status = DynamicStatus(hp=100, mp=50, max_hp=100, max_mp=50, exp=0, level=1, gold=1000)
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    
    player = Player(
        player_id=1,
        name="テストプレイヤー",
        role=Role.MERCHANT,
        current_spot_id=1,
        base_status=base_status,
        dynamic_status=dynamic_status,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )
    
    # プレイヤーにアイテムを追加
    player.add_item(potion, 5)
    
    # プレイヤーをリポジトリに保存
    player_repo.save(player)
    
    return player_repo, trade_repo


@pytest.fixture
def trade_service(sample_data):
    """取引サービスを作成"""
    player_repo, trade_repo = sample_data
    
    # イベントシステムを設定
    event_dispatcher = TradeEventDispatcher()
    logging_handler = LoggingTradeEventHandler()
    event_dispatcher.register_handler(logging_handler)
    
    trade_service = TradeService(event_dispatcher)
    return TradeApplicationService(trade_service, player_repo, trade_repo, event_dispatcher)


class TestTradeApplicationService:
    """TradeApplicationServiceのテスト"""
    
    def test_create_trade_success(self, trade_service):
        """取引作成の成功テスト"""
        command = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        
        result = trade_service.create_trade(command)
        
        assert isinstance(result, CreateTradeResultDto)
        assert result.success is True
        assert result.trade_id is not None
        assert "作成しました" in result.message
        assert result.error_message is None
    
    def test_create_trade_player_not_found(self, trade_service):
        """存在しないプレイヤーでの取引作成テスト"""
        command = CreateTradeCommand(
            seller_id=999,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        
        result = trade_service.create_trade(command)
        
        assert result.success is False
        assert "売り手プレイヤーが見つかりません" in result.error_message
    
    def test_create_trade_insufficient_items(self, trade_service):
        """アイテム不足での取引作成テスト"""
        command = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=10,  # プレイヤーは5個しか持っていない
            trade_type=TradeType.GLOBAL
        )
        
        result = trade_service.create_trade(command)
        
        assert result.success is False
        assert "所有していません" in result.error_message
    
    def test_create_trade_invalid_command(self, trade_service):
        """無効なコマンドでの取引作成テスト"""
        # countとunique_idの両方を指定
        with pytest.raises(ValueError, match="Cannot provide both"):
            CreateTradeCommand(
                seller_id=1,
                requested_gold=100,
                offered_item_id=1,
                offered_item_count=2,
                offered_unique_id=1,
                trade_type=TradeType.GLOBAL
            )
    
    def test_execute_trade_success(self, trade_service):
        """取引実行の成功テスト"""
        # まず取引を作成
        create_cmd = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        create_result = trade_service.create_trade(create_cmd)
        
        # 買い手プレイヤーを作成
        player_repo = trade_service._player_repository
        buyer = Player(
            player_id=2,
            name="買い手",
            role=Role.ADVENTURER,
            current_spot_id=1,
            base_status=BaseStatus(attack=8, defense=3, speed=9, critical_rate=0.15, evasion_rate=0.1),
            dynamic_status=DynamicStatus(hp=80, mp=40, max_hp=80, max_mp=40, exp=0, level=1, gold=500),
            inventory=Inventory(),
            equipment_set=EquipmentSet(),
            message_box=MessageBox()
        )
        player_repo.save(buyer)
        
        # 取引を実行
        execute_cmd = ExecuteTradeCommand(
            trade_id=create_result.trade_id,
            buyer_id=2
        )
        result = trade_service.execute_trade(execute_cmd)
        
        assert isinstance(result, ExecuteTradeResultDto)
        assert result.success is True
        assert result.trade_id == create_result.trade_id
        assert result.buyer_id == 2
        assert "成立しました" in result.message
    
    def test_execute_trade_not_found(self, trade_service):
        """存在しない取引の実行テスト"""
        command = ExecuteTradeCommand(
            trade_id=999,
            buyer_id=1
        )
        
        result = trade_service.execute_trade(command)
        
        assert result.success is False
        assert "取引が見つかりません" in result.error_message
    
    def test_cancel_trade_success(self, trade_service):
        """取引キャンセルの成功テスト"""
        # まず取引を作成
        create_cmd = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        create_result = trade_service.create_trade(create_cmd)
        
        # 取引をキャンセル
        cancel_cmd = CancelTradeCommand(
            trade_id=create_result.trade_id,
            player_id=1
        )
        result = trade_service.cancel_trade(cancel_cmd)
        
        assert isinstance(result, CancelTradeResultDto)
        assert result.success is True
        assert result.trade_id == create_result.trade_id
        assert result.player_id == 1
        assert "キャンセルしました" in result.message
    
    def test_cancel_trade_not_found(self, trade_service):
        """存在しない取引のキャンセルテスト"""
        command = CancelTradeCommand(
            trade_id=999,
            player_id=1
        )
        
        result = trade_service.cancel_trade(command)
        
        assert result.success is False
        assert "取引が見つかりません" in result.error_message
    
    def test_get_player_trades_success(self, trade_service):
        """プレイヤー取引取得の成功テスト"""
        # 取引を作成
        create_cmd = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        trade_service.create_trade(create_cmd)
        
        # プレイヤーの取引を取得
        command = GetPlayerTradesCommand(player_id=1)
        result = trade_service.get_player_trades(command)
        
        assert isinstance(result, PlayerTradesDto)
        assert result.player_id == 1
        assert result.player_name == "テストプレイヤー"
        assert len(result.active_trades) == 1
        assert result.total_trades == 1
    
    def test_get_player_trades_player_not_found(self, trade_service):
        """存在しないプレイヤーの取引取得テスト"""
        command = GetPlayerTradesCommand(player_id=999)
        result = trade_service.get_player_trades(command)
        
        assert result is None
    
    def test_get_global_trades_success(self, trade_service):
        """グローバル取引取得の成功テスト"""
        # 取引を作成
        create_cmd = CreateTradeCommand(
            seller_id=1,
            requested_gold=100,
            offered_item_id=1,
            offered_item_count=2,
            trade_type=TradeType.GLOBAL
        )
        trade_service.create_trade(create_cmd)
        
        # グローバル取引を取得
        command = GetGlobalTradesCommand(limit=5)
        result = trade_service.get_global_trades(command)
        
        assert isinstance(result, GlobalTradesDto)
        assert result.total_count == 1
        assert result.filtered_count == 1
        assert len(result.trades) == 1
    
    def test_get_global_trades_with_filter(self, trade_service):
        """フィルター付きグローバル取引取得テスト"""
        # 複数の取引を作成（少し時間を空けてIDを重複させない）
        import time
        
        trade_service.create_trade(CreateTradeCommand(
            seller_id=1, requested_gold=50, offered_item_id=1, offered_item_count=1, trade_type=TradeType.GLOBAL
        ))
        time.sleep(0.001)  # 1ms待機
        
        trade_service.create_trade(CreateTradeCommand(
            seller_id=1, requested_gold=150, offered_item_id=1, offered_item_count=2, trade_type=TradeType.GLOBAL
        ))
        time.sleep(0.001)  # 1ms待機
        
        trade_service.create_trade(CreateTradeCommand(
            seller_id=1, requested_gold=250, offered_item_id=1, offered_item_count=3, trade_type=TradeType.GLOBAL
        ))
        
        # 価格フィルター付きで取得
        command = GetGlobalTradesCommand(min_price=100, max_price=200, limit=5)
        result = trade_service.get_global_trades(command)
        
        assert result.total_count == 3
        assert result.filtered_count == 1  # 150Gの取引のみ
        assert len(result.trades) == 1
        assert result.trades[0].requested_gold == 150
