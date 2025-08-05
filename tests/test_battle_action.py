import pytest
from unittest.mock import Mock, MagicMock
from game.action.actions.battle_action import (
    BattleStartStrategy, BattleJoinStrategy, BattleActionStrategy,
    BattleStartCommand, BattleJoinCommand, BattleActionCommand,
    BattleStartResult, BattleJoinResult, BattleActionResult
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.enums import TurnActionType, BattleState
from game.world.spot import Spot


class TestBattleStartStrategy:
    def test_can_execute_with_monsters(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        spot = Mock(spec=Spot)
        spot.get_visible_monsters.return_value = [Mock(spec=Monster)]
        
        spot_manager = Mock(spec=SpotManager)
        spot_manager.get_spot.return_value = spot
        
        game_context = Mock(spec=GameContext)
        game_context.get_spot_manager.return_value = spot_manager
        
        strategy = BattleStartStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is True
        spot_manager.get_spot.assert_called_once_with("spot_1")
        spot.get_visible_monsters.assert_called_once()
    
    def test_can_execute_without_monsters(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        spot = Mock(spec=Spot)
        spot.get_visible_monsters.return_value = []
        
        spot_manager = Mock(spec=SpotManager)
        spot_manager.get_spot.return_value = spot
        
        game_context = Mock(spec=GameContext)
        game_context.get_spot_manager.return_value = spot_manager
        
        strategy = BattleStartStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_can_execute_spot_not_found(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        spot_manager = Mock(spec=SpotManager)
        spot_manager.get_spot.return_value = None
        
        game_context = Mock(spec=GameContext)
        game_context.get_spot_manager.return_value = spot_manager
        
        strategy = BattleStartStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_get_required_arguments(self):
        strategy = BattleStartStrategy()
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        
        # 実行
        args = strategy.get_required_arguments(player, game_context)
        
        # 検証
        assert len(args) == 0
    
    def test_build_action_command(self):
        strategy = BattleStartStrategy()
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        
        # 実行
        command = strategy.build_action_command(player, game_context)
        
        # 検証
        assert isinstance(command, BattleStartCommand)


class TestBattleJoinStrategy:
    def test_can_execute_with_active_battle(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        battle = Mock()
        battle.state = BattleState.ACTIVE
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleJoinStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is True
        battle_manager.get_battle_by_spot.assert_called_once_with("spot_1")
    
    def test_can_execute_without_battle(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = None
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleJoinStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_can_execute_battle_finished(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        battle = Mock()
        battle.state = BattleState.FINISHED
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleJoinStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_can_execute_no_battle_manager(self):
        # モックの設定
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = None
        
        strategy = BattleJoinStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_get_required_arguments(self):
        strategy = BattleJoinStrategy()
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        
        # 実行
        args = strategy.get_required_arguments(player, game_context)
        
        # 検証
        assert len(args) == 0
    
    def test_build_action_command(self):
        strategy = BattleJoinStrategy()
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        
        # 実行
        command = strategy.build_action_command(player, game_context)
        
        # 検証
        assert isinstance(command, BattleJoinCommand)


class TestBattleActionStrategy:
    def test_can_execute_with_participant(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_player_id.return_value = "player_1"
        player.get_current_spot_id.return_value = "spot_1"
        
        battle = Mock()
        battle.state = BattleState.ACTIVE
        battle.participants = {"player_1": player}
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleActionStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is True
    
    def test_can_execute_not_participant(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_player_id.return_value = "player_1"
        player.get_current_spot_id.return_value = "spot_1"
        
        battle = Mock()
        battle.state = BattleState.ACTIVE
        battle.participants = {"player_2": Mock(spec=Player)}
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleActionStrategy()
        
        # 実行
        result = strategy.can_execute(player, game_context)
        
        # 検証
        assert result is False
    
    def test_get_required_arguments(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        monster1 = Mock(spec=Monster)
        monster1.monster_id = "monster_1"
        monster1.is_alive.return_value = True
        
        monster2 = Mock(spec=Monster)
        monster2.monster_id = "monster_2"
        monster2.is_alive.return_value = False
        
        battle = Mock()
        battle.monsters = {"monster_1": monster1, "monster_2": monster2}
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        strategy = BattleActionStrategy()
        
        # 実行
        args = strategy.get_required_arguments(player, game_context)
        
        # 検証
        assert len(args) == 2
        assert args[0].name == "action_type"
        assert args[1].name == "target_monster_id"
        assert "monster_1" in args[1].candidates
        assert "monster_2" not in args[1].candidates  # 死亡したモンスターは含まれない
    
    def test_build_action_command(self):
        strategy = BattleActionStrategy()
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        
        # 実行
        command = strategy.build_action_command(player, game_context, "attack", "monster_1")
        
        # 検証
        assert isinstance(command, BattleActionCommand)
        assert command.action_type == TurnActionType.ATTACK
        assert command.target_monster_id == "monster_1"


class TestBattleStartCommand:
    def test_execute_success(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        
        monster = Mock(spec=Monster)
        spot = Mock(spec=Spot)
        spot.get_visible_monsters.return_value = [monster]
        
        spot_manager = Mock(spec=SpotManager)
        spot_manager.get_spot.return_value = spot
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.start_battle.return_value = "battle_1"
        
        game_context = Mock(spec=GameContext)
        game_context.get_spot_manager.return_value = spot_manager
        game_context.get_battle_manager.return_value = battle_manager
        
        command = BattleStartCommand()
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleStartResult)
        assert result.success is True
        assert result.battle_id == "battle_1"
        battle_manager.start_battle.assert_called_once_with("spot_1", [monster], player)
    
    def test_execute_no_battle_manager(self):
        # モックの設定
        player = Mock(spec=Player)
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = None
        
        command = BattleStartCommand()
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleStartResult)
        assert result.success is False
        assert "戦闘マネージャーが利用できません" in result.message


class TestBattleJoinCommand:
    def test_execute_success(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        player.get_player_id.return_value = "player_1"
        
        battle = Mock()
        battle.battle_id = "battle_1"
        battle.state = BattleState.ACTIVE
        battle.participants = {}
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        command = BattleJoinCommand()
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleJoinResult)
        assert result.success is True
        assert result.battle_id == "battle_1"
        battle_manager.join_battle.assert_called_once_with("battle_1", player)
    
    def test_execute_already_participating(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        player.get_player_id.return_value = "player_1"
        
        battle = Mock()
        battle.battle_id = "battle_1"
        battle.state = BattleState.ACTIVE
        battle.participants = {"player_1": player}
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        command = BattleJoinCommand()
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleJoinResult)
        assert result.success is False
        assert "既に戦闘に参加しています" in result.message


class TestBattleActionCommand:
    def test_execute_success(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        player.get_player_id.return_value = "player_1"
        
        monster = Mock(spec=Monster)
        monster.monster_id = "monster_1"
        monster.is_alive.return_value = True
        
        turn_action = Mock()
        turn_action.message = "攻撃が成功しました"
        
        battle = Mock()
        battle.monsters = {"monster_1": monster}
        battle.participants = {"player_1": player}
        battle.state = BattleState.ACTIVE
        battle.is_battle_finished.return_value = False
        battle.execute_player_action.return_value = turn_action
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = battle
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        command = BattleActionCommand(TurnActionType.ATTACK, "monster_1")
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleActionResult)
        assert result.success is True
        assert result.action_type == TurnActionType.ATTACK
        assert result.target_id == "monster_1"
        battle.execute_player_action.assert_called_once_with("player_1", "monster_1", TurnActionType.ATTACK)
    
    def test_execute_attack_without_target(self):
        # モックの設定
        player = Mock(spec=Player)
        player.get_current_spot_id.return_value = "spot_1"
        player.get_player_id.return_value = "player_1"
        
        battle_manager = Mock(spec=BattleManager)
        battle_manager.get_battle_by_spot.return_value = None
        
        game_context = Mock(spec=GameContext)
        game_context.get_battle_manager.return_value = battle_manager
        
        command = BattleActionCommand(TurnActionType.ATTACK, "")
        
        # 実行
        result = command.execute(player, game_context)
        
        # 検証
        assert isinstance(result, BattleActionResult)
        assert result.success is False
        assert "この場所で戦闘が行われていません" in result.message 