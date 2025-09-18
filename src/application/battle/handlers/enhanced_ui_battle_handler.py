"""
改善されたバトルイベントシステム用のUI統合ハンドラー
UIで戦闘画面を構成するために必要な全情報を含むイベントを処理
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.domain.battle.events.battle_events import (
    BattleStartedEvent,
    TurnStartedEvent,
    TurnExecutedEvent,
    TurnEndedEvent,
    RoundStartedEvent,
    RoundEndedEvent,
    BattleEndedEvent,
    MonsterDefeatedEvent,
    PlayerDefeatedEvent,
    ParticipantInfo,
    ActionInfo,
    TargetResult,
    StatusEffectApplication,
    BuffApplication
)
from src.domain.common.event_handler import EventHandler
from src.domain.battle.battle_enum import ParticipantType


@dataclass
class UIBattleState:
    """UI表示用の戦闘状態"""
    battle_id: int
    turn_number: int
    round_number: int
    current_actor_id: Optional[int] = None
    current_actor_type: Optional[ParticipantType] = None
    participants: List[ParticipantInfo] = None
    turn_order: List[tuple] = None
    messages: List[str] = None
    is_battle_active: bool = True
    
    def __post_init__(self):
        if self.participants is None:
            self.participants = []
        if self.turn_order is None:
            self.turn_order = []
        if self.messages is None:
            self.messages = []


@dataclass
class UIActionResult:
    """UI表示用のアクション結果"""
    actor_info: ParticipantInfo
    action_info: Optional[ActionInfo]
    target_results: List[TargetResult]
    status_effects_applied: List[StatusEffectApplication]
    buffs_applied: List[BuffApplication]
    participants_after: List[ParticipantInfo]
    messages: List[str]
    success: bool


class UIBattleNotifier:
    """擬似的なUI向けの戦闘情報通知システム"""
    
    def __init__(self):
        self._current_battle_state: Optional[UIBattleState] = None
        self._battle_log: List[str] = []
        self._ui_update_callbacks = []
    
    def register_ui_callback(self, callback):
        """UI更新コールバックを登録"""
        self._ui_update_callbacks.append(callback)
    
    def _notify_ui_update(self, update_type: str, data: Any):
        """UI更新を通知"""
        for callback in self._ui_update_callbacks:
            try:
                callback(update_type, data)
            except Exception as e:
                print(f"⚠️ UI更新エラー: {e}")
    
    def update_battle_state(self, battle_state: UIBattleState):
        """戦闘状態を更新"""
        self._current_battle_state = battle_state
        self._notify_ui_update("battle_state", battle_state)
    
    def add_action_result(self, action_result: UIActionResult):
        """アクション結果を追加"""
        self._notify_ui_update("action_result", action_result)
    
    def add_battle_message(self, message: str):
        """戦闘メッセージを追加"""
        self._battle_log.append(message)
        self._notify_ui_update("message", message)
    
    def end_battle(self, result_data: Dict[str, Any]):
        """戦闘終了を通知"""
        if self._current_battle_state:
            self._current_battle_state.is_battle_active = False
        self._notify_ui_update("battle_end", result_data)
    
    def get_current_state(self) -> Optional[UIBattleState]:
        """現在の戦闘状態を取得"""
        return self._current_battle_state
    
    def get_battle_log(self) -> List[str]:
        """戦闘ログを取得"""
        return self._battle_log.copy()


class EnhancedBattleStartedHandler(EventHandler[BattleStartedEvent]):
    """改善された戦闘開始ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: BattleStartedEvent):
        """戦闘開始イベントを処理"""
        battle_state = UIBattleState(
            battle_id=event.battle_id,
            turn_number=0,
            round_number=0,
            messages=[f"戦闘開始！参加者: プレイヤー {len(event.player_ids)}名, モンスター {len(event.monster_ids)}体"]
        )
        
        self._ui_notifier.update_battle_state(battle_state)
        self._ui_notifier.add_battle_message(
            f"🎮 戦闘が開始されました (Battle ID: {event.battle_id})"
        )


class EnhancedRoundStartedHandler(EventHandler[RoundStartedEvent]):
    """改善されたラウンド開始ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: RoundStartedEvent):
        """ラウンド開始イベントを処理"""
        battle_state = UIBattleState(
            battle_id=event.battle_id,
            turn_number=0,
            round_number=event.round_number,
            participants=event.all_participants,
            turn_order=event.turn_order,
            messages=event.messages
        )
        
        self._ui_notifier.update_battle_state(battle_state)
        self._ui_notifier.add_battle_message(
            f"🔄 ラウンド {event.round_number} 開始 - 参加者 {len(event.all_participants)}名"
        )


class EnhancedTurnStartedHandler(EventHandler[TurnStartedEvent]):
    """改善されたターン開始ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: TurnStartedEvent):
        """ターン開始イベントを処理"""
        battle_state = UIBattleState(
            battle_id=event.battle_id,
            turn_number=event.turn_number,
            round_number=event.round_number,
            current_actor_id=event.actor_id,
            current_actor_type=event.participant_type,
            participants=event.all_participants,
            turn_order=event.turn_order,
            messages=event.messages
        )
        
        self._ui_notifier.update_battle_state(battle_state)
        
        if event.actor_info:
            actor_name = event.actor_info.name
            actor_type = "プレイヤー" if event.participant_type == ParticipantType.PLAYER else "モンスター"
            self._ui_notifier.add_battle_message(
                f"⚡ {actor_name}({actor_type})のターン開始 (HP: {event.actor_info.current_hp}/{event.actor_info.max_hp})"
            )


class EnhancedTurnExecutedHandler(EventHandler[TurnExecutedEvent]):
    """改善されたターン実行ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: TurnExecutedEvent):
        """ターン実行イベントを処理"""
        # アクター情報を取得
        actor_info = None
        for participant in event.all_participants_after:
            if (participant.entity_id == event.actor_id and 
                participant.participant_type == event.participant_type):
                actor_info = participant
                break
        
        if not actor_info:
            # フォールバック: 基本情報を構築
            from src.domain.battle.events.battle_events import ParticipantInfo
            from src.domain.battle.battle_enum import Race, Element
            actor_info = ParticipantInfo(
                entity_id=event.actor_id,
                participant_type=event.participant_type,
                name=f"参加者{event.actor_id}",
                race=Race.HUMAN,
                element=Element.NONE,
                current_hp=0, max_hp=0,
                current_mp=0, max_mp=0,
                attack=0, defense=0, speed=0,
                is_defending=False, can_act=True
            )
        
        action_result = UIActionResult(
            actor_info=actor_info,
            action_info=event.action_info,
            target_results=event.target_results,
            status_effects_applied=event.applied_status_effects,
            buffs_applied=event.applied_buffs,
            participants_after=event.all_participants_after,
            messages=event.messages,
            success=event.success
        )
        
        self._ui_notifier.add_action_result(action_result)
        
        # 戦闘状態を更新
        current_state = self._ui_notifier.get_current_state()
        if current_state:
            current_state.participants = event.all_participants_after
            self._ui_notifier.update_battle_state(current_state)
        
        # メッセージを追加
        for message in event.messages:
            self._ui_notifier.add_battle_message(message)
        
        # アクション結果の詳細をログに追加
        if event.action_info:
            action_name = event.action_info.name
            total_damage = sum(result.damage_dealt for result in event.target_results)
            total_healing = sum(result.healing_done for result in event.target_results)
            
            if total_damage > 0:
                self._ui_notifier.add_battle_message(
                    f"💥 {action_name}: {total_damage}ダメージ!"
                )
            if total_healing > 0:
                self._ui_notifier.add_battle_message(
                    f"💚 {action_name}: {total_healing}回復!"
                )


class EnhancedTurnEndedHandler(EventHandler[TurnEndedEvent]):
    """改善されたターン終了ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: TurnEndedEvent):
        """ターン終了イベントを処理"""
        # 戦闘状態を更新
        current_state = self._ui_notifier.get_current_state()
        if current_state:
            current_state.participants = event.all_participants_after
            self._ui_notifier.update_battle_state(current_state)
        
        # 状態異常の発動結果をログに追加
        for trigger in event.status_effect_triggers:
            participant = next(
                (p for p in event.all_participants_after 
                 if p.entity_id == trigger.target_id and p.participant_type == trigger.target_participant_type),
                None
            )
            if participant:
                if trigger.damage_or_healing > 0:
                    self._ui_notifier.add_battle_message(
                        f"✨ {participant.name}は{trigger.effect_type.value}により{trigger.damage_or_healing}回復"
                    )
                elif trigger.damage_or_healing < 0:
                    self._ui_notifier.add_battle_message(
                        f"💀 {participant.name}は{trigger.effect_type.value}により{abs(trigger.damage_or_healing)}ダメージ"
                    )
        
        # 期限切れ効果をログに追加
        for entity_id, participant_type, effect_type in event.expired_status_effects:
            participant = next(
                (p for p in event.all_participants_after 
                 if p.entity_id == entity_id and p.participant_type == participant_type),
                None
            )
            if participant:
                self._ui_notifier.add_battle_message(
                    f"⏰ {participant.name}の{effect_type.value}が解除されました"
                )
        
        # 撃破チェック
        if event.is_actor_defeated and event.actor_info_after:
            actor_type = "プレイヤー" if event.participant_type == ParticipantType.PLAYER else "モンスター"
            self._ui_notifier.add_battle_message(
                f"💀 {event.actor_info_after.name}({actor_type})が撃破されました"
            )


class EnhancedBattleEndedHandler(EventHandler[BattleEndedEvent]):
    """改善された戦闘終了ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: BattleEndedEvent):
        """戦闘終了イベントを処理"""
        result_data = {
            "battle_id": event.battle_id,
            "result_type": event.result_type,
            "winner_ids": event.winner_ids,
            "total_turns": event.total_turns,
            "total_rounds": event.total_rounds,
            "rewards": event.total_rewards,
            "contribution_scores": event.contribution_scores
        }
        
        self._ui_notifier.end_battle(result_data)
        
        # 結果メッセージ
        if event.result_type.value == "VICTORY":
            self._ui_notifier.add_battle_message("🎉 戦闘勝利！")
        elif event.result_type.value == "DEFEAT":
            self._ui_notifier.add_battle_message("💀 戦闘敗北...")
        else:
            self._ui_notifier.add_battle_message("🤝 戦闘引き分け")
        
        # 統計情報
        self._ui_notifier.add_battle_message(
            f"📊 戦闘統計: {event.total_rounds}ラウンド, {event.total_turns}ターン"
        )


class EnhancedMonsterDefeatedHandler(EventHandler[MonsterDefeatedEvent]):
    """改善されたモンスター撃破ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: MonsterDefeatedEvent):
        """モンスター撃破イベントを処理"""
        monster_name = event.final_monster_info.name if event.final_monster_info else f"モンスター{event.monster_id}"
        
        self._ui_notifier.add_battle_message(
            f"🏆 {monster_name}を撃破！"
        )
        
        # ドロップ報酬の表示
        if event.drop_reward and (event.drop_reward.gold > 0 or event.drop_reward.exp > 0):
            rewards = []
            if event.drop_reward.gold > 0:
                rewards.append(f"ゴールド{event.drop_reward.gold}")
            if event.drop_reward.exp > 0:
                rewards.append(f"経験値{event.drop_reward.exp}")
            
            if rewards:
                self._ui_notifier.add_battle_message(
                    f"💰 報酬: {', '.join(rewards)}"
                )


class EnhancedPlayerDefeatedHandler(EventHandler[PlayerDefeatedEvent]):
    """改善されたプレイヤー撃破ハンドラー"""
    
    def __init__(self, ui_notifier: UIBattleNotifier):
        self._ui_notifier = ui_notifier
    
    def handle(self, event: PlayerDefeatedEvent):
        """プレイヤー撃破イベントを処理"""
        player_name = event.final_player_info.name if event.final_player_info else f"プレイヤー{event.player_id}"
        
        self._ui_notifier.add_battle_message(
            f"💀 {player_name}が戦闘不能になりました"
        )
