import pytest
from src.domain.spot.move_service import MoveService
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road, Condition
from src.domain.spot.road_enum import ConditionType
from src.domain.spot.spot_exception import (
    PlayerNotMeetConditionException,
    PlayerAlreadyInToSpotException,
    PlayerNotInFromSpotException,
    SpotNotConnectedException,
    RoadNotConnectedToFromSpotException,
    RoadNotConnectedToToSpotException,
)
from src.domain.player.player_enum import Role
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox


@pytest.fixture
def mock_player():
    """テスト用のプレイヤーオブジェクトを作成"""
    base_status = BaseStatus(
        attack=20, defense=10, speed=15, critical_rate=0.1, evasion_rate=0.05
    )
    dynamic_status = DynamicStatus(
        hp=100, mp=50, max_hp=100, max_mp=50, exp=250, level=5, gold=150
    )
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    
    return Player(
        player_id=1,
        name="TestPlayer",
        role=Role.ADVENTURER,
        current_spot_id=1,  # プレイヤーはスポット1にいる
        base_status=base_status,
        dynamic_status=dynamic_status,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )


@pytest.fixture
def spots_and_roads():
    """テスト用のスポットと道路を作成"""
    # スポット1: 町の入り口
    spot1 = Spot(
        spot_id=1,
        name="町の入り口",
        description="小さな町の入り口"
    )
    spot1.add_player(1)  # プレイヤー1がいる
    
    # スポット2: 市場
    spot2 = Spot(
        spot_id=2,
        name="市場",
        description="にぎやかな市場"
    )
    
    # スポット3: 冒険者ギルド
    spot3 = Spot(
        spot_id=3,
        name="冒険者ギルド",
        description="冒険者たちが集まる場所"
    )
    
    # 道路: スポット1 → スポット2（条件なし）
    road1_to_2 = Road(
        road_id=1,
        from_spot_id=1,
        from_spot_name="町の入り口",
        to_spot_id=2,
        to_spot_name="市場",
        description="町の入り口から市場への道"
    )
    
    # 道路: スポット2 → スポット3（レベル5以上必要）
    road2_to_3 = Road(
        road_id=2,
        from_spot_id=2,
        from_spot_name="市場",
        to_spot_id=3,
        to_spot_name="冒険者ギルド",
        description="市場から冒険者ギルドへの道",
        conditions=[Condition(ConditionType.MIN_LEVEL, 4)]
    )
    
    # 道路: スポット1 → スポット3（ゴールド200以上必要：満たされない）
    road1_to_3 = Road(
        road_id=3,
        from_spot_id=1,
        from_spot_name="町の入り口",
        to_spot_id=3,
        to_spot_name="冒険者ギルド",
        description="町の入り口から冒険者ギルドへの直行便",
        conditions=[Condition(ConditionType.HAS_GOLD, 200)]
    )
    
    # スポットに道路を追加
    spot1.add_road(road1_to_2)
    spot1.add_road(road1_to_3)
    spot2.add_road(road2_to_3)
    
    return {
        "spot1": spot1,
        "spot2": spot2,
        "spot3": spot3,
        "road1_to_2": road1_to_2,
        "road2_to_3": road2_to_3,
        "road1_to_3": road1_to_3,
    }


class TestMoveService:
    def test_successful_move_no_conditions(self, mock_player, spots_and_roads):
        """条件なしの移動成功テスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot2 = spots_and_roads["spot2"]
        road = spots_and_roads["road1_to_2"]
        
        # 移動前の状態確認
        assert mock_player.current_spot_id == 1
        assert spot1.is_player_in_spot(1)
        assert not spot2.is_player_in_spot(1)
        
        # 移動実行
        move_service.move_player_to_spot(mock_player, spot1, spot2, road)
        
        # 移動後の状態確認
        assert mock_player.current_spot_id == 2
        assert not spot1.is_player_in_spot(1)
        assert spot2.is_player_in_spot(1)
    
    def test_successful_move_with_satisfied_conditions(self, mock_player, spots_and_roads):
        """条件を満たした移動成功テスト"""
        move_service = MoveService()
        spot2 = spots_and_roads["spot2"]
        spot3 = spots_and_roads["spot3"]
        road = spots_and_roads["road2_to_3"]
        
        # プレイヤーをスポット2に移動させる
        mock_player.set_current_spot_id(2)
        spot2.add_player(1)
        
        # 移動前の状態確認
        assert mock_player.current_spot_id == 2
        assert spot2.is_player_in_spot(1)
        assert not spot3.is_player_in_spot(1)
        
        # 移動実行（プレイヤーはレベル5なのでレベル4以上の条件を満たす）
        move_service.move_player_to_spot(mock_player, spot2, spot3, road)
        
        # 移動後の状態確認
        assert mock_player.current_spot_id == 3
        assert not spot2.is_player_in_spot(1)
        assert spot3.is_player_in_spot(1)
    
    def test_move_failure_player_not_in_from_spot(self, mock_player, spots_and_roads):
        """プレイヤーが出発地点にいない場合のエラーテスト"""
        move_service = MoveService()
        spot2 = spots_and_roads["spot2"]  # プレイヤーはスポット1にいる
        spot3 = spots_and_roads["spot3"]
        road = spots_and_roads["road2_to_3"]  # スポット2→3の道路
        
        with pytest.raises(PlayerNotInFromSpotException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot2, spot3, road)
        
        assert "Player 1 is not in the from spot 2" in str(exc_info.value)
    
    def test_move_failure_player_already_in_to_spot(self, mock_player, spots_and_roads):
        """プレイヤーが既に目的地にいる場合のエラーテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        road = spots_and_roads["road1_to_2"]
        
        with pytest.raises(PlayerAlreadyInToSpotException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot1, road)
        
        assert "Player 1 is already in the spot 1" in str(exc_info.value)
    
    def test_move_failure_spots_not_connected(self, mock_player, spots_and_roads):
        """スポットが繋がっていない場合のエラーテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot3 = spots_and_roads["spot3"]
        
        # スポット3は直接スポット1に繋がっていない（片方向のみ）
        spot3_disconnected = Spot(
            spot_id=4,
            name="秘密の部屋",
            description="隠された部屋"
        )
        
        road = Road(
            road_id=99,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=4,
            to_spot_name="秘密の部屋",
            description="存在しない道"
        )
        
        with pytest.raises(SpotNotConnectedException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot3_disconnected, road)
        
        assert "from_spot 1 is not connected to to_spot 4" in str(exc_info.value)
    
    def test_move_failure_road_not_connected_to_from_spot(self, mock_player, spots_and_roads):
        """道路が出発地点に繋がっていない場合のエラーテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot2 = spots_and_roads["spot2"]
        
        # 間違ったfrom_spot_idを持つ道路
        wrong_road = Road(
            road_id=99,
            from_spot_id=99,  # 間違ったfrom_spot_id
            from_spot_name="間違った出発地",
            to_spot_id=2,
            to_spot_name="市場",
            description="間違った道路"
        )
        
        with pytest.raises(RoadNotConnectedToFromSpotException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot2, wrong_road)
        
        assert "road.from_spot_id 99 is not equal to from_spot.spot_id 1" in str(exc_info.value)
    
    def test_move_failure_road_not_connected_to_to_spot(self, mock_player, spots_and_roads):
        """道路が目的地に繋がっていない場合のエラーテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot2 = spots_and_roads["spot2"]
        
        # 間違ったto_spot_idを持つ道路
        wrong_road = Road(
            road_id=99,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=99,  # 間違ったto_spot_id
            to_spot_name="間違った目的地",
            description="間違った道路"
        )
        
        with pytest.raises(RoadNotConnectedToToSpotException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot2, wrong_road)
        
        assert "road.to_spot_id 99 is not equal to to_spot.spot_id 2" in str(exc_info.value)
    
    def test_move_failure_condition_not_met(self, mock_player, spots_and_roads):
        """移動条件が満たされていない場合のエラーテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot3 = spots_and_roads["spot3"]
        road = spots_and_roads["road1_to_3"]  # ゴールド200以上必要（プレイヤーは150）
        
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot3, road)
        
        assert "road 3 is not available for the player 1" in str(exc_info.value)
        assert "ゴールド 200 以上が必要" in str(exc_info.value)


class TestMoveServiceEdgeCases:
    def test_move_with_multiple_conditions_all_satisfied(self, mock_player, spots_and_roads):
        """複数の条件がすべて満たされている場合のテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot2 = spots_and_roads["spot2"]
        
        # 複数の条件を持つ道路
        complex_road = Road(
            road_id=10,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="複雑な道路",
            conditions=[
                Condition(ConditionType.MIN_LEVEL, 3),      # 満たされる（プレイヤーはレベル5）
                Condition(ConditionType.HAS_GOLD, 100),     # 満たされる（プレイヤーは150ゴールド）
                Condition(ConditionType.HAS_ROLE, Role.ADVENTURER)  # 満たされる
            ]
        )
        
        # スポット1に道路を追加
        spot1.add_road(complex_road)
        
        # 移動実行
        move_service.move_player_to_spot(mock_player, spot1, spot2, complex_road)
        
        # 移動後の状態確認
        assert mock_player.current_spot_id == 2
        assert not spot1.is_player_in_spot(1)
        assert spot2.is_player_in_spot(1)
    
    def test_move_with_multiple_conditions_one_not_satisfied(self, mock_player, spots_and_roads):
        """複数の条件のうち一つが満たされていない場合のテスト"""
        move_service = MoveService()
        spot1 = spots_and_roads["spot1"]
        spot2 = spots_and_roads["spot2"]
        
        # 複数の条件を持つ道路（一つが満たされない）
        complex_road = Road(
            road_id=11,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="複雑な道路",
            conditions=[
                Condition(ConditionType.MIN_LEVEL, 3),      # 満たされる
                Condition(ConditionType.HAS_GOLD, 200),     # 満たされない（プレイヤーは150ゴールド）
                Condition(ConditionType.HAS_ROLE, Role.ADVENTURER)  # 満たされる
            ]
        )
        
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            move_service.move_player_to_spot(mock_player, spot1, spot2, complex_road)
        
        assert "ゴールド 200 以上が必要" in str(exc_info.value)
