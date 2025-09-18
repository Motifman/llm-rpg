"""
TurnProcessorドメインサービスのテスト
"""
import pytest
from unittest.mock import Mock, MagicMock
from src.domain.battle.services.turn_processor import TurnProcessor
from src.domain.battle.battle import Battle
from src.domain.battle.battle_enum import BattleState, ParticipantType, BattleResultType
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.combat_state import CombatState


@pytest.fixture
def mock_battle_logic_service():
    """テスト用のBattleLogicServiceモック"""
    service = Mock()
    service.process_on_turn_start.return_value = TurnStartResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        can_act=True,
        damage=0,
        healing=0
    )
    service.process_on_turn_end.return_value = TurnEndResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        damage=0,
        healing=0
    )
    return service


@pytest.fixture
def turn_processor(mock_battle_logic_service):
    """テスト用のTurnProcessorインスタンス"""
    return TurnProcessor(mock_battle_logic_service)


@pytest.fixture
def mock_battle():
    """テスト用のBattleモック"""
    battle = Mock(spec=Battle)
    
    # モックの戦闘状態
    mock_combat_state = Mock(spec=CombatState)
    mock_combat_state.entity_id = 1
    mock_combat_state.participant_type = ParticipantType.PLAYER
    
    battle.get_combat_state.return_value = mock_combat_state
    battle.check_battle_end_conditions.return_value = None  # デフォルトは戦闘継続
    
    return battle


@pytest.fixture
def player_actor():
    """テスト用のプレイヤーアクター"""
    return TurnEntry(
        participant_key=(ParticipantType.PLAYER, 1),
        speed=20,
        priority=0
    )


@pytest.fixture
def monster_actor():
    """テスト用のモンスターアクター"""
    return TurnEntry(
        participant_key=(ParticipantType.MONSTER, 1),
        speed=15,
        priority=0
    )


class TestTurnProcessorTurnStart:
    """ターン開始処理のテスト"""
    
    def test_process_turn_start_success(self, turn_processor, mock_battle, player_actor, mock_battle_logic_service):
        """正常にターン開始処理を実行できる"""
        result = turn_processor.process_turn_start(mock_battle, player_actor)
        
        # BattleLogicServiceが呼び出される
        mock_battle_logic_service.process_on_turn_start.assert_called_once()
        
        # Battleに結果が適用される
        mock_battle.apply_turn_start_result.assert_called_once()
        
        # 結果が返される
        assert result.actor_id == 1
        assert result.participant_type == ParticipantType.PLAYER
        assert result.can_act is True
    
    def test_process_turn_start_combat_state_not_found(self, turn_processor, mock_battle, player_actor):
        """戦闘状態が見つからない場合はエラー"""
        mock_battle.get_combat_state.return_value = None
        
        with pytest.raises(ValueError, match="Combat state not found for actor"):
            turn_processor.process_turn_start(mock_battle, player_actor)
    
    def test_process_turn_start_with_monster(self, turn_processor, mock_battle, monster_actor, mock_battle_logic_service):
        """モンスターのターン開始処理も正常に動作する"""
        # モンスター用の戦闘状態を設定
        mock_monster_state = Mock(spec=CombatState)
        mock_monster_state.entity_id = 1
        mock_monster_state.participant_type = ParticipantType.MONSTER
        mock_battle.get_combat_state.return_value = mock_monster_state
        
        # モンスター用の結果を設定
        mock_battle_logic_service.process_on_turn_start.return_value = TurnStartResult(
            actor_id=1,
            participant_type=ParticipantType.MONSTER,
            can_act=True,
            damage=5,  # 毒ダメージなど
            healing=0
        )
        
        result = turn_processor.process_turn_start(mock_battle, monster_actor)
        
        assert result.participant_type == ParticipantType.MONSTER
        assert result.damage == 5


class TestTurnProcessorTurnEnd:
    """ターン終了処理のテスト"""
    
    def test_process_turn_end_success(self, turn_processor, mock_battle, player_actor, mock_battle_logic_service):
        """正常にターン終了処理を実行できる"""
        result = turn_processor.process_turn_end(mock_battle, player_actor)
        
        # BattleLogicServiceが呼び出される
        mock_battle_logic_service.process_on_turn_end.assert_called_once()
        
        # Battleに結果が適用される
        mock_battle.apply_turn_end_result.assert_called_once()
        
        # 結果が返される
        assert result.actor_id == 1
        assert result.participant_type == ParticipantType.PLAYER
    
    def test_process_turn_end_combat_state_not_found(self, turn_processor, mock_battle, player_actor):
        """戦闘状態が見つからない場合はエラー"""
        mock_battle.get_combat_state.return_value = None
        
        with pytest.raises(ValueError, match="Combat state not found for actor"):
            turn_processor.process_turn_end(mock_battle, player_actor)
    
    def test_process_turn_end_with_healing(self, turn_processor, mock_battle, player_actor, mock_battle_logic_service):
        """回復効果がある場合の処理"""
        mock_battle_logic_service.process_on_turn_end.return_value = TurnEndResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            damage=0,
            healing=10  # 回復効果
        )
        
        result = turn_processor.process_turn_end(mock_battle, player_actor)
        
        assert result.healing == 10


class TestTurnProcessorBattleEnd:
    """戦闘終了処理のテスト"""
    
    def test_check_and_handle_battle_end_no_end_condition(self, turn_processor, mock_battle):
        """戦闘終了条件を満たさない場合"""
        mock_battle.check_battle_end_conditions.return_value = None
        
        result = turn_processor.check_and_handle_battle_end(mock_battle)
        
        assert result is False
        mock_battle.end_battle.assert_not_called()
    
    def test_check_and_handle_battle_end_victory(self, turn_processor, mock_battle):
        """勝利条件を満たした場合"""
        mock_battle.check_battle_end_conditions.return_value = BattleResultType.VICTORY
        
        result = turn_processor.check_and_handle_battle_end(mock_battle)
        
        assert result is True
        mock_battle.end_battle.assert_called_once_with(BattleResultType.VICTORY)
    
    def test_check_and_handle_battle_end_defeat(self, turn_processor, mock_battle):
        """敗北条件を満たした場合"""
        mock_battle.check_battle_end_conditions.return_value = BattleResultType.DEFEAT
        
        result = turn_processor.check_and_handle_battle_end(mock_battle)
        
        assert result is True
        mock_battle.end_battle.assert_called_once_with(BattleResultType.DEFEAT)
    
    def test_check_and_handle_battle_end_draw(self, turn_processor, mock_battle):
        """引き分け条件を満たした場合"""
        mock_battle.check_battle_end_conditions.return_value = BattleResultType.DRAW
        
        result = turn_processor.check_and_handle_battle_end(mock_battle)
        
        assert result is True
        mock_battle.end_battle.assert_called_once_with(BattleResultType.DRAW)


class TestTurnProcessorAdvanceTurn:
    """ターン進行処理のテスト"""
    
    def test_advance_turn_without_result(self, turn_processor, mock_battle):
        """結果なしでターンを進める"""
        turn_processor.advance_turn(mock_battle)
        
        mock_battle.advance_to_next_turn.assert_called_once_with(None)
    
    def test_advance_turn_with_result(self, turn_processor, mock_battle):
        """ターン終了結果ありでターンを進める"""
        turn_end_result = TurnEndResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            damage=0,
            healing=0
        )
        
        turn_processor.advance_turn(mock_battle, turn_end_result)
        
        mock_battle.advance_to_next_turn.assert_called_once_with(turn_end_result)
