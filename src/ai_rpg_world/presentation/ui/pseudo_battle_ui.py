"""
擬似的な戦闘UI
コンソールベースで戦闘画面を模擬的に表示
実際のWebUIやGUIの代替として動作
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time
from ai_rpg_world.domain.common.value_object import Gold, Exp
from ai_rpg_world.application.combat.handlers.enhanced_ui_battle_handler import (
    UIBattleState, UIActionResult, ParticipantInfo
)
from ai_rpg_world.domain.battle.battle_enum import ParticipantType, BattleResultType


class PseudoBattleUI:
    """擬似的な戦闘UI"""
    
    def __init__(self):
        self._current_state: Optional[UIBattleState] = None
        self._battle_log: List[str] = []
        self._display_enabled = True
        self._animation_delay = 0.5  # アニメーション遅延（秒）
    
    def set_display_enabled(self, enabled: bool):
        """表示の有効/無効を設定"""
        self._display_enabled = enabled
    
    def set_animation_delay(self, delay: float):
        """アニメーション遅延を設定"""
        self._animation_delay = delay
    
    def handle_ui_update(self, update_type: str, data: Any):
        """UI更新を処理（UIBattleNotifierからのコールバック）"""
        if not self._display_enabled:
            return
        
        if update_type == "battle_state":
            self._handle_battle_state_update(data)
        elif update_type == "action_result":
            self._handle_action_result(data)
        elif update_type == "message":
            self._handle_message(data)
        elif update_type == "battle_end":
            self._handle_battle_end(data)
    
    def _handle_battle_state_update(self, battle_state: UIBattleState):
        """戦闘状態更新を処理"""
        self._current_state = battle_state
        self._refresh_display()
    
    def _handle_action_result(self, action_result: UIActionResult):
        """アクション結果を処理"""
        if self._current_state:
            self._current_state.participants = action_result.participants_after
        self._show_action_animation(action_result)
        self._refresh_display()
    
    def _handle_message(self, message: str):
        """メッセージを処理"""
        self._battle_log.append(message)
        if len(self._battle_log) > 20:  # ログの最大行数制限
            self._battle_log = self._battle_log[-20:]
        self._refresh_display()
    
    def _handle_battle_end(self, result_data: Dict[str, Any]):
        """戦闘終了を処理"""
        self._show_battle_result(result_data)
        if self._current_state:
            self._current_state.is_battle_active = False
        self._refresh_display()
    
    def _refresh_display(self):
        """画面を再描画"""
        if not self._display_enabled or not self._current_state:
            return
        
        # 画面クリア（簡易版）
        print("\n" * 2)
        print("=" * 80)
        
        # ヘッダー表示
        self._display_header()
        
        # 参加者ステータス表示
        self._display_participants()
        
        # ターン情報表示
        self._display_turn_info()
        
        # バトルログ表示
        self._display_battle_log()
        
        print("=" * 80)
    
    def _display_header(self):
        """ヘッダー情報を表示"""
        if not self._current_state:
            return
        
        status = "進行中" if self._current_state.is_battle_active else "終了"
        print(f"🎮 戦闘画面 (Battle ID: {self._current_state.battle_id}) - {status}")
        print(f"📅 ラウンド {self._current_state.round_number} / ターン {self._current_state.turn_number}")
        print("-" * 80)
    
    def _display_participants(self):
        """参加者情報を表示"""
        if not self._current_state or not self._current_state.participants:
            return
        
        print("👥 参加者ステータス:")
        
        # プレイヤーを先に表示
        players = [p for p in self._current_state.participants if p.participant_type == ParticipantType.PLAYER]
        monsters = [p for p in self._current_state.participants if p.participant_type == ParticipantType.MONSTER]
        
        for player in players:
            self._display_participant_status(player, "👤")
        
        for monster in monsters:
            self._display_participant_status(monster, "👹")
        
        print()
    
    def _display_participant_status(self, participant: ParticipantInfo, icon: str):
        """個別参加者のステータスを表示"""
        # 現在のアクターかどうかをチェック
        is_current_actor = (
            self._current_state and
            participant.entity_id == self._current_state.current_actor_id and
            participant.participant_type == self._current_state.current_actor_type
        )
        
        # 名前とアクター表示
        name_display = f"{icon} {participant.name}"
        if is_current_actor:
            name_display += " ⚡"
        
        # HPバーの表示
        hp_percentage = participant.current_hp / max(participant.max_hp, 1)
        hp_bar_length = 20
        filled_length = int(hp_bar_length * hp_percentage)
        hp_bar = "█" * filled_length + "░" * (hp_bar_length - filled_length)
        
        # MPバーの表示
        mp_percentage = participant.current_mp / max(participant.max_mp, 1)
        mp_bar_length = 10
        filled_mp_length = int(mp_bar_length * mp_percentage)
        mp_bar = "█" * filled_mp_length + "░" * (mp_bar_length - filled_mp_length)
        
        # ステータス表示
        print(f"  {name_display}")
        print(f"    HP: {hp_bar} {participant.current_hp}/{participant.max_hp}")
        print(f"    MP: {mp_bar} {participant.current_mp}/{participant.max_mp}")
        print(f"    ATK:{participant.attack:3d} DEF:{participant.defense:3d} SPD:{participant.speed:3d}")
        
        # 状態異常・バフ表示
        status_icons = []
        if participant.status_effects:
            for effect_type, duration in participant.status_effects.items():
                status_icons.append(f"{effect_type.value}({duration})")
        if participant.buffs:
            for buff_type, (multiplier, duration) in participant.buffs.items():
                status_icons.append(f"{buff_type.value}x{multiplier:.1f}({duration})")
        if participant.is_defending:
            status_icons.append("🛡️防御")
        if not participant.can_act:
            status_icons.append("😵行動不能")
        
        if status_icons:
            print(f"    状態: {' '.join(status_icons)}")
        
        print()
    
    def _display_turn_info(self):
        """ターン情報を表示"""
        if not self._current_state:
            return
        
        print("🎯 ターン情報:")
        
        if self._current_state.current_actor_id is not None:
            actor = next(
                (p for p in self._current_state.participants 
                 if p.entity_id == self._current_state.current_actor_id and 
                    p.participant_type == self._current_state.current_actor_type),
                None
            )
            if actor:
                actor_type = "プレイヤー" if actor.participant_type == ParticipantType.PLAYER else "モンスター"
                print(f"  現在のアクター: {actor.name} ({actor_type})")
            else:
                print(f"  現在のアクター: ID {self._current_state.current_actor_id}")
        
        # ターン順序表示
        if self._current_state.turn_order:
            turn_order_display = []
            for i, (participant_type, entity_id) in enumerate(self._current_state.turn_order):
                participant = next(
                    (p for p in self._current_state.participants 
                     if p.entity_id == entity_id and p.participant_type == participant_type),
                    None
                )
                name = participant.name if participant else f"ID{entity_id}"
                if (entity_id == self._current_state.current_actor_id and 
                    participant_type == self._current_state.current_actor_type):
                    name = f"[{name}]"  # 現在のアクターを括弧で囲む
                turn_order_display.append(name)
            
            print(f"  ターン順序: {' → '.join(turn_order_display)}")
        
        print()
    
    def _display_battle_log(self):
        """バトルログを表示"""
        print("📜 バトルログ:")
        if self._battle_log:
            # 最新の10件を表示
            recent_logs = self._battle_log[-10:]
            for log in recent_logs:
                print(f"  {log}")
        else:
            print("  (ログなし)")
        print()
    
    def _show_action_animation(self, action_result: UIActionResult):
        """アクション結果のアニメーション表示"""
        if not self._display_enabled:
            return
        
        # アクション実行の表示
        if action_result.action_info:
            print(f"\n💥 {action_result.actor_info.name} が {action_result.action_info.name} を使用！")
        
        # ターゲットへの効果表示
        for target_result in action_result.target_results:
            target = next(
                (p for p in action_result.participants_after 
                 if p.entity_id == target_result.target_id and 
                    p.participant_type == target_result.target_participant_type),
                None
            )
            target_name = target.name if target else f"ID{target_result.target_id}"
            
            effects = []
            if target_result.damage_dealt > 0:
                crit_text = " (クリティカル!)" if target_result.was_critical else ""
                effects.append(f"{target_result.damage_dealt}ダメージ{crit_text}")
            if target_result.healing_done > 0:
                effects.append(f"{target_result.healing_done}回復")
            if target_result.was_evaded:
                effects.append("回避!")
            if target_result.was_blocked:
                effects.append("ブロック!")
            
            if effects:
                print(f"    → {target_name}: {', '.join(effects)}")
        
        # 状態異常・バフ適用の表示
        for effect_app in action_result.status_effects_applied:
            target = next(
                (p for p in action_result.participants_after 
                 if p.entity_id == effect_app.target_id and 
                    p.participant_type == effect_app.target_participant_type),
                None
            )
            target_name = target.name if target else f"ID{effect_app.target_id}"
            print(f"    → {target_name}に{effect_app.effect_type.value}を付与 ({effect_app.duration}ターン)")
        
        for buff_app in action_result.buffs_applied:
            target = next(
                (p for p in action_result.participants_after 
                 if p.entity_id == buff_app.target_id and 
                    p.participant_type == buff_app.target_participant_type),
                None
            )
            target_name = target.name if target else f"ID{buff_app.target_id}"
            print(f"    → {target_name}に{buff_app.buff_type.value}バフを付与 (x{buff_app.multiplier:.1f}, {buff_app.duration}ターン)")
        
        # アニメーション遅延
        if self._animation_delay > 0:
            time.sleep(self._animation_delay)
    
    def _show_battle_result(self, result_data: Dict[str, Any]):
        """戦闘結果を表示"""
        print("\n" + "=" * 80)
        print("🏆 戦闘結果")
        print("=" * 80)
        
        # 結果表示
        result_type = result_data.get("result_type")
        
        if result_type == BattleResultType.VICTORY:
            print("🎉 勝利！")
        elif result_type == BattleResultType.DEFEAT:
            print("💀 敗北...")
        elif result_type == BattleResultType.DRAW:
            print("🤝 引き分け")
        else:
            print("🤝 不明な結果")
        
        # 統計情報
        print(f"📊 戦闘統計:")
        print(f"  ラウンド数: {result_data.get('total_rounds', 0)}")
        print(f"  ターン数: {result_data.get('total_turns', 0)}")
        
        # 貢献度スコア
        contribution_scores = result_data.get("contribution_scores", {})
        if contribution_scores:
            print(f"🏅 貢献度スコア:")
            for player_id, score in contribution_scores.items():
                print(f"  プレイヤー{player_id}: {score}")
        
        # 報酬
        rewards = result_data.get("rewards")
        if rewards:
            print(f"💰 報酬:")
            if hasattr(rewards, 'gold') and rewards.gold > Gold(0):
                print(f"  ゴールド: {rewards.gold.value}")
            if hasattr(rewards, 'exp') and rewards.exp > Exp(0):
                print(f"  経験値: {rewards.exp.value}")
            if hasattr(rewards, 'items') and rewards.items:
                print(f"  アイテム:")
                for item in rewards.items:
                    print(f"    - {item.item.name} x{item.quantity}")
            if hasattr(rewards, 'information') and rewards.information:
                print(f"  情報:")
                for info in rewards.information:
                    print(f"    - {info}")
        
        print("=" * 80)
        
        # 結果表示の遅延
        if self._animation_delay > 0:
            time.sleep(self._animation_delay * 2)
    
    def show_initial_screen(self):
        """初期画面を表示"""
        if self._display_enabled:
            print("\n" * 3)
            print("=" * 80)
            print("🎮 戦闘システム - 擬似UI")
            print("=" * 80)
            print("戦闘開始を待機中...")
            print("=" * 80)
    
    def show_final_screen(self):
        """最終画面を表示"""
        if self._display_enabled:
            print("\n" + "=" * 80)
            print("🎮 戦闘システム終了")
            print("=" * 80)
            print("デモを終了します。")
            print("=" * 80)


class BattleUIManager:
    """戦闘UI管理クラス"""
    
    def __init__(self):
        self.ui = PseudoBattleUI()
        self._is_initialized = False
    
    def initialize(self, ui_notifier):
        """UI通知システムと連携を初期化"""
        if not self._is_initialized:
            ui_notifier.register_ui_callback(self.ui.handle_ui_update)
            self.ui.show_initial_screen()
            self._is_initialized = True
    
    def configure_display(self, enabled: bool = True, animation_delay: float = 0.5):
        """表示設定を構成"""
        self.ui.set_display_enabled(enabled)
        self.ui.set_animation_delay(animation_delay)
    
    def finalize(self):
        """UI終了処理"""
        if self._is_initialized:
            self.ui.show_final_screen()
            self._is_initialized = False
