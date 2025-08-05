from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from game.enums import TurnActionType
from game.monster.monster import Monster,MonsterDropReward
from game.battle.contribution_data import DistributedReward


@dataclass
class BattleEvent:
    """戦闘イベント情報"""
    event_id: str
    timestamp: datetime
    event_type: str  # "player_action", "monster_action", "status_effect", "battle_state_change", etc.
    actor_id: str  # プレイヤーIDまたはモンスターID
    target_id: Optional[str] = None  # 対象のID
    action_type: Optional[TurnActionType] = None
    damage: int = 0
    success: bool = True
    critical: bool = False
    evaded: bool = False
    counter_attack: bool = False
    status_effects_applied: List = field(default_factory=list)
    
    # LLMフレンドリーな文字列メッセージ
    message: str = ""
    
    # 構造化データ（LLMが解析しやすい形式）
    structured_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BattleEventLog:
    """戦闘イベントログ管理クラス"""
    events: List[BattleEvent] = field(default_factory=list)
    player_read_positions: Dict[str, int] = field(default_factory=dict)  # プレイヤーID -> 最後に読んだイベントのインデックス
    
    def add_event(self, event: BattleEvent):
        """イベントを追加"""
        self.events.append(event)
    
    def get_unread_events_for_player(self, player_id: str) -> List[BattleEvent]:
        """プレイヤーの未読イベントを取得"""
        last_read = self.player_read_positions.get(player_id, -1)
        return self.events[last_read + 1:]
    
    def mark_events_as_read(self, player_id: str):
        """プレイヤーの既読位置を更新"""
        self.player_read_positions[player_id] = len(self.events) - 1
    
    def get_all_events(self) -> List[BattleEvent]:
        """全イベントを取得"""
        return self.events.copy()
    
    def get_events_since(self, timestamp: datetime) -> List[BattleEvent]:
        """指定時刻以降のイベントを取得"""
        return [event for event in self.events if event.timestamp >= timestamp]
    
    def get_llm_context_for_player(self, player_id: str) -> str:
        """LLM用のコンテキスト文字列を生成"""
        unread_events = self.get_unread_events_for_player(player_id)
        if not unread_events:
            return "新しい戦闘イベントはありません。"
        
        context_lines = []
        for event in unread_events:
            context_lines.append(f"[{event.timestamp.strftime('%H:%M:%S')}] {event.message}")
        
        return "\n".join(context_lines)
    
    def get_structured_context_for_player(self, player_id: str) -> Dict[str, Any]:
        """LLM用の構造化コンテキストを生成"""
        unread_events = self.get_unread_events_for_player(player_id)
        
        return {
            "unread_events_count": len(unread_events),
            "events": [
                {
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "target_id": event.target_id,
                    "action_type": event.action_type.value if event.action_type else None,
                    "damage": event.damage,
                    "success": event.success,
                    "critical": event.critical,
                    "evaded": event.evaded,
                    "counter_attack": event.counter_attack,
                    "status_effects": [str(effect) for effect in event.status_effects_applied],
                    "message": event.message,
                    "structured_data": event.structured_data
                }
                for event in unread_events
            ]
        }


@dataclass
class TurnAction:
    """ターン行動情報（後方互換性のため保持）"""
    actor_id: str  # プレイヤーIDまたはモンスターID
    action_type: TurnActionType
    target_id: Optional[str] = None  # 攻撃対象のID
    damage: int = 0
    success: bool = True
    message: str = ""
    critical: bool = False  # クリティカルヒット
    evaded: bool = False   # 回避
    counter_attack: bool = False  # 反撃
    status_effects_applied: List = field(default_factory=list)  # 適用された状態異常


@dataclass
class BattleResult:
    """戦闘結果"""
    victory: bool
    participants: List[str]  # 参加プレイヤーID
    defeated_monsters: List[Monster] = field(default_factory=list)  # 倒されたモンスターのリスト
    total_rewards: Optional[MonsterDropReward] = None  # 合計報酬
    distributed_rewards: Dict[str, 'DistributedReward'] = field(default_factory=dict)  # 分配された報酬
    escaped: bool = False
    battle_log: List[str] = field(default_factory=list)  # 後方互換性のため保持
    event_log: Optional[BattleEventLog] = None  # 新しいイベントログ