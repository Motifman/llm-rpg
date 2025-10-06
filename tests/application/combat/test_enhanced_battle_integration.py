"""
改良された戦闘システムの統合テスト

実際の戦闘フローを通して、新しいサービスクラスが正しく連携することを確認
モックを最小限に抑え、実用的なテストを実装
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from src.application.combat.services.enhanced_battle_service import EnhancedBattleApplicationService
from src.application.combat.services.player_action_waiter import PlayerActionWaiter
from src.domain.battle.battle import Battle
from src.domain.battle.battle_enum import BattleState, ParticipantType, BattleResultType
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.combat_state import CombatState
from src.application.combat.contracts.dtos import PlayerActionDto
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.base_status import BaseStatus
from src.domain.battle.battle_enum import Element, Race


@pytest.fixture
def mock_repositories():
    """テスト用のリポジトリモック群"""
    # BattleRepository
    battle_repo = Mock()
    battle_repo.generate_battle_id.return_value = 1
    battle_repo.find_by_spot_id.return_value = None  # 戦闘が存在しない
    battle_repo.save.return_value = None
    
    # PlayerRepository
    player_repo = Mock()
    mock_player = Mock()
    mock_player.player_id = 1
    mock_player.name = "TestPlayer"
    mock_player.current_spot_id = 100
    mock_player.race = Race.HUMAN
    mock_player.element = Element.FIRE
    mock_player.hp = Hp(100, 100)
    mock_player.mp = Mp(50, 50)
    mock_player.calculate_status_including_equipment.return_value = BaseStatus(
        attack=50, defense=30, speed=20, critical_rate=0.1, evasion_rate=0.05
    )
    player_repo.find_by_id.return_value = mock_player
    
    # AreaRepository
    area_repo = Mock()
    mock_area = Mock()
    mock_area.get_spawn_monster_type_ids.return_value = {101, 102}
    area_repo.find_by_spot_id.return_value = mock_area
    
    # MonsterRepository
    monster_repo = Mock()
    mock_monster = Mock()
    mock_monster.monster_type_id = 101
    mock_monster.name = "TestMonster"
    mock_monster.race = Race.DRAGON
    mock_monster.element = Element.WATER
    mock_monster.max_hp = 200
    mock_monster.max_mp = 30
    mock_monster.calculate_status_including_equipment.return_value = BaseStatus(
        attack=60, defense=40, speed=15, critical_rate=0.05, evasion_rate=0.03
    )
    monster_repo.find_by_ids.return_value = [mock_monster]
    
    # ActionRepository
    action_repo = Mock()
    mock_action = Mock()
    mock_action.action_id = 1
    mock_action.name = "TestAttack"
    mock_action.execute.return_value = Mock(
        success=True,
        messages=["攻撃成功"],
        actor_state_change=Mock(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=0,
            mp_change=-5
        ),
        target_state_changes=[
            Mock(
                target_id=1,
                participant_type=ParticipantType.MONSTER,
                hp_change=-20,
                mp_change=0
            )
        ]
    )
    action_repo.find_by_id.return_value = mock_action
    
    return {
        'battle': battle_repo,
        'player': player_repo,
        'area': area_repo,
        'monster': monster_repo,
        'action': action_repo
    }


@pytest.fixture
def mock_services():
    """テスト用のサービスモック群"""
    # BattleLogicService
    battle_logic = Mock()
    battle_logic.process_on_turn_start.return_value = TurnStartResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        can_act=True,
        damage=0,
        healing=0
    )
    battle_logic.process_on_turn_end.return_value = TurnEndResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        damage=0,
        healing=0
    )
    
    # MonsterActionService
    monster_action = Mock()
    monster_action.select_monster_action_with_targets.return_value = None  # モンスター行動なし
    
    # Notifier
    notifier = Mock()
    
    # EventPublisher
    event_publisher = Mock()
    event_publisher.publish_all.return_value = None
    event_publisher.register_handler.return_value = None
    
    return {
        'battle_logic': battle_logic,
        'monster_action': monster_action,
        'notifier': notifier,
        'event_publisher': event_publisher
    }


@pytest.fixture
def enhanced_battle_service(mock_repositories, mock_services):
    """テスト用のEnhancedBattleApplicationServiceインスタンス"""
    player_action_waiter = PlayerActionWaiter(default_timeout_seconds=1.0)
    
    return EnhancedBattleApplicationService(
        battle_repository=mock_repositories['battle'],
        player_repository=mock_repositories['player'],
        area_repository=mock_repositories['area'],
        monster_repository=mock_repositories['monster'],
        action_repository=mock_repositories['action'],
        battle_logic_service=mock_services['battle_logic'],
        monster_action_service=mock_services['monster_action'],
        notifier=mock_services['notifier'],
        event_publisher=mock_services['event_publisher'],
        player_action_waiter=player_action_waiter
    )


class TestEnhancedBattleServiceIntegration:
    """改良された戦闘サービスの統合テスト"""
    
    @pytest.mark.asyncio
    async def test_start_battle_creates_battle_and_starts_loop(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """戦闘開始により戦闘が作成され、ループが開始される"""
        player_id = 1
        
        # 戦闘開始
        await enhanced_battle_service.start_battle(player_id)
        
        # 戦闘が保存される
        mock_repositories['battle'].save.assert_called()
        
        # 戦闘ループが開始される
        battle_id = 1
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is True
        
        # クリーンアップ
        enhanced_battle_service.stop_battle_loop(battle_id)
    
    @pytest.mark.asyncio
    async def test_player_action_execution_notifies_waiter(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """プレイヤー行動実行により行動待機が通知される"""
        battle_id = 1
        player_id = 1
        
        # モック戦闘を設定
        mock_battle = Mock(spec=Battle)
        mock_battle.battle_id = battle_id
        mock_battle.spot_id = 100
        mock_battle.is_in_progress.return_value = True
        
        # 現在のアクターをプレイヤーに設定
        mock_battle.get_current_actor.return_value = TurnEntry(
            participant_key=(ParticipantType.PLAYER, player_id),
            speed=20,
            priority=0
        )
        
        # プレイヤーの戦闘状態を設定
        mock_combat_state = Mock(spec=CombatState)
        mock_combat_state.entity_id = player_id
        mock_combat_state.participant_type = ParticipantType.PLAYER
        mock_battle.get_combat_state.return_value = mock_combat_state
        mock_battle.get_combat_states.return_value = {
            (ParticipantType.PLAYER, player_id): mock_combat_state
        }
        
        # イベント関連のモック設定
        mock_battle.get_events.return_value = []
        mock_battle.clear_events.return_value = None
        mock_battle.apply_battle_action_result.return_value = None
        mock_battle.execute_turn.return_value = None
        
        # リポジトリにモック戦闘を設定
        mock_repositories['battle'].find_by_id.return_value = mock_battle
        
        # 行動データ
        action_data = PlayerActionDto(
            battle_id=battle_id,
            player_id=player_id,
            action_id=1,
            target_ids=[1],
            target_participant_types=[ParticipantType.MONSTER]
        )
        
        # プレイヤー行動実行
        await enhanced_battle_service.execute_player_action(
            battle_id, player_id, action_data
        )
        
        # 戦闘状態が更新される
        mock_battle.apply_battle_action_result.assert_called_once()
        mock_battle.execute_turn.assert_called_once()
        
        # 戦闘が保存される
        mock_repositories['battle'].save.assert_called()
    
    def test_battle_status_retrieval(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """戦闘状態を正しく取得できる"""
        battle_id = 1
        
        # モック戦闘を設定
        mock_battle = Mock(spec=Battle)
        mock_battle.battle_id = battle_id
        mock_battle.is_in_progress.return_value = True
        mock_battle._current_turn = 5
        mock_battle._current_round = 2
        mock_battle.get_player_ids.return_value = [1, 2]
        mock_battle.get_monster_type_ids.return_value = [101]
        mock_battle._state = BattleState.IN_PROGRESS
        mock_battle._max_players = 4
        
        mock_repositories['battle'].find_by_id.return_value = mock_battle
        
        # 戦闘状態取得
        status = enhanced_battle_service.get_battle_status(battle_id)
        
        # 正しい情報が返される
        assert status.battle_id == battle_id
        assert status.is_active is True
        assert status.current_turn == 5
        assert status.current_round == 2
        assert status.player_count == 2
        assert status.monster_count == 1
    
    def test_join_and_leave_battle(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """戦闘参加と離脱が正しく動作する"""
        battle_id = 1
        player_id = 2
        
        # モック戦闘を設定
        mock_battle = Mock(spec=Battle)
        mock_battle.battle_id = battle_id
        mock_battle.spot_id = 100
        mock_battle.join_player.return_value = None
        mock_battle.player_escape.return_value = None
        mock_battle.get_events.return_value = []
        mock_battle.clear_events.return_value = None
        mock_battle._current_turn = 1
        
        mock_repositories['battle'].find_by_id.return_value = mock_battle
        
        # 新しいプレイヤーのモック
        mock_new_player = Mock()
        mock_new_player.player_id = player_id
        mock_new_player.current_spot_id = 100
        mock_repositories['player'].find_by_id.return_value = mock_new_player
        
        # 戦闘参加
        enhanced_battle_service.join_battle(battle_id, player_id)
        
        # 参加処理が呼ばれる
        mock_battle.join_player.assert_called_once()
        
        # 戦闘離脱
        enhanced_battle_service.leave_battle(battle_id, player_id)
        
        # 離脱処理が呼ばれる
        mock_battle.player_escape.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_battle_loop_stop_and_status(
        self, 
        enhanced_battle_service
    ):
        """戦闘ループの停止と状態確認"""
        battle_id = 1
        
        # 初期状態では実行されていない
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is False
        
        # 戦闘ループを開始（モック戦闘で）
        mock_battle = Mock(spec=Battle)
        mock_battle.battle_id = battle_id
        mock_battle.is_in_progress.return_value = True
        enhanced_battle_service._battle_repository.find_by_id.return_value = mock_battle
        
        await enhanced_battle_service._battle_loop_service.start_battle_loop(battle_id)
        
        # 実行中になる
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is True
        
        # 戦闘ループを停止
        enhanced_battle_service.stop_battle_loop(battle_id)
        
        # 停止する
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is False
    
    def test_player_action_waiter_statistics(
        self, 
        enhanced_battle_service
    ):
        """プレイヤー行動待機の統計情報を取得できる"""
        stats = enhanced_battle_service.get_player_action_waiter_statistics()
        
        # 統計情報が返される
        assert isinstance(stats, dict)
        assert "waiting_players" in stats
        assert "active_events" in stats
        assert "total_tracked" in stats
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_player(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """無効なプレイヤーIDでのエラーハンドリング"""
        # プレイヤーが見つからない場合
        mock_repositories['player'].find_by_id.return_value = None
        
        with pytest.raises(ValueError, match="Player not found"):
            await enhanced_battle_service.start_battle(999)
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_battle(
        self, 
        enhanced_battle_service, 
        mock_repositories
    ):
        """無効な戦闘IDでのエラーハンドリング"""
        # 戦闘が見つからない場合
        mock_repositories['battle'].find_by_id.return_value = None
        
        action_data = PlayerActionDto(
            battle_id=999,
            player_id=1,
            action_id=1
        )
        
        with pytest.raises(Exception):  # BattleNotFoundExceptionまたはその他の例外
            await enhanced_battle_service.execute_player_action(999, 1, action_data)


class TestBattleFlowIntegration:
    """戦闘フロー全体の統合テスト"""
    
    @pytest.mark.asyncio
    async def test_complete_battle_flow_simulation(
        self, 
        enhanced_battle_service, 
        mock_repositories, 
        mock_services
    ):
        """完全な戦闘フローのシミュレーション"""
        player_id = 1
        battle_id = 1
        
        # 1. 戦闘開始
        await enhanced_battle_service.start_battle(player_id)
        
        # 戦闘が作成され、ループが開始される
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is True
        
        # 2. モック戦闘の設定（プレイヤー行動のため）
        mock_battle = Mock(spec=Battle)
        mock_battle.battle_id = battle_id
        mock_battle.is_in_progress.return_value = True
        mock_battle.get_current_actor.return_value = TurnEntry(
            participant_key=(ParticipantType.PLAYER, player_id),
            speed=20,
            priority=0
        )
        
        mock_combat_state = Mock(spec=CombatState)
        mock_combat_state.entity_id = player_id
        mock_combat_state.participant_type = ParticipantType.PLAYER
        mock_battle.get_combat_state.return_value = mock_combat_state
        mock_battle.get_combat_states.return_value = {
            (ParticipantType.PLAYER, player_id): mock_combat_state
        }
        mock_battle.get_events.return_value = []
        mock_battle.clear_events.return_value = None
        mock_battle.apply_battle_action_result.return_value = None
        mock_battle.execute_turn.return_value = None
        mock_battle._current_turn = 1
        mock_battle._current_round = 1
        mock_battle.get_player_ids.return_value = [player_id]
        mock_battle.get_monster_type_ids.return_value = [101]
        mock_battle._state = BattleState.IN_PROGRESS
        mock_battle._max_players = 4
        
        mock_repositories['battle'].find_by_id.return_value = mock_battle
        
        # 3. プレイヤー行動実行
        action_data = PlayerActionDto(
            battle_id=battle_id,
            player_id=player_id,
            action_id=1,
            target_ids=[1],
            target_participant_types=[ParticipantType.MONSTER]
        )
        
        await enhanced_battle_service.execute_player_action(
            battle_id, player_id, action_data
        )
        
        # 行動が実行される
        mock_battle.apply_battle_action_result.assert_called()
        mock_battle.execute_turn.assert_called()
        
        # 4. 戦闘状態確認
        status = enhanced_battle_service.get_battle_status(battle_id)
        assert status.battle_id == battle_id
        
        # 5. 戦闘終了
        enhanced_battle_service.stop_battle_loop(battle_id)
        assert enhanced_battle_service.is_battle_loop_running(battle_id) is False
        
        # 統計情報も確認
        stats = enhanced_battle_service.get_player_action_waiter_statistics()
        assert isinstance(stats, dict)
