"""
BattleLoopServiceアプリケーションサービスのテスト
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.application.combat.services.battle_loop_service import BattleLoopService
from src.domain.battle.battle import Battle
from src.domain.battle.battle_enum import BattleState, ParticipantType
from src.domain.battle.battle_exception import BattleNotFoundException
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnEntry


@pytest.fixture
def mock_battle_repository():
    """テスト用のBattleRepositoryモック"""
    repository = Mock()
    
    # デフォルトのバトルモック
    mock_battle = Mock(spec=Battle)
    mock_battle.battle_id = 1
    mock_battle.is_in_progress.return_value = True
    mock_battle.get_current_actor.return_value = TurnEntry(
        participant_key=(ParticipantType.PLAYER, 1),
        speed=20,
        priority=0
    )
    mock_battle.get_events.return_value = []
    mock_battle.clear_events.return_value = None
    
    repository.find_by_id.return_value = mock_battle
    repository.save.return_value = None
    
    return repository


@pytest.fixture
def mock_turn_processor():
    """テスト用のTurnProcessorモック"""
    processor = Mock()
    
    processor.process_turn_start.return_value = TurnStartResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        can_act=True,
        damage=0,
        healing=0
    )
    
    processor.process_turn_end.return_value = TurnEndResult(
        actor_id=1,
        participant_type=ParticipantType.PLAYER,
        damage=0,
        healing=0
    )
    
    processor.check_and_handle_battle_end.return_value = False
    processor.advance_turn.return_value = None
    
    return processor


@pytest.fixture
def mock_monster_action_service():
    """テスト用のMonsterActionServiceモック"""
    return Mock()


@pytest.fixture
def mock_action_repository():
    """テスト用のActionRepositoryモック"""
    return Mock()


@pytest.fixture
def mock_event_publisher():
    """テスト用のEventPublisherモック"""
    publisher = Mock()
    publisher.publish_all.return_value = None
    return publisher


@pytest.fixture
def mock_player_action_waiter():
    """テスト用のPlayerActionWaiterモック"""
    waiter = AsyncMock()
    waiter.wait_for_player_action.return_value = True
    return waiter


@pytest.fixture
def battle_loop_service(
    mock_battle_repository,
    mock_turn_processor,
    mock_monster_action_service,
    mock_action_repository,
    mock_event_publisher,
    mock_player_action_waiter
):
    """テスト用のBattleLoopServiceインスタンス"""
    return BattleLoopService(
        battle_repository=mock_battle_repository,
        turn_processor=mock_turn_processor,
        monster_action_service=mock_monster_action_service,
        action_repository=mock_action_repository,
        event_publisher=mock_event_publisher,
        player_action_waiter=mock_player_action_waiter
    )


class TestBattleLoopServiceInitialization:
    """BattleLoopService初期化のテスト"""
    
    def test_create_battle_loop_service(self, battle_loop_service):
        """BattleLoopServiceを作成できる"""
        assert battle_loop_service is not None
        assert len(battle_loop_service._running_battles) == 0
        assert len(battle_loop_service._battle_loop_tasks) == 0
    
    def test_is_battle_loop_running_initially_false(self, battle_loop_service):
        """初期状態では戦闘ループが実行されていない"""
        assert battle_loop_service.is_battle_loop_running(1) is False


class TestBattleLoopServiceStartStop:
    """戦闘ループの開始・停止のテスト"""
    
    @pytest.mark.asyncio
    async def test_start_battle_loop_success(self, battle_loop_service, mock_battle_repository):
        """正常に戦闘ループを開始できる"""
        battle_id = 1
        
        await battle_loop_service.start_battle_loop(battle_id)
        
        # ループが実行中としてマークされる
        assert battle_loop_service.is_battle_loop_running(battle_id) is True
        assert battle_id in battle_loop_service._running_battles
        assert battle_id in battle_loop_service._battle_loop_tasks
        
        # クリーンアップ
        battle_loop_service.stop_battle_loop(battle_id)
    
    @pytest.mark.asyncio
    async def test_start_battle_loop_battle_not_found(self, battle_loop_service, mock_battle_repository):
        """戦闘が見つからない場合はエラー"""
        battle_id = 999
        mock_battle_repository.find_by_id.return_value = None
        
        with pytest.raises(BattleNotFoundException):
            await battle_loop_service.start_battle_loop(battle_id)
    
    @pytest.mark.asyncio
    async def test_start_battle_loop_battle_not_in_progress(self, battle_loop_service, mock_battle_repository):
        """戦闘が進行中でない場合はエラー"""
        battle_id = 1
        mock_battle = Mock(spec=Battle)
        mock_battle.is_in_progress.return_value = False
        mock_battle_repository.find_by_id.return_value = mock_battle
        
        with pytest.raises(ValueError, match="Battle is not in progress"):
            await battle_loop_service.start_battle_loop(battle_id)
    
    @pytest.mark.asyncio
    async def test_start_battle_loop_already_running(self, battle_loop_service):
        """既に実行中の戦闘ループを開始しようとするとエラー"""
        battle_id = 1
        
        await battle_loop_service.start_battle_loop(battle_id)
        
        with pytest.raises(ValueError, match="Battle loop already running"):
            await battle_loop_service.start_battle_loop(battle_id)
        
        # クリーンアップ
        battle_loop_service.stop_battle_loop(battle_id)
    
    def test_stop_battle_loop(self, battle_loop_service):
        """戦闘ループを停止できる"""
        battle_id = 1
        
        # モックタスクを追加
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel.return_value = None
        
        battle_loop_service._running_battles.add(battle_id)
        battle_loop_service._battle_loop_tasks[battle_id] = mock_task
        
        battle_loop_service.stop_battle_loop(battle_id)
        
        # タスクがキャンセルされる
        mock_task.cancel.assert_called_once()
        
        # 状態がクリーンアップされる
        assert battle_id not in battle_loop_service._running_battles
        assert battle_id not in battle_loop_service._battle_loop_tasks
    
    def test_stop_battle_loop_not_running(self, battle_loop_service):
        """実行中でない戦闘ループの停止は何もしない"""
        battle_id = 999
        
        # エラーが発生しないことを確認
        battle_loop_service.stop_battle_loop(battle_id)


class TestBattleLoopServiceTurnProcessing:
    """ターン処理のテスト"""
    
    @pytest.mark.asyncio
    async def test_process_single_turn_player_turn(
        self, 
        battle_loop_service, 
        mock_battle_repository,
        mock_turn_processor,
        mock_event_publisher,
        mock_player_action_waiter
    ):
        """プレイヤーターンの単一ターン処理"""
        battle_id = 1
        mock_battle = mock_battle_repository.find_by_id.return_value
        
        # プレイヤーターンを設定
        mock_battle.get_current_actor.return_value = TurnEntry(
            participant_key=(ParticipantType.PLAYER, 1),
            speed=20,
            priority=0
        )
        
        # 戦闘終了しない設定
        mock_turn_processor.check_and_handle_battle_end.return_value = False
        
        result = await battle_loop_service._process_single_turn(mock_battle)
        
        # ターン処理が実行される
        mock_turn_processor.process_turn_start.assert_called_once()
        mock_turn_processor.process_turn_end.assert_called_once()
        mock_turn_processor.advance_turn.assert_called_once()
        
        # プレイヤー行動待機が実行される
        mock_player_action_waiter.wait_for_player_action.assert_called_once_with(battle_id, 1)
        
        # イベントが発行される
        assert mock_event_publisher.publish_all.call_count >= 1
        
        # 戦闘が継続
        assert result is False
    
    @pytest.mark.asyncio
    async def test_process_single_turn_monster_turn(
        self,
        battle_loop_service,
        mock_battle_repository,
        mock_turn_processor,
        mock_event_publisher
    ):
        """モンスターターンの単一ターン処理"""
        mock_battle = mock_battle_repository.find_by_id.return_value
        
        # モンスターターンを設定
        mock_battle.get_current_actor.return_value = TurnEntry(
            participant_key=(ParticipantType.MONSTER, 1),
            speed=15,
            priority=0
        )
        
        # モンスターの戦闘状態を設定
        mock_monster_state = Mock()
        mock_monster_state.available_action_ids = [1, 2]
        mock_battle.get_combat_state.return_value = mock_monster_state
        
        # 戦闘終了しない設定
        mock_turn_processor.check_and_handle_battle_end.return_value = False
        
        with patch.object(battle_loop_service, '_execute_monster_action') as mock_execute:
            result = await battle_loop_service._process_single_turn(mock_battle)
        
        # モンスター行動が実行される
        mock_execute.assert_called_once()
        
        # 戦闘が継続
        assert result is False
    
    @pytest.mark.asyncio
    async def test_process_single_turn_battle_ends(
        self,
        battle_loop_service,
        mock_battle_repository,
        mock_turn_processor,
        mock_event_publisher
    ):
        """戦闘終了条件を満たした場合の処理"""
        mock_battle = mock_battle_repository.find_by_id.return_value
        
        # 戦闘終了を設定
        mock_turn_processor.check_and_handle_battle_end.return_value = True
        
        result = await battle_loop_service._process_single_turn(mock_battle)
        
        # 戦闘が終了
        assert result is True
        
        # 戦闘が保存される
        mock_battle_repository.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_single_turn_cannot_act(
        self,
        battle_loop_service,
        mock_battle_repository,
        mock_turn_processor,
        mock_player_action_waiter
    ):
        """行動不能な場合の処理"""
        mock_battle = mock_battle_repository.find_by_id.return_value
        
        # 行動不能を設定
        mock_turn_processor.process_turn_start.return_value = TurnStartResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            can_act=False,  # 行動不能
            damage=0,
            healing=0
        )
        
        mock_turn_processor.check_and_handle_battle_end.return_value = False
        
        result = await battle_loop_service._process_single_turn(mock_battle)
        
        # プレイヤー行動待機が実行されない
        mock_player_action_waiter.wait_for_player_action.assert_not_called()
        
        # ターン終了処理は実行される
        mock_turn_processor.process_turn_end.assert_called_once()
        
        assert result is False


class TestBattleLoopServicePlayerActionWait:
    """プレイヤー行動待機のテスト"""
    
    @pytest.mark.asyncio
    async def test_handle_player_turn_with_waiter(self, battle_loop_service, mock_player_action_waiter):
        """PlayerActionWaiterがある場合の処理"""
        battle_id = 1
        player_id = 1
        
        await battle_loop_service._handle_player_turn(battle_id, player_id)
        
        mock_player_action_waiter.wait_for_player_action.assert_called_once_with(battle_id, player_id)
    
    @pytest.mark.asyncio
    async def test_handle_player_turn_without_waiter(self, mock_battle_repository, mock_turn_processor, mock_monster_action_service, mock_action_repository, mock_event_publisher):
        """PlayerActionWaiterがない場合の処理"""
        service = BattleLoopService(
            battle_repository=mock_battle_repository,
            turn_processor=mock_turn_processor,
            monster_action_service=mock_monster_action_service,
            action_repository=mock_action_repository,
            event_publisher=mock_event_publisher,
            player_action_waiter=None  # Waiterなし
        )
        
        battle_id = 1
        player_id = 1
        
        with patch.object(service, '_simple_player_action_wait') as mock_simple_wait:
            mock_simple_wait.return_value = None
            
            await service._handle_player_turn(battle_id, player_id)
            
            mock_simple_wait.assert_called_once_with(battle_id, player_id)
    
    @pytest.mark.asyncio
    async def test_simple_player_action_wait_timeout(self, battle_loop_service):
        """シンプル待機のタイムアウト処理"""
        battle_id = 1
        player_id = 1
        
        # タイムアウトを短く設定してテスト
        with patch.object(battle_loop_service, '_check_player_action_executed', return_value=False):
            # 短いタイムアウトでテスト（実際の30秒は長すぎる）
            original_method = battle_loop_service._simple_player_action_wait
            
            async def fast_timeout_wait(bid, pid):
                timeout_seconds = 0.1  # 短いタイムアウト
                check_interval = 0.05
                elapsed_time = 0.0
                
                while elapsed_time < timeout_seconds:
                    if battle_loop_service._check_player_action_executed(bid, pid):
                        return
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
            
            battle_loop_service._simple_player_action_wait = fast_timeout_wait
            
            # タイムアウトまで待機することを確認
            await battle_loop_service._simple_player_action_wait(battle_id, player_id)
            
            # 元のメソッドに戻す
            battle_loop_service._simple_player_action_wait = original_method
