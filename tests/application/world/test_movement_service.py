import pytest
from datetime import datetime
from src.application.world.commands import MovePlayerCommand, GetPlayerLocationCommand
from src.application.world.movement_service import MovementService
from src.application.world.dtos import MoveResultDto, PlayerLocationDto
from src.domain.spot.move_service import MoveService
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.spot_repository import SpotRepository
from src.domain.player.player import Player
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.spot.road_enum import ConditionType
from src.domain.spot.road import Condition


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


class MockSpotRepository(SpotRepository):
    """モックスポットリポジトリ"""
    
    def __init__(self):
        self._spots = {}
    
    def find_by_id(self, spot_id: int):
        return self._spots.get(spot_id)
    
    def save(self, spot: Spot):
        self._spots[spot.spot_id] = spot
        return spot
    
    def delete(self, spot_id: int):
        if spot_id in self._spots:
            del self._spots[spot_id]
            return True
        return False
    
    def find_all(self):
        return list(self._spots.values())
    
    def find_by_name(self, name: str):
        for spot in self._spots.values():
            if spot.name == name:
                return spot
        return None
    
    def find_by_area_id(self, area_id: int):
        return [spot for spot in self._spots.values() if spot.area_id == area_id]
    
    def find_connected_spots(self, spot_id: int):
        spot = self._spots.get(spot_id)
        if not spot:
            return []
        return [self._spots.get(connected_id) for connected_id in spot.get_connected_spot_ids()]


@pytest.fixture
def sample_data():
    """テスト用のサンプルデータを作成"""
    player_repo = MockPlayerRepository()
    spot_repo = MockSpotRepository()
    
    # スポットを作成
    spot1 = Spot(spot_id=1, name="スポット1", description="テスト用スポット1")
    spot2 = Spot(spot_id=2, name="スポット2", description="テスト用スポット2")
    
    # 道路を作成
    road = Road(
        road_id=1,
        from_spot_id=1,
        from_spot_name="スポット1",
        to_spot_id=2,
        to_spot_name="スポット2",
        description="テスト道路"
    )
    
    # スポットに道路を追加
    spot1.add_road(road)
    
    # スポットをリポジトリに保存
    spot_repo.save(spot1)
    spot_repo.save(spot2)
    
    # プレイヤーを作成
    base_status = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dynamic_status = DynamicStatus(hp=100, mp=50, max_hp=100, max_mp=50, exp=0, level=1, gold=1000)
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    
    player = Player(
        player_id=1,
        name="テストプレイヤー",
        role=Role.ADVENTURER,
        current_spot_id=1,
        base_status=base_status,
        dynamic_status=dynamic_status,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )
    
    # プレイヤーをリポジトリに保存
    player_repo.save(player)
    
    # プレイヤーをスポットに追加
    spot1.add_player(player.player_id)
    
    return player_repo, spot_repo


@pytest.fixture
def movement_service(sample_data):
    """移動サービスを作成"""
    player_repo, spot_repo = sample_data
    move_service = MoveService()
    return MovementService(move_service, player_repo, spot_repo)


class TestMovementService:
    """MovementServiceのテスト"""
    
    def test_move_player_success(self, movement_service):
        """プレイヤー移動の成功テスト"""
        # 移動コマンドを作成
        command = MovePlayerCommand(player_id=1, to_spot_id=2)
        
        # 移動実行
        result = movement_service.move_player(command)
        
        # アサーション
        assert isinstance(result, MoveResultDto)
        assert result.success is True
        assert result.player_id == 1
        assert result.from_spot_id == 1
        assert result.to_spot_id == 2
        assert "移動しました" in result.message
        assert result.error_message is None
    
    def test_move_player_player_not_found(self, movement_service):
        """存在しないプレイヤーでの移動テスト"""
        command = MovePlayerCommand(player_id=999, to_spot_id=2)
        
        with pytest.raises(ValueError, match="Player not found"):
            movement_service.move_player(command)
    
    def test_move_player_spot_not_found(self, movement_service):
        """存在しないスポットへの移動テスト"""
        command = MovePlayerCommand(player_id=1, to_spot_id=999)
        
        with pytest.raises(ValueError, match="Destination spot not found"):
            movement_service.move_player(command)
    
    def test_move_player_no_road_connection(self, movement_service):
        """道路が接続されていないスポットへの移動テスト"""
        # スポット3を作成（道路なし）
        spot_repo = movement_service._spot_repository
        spot3 = Spot(spot_id=3, name="スポット3", description="接続されていないスポット")
        spot_repo.save(spot3)
        
        command = MovePlayerCommand(player_id=1, to_spot_id=3)
        result = movement_service.move_player(command)
        
        assert result.success is False
        assert "道路がありません" in result.error_message
    
    def test_get_player_location_success(self, movement_service):
        """プレイヤー位置取得の成功テスト"""
        command = GetPlayerLocationCommand(player_id=1)
        location = movement_service.get_player_location(command)
        
        assert isinstance(location, PlayerLocationDto)
        assert location.player_id == 1
        assert location.player_name == "テストプレイヤー"
        assert location.current_spot_id == 1
        assert location.current_spot_name == "スポット1"
    
    def test_get_player_location_player_not_found(self, movement_service):
        """存在しないプレイヤーの位置取得テスト"""
        command = GetPlayerLocationCommand(player_id=999)
        location = movement_service.get_player_location(command)
        
        assert location is None
    
    def test_get_player_movement_options(self, movement_service):
        """プレイヤーの移動オプション取得テスト"""
        options = movement_service.get_player_movement_options(1)
        
        assert options is not None
        assert options.player_id == 1
        assert options.current_spot_id == 1
        assert len(options.available_moves) == 1
        assert options.available_moves[0].spot_id == 2
        assert options.available_moves[0].conditions_met is True
    
    def test_move_player_with_condition_failure(self, movement_service):
        """条件未満での移動テスト"""
        # 条件付き道路を作成
        spot_repo = movement_service._spot_repository
        spot1 = spot_repo.find_by_id(1)
        spot3 = Spot(spot_id=3, name="条件付きスポット", description="レベル5以上が必要")
        spot_repo.save(spot3)
        
        # レベル5以上が必要な道路を作成
        conditional_road = Road(
            road_id=2,
            from_spot_id=1,
            from_spot_name="スポット1",
            to_spot_id=3,
            to_spot_name="条件付きスポット",
            description="レベル制限付き道路",
            conditions=[Condition(ConditionType.MIN_LEVEL, 5)]
        )
        spot1.add_road(conditional_road)
        
        # 移動試行（レベル1なので失敗）
        command = MovePlayerCommand(player_id=1, to_spot_id=3)
        result = movement_service.move_player(command)
        
        assert result.success is False
        assert "level" in result.error_message.lower() or "レベル" in result.error_message
    
    def test_move_player_after_level_up(self, movement_service):
        """レベルアップ後の移動テスト"""
        # プレイヤーをレベルアップ
        player_repo = movement_service._player_repository
        player = player_repo.find_by_id(1)
        # 直接レベルアップ（経験値は関係ない）
        player.level_up()
        player.level_up()
        player.level_up()
        player.level_up()
        player.level_up()  # レベル6にする（5以上）
        player_repo.save(player)
        
        # 条件付き道路を作成
        spot_repo = movement_service._spot_repository
        spot1 = spot_repo.find_by_id(1)
        spot3 = Spot(spot_id=3, name="条件付きスポット", description="レベル5以上が必要")
        spot_repo.save(spot3)
        
        conditional_road = Road(
            road_id=2,
            from_spot_id=1,
            from_spot_name="スポット1",
            to_spot_id=3,
            to_spot_name="条件付きスポット",
            description="レベル制限付き道路",
            conditions=[Condition(ConditionType.MIN_LEVEL, 5)]
        )
        spot1.add_road(conditional_road)
        
        # 移動試行（レベルアップ後なので成功）
        command = MovePlayerCommand(player_id=1, to_spot_id=3)
        result = movement_service.move_player(command)
        
        assert result.success is True
        assert result.to_spot_id == 3
