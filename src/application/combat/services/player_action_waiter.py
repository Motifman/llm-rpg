"""
プレイヤー行動待機を管理するサービス

責務:
- プレイヤーの行動完了を待機
- タイムアウト処理
- 行動完了状態の管理
- WebSocketやメッセージキューとの統合ポイント
"""
import asyncio
from typing import Dict, Set, Optional
from enum import Enum


class PlayerActionStatus(Enum):
    """プレイヤー行動状態"""
    WAITING = "waiting"        # 行動待機中
    COMPLETED = "completed"    # 行動完了
    TIMEOUT = "timeout"        # タイムアウト
    CANCELLED = "cancelled"    # キャンセル


class PlayerActionWaiter:
    """プレイヤー行動待機サービス"""
    
    def __init__(self, default_timeout_seconds: float = 30.0):
        """
        初期化
        
        Args:
            default_timeout_seconds: デフォルトタイムアウト時間（秒）
        """
        self._default_timeout_seconds = default_timeout_seconds
        
        # プレイヤー行動状態を管理
        self._player_action_status: Dict[tuple[int, int], PlayerActionStatus] = {}
        
        # 行動完了待機中のプレイヤー
        self._waiting_players: Set[tuple[int, int]] = set()
        
        # 行動完了イベント（battle_id, player_id）-> asyncio.Event
        self._action_events: Dict[tuple[int, int], asyncio.Event] = {}
    
    async def wait_for_player_action(
        self, 
        battle_id: int, 
        player_id: int, 
        timeout_seconds: Optional[float] = None
    ) -> bool:
        """
        プレイヤーの行動完了を待機
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            timeout_seconds: タイムアウト時間（秒）。Noneの場合はデフォルト値を使用
            
        Returns:
            bool: 行動が完了した場合True、タイムアウトした場合False
        """
        if timeout_seconds is None:
            timeout_seconds = self._default_timeout_seconds
        
        key = (battle_id, player_id)
        
        # 既に完了している場合は即座に返す
        if self._player_action_status.get(key) == PlayerActionStatus.COMPLETED:
            self._cleanup_player_action(key)
            return True
        
        # 待機状態に設定
        self._player_action_status[key] = PlayerActionStatus.WAITING
        self._waiting_players.add(key)
        
        # 行動完了イベントを作成
        action_event = asyncio.Event()
        self._action_events[key] = action_event
        
        try:
            # タイムアウト付きで行動完了を待機
            await asyncio.wait_for(action_event.wait(), timeout=timeout_seconds)
            
            # キャンセルされていないかチェック
            if self._player_action_status.get(key) == PlayerActionStatus.CANCELLED:
                return False
            
            # 行動完了
            self._player_action_status[key] = PlayerActionStatus.COMPLETED
            return True
            
        except asyncio.TimeoutError:
            # タイムアウト
            self._player_action_status[key] = PlayerActionStatus.TIMEOUT
            return False
            
        finally:
            # クリーンアップ
            self._cleanup_player_action(key)
    
    def notify_player_action_completed(self, battle_id: int, player_id: int) -> bool:
        """
        プレイヤーの行動完了を通知
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            
        Returns:
            bool: 待機中のプレイヤーが存在し、通知が成功した場合True
        """
        key = (battle_id, player_id)
        
        # 待機中でない場合は何もしない
        if key not in self._waiting_players:
            return False
        
        # 行動完了イベントを発火
        if key in self._action_events:
            self._action_events[key].set()
            return True
        
        return False
    
    def cancel_player_action_wait(self, battle_id: int, player_id: int) -> bool:
        """
        プレイヤー行動待機をキャンセル
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            
        Returns:
            bool: キャンセルが成功した場合True
        """
        key = (battle_id, player_id)
        
        if key not in self._waiting_players:
            return False
        
        # キャンセル状態に設定
        self._player_action_status[key] = PlayerActionStatus.CANCELLED
        
        # イベントを発火してwait_for_player_actionを終了させる
        if key in self._action_events:
            self._action_events[key].set()
        
        return True
    
    def get_player_action_status(self, battle_id: int, player_id: int) -> Optional[PlayerActionStatus]:
        """
        プレイヤー行動状態を取得
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            
        Returns:
            PlayerActionStatus: 行動状態。存在しない場合はNone
        """
        key = (battle_id, player_id)
        return self._player_action_status.get(key)
    
    def is_player_waiting(self, battle_id: int, player_id: int) -> bool:
        """
        プレイヤーが行動待機中かどうか
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            
        Returns:
            bool: 待機中の場合True
        """
        key = (battle_id, player_id)
        return key in self._waiting_players
    
    def get_waiting_players(self) -> Set[tuple[int, int]]:
        """
        現在待機中のプレイヤー一覧を取得
        
        Returns:
            Set[tuple[int, int]]: 待機中のプレイヤー（battle_id, player_id）のセット
        """
        return self._waiting_players.copy()
    
    def cleanup_battle_players(self, battle_id: int) -> None:
        """
        指定した戦闘の全プレイヤーの待機状態をクリーンアップ
        
        Args:
            battle_id: 戦闘ID
        """
        keys_to_remove = [key for key in self._waiting_players if key[0] == battle_id]
        
        for key in keys_to_remove:
            # キャンセル状態に設定してイベントを発火
            self._player_action_status[key] = PlayerActionStatus.CANCELLED
            if key in self._action_events:
                self._action_events[key].set()
            
            self._cleanup_player_action(key)
    
    def _cleanup_player_action(self, key: tuple[int, int]) -> None:
        """
        プレイヤー行動の内部状態をクリーンアップ
        
        Args:
            key: (battle_id, player_id)のタプル
        """
        self._waiting_players.discard(key)
        
        if key in self._action_events:
            del self._action_events[key]
        
        # 状態は一定時間保持（デバッグ用）
        # 実際の実装では適切なタイミングで削除
    
    def get_statistics(self) -> Dict[str, int]:
        """
        統計情報を取得（監視・デバッグ用）
        
        Returns:
            Dict[str, int]: 統計情報
        """
        status_counts = {}
        for status in PlayerActionStatus:
            status_counts[status.value] = sum(
                1 for s in self._player_action_status.values() if s == status
            )
        
        return {
            "waiting_players": len(self._waiting_players),
            "active_events": len(self._action_events),
            "total_tracked": len(self._player_action_status),
            **status_counts
        }
