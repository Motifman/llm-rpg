import pytest
from unittest.mock import Mock, MagicMock
from game.world.poi import POI, POIUnlockCondition
from game.world.poi_progress import POIProgressManager, POIExplorationResult
from game.world.poi_manager import POIManager
from game.core.game_context import GameContext
from game.player.player import Player
from game.item.item import Item
from game.monster.monster import Monster
from game.battle.battle_manager import BattleManager
from game.enums import MonsterType, PlayerState


class TestPOISystem:
    @pytest.fixture
    def game_context(self):
        context = MagicMock(spec=GameContext)
        battle_manager = Mock(spec=BattleManager)
        spot_manager = Mock()
        spot = Mock()
        spot.spot_id = "test_spot"
        spot_manager.get_spot.return_value = spot
        context.get_battle_manager.return_value = battle_manager
        context.get_spot_manager.return_value = spot_manager
        context.get_poi_manager.return_value = POIManager()
        return context

    @pytest.fixture
    def player(self):
        player = Mock(spec=Player)
        player.player_id = "test_player"
        inventory = Mock()
        inventory.has_item = Mock()
        player.get_inventory.return_value = inventory
        player.is_in_state.return_value = True
        return player

    @pytest.fixture
    def test_item(self):
        item = Mock(spec=Item)
        item.item_id = "test_item"
        return item

    @pytest.fixture
    def test_monster(self):
        monster = Mock(spec=Monster)
        monster.monster_id = "test_monster"
        monster.monster_type = MonsterType.NORMAL
        return monster

    def test_poi_creation(self):
        """POIの基本的な作成と属性のテスト"""
        poi = POI(
            poi_id="test_poi",
            name="Test POI",
            description="Test Description",
            detailed_description="Detailed Test Description"
        )
        
        assert poi.poi_id == "test_poi"
        assert poi.name == "Test POI"
        assert poi.description == "Test Description"
        assert poi.detailed_description == "Detailed Test Description"

    def test_poi_unlock_condition(self):
        """POIのアンロック条件のテスト"""
        condition = POIUnlockCondition(
            required_items={"item1", "item2"},
            required_player_states={"state1"},
            required_poi_discoveries={"poi1"}
        )
        
        player = Mock(spec=Player)
        player.get_inventory().has_item.side_effect = lambda x: x in {"item1", "item2"}
        player.is_in_state.return_value = True
        
        # 全条件満たす場合
        assert condition.is_satisfied(player, {"poi1"})
        
        # POI発見条件を満たさない場合
        assert not condition.is_satisfied(player, set())

    def test_poi_progress_tracking(self):
        """プレイヤーのPOI探索進捗管理のテスト"""
        progress_manager = POIProgressManager()
        player_progress = progress_manager.get_player_progress("player1")
        
        # 新しいSpotの進捗を開始
        player_progress.add_spot("spot1")
        
        # POI発見を記録
        result = POIExplorationResult(
            description="Found something",
            found_items=["item1"],
            encountered_monsters=["monster1"],
            unlocked_pois=["poi2"]
        )
        player_progress.record_poi_discovery("spot1", "poi1", result)
        
        # 記録の確認
        assert player_progress.has_discovered_poi("spot1", "poi1")
        assert "poi1" in player_progress.get_discovered_pois("spot1")
        stored_result = player_progress.get_exploration_result("spot1", "poi1")
        assert stored_result.description == "Found something"

    def test_poi_manager_integration(self, game_context, player, test_item, test_monster):
        """POIマネージャーの統合テスト"""
        poi_manager = POIManager()
        
        # POIを作成
        poi = POI(
            poi_id="test_poi",
            name="Test POI",
            description="Test Description",
            detailed_description="You found something!"
        )
        poi.add_item(test_item)
        poi.add_hidden_monster(test_monster)
        
        # POIを登録
        poi_manager.register_poi("test_spot", poi)
        
        # 利用可能なPOIを確認
        available_pois = poi_manager.get_available_pois("test_spot", player)
        assert len(available_pois) == 1
        assert available_pois[0].poi_id == "test_poi"
        
        # POIを探索
        result = poi_manager.explore_poi("test_spot", "test_poi", player, game_context)
        
        # 結果を確認
        assert result.description == "You found something!"
        assert test_item.item_id in result.found_items
        assert test_monster.monster_id in result.encountered_monsters
        
        # 戦闘開始が呼ばれたことを確認
        battle_manager = game_context.get_battle_manager()
        battle_manager.start_battle.assert_called_once_with("test_spot", [test_monster], player)
        
        # プレイヤーの状態が更新されたことを確認
        player.set_player_state.assert_called_with(PlayerState.BATTLE)

    def test_poi_exploration_action(self, game_context, player):
        """探索アクションの統合テスト"""
        from game.action.actions.explore_action import ExploreActionStrategy, ExploreActionCommand
        
        # POIを設定
        poi_manager = game_context.get_poi_manager()
        poi = POI(
            poi_id="test_poi",
            name="Test POI",
            description="Test Description",
            detailed_description="You found something!"
        )
        poi_manager.register_poi("test_spot", poi)
        
        # 探索アクションを作成
        strategy = ExploreActionStrategy()
        
        # 引数情報を取得
        player.get_current_spot_id.return_value = "test_spot"
        player.get_inventory().has_item.return_value = True
        player.is_in_state.return_value = True
        args = strategy.get_required_arguments(player, game_context)
        assert len(args) == 1
        assert args[0].name == "poi_id"
        assert "test_poi" in args[0].candidates
        
        # アクションを実行
        command = strategy.build_action_command(player, game_context, "test_poi")
        result = command.execute(player, game_context)
        
        # 結果を確認
        assert result.success
        assert "You found something!" in result.poi_result.description