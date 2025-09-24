"""
PlayerActionWaiterサービスのテスト
"""
import pytest
import asyncio
from src.application.battle.services.player_action_waiter import PlayerActionWaiter, PlayerActionStatus


@pytest.fixture
def player_action_waiter():
    """テスト用のPlayerActionWaiterインスタンス"""
    return PlayerActionWaiter(default_timeout_seconds=1.0)  # テスト用に短いタイムアウト


class TestPlayerActionWaiterInitialization:
    """PlayerActionWaiter初期化のテスト"""
    
    def test_create_player_action_waiter(self, player_action_waiter):
        """PlayerActionWaiterを作成できる"""
        assert player_action_waiter is not None
        assert player_action_waiter._default_timeout_seconds == 1.0
        assert len(player_action_waiter._waiting_players) == 0
        assert len(player_action_waiter._action_events) == 0
    
    def test_is_player_waiting_initially_false(self, player_action_waiter):
        """初期状態ではプレイヤーが待機していない"""
        assert player_action_waiter.is_player_waiting(1, 1) is False
    
    def test_get_player_action_status_initially_none(self, player_action_waiter):
        """初期状態では行動状態がNone"""
        assert player_action_waiter.get_player_action_status(1, 1) is None
    
    def test_get_waiting_players_initially_empty(self, player_action_waiter):
        """初期状態では待機中プレイヤーが空"""
        assert len(player_action_waiter.get_waiting_players()) == 0


class TestPlayerActionWaiterWaitForAction:
    """行動待機のテスト"""
    
    @pytest.mark.asyncio
    async def test_wait_for_player_action_completed(self, player_action_waiter):
        """行動完了通知により待機が終了する"""
        battle_id = 1
        player_id = 1
        
        # 別のタスクで行動完了を通知
        async def notify_completion():
            await asyncio.sleep(0.1)  # 少し待ってから通知
            player_action_waiter.notify_player_action_completed(battle_id, player_id)
        
        # 通知タスクを開始
        notify_task = asyncio.create_task(notify_completion())
        
        # 行動待機
        result = await player_action_waiter.wait_for_player_action(battle_id, player_id)
        
        # 行動が完了したことを確認
        assert result is True
        
        # 通知タスクの完了を待つ
        await notify_task
        
        # 待機状態がクリーンアップされている
        assert not player_action_waiter.is_player_waiting(battle_id, player_id)
    
    @pytest.mark.asyncio
    async def test_wait_for_player_action_timeout(self, player_action_waiter):
        """タイムアウトにより待機が終了する"""
        battle_id = 1
        player_id = 1
        
        # 行動待機（タイムアウトを短く設定）
        result = await player_action_waiter.wait_for_player_action(
            battle_id, player_id, timeout_seconds=0.1
        )
        
        # タイムアウトしたことを確認
        assert result is False
        
        # 状態がタイムアウトになっている
        status = player_action_waiter.get_player_action_status(battle_id, player_id)
        assert status == PlayerActionStatus.TIMEOUT
    
    @pytest.mark.asyncio
    async def test_wait_for_player_action_already_completed(self, player_action_waiter):
        """既に完了している場合は即座に返す"""
        battle_id = 1
        player_id = 1
        
        # 事前に完了状態に設定
        key = (battle_id, player_id)
        player_action_waiter._player_action_status[key] = PlayerActionStatus.COMPLETED
        
        # 行動待機
        result = await player_action_waiter.wait_for_player_action(battle_id, player_id)
        
        # 即座に完了
        assert result is True
    
    @pytest.mark.asyncio
    async def test_wait_for_player_action_custom_timeout(self, player_action_waiter):
        """カスタムタイムアウトが正しく動作する"""
        battle_id = 1
        player_id = 1
        
        start_time = asyncio.get_event_loop().time()
        
        # 短いカスタムタイムアウトで待機
        result = await player_action_waiter.wait_for_player_action(
            battle_id, player_id, timeout_seconds=0.2
        )
        
        end_time = asyncio.get_event_loop().time()
        elapsed_time = end_time - start_time
        
        # タイムアウトしたことを確認
        assert result is False
        # 指定した時間程度でタイムアウトしたことを確認（多少の誤差を許容）
        assert 0.15 <= elapsed_time <= 0.5  # 許容範囲を広げる


class TestPlayerActionWaiterNotification:
    """行動完了通知のテスト"""
    
    def test_notify_player_action_completed_success(self, player_action_waiter):
        """待機中のプレイヤーに正しく通知される"""
        battle_id = 1
        player_id = 1
        key = (battle_id, player_id)
        
        # 待機状態を設定
        player_action_waiter._waiting_players.add(key)
        player_action_waiter._action_events[key] = asyncio.Event()
        
        # 通知実行
        result = player_action_waiter.notify_player_action_completed(battle_id, player_id)
        
        # 通知成功
        assert result is True
        
        # イベントが発火されている
        assert player_action_waiter._action_events[key].is_set()
    
    def test_notify_player_action_completed_not_waiting(self, player_action_waiter):
        """待機中でないプレイヤーへの通知は失敗する"""
        battle_id = 1
        player_id = 1
        
        # 通知実行（待機状態でない）
        result = player_action_waiter.notify_player_action_completed(battle_id, player_id)
        
        # 通知失敗
        assert result is False
    
    def test_notify_player_action_completed_no_event(self, player_action_waiter):
        """イベントが存在しない場合の通知"""
        battle_id = 1
        player_id = 1
        key = (battle_id, player_id)
        
        # 待機状態だがイベントがない状態を設定
        player_action_waiter._waiting_players.add(key)
        
        # 通知実行
        result = player_action_waiter.notify_player_action_completed(battle_id, player_id)
        
        # 通知失敗
        assert result is False


class TestPlayerActionWaiterCancellation:
    """行動キャンセルのテスト"""
    
    def test_cancel_player_action_wait_success(self, player_action_waiter):
        """待機中の行動を正常にキャンセルできる"""
        battle_id = 1
        player_id = 1
        key = (battle_id, player_id)
        
        # 待機状態を設定
        player_action_waiter._waiting_players.add(key)
        player_action_waiter._action_events[key] = asyncio.Event()
        
        # キャンセル実行
        result = player_action_waiter.cancel_player_action_wait(battle_id, player_id)
        
        # キャンセル成功
        assert result is True
        
        # 状態がキャンセルになっている
        status = player_action_waiter.get_player_action_status(battle_id, player_id)
        assert status == PlayerActionStatus.CANCELLED
        
        # イベントが発火されている
        assert player_action_waiter._action_events[key].is_set()
    
    def test_cancel_player_action_wait_not_waiting(self, player_action_waiter):
        """待機中でない行動のキャンセルは失敗する"""
        battle_id = 1
        player_id = 1
        
        # キャンセル実行（待機状態でない）
        result = player_action_waiter.cancel_player_action_wait(battle_id, player_id)
        
        # キャンセル失敗
        assert result is False
    
    @pytest.mark.asyncio
    async def test_wait_for_player_action_cancelled(self, player_action_waiter):
        """キャンセルされた行動待機の動作"""
        battle_id = 1
        player_id = 1
        
        # 別のタスクでキャンセル
        async def cancel_action():
            await asyncio.sleep(0.1)  # 少し待ってからキャンセル
            player_action_waiter.cancel_player_action_wait(battle_id, player_id)
        
        # キャンセルタスクを開始
        cancel_task = asyncio.create_task(cancel_action())
        
        # 行動待機
        result = await player_action_waiter.wait_for_player_action(battle_id, player_id)
        
        # キャンセルされたため失敗
        assert result is False
        
        # キャンセルタスクの完了を待つ
        await cancel_task
        
        # 状態がキャンセルになっている
        status = player_action_waiter.get_player_action_status(battle_id, player_id)
        assert status == PlayerActionStatus.CANCELLED


class TestPlayerActionWaiterUtility:
    """ユーティリティメソッドのテスト"""
    
    def test_get_waiting_players(self, player_action_waiter):
        """待機中プレイヤー一覧を取得できる"""
        battle_id = 1
        player1_id = 1
        player2_id = 2
        
        # 複数のプレイヤーを待機状態に設定
        player_action_waiter._waiting_players.add((battle_id, player1_id))
        player_action_waiter._waiting_players.add((battle_id, player2_id))
        
        waiting_players = player_action_waiter.get_waiting_players()
        
        assert len(waiting_players) == 2
        assert (battle_id, player1_id) in waiting_players
        assert (battle_id, player2_id) in waiting_players
    
    def test_cleanup_battle_players(self, player_action_waiter):
        """戦闘の全プレイヤーをクリーンアップできる"""
        battle1_id = 1
        battle2_id = 2
        player1_id = 1
        player2_id = 2
        
        # 複数の戦闘のプレイヤーを設定
        keys = [
            (battle1_id, player1_id),
            (battle1_id, player2_id),
            (battle2_id, player1_id),
        ]
        
        for key in keys:
            player_action_waiter._waiting_players.add(key)
            player_action_waiter._action_events[key] = asyncio.Event()
        
        # 戦闘1のプレイヤーをクリーンアップ
        player_action_waiter.cleanup_battle_players(battle1_id)
        
        # 戦闘1のプレイヤーがクリーンアップされている
        assert (battle1_id, player1_id) not in player_action_waiter._waiting_players
        assert (battle1_id, player2_id) not in player_action_waiter._waiting_players
        
        # 戦闘2のプレイヤーは残っている
        assert (battle2_id, player1_id) in player_action_waiter._waiting_players
        
        # 状態がキャンセルになっている
        assert player_action_waiter.get_player_action_status(battle1_id, player1_id) == PlayerActionStatus.CANCELLED
        assert player_action_waiter.get_player_action_status(battle1_id, player2_id) == PlayerActionStatus.CANCELLED
    
    def test_get_statistics(self, player_action_waiter):
        """統計情報を取得できる"""
        battle_id = 1
        player1_id = 1
        player2_id = 2
        
        # 異なる状態のプレイヤーを設定
        player_action_waiter._player_action_status[(battle_id, player1_id)] = PlayerActionStatus.WAITING
        player_action_waiter._player_action_status[(battle_id, player2_id)] = PlayerActionStatus.COMPLETED
        player_action_waiter._waiting_players.add((battle_id, player1_id))
        player_action_waiter._action_events[(battle_id, player1_id)] = asyncio.Event()
        
        stats = player_action_waiter.get_statistics()
        
        assert stats["waiting_players"] == 1
        assert stats["active_events"] == 1
        assert stats["total_tracked"] == 2
        assert stats["waiting"] == 1
        assert stats["completed"] == 1
        assert stats["timeout"] == 0
        assert stats["cancelled"] == 0
