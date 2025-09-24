"""
移動アプリケーションサービスのデモ

このデモでは、DTOとコマンドパターンを使用した移動システムの使用例を示します。
"""

from datetime import datetime
from src.application.world.contracts.commands import MovePlayerCommand, GetPlayerLocationCommand, GetSpotInfoCommand
from src.application.world.services.movement_service import MovementApplicationService
from src.domain.spot.movement_service import MovementService
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.spot_repository import SpotRepository
from src.domain.player.player import Player
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.message_box import MessageBox
from src.domain.player.player_enum import Role
from src.domain.spot.road_enum import ConditionType
from src.domain.spot.condition import Condition


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


def create_sample_data():
    """サンプルデータを作成"""
    
    # プレイヤーリポジトリ
    player_repo = MockPlayerRepository()
    
    # スポットリポジトリ
    spot_repo = MockSpotRepository()
    
    # スポットを作成
    town_square = Spot(
        spot_id=1,
        name="街の広場",
        description="街の中心にある広場。多くの冒険者が集まる場所。",
        area_id=1
    )
    
    tavern = Spot(
        spot_id=2,
        name="酒場",
        description="冒険者たちが情報交換をする酒場。",
        area_id=1
    )
    
    shop = Spot(
        spot_id=3,
        name="武器屋",
        description="武器や防具を売っている店。",
        area_id=1
    )
    
    # 道路を作成
    road_to_tavern = Road(
        road_id=1,
        from_spot_id=1,
        from_spot_name="街の広場",
        to_spot_id=2,
        to_spot_name="酒場",
        description="広場から酒場への道"
    )
    
    road_to_shop = Road(
        road_id=2,
        from_spot_id=1,
        from_spot_name="街の広場",
        to_spot_id=3,
        to_spot_name="武器屋",
        description="広場から武器屋への道",
        conditions=[Condition(ConditionType.MIN_LEVEL, 5)]  # レベル5以上が必要
    )
    
    # スポットに道路を追加
    town_square.add_road(road_to_tavern)
    town_square.add_road(road_to_shop)
    
    # スポットをリポジトリに保存
    spot_repo.save(town_square)
    spot_repo.save(tavern)
    spot_repo.save(shop)
    
    # プレイヤーを作成
    base_status = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dynamic_status = DynamicStatus(hp=100, mp=50, max_hp=100, max_mp=50, exp=0, level=1, gold=1000)
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    
    player = Player(
        player_id=1,
        name="勇者",
        role=Role.ADVENTURER,
        current_spot_id=1,  # 街の広場にいる
        base_status=base_status,
        dynamic_status=dynamic_status,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )
    
    # プレイヤーをリポジトリに保存
    player_repo.save(player)
    
    # プレイヤーをスポットに追加
    town_square.add_player(player.player_id)
    
    return player_repo, spot_repo


def demo_movement_service():
    """移動サービスのデモ"""
    print("=== 移動アプリケーションサービスのデモ ===\n")
    
    # サンプルデータを作成
    player_repo, spot_repo = create_sample_data()
    
    # 移動サービスを作成
    move_service = MovementService()
    movement_service = MovementApplicationService(move_service, player_repo, spot_repo)
    
    # 1. プレイヤーの現在位置を確認
    print("1. プレイヤーの現在位置を確認")
    location_cmd = GetPlayerLocationCommand(player_id=1)
    location = movement_service.get_player_location(location_cmd)
    
    if location:
        print(f"プレイヤー: {location.player_name}")
        print(f"現在位置: {location.current_spot_name} ({location.current_spot_id})")
        print(f"説明: {location.current_spot_description}")
    print()
    
    # 2. 移動オプションを確認
    print("2. 移動オプションを確認")
    options = movement_service.get_player_movement_options(1)
    
    if options:
        print(f"プレイヤー: {options.player_name}")
        print(f"現在位置: {options.current_spot_name}")
        print(f"利用可能な移動先: {options.total_available_moves}個")
        
        for move in options.available_moves:
            status = "✅ 移動可能" if move.conditions_met else "❌ 条件未満"
            print(f"  - {move.spot_name} ({move.road_description}): {status}")
            if not move.conditions_met:
                for condition in move.failed_conditions:
                    print(f"    → {condition}")
    print()
    
    # 3. 酒場に移動（成功する移動）
    print("3. 酒場に移動")
    move_cmd = MovePlayerCommand(player_id=1, to_spot_id=2)
    result = movement_service.move_player(move_cmd)
    
    print(f"移動結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.error_message:
        print(f"エラー: {result.error_message}")
    print()
    
    # 4. 移動後の位置を確認
    print("4. 移動後の位置を確認")
    location = movement_service.get_player_location(location_cmd)
    if location:
        print(f"現在位置: {location.current_spot_name} ({location.current_spot_id})")
    print()
    
    # 5. 武器屋に移動（条件未満で失敗する移動）
    print("5. 武器屋に移動（レベル不足で失敗）")
    move_cmd = MovePlayerCommand(player_id=1, to_spot_id=3)
    result = movement_service.move_player(move_cmd)
    
    print(f"移動結果: {'成功' if result.success else '失敗'}")
    print(f"メッセージ: {result.message}")
    if result.error_message:
        print(f"エラー: {result.error_message}")
    print()
    
    # 6. プレイヤーをレベルアップしてから再試行
    print("6. プレイヤーをレベルアップしてから武器屋に移動")
    player = player_repo.find_by_id(1)
    if player:
        # レベルアップ（経験値を追加）
        player.receive_exp(1000)  # レベルアップに十分な経験値
        player_repo.save(player)
        
        # 再試行
        result = movement_service.move_player(move_cmd)
        
        print(f"移動結果: {'成功' if result.success else '失敗'}")
        print(f"メッセージ: {result.message}")
        if result.error_message:
            print(f"エラー: {result.error_message}")
    print()
    
    # 7. 最終的な位置を確認
    print("7. 最終的な位置を確認")
    location = movement_service.get_player_location(location_cmd)
    if location:
        print(f"最終位置: {location.current_spot_name} ({location.current_spot_id})")
    
    print("\n=== デモ完了 ===")


if __name__ == "__main__":
    demo_movement_service()
