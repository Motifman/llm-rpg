import random
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from game.enums import BattleState, TurnActionType, StatusEffectType
from game.monster.monster import MonsterDropReward, Monster
from game.battle.battle_data import TurnAction, BattleResult, BattleEvent, BattleEventLog
from game.battle.battle_effect_manager import BattleEffectManager
from game.battle.battle_effects import BattleContext
from game.player.player import Player
from game.battle.contribution_data import PlayerContribution, DistributedReward


class Battle:
    """戦闘管理クラス"""
    DEFAULT_EVASION_RATE = 0.05
    DEFAULT_CRITICAL_RATE = 0.05
    DEFAULT_ESCAPE_CHANCE = 0.4
    DEFAULT_ESCAPE_SPEED_BONUS = 0.02
    DEFAULT_CRITICAL_HIT_MULTIPLIER = 1.5
    DEFAULT_DEFENSE_DAMAGE_REDUCTION = 0.5  # 防御状態時のダメージ軽減率（50%）
    
    def __init__(self, battle_id: str, spot_id: str, monsters: List[Monster]):
        self.battle_id = battle_id
        self.spot_id = spot_id
        self.monsters: Dict[str, Monster] = {monster.monster_id: monster for monster in monsters}
        self.participants: Dict[str, Player] = {}
        self.state = BattleState.ACTIVE
        self.current_turn = 1
        self.created_at = datetime.now()
        
        # イベントログシステム
        self.event_log = BattleEventLog()
        self.event_counter = 0
        
        # ターン順序を管理
        self.turn_order: List[str] = []  # プレイヤーIDとモンスターIDの順序
        self.current_turn_index = 0
        
        # 貢献度追跡システム
        self.player_contributions: Dict[str, PlayerContribution] = {}
        self.battle_start_time = datetime.now()
        
    def _initialize_player_contribution(self, player_id: str):
        """プレイヤーの貢献度を初期化"""
        if player_id not in self.player_contributions:
            self.player_contributions[player_id] = PlayerContribution(player_id=player_id)
    
    def _update_player_contribution(self, player_id: str, **kwargs):
        """プレイヤーの貢献度を更新"""
        if player_id not in self.player_contributions:
            self._initialize_player_contribution(player_id)
        
        contribution = self.player_contributions[player_id]
        for key, value in kwargs.items():
            if hasattr(contribution, key):
                current_value = getattr(contribution, key)
                if isinstance(current_value, (int, float)):
                    setattr(contribution, key, current_value + value)
                else:
                    setattr(contribution, key, value)
        
    def _create_battle_event(self, event_type: str, actor_id: str, message: str, 
                           target_id: Optional[str] = None, action_type: Optional[TurnActionType] = None,
                           damage: int = 0, success: bool = True, critical: bool = False,
                           evaded: bool = False, counter_attack: bool = False,
                           status_effects_applied: List = None, structured_data: Dict = None) -> BattleEvent:
        """戦闘イベントを作成"""
        self.event_counter += 1
        event_id = f"{self.battle_id}_event_{self.event_counter:04d}"
        
        if status_effects_applied is None:
            status_effects_applied = []
        if structured_data is None:
            structured_data = {}
        
        event = BattleEvent(
            event_id=event_id,
            timestamp=datetime.now(),
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            action_type=action_type,
            damage=damage,
            success=success,
            critical=critical,
            evaded=evaded,
            counter_attack=counter_attack,
            status_effects_applied=status_effects_applied,
            message=message,
            structured_data=structured_data
        )
        
        self.event_log.add_event(event)
        return event
        
    def add_participant(self, player: Player):
        """戦闘に参加者を追加"""
        if self.state != BattleState.ACTIVE:
            raise ValueError("戦闘が終了しているため参加できません")
        
        self.participants[player.player_id] = player
        
        # 貢献度を初期化
        self._initialize_player_contribution(player.player_id)
        
        # イベントログに記録
        self._create_battle_event(
            event_type="player_joined",
            actor_id=player.player_id,
            message=f"{player.name} が戦闘に参加しました"
        )
        
        # ターン順序を再計算
        self._recalculate_turn_order()
    
    def remove_participant(self, player_id: str):
        """参加者を戦闘から削除"""
        if player_id in self.participants:
            player = self.participants[player_id]
            del self.participants[player_id]
            
            # イベントログに記録
            self._create_battle_event(
                event_type="player_left",
                actor_id=player_id,
                message=f"{player.name} が戦闘から離脱しました"
            )
            
            # ターン順序を再計算
            self._recalculate_turn_order()
            
            # 参加者がいなくなった場合は戦闘終了
            if not self.participants:
                self.state = BattleState.ESCAPED
                self._create_battle_event(
                    event_type="battle_state_change",
                    actor_id="system",
                    message="全プレイヤーが離脱したため戦闘が終了しました"
                )
    
    def _recalculate_turn_order(self):
        """素早さに基づいてターン順序を再計算"""
        # プレイヤーとモンスターをまとめて素早さ順にソート
        all_actors = []
        
        # プレイヤーを追加（生存している場合のみ）
        for player in self.participants.values():
            if player.is_alive():
                all_actors.append((player.get_player_id(), player.get_speed(), "player"))
        
        # モンスターを追加（生存している場合のみ）
        for monster in self.monsters.values():
            if monster.is_alive():
                all_actors.append((monster.get_monster_id(), monster.get_speed(), "monster"))
        
        # 素早さでソート（降順）
        all_actors.sort(key=lambda x: x[1], reverse=True)
        
        old_turn_order = self.turn_order.copy() if self.turn_order else []
        self.turn_order = [actor[0] for actor in all_actors]
        
        # 現在のターンインデックスを調整
        if self.turn_order:
            # 現在のアクターが新しい順序に存在する場合は維持
            current_actor = None
            if self.current_turn_index < len(self.turn_order):
                current_actor = self.turn_order[self.current_turn_index]
            
            if current_actor and current_actor in self.turn_order:
                self.current_turn_index = self.turn_order.index(current_actor)
            else:
                # 存在しない場合は0にリセット
                self.current_turn_index = 0
        else:
            self.current_turn_index = 0
    
    def get_current_actor(self) -> Optional[str]:
        """現在のターンのアクターIDを取得"""
        if not self.turn_order or self.state != BattleState.ACTIVE:
            return None
        if self.current_turn_index >= len(self.turn_order):
            return None
        return self.turn_order[self.current_turn_index]
    
    def is_player_turn(self) -> bool:
        """現在がプレイヤーのターンかどうか"""
        current_actor = self.get_current_actor()
        return current_actor in self.participants
    
    def is_monster_turn(self) -> bool:
        """現在がモンスターのターンかどうか"""
        current_actor = self.get_current_actor()
        return current_actor in self.monsters
    
    def get_current_monster(self) -> Optional[Monster]:
        """現在のターンのモンスターを取得"""
        current_actor = self.get_current_actor()
        if current_actor and current_actor in self.monsters:
            return self.monsters[current_actor]
        return None
    
    def execute_player_action(self, player_id: str, target_monster_id: Optional[str], action: TurnActionType) -> TurnAction:
        """プレイヤーの行動を実行"""
        if self.state != BattleState.ACTIVE:
            raise ValueError("戦闘が終了しています")
        
        if player_id not in self.participants:
            raise ValueError("戦闘に参加していないプレイヤーです")
        
        if self.get_current_actor() != player_id:
            raise ValueError("現在はこのプレイヤーのターンではありません")
        
        player = self.participants[player_id]
        
        # 状態異常チェック
        if not self._can_player_act(player):
            event = self._create_battle_event(
                event_type="status_effect",
                actor_id=player_id,
                action_type=TurnActionType.STATUS_EFFECT,
                success=False,
                message=f"{player.get_name()} は行動できない状態です"
            )
            return TurnAction(
                actor_id=player_id,
                action_type=TurnActionType.STATUS_EFFECT,
                success=False,
                message=event.message
            )
        
        if action == TurnActionType.ATTACK:
            # 攻撃対象のモンスターを取得
            if not target_monster_id:
                event = self._create_battle_event(
                    event_type="player_action",
                    actor_id=player_id,
                    action_type=TurnActionType.ATTACK,
                    success=False,
                    message=f"攻撃対象のモンスターが指定されていません"
                )
                return TurnAction(
                    actor_id=player_id,
                    action_type=TurnActionType.ATTACK,
                    success=False,
                    message=event.message
                )
            
            target_monster = self.monsters.get(target_monster_id)
            if not target_monster:
                event = self._create_battle_event(
                    event_type="player_action",
                    actor_id=player_id,
                    action_type=TurnActionType.ATTACK,
                    success=False,
                    message=f"攻撃対象のモンスターが見つかりません"
                )
                return TurnAction(
                    actor_id=player_id,
                    action_type=TurnActionType.ATTACK,
                    success=False,
                    message=event.message
                )
            return self._execute_attack(player, target_monster)
        elif action == TurnActionType.DEFEND:
            return self._execute_defend(player)
        elif action == TurnActionType.ESCAPE:
            return self._execute_escape(player)
        else:
            raise ValueError(f"不明な戦闘行動: {action}")
    
    def _can_player_act(self, player: Player) -> bool:
        """プレイヤーが行動可能かチェック"""
        # 麻痺、睡眠の場合は行動不可
        if (player.has_status_condition(StatusEffectType.PARALYSIS) or 
            player.has_status_condition(StatusEffectType.SLEEP)):
            return False
        
        return player.is_alive()
    
    def _execute_attack(self, attacker: Player, target: Monster) -> TurnAction:
        """攻撃行動を実行（BattleEffectManager使用版）"""
        # 混乱チェック
        if self._is_confused_attack(attacker):
            return self._execute_confused_attack(attacker)
        
        # 回避チェック
        if self._check_evasion(target):
            event = self._create_battle_event(
                event_type="player_action",
                actor_id=attacker.player_id,
                action_type=TurnActionType.ATTACK,
                target_id=target.monster_id,
                damage=0,
                success=True,
                evaded=True,
                message=f"{target.get_name()} が攻撃を回避した！"
            )
            return TurnAction(
                actor_id=attacker.player_id,
                action_type=TurnActionType.ATTACK,
                target_id=target.monster_id,
                damage=0,
                success=True,
                evaded=True,
                message=event.message
            )
        
        # 基本ダメージ計算
        base_damage = self._calculate_attack_damage(attacker, target)
        
        # クリティカルチェック
        is_critical = self._check_critical_hit(attacker)
        if is_critical:
            base_damage = int(base_damage * self.DEFAULT_CRITICAL_HIT_MULTIPLIER)
        
        # BattleEffectManagerを使用した効果適用
        effect_manager = self._create_attack_effect_manager(attacker)
        context = BattleContext(
            attacker=attacker,
            target=target,
            is_critical=is_critical
        )
        
        # 攻撃効果を適用
        attack_result = effect_manager.apply_attack_effects(context, base_damage)
        final_damage = attack_result.final_damage
        
        # 防御状態によるダメージ軽減処理
        defense_reduction_applied = False
        if target.is_defending():
            original_damage = final_damage
            final_damage = int(final_damage * (1 - self.DEFAULT_DEFENSE_DAMAGE_REDUCTION))
            defense_reduction_applied = True
            
            # 防御軽減のログを記録
            defense_event = self._create_battle_event(
                event_type="defense_reduction",
                actor_id=target.get_monster_id(),
                target_id=attacker.get_player_id(),
                damage=original_damage - final_damage,
                message=f"{target.get_name()} の防御によりダメージを {original_damage - final_damage} 軽減した！",
                structured_data={
                    "original_damage": original_damage,
                    "reduced_damage": original_damage - final_damage,
                    "final_damage": final_damage,
                    "defense_reduction_rate": self.DEFAULT_DEFENSE_DAMAGE_REDUCTION
                }
            )
        
        # ダメージを適用
        target.take_damage(final_damage)
        
        # 貢献度を更新
        self._update_player_contribution(
            attacker.player_id,
            total_damage_dealt=final_damage,
            successful_attacks=1,
            critical_hits=1 if is_critical else 0,
            status_effects_applied=len(attack_result.status_effects)
        )
        
        # メッセージを作成
        effect_messages = attack_result.messages.copy()
        if defense_reduction_applied:
            effect_messages.append(f"防御によりダメージ軽減")
        
        message = self._create_attack_message_with_effects(
            attacker, target, final_damage, is_critical, 
            attack_result.status_effects, effect_messages
        )
        
        # イベントログに記録
        event = self._create_battle_event(
            event_type="player_action",
            actor_id=attacker.player_id,
            action_type=TurnActionType.ATTACK,
            target_id=target.monster_id,
            damage=final_damage,
            critical=is_critical,
            status_effects_applied=attack_result.status_effects,
            message=message,
            structured_data={
                "attacker_name": attacker.name,
                "target_name": target.name,
                "base_damage": base_damage,
                "final_damage": final_damage,
                "is_critical": is_critical,
                "effect_messages": attack_result.messages
            }
        )
        
        action = TurnAction(
            actor_id=attacker.player_id,
            action_type=TurnActionType.ATTACK,
            target_id=target.monster_id,
            damage=final_damage,
            critical=is_critical,
            status_effects_applied=attack_result.status_effects,
            message=event.message
        )
        
        # モンスターが倒された場合
        if not target.is_alive():
            defeat_event = self._create_battle_event(
                event_type="monster_defeated",
                actor_id=target.monster_id,
                message=f"{target.get_name()} を倒した！"
            )
            # 全モンスターが倒されたかチェック
            if self._are_all_monsters_defeated():
                self.state = BattleState.FINISHED
                self._create_battle_event(
                    event_type="battle_state_change",
                    actor_id="system",
                    message="全モンスターを倒した！戦闘に勝利した！"
                )
        
        return action
    
    def _is_confused_attack(self, attacker: Player) -> bool:
        """混乱による誤攻撃チェック"""
        return attacker.has_status_condition(StatusEffectType.CONFUSION)
    
    def _execute_confused_attack(self, attacker: Player) -> TurnAction:
        """混乱時の攻撃（味方攻撃）"""
        # 混乱時は自分自身にダメージ
        confusion_damage = max(1, attacker.get_attack() // 4)
        attacker.set_hp(attacker.current_hp - confusion_damage)
        
        event = self._create_battle_event(
            event_type="player_action",
            actor_id=attacker.player_id,
            action_type=TurnActionType.ATTACK,
            damage=confusion_damage,
            success=True,
            message=f"{attacker.get_name()} は混乱して自分を攻撃してしまった！ {confusion_damage} のダメージ",
            structured_data={
                "confusion_damage": confusion_damage,
                "is_confused_attack": True
            }
        )
        
        return TurnAction(
            actor_id=attacker.player_id,
            action_type=TurnActionType.ATTACK,
            damage=confusion_damage,
            success=True,
            message=event.message
        )
    
    def _check_evasion(self, target: Union[Monster, Player]) -> bool:
        """回避チェック"""
        # 簡単な回避判定（将来的に拡張可能）
        if hasattr(target, 'get_evasion_rate'):
            evasion_chance = target.get_evasion_rate()
        else:
            evasion_chance = self.DEFAULT_EVASION_RATE
        return random.random() < evasion_chance
    
    def _check_critical_hit(self, attacker: Union[Monster, Player]) -> bool:
        """クリティカルヒットチェック"""
        if hasattr(attacker, 'get_critical_rate'):
            critical_chance = attacker.get_critical_rate()
        else:
            critical_chance = self.DEFAULT_CRITICAL_RATE
        return random.random() < critical_chance
    
    def _calculate_attack_damage(self, attacker: Union[Monster, Player], target: Union[Monster, Player]) -> int:
        """攻撃ダメージを計算（基本値のみ）"""
        # 基本ダメージ計算（武器効果はBattleEffectManagerで処理）
        base_damage = max(1, attacker.get_attack() - target.get_defense())
        return base_damage
    
    def _execute_defend(self, defender: Player) -> TurnAction:
        """防御行動を実行"""
        # 防御状態を設定（次のターンのダメージ軽減）
        defender.set_defending(True)
        
        # 貢献度を更新
        self._update_player_contribution(
            defender.player_id,
            successful_defenses=1
        )
        
        event = self._create_battle_event(
            event_type="player_action",
            actor_id=defender.player_id,
            action_type=TurnActionType.DEFEND,
            success=True,
            message=f"{defender.get_name()} は防御の構えを取った",
            structured_data={
                "defender_name": defender.name,
                "is_defending": True
            }
        )
        
        action = TurnAction(
            actor_id=defender.player_id,
            action_type=TurnActionType.DEFEND,
            success=True,
            message=event.message
        )
        
        return action
    
    def _execute_escape(self, player: Player) -> TurnAction:
        """逃走行動を実行"""
        # 逃走成功率計算（素早さに基づく）
        escape_chance = self.DEFAULT_ESCAPE_CHANCE + (player.get_speed() * self.DEFAULT_ESCAPE_SPEED_BONUS)  # 50% + 素早さ補正
        escape_success = random.random() < escape_chance
        
        if escape_success:
            self.remove_participant(player.get_player_id())
            event = self._create_battle_event(
                event_type="player_action",
                actor_id=player.get_player_id(),
                action_type=TurnActionType.ESCAPE,
                success=True,
                message=f"{player.get_name()} は逃走に成功した",
                structured_data={
                    "escape_success": True,
                    "escape_chance": escape_chance
                }
            )
            action = TurnAction(
                actor_id=player.get_player_id(),
                action_type=TurnActionType.ESCAPE,
                success=True,
                message=event.message
            )
        else:
            event = self._create_battle_event(
                event_type="player_action",
                actor_id=player.get_player_id(),
                action_type=TurnActionType.ESCAPE,
                success=False,
                message=f"{player.get_name()} は逃走に失敗した",
                structured_data={
                    "escape_success": False,
                    "escape_chance": escape_chance
                }
            )
            action = TurnAction(
                actor_id=player.get_player_id(),
                action_type=TurnActionType.ESCAPE,
                success=False,
                message=event.message
            )
        
        return action
    
    def execute_monster_turn(self) -> TurnAction:
        """モンスターのターンを実行（拡張版）"""
        if self.state != BattleState.ACTIVE:
            raise ValueError("戦闘が終了しています")
        
        current_monster = self.get_current_monster()
        if not current_monster:
            event = self._create_battle_event(
                event_type="monster_action",
                actor_id="unknown",
                action_type=TurnActionType.STATUS_EFFECT,
                message="モンスターが見つかりません"
            )
            return TurnAction(
                actor_id="unknown",
                action_type=TurnActionType.STATUS_EFFECT,
                message=event.message
            )
        
        # モンスターが死亡している場合
        if not current_monster.is_alive():
            event = self._create_battle_event(
                event_type="monster_action",
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.STATUS_EFFECT,
                message=f"{current_monster.get_name()} は既に倒されている"
            )
            return TurnAction(
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.STATUS_EFFECT,
                message=event.message
            )
        
        # 状態異常チェック
        if not current_monster.can_act():
            event = self._create_battle_event(
                event_type="monster_action",
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.STATUS_EFFECT,
                message=f"{current_monster.get_name()} は行動できない状態です"
            )
            return TurnAction(
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.STATUS_EFFECT,
                message=event.message
            )
        
        if not self.participants:
            # 参加者がいない場合は何もしない
            event = self._create_battle_event(
                event_type="monster_action",
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.MONSTER_ACTION,
                message=f"{current_monster.get_name()} は様子を見ている"
            )
            return TurnAction(
                actor_id=current_monster.monster_id,
                action_type=TurnActionType.MONSTER_ACTION,
                message=event.message
            )
        
        # 混乱チェック
        if current_monster.is_confused():
            return self._execute_confused_monster_action(current_monster)
        
        # 行動決定
        monster_action = current_monster.get_battle_action()
        
        if monster_action == "attack":
            # ランダムなプレイヤーを攻撃
            target_player = random.choice(list(self.participants.values()))
            return self._execute_monster_attack(current_monster, target_player)
        else:
            # 防御
            return self._execute_monster_defend(current_monster)
    
    def _execute_confused_monster_action(self, monster: Monster) -> TurnAction:
        """混乱時のモンスター行動"""
        # 混乱時は自分にダメージ
        confusion_damage = max(1, monster.get_attack() // 4)
        monster.take_damage(confusion_damage)
        
        event = self._create_battle_event(
            event_type="monster_action",
            actor_id=monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            damage=confusion_damage,
            message=f"{monster.get_name()} は混乱して自分を攻撃してしまった！ {confusion_damage} のダメージ",
            structured_data={
                "confusion_damage": confusion_damage,
                "is_confused_attack": True
            }
        )
        
        return TurnAction(
            actor_id=monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            damage=confusion_damage,
            message=event.message
        )
    
    def _execute_monster_attack(self, monster: Monster, target: Player) -> TurnAction:
        """モンスターの攻撃を実行（BattleEffectManager使用版）"""
        # 回避チェック
        if self._check_evasion(target):
            event = self._create_battle_event(
                event_type="monster_action",
                actor_id=monster.get_monster_id(),
                action_type=TurnActionType.MONSTER_ACTION,
                target_id=target.get_player_id(),
                damage=0,
                evaded=True,
                message=f"{target.get_name()} が {monster.get_name()} の攻撃を回避した！"
            )
            return TurnAction(
                actor_id=monster.get_monster_id(),
                action_type=TurnActionType.MONSTER_ACTION,
                target_id=target.get_player_id(),
                damage=0,
                evaded=True,
                message=event.message
            )
        
        base_damage = self._calculate_attack_damage(monster, target)
        
        # BattleEffectManagerを使用した防具効果適用
        effect_manager = self._create_defense_effect_manager(target)
        context = BattleContext(
            attacker=monster,
            target=target,
            is_critical=False
        )
        
        # 防御効果を適用
        defense_result = effect_manager.apply_defense_effects(context, base_damage)
        final_damage = defense_result.final_damage
        
        # 防御状態によるダメージ軽減処理
        defense_reduction_applied = False
        if target.is_defending():
            original_damage = final_damage
            final_damage = int(final_damage * (1 - self.DEFAULT_DEFENSE_DAMAGE_REDUCTION))
            defense_reduction_applied = True
            
            # 防御軽減のログを記録
            defense_event = self._create_battle_event(
                event_type="defense_reduction",
                actor_id=target.get_player_id(),
                target_id=monster.get_monster_id(),
                damage=original_damage - final_damage,
                message=f"{target.get_name()} の防御によりダメージを {original_damage - final_damage} 軽減した！",
                structured_data={
                    "original_damage": original_damage,
                    "reduced_damage": original_damage - final_damage,
                    "final_damage": final_damage,
                    "defense_reduction_rate": self.DEFAULT_DEFENSE_DAMAGE_REDUCTION
                }
            )
        
        # ダメージを適用
        target.take_damage(final_damage)
        
        # 貢献度を更新（受けたダメージ）
        self._update_player_contribution(
            target.get_player_id(),
            total_damage_taken=final_damage
        )
        
        # メッセージを作成
        effect_messages = defense_result.messages.copy()
        if defense_reduction_applied:
            effect_messages.append(f"防御によりダメージ軽減")
        
        message = self._create_monster_attack_message_with_effects(
            monster, target, final_damage, effect_messages
        )
        
        # イベントログに記録
        event = self._create_battle_event(
            event_type="monster_action",
            actor_id=monster.get_monster_id(),
            action_type=TurnActionType.MONSTER_ACTION,
            target_id=target.get_player_id(),
            damage=final_damage,
            message=message,
            structured_data={
                "monster_name": monster.get_name(),
                "target_name": target.get_name(),
                "base_damage": base_damage,
                "final_damage": final_damage,
                "effect_messages": defense_result.messages
            }
        )
        
        action = TurnAction(
            actor_id=monster.get_monster_id(),
            action_type=TurnActionType.MONSTER_ACTION,
            target_id=target.get_player_id(),
            damage=final_damage,
            message=event.message
        )
        
        # 反撃ダメージがある場合
        if defense_result.counter_damage > 0:
            monster.take_damage(defense_result.counter_damage)
            action.counter_attack = True
            
            # 反撃の貢献度を更新
            self._update_player_contribution(
                target.get_player_id(),
                total_damage_dealt=defense_result.counter_damage,
                counter_attacks=1
            )
            
            counter_event = self._create_battle_event(
                event_type="counter_attack",
                actor_id=target.get_player_id(),
                target_id=monster.get_monster_id(),
                damage=defense_result.counter_damage,
                message=f"{target.get_name()} の反撃！ {monster.get_name()} に {defense_result.counter_damage} のダメージ",
                structured_data={
                    "counter_damage": defense_result.counter_damage,
                    "counter_attacker": target.get_name(),
                    "counter_target": monster.get_name()
                }
            )
            action.message += f" {counter_event.message}"
        
        # プレイヤーが倒された場合
        if not target.is_alive():
            defeat_event = self._create_battle_event(
                event_type="player_defeated",
                actor_id=target.get_player_id(),
                message=f"{target.get_name()} は力尽きた..."
            )
            # 全プレイヤーが倒されたかチェック
            if self._are_all_players_defeated():
                self.state = BattleState.FINISHED
                self._create_battle_event(
                    event_type="battle_state_change",
                    actor_id="system",
                    message="全プレイヤーが倒された！戦闘に敗北した..."
                )
        
        return action
    
    def _create_attack_effect_manager(self, attacker: Player) -> BattleEffectManager:
        """攻撃用のBattleEffectManagerを作成"""
        effect_manager = BattleEffectManager()
        
        # 武器から効果を作成
        weapon = attacker.get_equipped_weapon()
        if weapon:
            weapon_effects = effect_manager.create_weapon_effects_from_weapon(weapon)
            for effect in weapon_effects:
                effect_manager.add_weapon_effect(effect)
        
        return effect_manager
    
    def _create_defense_effect_manager(self, defender: Player) -> BattleEffectManager:
        """防御用のBattleEffectManagerを作成"""
        effect_manager = BattleEffectManager()
        
        # 防具から効果を作成
        armors = defender.equipment.get_equipped_armors()
        for armor in armors:
            armor_effects = effect_manager.create_armor_effects_from_armor(armor)
            for effect in armor_effects:
                effect_manager.add_armor_effect(effect)
        
        return effect_manager
    
    def _create_attack_message_with_effects(self, attacker: Player, target: Monster, 
                                          damage: int, is_critical: bool, 
                                          status_effects: List, effect_messages: List[str]) -> str:
        """効果付きの攻撃メッセージを作成"""
        base_message = f"{attacker.get_name()} の攻撃！ {target.get_name()} に {damage} のダメージ"
        
        if is_critical:
            base_message += " (クリティカル！)"
        
        if status_effects:
            effect_names = [str(effect) for effect in status_effects]
            base_message += f" 状態異常: {', '.join(effect_names)}"
        
        if effect_messages:
            base_message += f" {' / '.join(effect_messages)}"
        
        return base_message
    
    def _create_monster_attack_message_with_effects(self, monster: Monster, target: Player,
                                                  damage: int, effect_messages: List[str]) -> str:
        """効果付きのモンスター攻撃メッセージを作成"""
        base_message = f"{monster.get_name()} の攻撃！ {target.get_name()} に {damage} のダメージ"
        
        if effect_messages:
            base_message += f" {' / '.join(effect_messages)}"
        
        return base_message
    
    def _execute_monster_defend(self, monster: Monster) -> TurnAction:
        """モンスターの防御を実行"""
        # モンスターの防御状態を設定
        monster.set_defending(True)
        
        event = self._create_battle_event(
            event_type="monster_action",
            actor_id=monster.get_monster_id(),
            action_type=TurnActionType.MONSTER_ACTION,
            message=f"{monster.get_name()} は防御の構えを取った",
            structured_data={
                "monster_name": monster.get_name(),
                "is_defending": True
            }
        )
        
        return TurnAction(
            actor_id=monster.get_monster_id(),
            action_type=TurnActionType.MONSTER_ACTION,
            message=event.message
        )
    
    def advance_turn(self):
        """ターンを進める"""
        if self.state != BattleState.ACTIVE:
            return
        
        # 現在のアクターのターンが終了
        self.current_turn_index += 1
        
        # 全アクターのターンが終了したら次のターン
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn += 1
            self.current_turn_index = 0
            
            # ターン開始時の状態異常処理
            self._process_all_status_effects()
            
            # 参加者の貢献度を更新（参加ターン数）
            for player_id in self.participants.keys():
                self._update_player_contribution(player_id, turns_participated=1)
        
        # ターン順序を再計算（死亡したアクターを除外）
        self._recalculate_turn_order()
        
        # 現在のアクターが存在しない場合は次のアクターに進む
        while (self.current_turn_index < len(self.turn_order) and 
               self.get_current_actor() is None):
            self.current_turn_index += 1
    
    def _process_all_status_effects(self):
        """全アクターの状態異常を処理"""
        # プレイヤーの状態異常処理と防御状態解除
        for player in self.participants.values():
            player.process_status_effects()
            # 防御状態を解除
            if player.is_defending():
                player.set_defending(False)
        
        # モンスターの状態異常処理と防御状態解除
        for monster in self.monsters.values():
            monster.process_status_effects()
            # 防御状態を解除
            if monster.is_defending():
                monster.set_defending(False)
    
    def _are_all_monsters_defeated(self) -> bool:
        """全モンスターが倒されているかチェック"""
        return all(not monster.is_alive() for monster in self.monsters.values())
    
    def _are_all_players_defeated(self) -> bool:
        """全プレイヤーが倒されているかチェック"""
        return all(not player.is_alive() for player in self.participants.values())
    
    def is_battle_finished(self) -> bool:
        """戦闘が終了しているかどうか"""
        return (self.state != BattleState.ACTIVE or 
                self._are_all_monsters_defeated() or 
                self._are_all_players_defeated())
    
    def check_battle_end_conditions(self) -> Dict[str, Any]:
        """戦闘終了条件を詳細にチェック"""
        conditions = {
            "is_finished": False,
            "end_reason": None,
            "victory": False,
            "defeated": False,
            "escaped": False,
            "details": {}
        }
        
        # 戦闘状態のチェック
        if self.state != BattleState.ACTIVE:
            conditions["is_finished"] = True
            if self.state == BattleState.FINISHED:
                conditions["end_reason"] = "battle_finished"
                conditions["victory"] = True
            elif self.state == BattleState.ESCAPED:
                conditions["end_reason"] = "escaped"
                conditions["escaped"] = True
            return conditions
        
        # 全モンスターが倒されているかチェック
        all_monsters_defeated = self._are_all_monsters_defeated()
        if all_monsters_defeated:
            conditions["is_finished"] = True
            conditions["end_reason"] = "monsters_defeated"
            conditions["victory"] = True
            conditions["details"]["defeated_monsters"] = [
                monster.get_name() for monster in self.monsters.values() 
                if not monster.is_alive()
            ]
            return conditions
        
        # 全プレイヤーが倒されているかチェック
        all_players_defeated = self._are_all_players_defeated()
        if all_players_defeated:
            conditions["is_finished"] = True
            conditions["end_reason"] = "players_defeated"
            conditions["defeated"] = True
            conditions["details"]["defeated_players"] = [
                player.get_name() for player in self.participants.values() 
                if not player.is_alive()
            ]
            return conditions
        
        # 参加者がいない場合
        if not self.participants:
            conditions["is_finished"] = True
            conditions["end_reason"] = "no_participants"
            conditions["escaped"] = True
            return conditions
        
        # 生存しているモンスターがいない場合
        alive_monsters = [monster for monster in self.monsters.values() if monster.is_alive()]
        if not alive_monsters:
            conditions["is_finished"] = True
            conditions["end_reason"] = "no_alive_monsters"
            conditions["victory"] = True
            return conditions
        
        return conditions
    
    def get_battle_end_status(self) -> str:
        """戦闘終了状況の文字列を取得"""
        conditions = self.check_battle_end_conditions()
        
        if not conditions["is_finished"]:
            return "戦闘継続中"
        
        if conditions["victory"]:
            if conditions["end_reason"] == "monsters_defeated":
                return "勝利: 全モンスターを倒した"
            elif conditions["end_reason"] == "no_alive_monsters":
                return "勝利: 生存しているモンスターがいない"
            else:
                return "勝利"
        elif conditions["defeated"]:
            return "敗北: 全プレイヤーが倒された"
        elif conditions["escaped"]:
            return "逃走: 全プレイヤーが離脱した"
        else:
            return "戦闘終了"
    
    def get_battle_result(self) -> BattleResult:
        """戦闘結果を取得"""
        if self.state == BattleState.FINISHED:
            # 勝利の場合
            defeated_monsters = [monster for monster in self.monsters.values() if not monster.is_alive()]
            total_rewards = self._calculate_total_rewards(defeated_monsters)
            distributed_rewards = self._calculate_contribution_based_rewards(total_rewards)
            
            return BattleResult(
                victory=True,
                participants=list(self.participants.keys()),
                defeated_monsters=defeated_monsters,
                total_rewards=total_rewards,
                distributed_rewards=distributed_rewards,
                event_log=self.event_log
            )
        elif self.state == BattleState.ESCAPED:
            # 逃走の場合
            return BattleResult(
                victory=False,
                participants=list(self.participants.keys()),
                escaped=True,
                event_log=self.event_log
            )
        else:
            # まだ戦闘中
            return BattleResult(
                victory=False,
                participants=list(self.participants.keys()),
                event_log=self.event_log
            )
    
    def get_unread_events_for_player(self, player_id: str) -> List[BattleEvent]:
        """プレイヤーの未読イベントを取得"""
        return self.event_log.get_unread_events_for_player(player_id)
    
    def mark_events_as_read_for_player(self, player_id: str):
        """プレイヤーの既読位置を更新"""
        self.event_log.mark_events_as_read(player_id)
    
    def get_llm_context_for_player(self, player_id: str) -> str:
        """LLM用のコンテキスト文字列を生成"""
        return self.event_log.get_llm_context_for_player(player_id)
    
    def get_structured_context_for_player(self, player_id: str) -> Dict[str, Any]:
        """LLM用の構造化コンテキストを生成"""
        return self.event_log.get_structured_context_for_player(player_id)
    
    def get_battle_status_for_llm(self, player_id: str) -> Dict[str, Any]:
        """LLM用の戦闘状況を取得"""
        # 現在の戦闘状況
        current_actor = self.get_current_actor()
        is_player_turn = self.is_player_turn()
        is_monster_turn = self.is_monster_turn()
        
        # プレイヤー情報
        players_info = []
        for player in self.participants.values():
            players_info.append({
                "player_id": player.get_player_id(),
                "name": player.get_name(),
                "current_hp": player.get_hp(),
                "max_hp": player.get_max_hp(),
                "is_alive": player.is_alive(),
                "is_current_turn": current_actor == player.player_id
            })
        
        # モンスター情報
        monsters_info = []
        for monster in self.monsters.values():
            monsters_info.append({
                "monster_id": monster.get_monster_id(),
                "name": monster.get_name(),
                "current_hp": monster.get_hp(),
                "max_hp": monster.get_max_hp(),
                "is_alive": monster.is_alive(),
                "is_current_turn": current_actor == monster.get_monster_id()
            })
        
        return {
            "battle_id": self.battle_id,
            "current_turn": self.current_turn,
            "current_actor": current_actor,
            "is_player_turn": is_player_turn,
            "is_monster_turn": is_monster_turn,
            "battle_state": self.state.value,
            "players": players_info,
            "monsters": monsters_info,
            "unread_events_count": len(self.get_unread_events_for_player(player_id))
        }
    
    def _calculate_total_rewards(self, defeated_monsters: List[Monster]) -> MonsterDropReward:
        """倒されたモンスターの合計報酬を計算"""
        total_reward = MonsterDropReward()
        
        for monster in defeated_monsters:
            if monster.drop_reward:
                total_reward.money += monster.drop_reward.money
                total_reward.experience += monster.drop_reward.experience
                total_reward.items.extend(monster.drop_reward.items)
                total_reward.information.extend(monster.drop_reward.information)
        
        return total_reward
    
    def _calculate_contribution_based_rewards(self, total_rewards: MonsterDropReward) -> Dict[str, DistributedReward]:
        """貢献度に基づいて報酬を分配"""
        if not self.player_contributions:
            return {}
        
        # 各プレイヤーの貢献度スコアを計算
        contribution_scores = {}
        total_score = 0.0
        
        for player_id, contribution in self.player_contributions.items():
            score = contribution.calculate_contribution_score()
            contribution_scores[player_id] = score
            total_score += score
        
        # 貢献度に基づく分配率を計算
        distribution_ratios = {}
        for player_id, score in contribution_scores.items():
            if total_score > 0:
                distribution_ratios[player_id] = score / total_score
            else:
                distribution_ratios[player_id] = 1.0 / len(contribution_scores)
        
        # 各プレイヤーに報酬を分配
        distributed_rewards = {}
        
        for player_id, ratio in distribution_ratios.items():
            # moneyとexpは比例分配
            money_share = int(total_rewards.money * ratio)
            exp_share = int(total_rewards.experience * ratio)
            
            # itemsは内容はランダムで個数は比例分配
            item_count = max(1, int(len(total_rewards.items) * ratio))
            if total_rewards.items:
                # ランダムにアイテムを選択
                selected_items = random.sample(total_rewards.items, min(item_count, len(total_rewards.items)))
            else:
                selected_items = []
            
            # informationは全員に渡す
            information_share = total_rewards.information.copy()
            
            distributed_rewards[player_id] = DistributedReward(
                player_id=player_id,
                money=money_share,
                experience=exp_share,
                items=selected_items,
                information=information_share,
                contribution_score=contribution_scores[player_id],
                contribution_percentage=ratio * 100
            )
        
        return distributed_rewards
    
    def log_message(self, message: str):
        """戦闘ログにメッセージを追加"""
        # イベントログに記録（システムメッセージとして）
        self._create_battle_event(
            event_type="system_message",
            actor_id="system",
            message=message
        )
    
    def get_participants(self) -> List[Player]:
        """参加者リストを取得"""
        return list(self.participants.values())
    
    def get_battle_status(self) -> str:
        """戦闘状況の要約を取得"""
        status = f"戦闘ID: {self.battle_id}\n"
        status += f"場所: {self.spot_id}\n"
        status += f"ターン: {self.current_turn}\n"
        status += f"モンスター: {len(self.monsters)}体\n"
        
        for monster in self.monsters.values():
            status += f"  - {monster.name} ({monster.get_status_summary()})\n"
        
        status += f"参加者: {len(self.participants)}人\n"
        
        for player in self.participants.values():
            status += f"  - {player.name} ({player.get_status_summary()})\n"
        
        return status


class BattleManager:
    """戦闘管理システム"""
    
    def __init__(self):
        self.battles: Dict[str, Battle] = {}
        self.battle_counter = 0
        self.spot_battles: Dict[str, str] = {}  # spot_id -> battle_id
    
    def start_battle(self, spot_id: str, monsters: List[Monster], player: Player) -> str:
        """戦闘を開始（複数モンスター対応）"""
        # 既にそのスポットで戦闘が進行中の場合はエラー
        if spot_id in self.spot_battles:
            raise ValueError(f"スポット {spot_id} では既に戦闘が進行中です")
        
        # モンスターが存在しない場合はエラー
        if not monsters:
            raise ValueError("戦闘対象のモンスターが存在しません")
        
        # 新しい戦闘を作成
        self.battle_counter += 1
        battle_id = f"battle_{self.battle_counter:04d}"
        
        battle = Battle(battle_id, spot_id, monsters)
        battle.add_participant(player)
        
        self.battles[battle_id] = battle
        self.spot_battles[spot_id] = battle_id
        
        monster_names = ", ".join([monster.name for monster in monsters])
        battle._create_battle_event(
            event_type="battle_start",
            actor_id="system",
            message=f"戦闘開始！ {player.name} vs {monster_names}"
        )
        
        return battle_id
    
    def join_battle(self, battle_id: str, player: Player):
        """戦闘に参加"""
        if battle_id not in self.battles:
            raise ValueError(f"戦闘 {battle_id} が見つかりません")
        
        battle = self.battles[battle_id]
        battle.add_participant(player)
    
    def get_battle(self, battle_id: str) -> Optional[Battle]:
        """戦闘を取得"""
        return self.battles.get(battle_id)
    
    def get_battle_by_spot(self, spot_id: str) -> Optional[Battle]:
        """スポットの戦闘を取得"""
        battle_id = self.spot_battles.get(spot_id)
        if battle_id:
            return self.battles.get(battle_id)
        return None
    
    def finish_battle(self, battle_id: str) -> BattleResult:
        """戦闘を終了"""
        if battle_id not in self.battles:
            raise ValueError(f"戦闘 {battle_id} が見つかりません")
        
        battle = self.battles[battle_id]
        result = battle.get_battle_result()
        
        # 戦闘を削除
        del self.battles[battle_id]
        
        # スポットの戦闘情報を削除
        spot_id = battle.spot_id
        if spot_id in self.spot_battles and self.spot_battles[spot_id] == battle_id:
            del self.spot_battles[spot_id]
        
        return result
    
    def get_active_battles(self) -> List[Battle]:
        """進行中の戦闘リストを取得"""
        return [battle for battle in self.battles.values() if not battle.is_battle_finished()]
    
    def cleanup_finished_battles(self):
        """終了した戦闘をクリーンアップし、参加プレイヤーに報酬を分配"""
        finished_battle_ids = []
        for battle_id, battle in self.battles.items():
            if battle.is_battle_finished():
                finished_battle_ids.append(battle_id)
        
        for battle_id in finished_battle_ids:
            battle = self.battles[battle_id]
            
            # 戦闘結果を取得
            battle_result = battle.get_battle_result()
            
            # 勝利の場合、参加プレイヤーに報酬を分配
            if battle_result.result_type == "victory":
                try:
                    # 貢献度ベースの報酬計算
                    distributed_rewards = battle._calculate_contribution_based_rewards(battle_result.rewards)
                    
                    # 各プレイヤーに報酬を分配
                    for player_id, distributed_reward in distributed_rewards.items():
                        if player_id in battle.participants:
                            player = battle.participants[player_id]
                            
                            # 経験値とゴールドを追加
                            if distributed_reward.experience > 0:
                                player.add_experience(distributed_reward.experience)
                            
                            if distributed_reward.gold > 0:
                                player.add_gold(distributed_reward.gold)
                            
                            # アイテムを追加
                            for item in distributed_reward.items:
                                player.inventory.add_item(item)
                            
                            # 戦闘イベントログに報酬分配を記録
                            battle._create_battle_event(
                                event_type="reward_distribution",
                                actor_id="system",
                                message=f"{player.name} に報酬を分配しました (経験値: {distributed_reward.experience}, ゴールド: {distributed_reward.gold}, アイテム: {len(distributed_reward.items)}個)",
                                structured_data={
                                    "player_id": player_id,
                                    "experience": distributed_reward.experience,
                                    "gold": distributed_reward.gold,
                                    "items_count": len(distributed_reward.items)
                                }
                            )
                except Exception as e:
                    # 報酬分配でエラーが発生した場合も戦闘は終了させる
                    battle._create_battle_event(
                        event_type="reward_error",
                        actor_id="system",
                        message=f"報酬分配中にエラーが発生しました: {e}"
                    )
            
            # 戦闘を終了
            self.finish_battle(battle_id) 