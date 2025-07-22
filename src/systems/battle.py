from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import random

from ..models.agent import Agent
from ..models.monster import Monster, MonsterDropReward
from ..models.action import AttackMonster, DefendBattle, EscapeBattle


class BattleState(Enum):
    """戦闘状態"""
    ACTIVE = "active"       # 戦闘中
    FINISHED = "finished"   # 戦闘終了
    ESCAPED = "escaped"     # 逃走による終了


class TurnActionType(Enum):
    """ターン中の行動タイプ"""
    ATTACK = "attack"
    DEFEND = "defend"
    ESCAPE = "escape"
    MONSTER_ACTION = "monster_action"
    STATUS_EFFECT = "status_effect"


@dataclass
class TurnAction:
    """ターン行動情報"""
    actor_id: str  # エージェントIDまたはモンスターID
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
    participants: List[str]  # 参加エージェントID
    defeated_monster: Optional[Monster] = None
    rewards: Optional[MonsterDropReward] = None
    escaped: bool = False
    battle_log: List[str] = field(default_factory=list)


class Battle:
    """戦闘管理クラス"""
    
    def __init__(self, battle_id: str, spot_id: str, monster: Monster):
        self.battle_id = battle_id
        self.spot_id = spot_id
        self.monster = monster
        self.participants: Dict[str, Agent] = {}
        self.state = BattleState.ACTIVE
        self.current_turn = 1
        self.battle_log: List[str] = []
        self.created_at = datetime.now()
        
        # ターン順序を管理
        self.turn_order: List[str] = []  # エージェントIDとモンスターIDの順序
        self.current_turn_index = 0
        
    def add_participant(self, agent: Agent):
        """戦闘に参加者を追加"""
        if self.state != BattleState.ACTIVE:
            raise ValueError("戦闘が終了しているため参加できません")
        
        self.participants[agent.agent_id] = agent
        self.log_message(f"{agent.name} が戦闘に参加しました")
        
        # ターン順序を再計算
        self._recalculate_turn_order()
    
    def remove_participant(self, agent_id: str):
        """参加者を戦闘から削除"""
        if agent_id in self.participants:
            agent = self.participants[agent_id]
            del self.participants[agent_id]
            self.log_message(f"{agent.name} が戦闘から離脱しました")
            
            # ターン順序を再計算
            self._recalculate_turn_order()
            
            # 参加者がいなくなった場合は戦闘終了
            if not self.participants:
                self.state = BattleState.ESCAPED
    
    def _recalculate_turn_order(self):
        """素早さに基づいてターン順序を再計算"""
        # エージェントとモンスターをまとめて素早さ順にソート
        all_actors = []
        
        # エージェントを追加
        for agent in self.participants.values():
            all_actors.append((agent.agent_id, agent.get_speed(), "agent"))
        
        # モンスターを追加（生存している場合のみ）
        if self.monster.is_alive:
            all_actors.append((self.monster.monster_id, self.monster.speed, "monster"))
        
        # 素早さでソート（降順）
        all_actors.sort(key=lambda x: x[1], reverse=True)
        
        self.turn_order = [actor[0] for actor in all_actors]
        
        # 現在のターンインデックスを調整
        if self.turn_order:
            self.current_turn_index = self.current_turn_index % len(self.turn_order)
        else:
            self.current_turn_index = 0
    
    def get_current_actor(self) -> Optional[str]:
        """現在のターンのアクターIDを取得"""
        if not self.turn_order or self.state != BattleState.ACTIVE:
            return None
        return self.turn_order[self.current_turn_index]
    
    def is_agent_turn(self) -> bool:
        """現在がエージェントのターンかどうか"""
        current_actor = self.get_current_actor()
        return current_actor in self.participants
    
    def is_monster_turn(self) -> bool:
        """現在がモンスターのターンかどうか"""
        current_actor = self.get_current_actor()
        return current_actor == self.monster.monster_id
    
    def execute_agent_action(self, agent_id: str, action) -> TurnAction:
        """エージェントの行動を実行"""
        if self.state != BattleState.ACTIVE:
            raise ValueError("戦闘が終了しています")
        
        if agent_id not in self.participants:
            raise ValueError("戦闘に参加していないエージェントです")
        
        if self.get_current_actor() != agent_id:
            raise ValueError("現在はこのエージェントのターンではありません")
        
        agent = self.participants[agent_id]
        
        # 状態異常チェック
        if not self._can_agent_act(agent):
            return TurnAction(
                actor_id=agent_id,
                action_type=TurnActionType.STATUS_EFFECT,
                success=False,
                message=f"{agent.name} は行動できない状態です"
            )
        
        if isinstance(action, AttackMonster):
            return self._execute_attack(agent, self.monster)
        elif isinstance(action, DefendBattle):
            return self._execute_defend(agent)
        elif isinstance(action, EscapeBattle):
            return self._execute_escape(agent)
        else:
            raise ValueError(f"不明な戦闘行動: {action}")
    
    def _can_agent_act(self, agent: Agent) -> bool:
        """エージェントが行動可能かチェック"""
        from ..models.weapon import StatusEffect
        
        # 麻痺、睡眠の場合は行動不可
        if (agent.has_status_condition(StatusEffect.PARALYSIS) or 
            agent.has_status_condition(StatusEffect.SLEEP)):
            return False
        
        return agent.is_alive()
    
    def _execute_attack(self, attacker: Agent, target: Monster) -> TurnAction:
        """攻撃行動を実行（拡張版）"""
        # 混乱チェック
        if self._is_confused_attack(attacker):
            return self._execute_confused_attack(attacker)
        
        # 回避チェック
        if self._check_evasion(target):
            return TurnAction(
                actor_id=attacker.agent_id,
                action_type=TurnActionType.ATTACK,
                target_id=target.monster_id,
                damage=0,
                success=True,
                evaded=True,
                message=f"{target.name} が攻撃を回避した！"
            )
        
        # 基本ダメージ計算
        base_damage = self._calculate_attack_damage(attacker, target)
        
        # クリティカルチェック
        is_critical = self._check_critical_hit(attacker)
        if is_critical:
            base_damage = int(base_damage * 1.5)  # クリティカル倍率
        
        target.take_damage(base_damage)
        
        # 状態異常付与チェック
        applied_status_effects = self._apply_weapon_status_effects(attacker, target)
        
        action = TurnAction(
            actor_id=attacker.agent_id,
            action_type=TurnActionType.ATTACK,
            target_id=target.monster_id,
            damage=base_damage,
            critical=is_critical,
            status_effects_applied=applied_status_effects,
            message=self._create_attack_message(attacker, target, base_damage, is_critical, applied_status_effects)
        )
        
        self.log_message(action.message)
        
        # モンスターが倒された場合
        if not target.is_alive:
            self.log_message(f"{target.name} を倒した！")
            self.state = BattleState.FINISHED
        
        return action
    
    def _is_confused_attack(self, attacker: Agent) -> bool:
        """混乱による誤攻撃チェック"""
        from ..models.weapon import StatusEffect
        return attacker.has_status_condition(StatusEffect.CONFUSION)
    
    def _execute_confused_attack(self, attacker: Agent) -> TurnAction:
        """混乱時の攻撃（味方攻撃）"""
        # 混乱時は自分自身にダメージ
        confusion_damage = max(1, attacker.get_attack() // 4)
        attacker.set_hp(attacker.current_hp - confusion_damage)
        
        return TurnAction(
            actor_id=attacker.agent_id,
            action_type=TurnActionType.ATTACK,
            target_id=attacker.agent_id,
            damage=confusion_damage,
            message=f"{attacker.name} は混乱して自分を攻撃してしまった！ {confusion_damage} のダメージ"
        )
    
    def _check_evasion(self, target) -> bool:
        """回避チェック"""
        # モンスターの場合は基本回避率のみ
        if isinstance(target, Monster):
            base_evasion = 0.05  # 5%
            return random.random() < base_evasion
        
        # エージェントの場合は装備補正込み
        if isinstance(target, Agent):
            return random.random() < target.get_evasion_rate()
        
        return False
    
    def _check_critical_hit(self, attacker: Agent) -> bool:
        """クリティカルヒットチェック"""
        return random.random() < attacker.get_critical_rate()
    
    def _calculate_attack_damage(self, attacker: Agent, target: Monster) -> int:
        """攻撃ダメージ計算（武器効果込み）"""
        base_damage = max(1, attacker.get_attack() - target.defense)
        
        # 武器の特殊効果を適用
        weapon = attacker.equipment.weapon
        if weapon:
            # 種族特攻チェック
            weapon_damage = weapon.calculate_damage(attacker.base_attack, target.race)
            # 装備補正を考慮
            total_damage = weapon_damage + attacker.equipment.get_total_attack_bonus() - target.defense
            return max(1, total_damage)
        
        return base_damage
    
    def _apply_weapon_status_effects(self, attacker: Agent, target: Monster) -> List:
        """武器の状態異常効果を適用"""
        from ..models.weapon import StatusCondition
        applied_effects = []
        
        weapon = attacker.equipment.weapon
        if weapon and weapon.effect.status_effects and weapon.effect.status_chance > 0:
            if random.random() < weapon.effect.status_chance:
                for status_effect in weapon.effect.status_effects:
                    # 新しいStatusConditionを作成
                    condition = StatusCondition(
                        effect=status_effect.effect,
                        duration=status_effect.duration,
                        value=status_effect.value
                    )
                    target.add_status_condition(condition)
                    applied_effects.append(condition)
        
        return applied_effects
    
    def _create_attack_message(self, attacker: Agent, target: Monster, damage: int, is_critical: bool, status_effects: List) -> str:
        """攻撃メッセージの生成"""
        message = f"{attacker.name} が {target.name} に"
        
        if is_critical:
            message += " クリティカルヒットで"
        
        message += f" {damage} のダメージを与えた"
        
        if status_effects:
            effect_names = [str(effect) for effect in status_effects]
            message += f"！さらに {', '.join(effect_names)} を付与した"
        
        return message + "！"
    
    def _execute_defend(self, defender: Agent) -> TurnAction:
        """防御行動を実行（拡張版）"""
        # 防御時の効果（ダメージ軽減率上昇など）
        defend_bonus = 0.5  # 50%ダメージ軽減
        
        action = TurnAction(
            actor_id=defender.agent_id,
            action_type=TurnActionType.DEFEND,
            message=f"{defender.name} は身を守っている（ダメージ{defend_bonus:.0%}軽減）"
        )
        
        self.log_message(action.message)
        return action
    
    def _execute_escape(self, escaper: Agent) -> TurnAction:
        """逃走行動を実行"""
        # 逃走成功率の計算（素早さ差を考慮）
        escape_base_rate = 0.6
        speed_diff = escaper.get_speed() - self.monster.speed
        escape_rate = min(0.95, escape_base_rate + (speed_diff * 0.05))
        
        escape_success = random.random() < escape_rate
        
        if escape_success:
            self.remove_participant(escaper.agent_id)
            action = TurnAction(
                actor_id=escaper.agent_id,
                action_type=TurnActionType.ESCAPE,
                success=True,
                message=f"{escaper.name} は逃走に成功した"
            )
        else:
            action = TurnAction(
                actor_id=escaper.agent_id,
                action_type=TurnActionType.ESCAPE,
                success=False,
                message=f"{escaper.name} は逃走に失敗した"
            )
        
        self.log_message(action.message)
        return action
    
    def execute_monster_turn(self) -> TurnAction:
        """モンスターのターンを実行（拡張版）"""
        if self.state != BattleState.ACTIVE or not self.monster.is_alive:
            raise ValueError("モンスターは行動できません")
        
        # 状態異常チェック
        if not self.monster.can_act():
            return TurnAction(
                actor_id=self.monster.monster_id,
                action_type=TurnActionType.STATUS_EFFECT,
                message=f"{self.monster.name} は行動できない状態です"
            )
        
        if not self.participants:
            # 参加者がいない場合は何もしない
            return TurnAction(
                actor_id=self.monster.monster_id,
                action_type=TurnActionType.MONSTER_ACTION,
                message=f"{self.monster.name} は様子を見ている"
            )
        
        # 混乱チェック
        if self.monster.is_confused():
            return self._execute_confused_monster_action()
        
        # 行動決定
        monster_action = self.monster.get_battle_action()
        
        if monster_action == "attack":
            # ランダムなエージェントを攻撃
            target_agent = random.choice(list(self.participants.values()))
            return self._execute_monster_attack(target_agent)
        else:
            # 防御
            return self._execute_monster_defend()
    
    def _execute_confused_monster_action(self) -> TurnAction:
        """混乱時のモンスター行動"""
        # 混乱時は自分にダメージ
        confusion_damage = max(1, self.monster.attack // 4)
        self.monster.take_damage(confusion_damage)
        
        return TurnAction(
            actor_id=self.monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            damage=confusion_damage,
            message=f"{self.monster.name} は混乱して自分を攻撃してしまった！ {confusion_damage} のダメージ"
        )
    
    def _execute_monster_attack(self, target: Agent) -> TurnAction:
        """モンスターの攻撃を実行（拡張版）"""
        # 回避チェック
        if self._check_evasion(target):
            return TurnAction(
                actor_id=self.monster.monster_id,
                action_type=TurnActionType.MONSTER_ACTION,
                target_id=target.agent_id,
                damage=0,
                evaded=True,
                message=f"{target.name} が {self.monster.name} の攻撃を回避した！"
            )
        
        damage = max(1, self.monster.attack - target.get_defense())
        
        # 防具の特殊効果適用
        from ..models.weapon import DamageType
        damage = self._apply_armor_effects(target, damage, DamageType.PHYSICAL)
        
        target.set_hp(target.current_hp - damage)
        
        # 反撃チェック
        counter_action = self._check_counter_attack(target, self.monster)
        
        action = TurnAction(
            actor_id=self.monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            target_id=target.agent_id,
            damage=damage,
            counter_attack=counter_action is not None,
            message=f"{self.monster.name} が {target.name} に {damage} のダメージを与えた"
        )
        
        self.log_message(action.message)
        
        # 反撃処理
        if counter_action:
            self.log_message(counter_action)
        
        # エージェントが倒された場合
        if not target.is_alive():
            self.log_message(f"{target.name} は倒れてしまった...")
            # TODO: エージェントの戦闘不能処理
        
        return action
    
    def _apply_armor_effects(self, target: Agent, damage: int, damage_type) -> int:
        """防具効果を適用してダメージを計算"""
        from ..models.weapon import DamageType
        
        total_reduction = 0.0
        for armor in target.equipment.get_equipped_armors():
            total_reduction += armor.get_damage_reduction(damage_type)
        
        # ダメージ軽減を適用
        final_damage = damage * (1.0 - min(total_reduction, 0.8))  # 最大80%軽減
        return max(1, int(final_damage))
    
    def _check_counter_attack(self, defender: Agent, attacker: Monster) -> Optional[str]:
        """反撃チェック"""
        for armor in defender.equipment.get_equipped_armors():
            if armor.get_counter_chance() > 0 and random.random() < armor.get_counter_chance():
                counter_damage = armor.get_counter_damage()
                attacker.take_damage(counter_damage)
                
                message = f"{defender.name} の {armor.item_id} が反撃！ {attacker.name} に {counter_damage} のダメージ"
                
                if not attacker.is_alive:
                    message += f" {attacker.name} を倒した！"
                    self.state = BattleState.FINISHED
                
                return message
        
        return None
    
    def _execute_monster_defend(self) -> TurnAction:
        """モンスターの防御を実行"""
        action = TurnAction(
            actor_id=self.monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            message=f"{self.monster.name} は身を守っている"
        )
        
        self.log_message(action.message)
        return action
    
    def advance_turn(self):
        """ターンを進める（拡張版）"""
        # 状態異常の処理
        self._process_all_status_effects()
        
        if self.state == BattleState.ACTIVE and self.turn_order:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            if self.current_turn_index == 0:
                self.current_turn += 1
    
    def _process_all_status_effects(self):
        """全員の状態異常を処理"""
        # エージェントの状態異常処理
        for agent in self.participants.values():
            agent.process_status_effects()
        
        # モンスターの状態異常処理
        self.monster.process_status_effects()
    
    def is_battle_finished(self) -> bool:
        """戦闘が終了しているかどうか"""
        return self.state != BattleState.ACTIVE
    
    def get_battle_result(self) -> BattleResult:
        """戦闘結果を取得"""
        if self.state == BattleState.FINISHED:
            # 勝利の場合
            return BattleResult(
                victory=True,
                participants=list(self.participants.keys()),
                defeated_monster=self.monster,
                rewards=self.monster.drop_reward,
                battle_log=self.battle_log.copy()
            )
        elif self.state == BattleState.ESCAPED:
            # 逃走の場合
            return BattleResult(
                victory=False,
                participants=list(self.participants.keys()),
                escaped=True,
                battle_log=self.battle_log.copy()
            )
        else:
            # まだ戦闘中
            return BattleResult(
                victory=False,
                participants=list(self.participants.keys()),
                battle_log=self.battle_log.copy()
            )
    
    def log_message(self, message: str):
        """戦闘ログにメッセージを追加"""
        self.battle_log.append(f"ターン{self.current_turn}: {message}")
    
    def get_participants(self) -> List[Agent]:
        """参加者リストを取得"""
        return list(self.participants.values())
    
    def get_battle_status(self) -> str:
        """戦闘状況の要約を取得"""
        status = f"戦闘ID: {self.battle_id}\n"
        status += f"場所: {self.spot_id}\n"
        status += f"ターン: {self.current_turn}\n"
        status += f"モンスター: {self.monster.name} ({self.monster.get_status_summary()})\n"
        status += f"参加者: {len(self.participants)}人\n"
        
        for agent in self.participants.values():
            status += f"  - {agent.name} ({agent.get_status_summary()})\n"
        
        return status


class BattleManager:
    """戦闘管理システム"""
    
    def __init__(self):
        self.battles: Dict[str, Battle] = {}
        self.battle_counter = 0
        self.spot_battles: Dict[str, str] = {}  # spot_id -> battle_id
    
    def start_battle(self, spot_id: str, monster: Monster, initiator: Agent) -> str:
        """戦闘を開始"""
        # 既にそのスポットで戦闘が進行中の場合はエラー
        if spot_id in self.spot_battles:
            raise ValueError(f"スポット {spot_id} では既に戦闘が進行中です")
        
        # 新しい戦闘を作成
        self.battle_counter += 1
        battle_id = f"battle_{self.battle_counter:04d}"
        
        battle = Battle(battle_id, spot_id, monster)
        battle.add_participant(initiator)
        
        self.battles[battle_id] = battle
        self.spot_battles[spot_id] = battle_id
        
        battle.log_message(f"戦闘開始！ {initiator.name} vs {monster.name}")
        
        return battle_id
    
    def join_battle(self, battle_id: str, agent: Agent):
        """戦闘に参加"""
        if battle_id not in self.battles:
            raise ValueError(f"戦闘 {battle_id} が見つかりません")
        
        battle = self.battles[battle_id]
        battle.add_participant(agent)
    
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
        """終了した戦闘をクリーンアップ"""
        finished_battle_ids = []
        for battle_id, battle in self.battles.items():
            if battle.is_battle_finished():
                finished_battle_ids.append(battle_id)
        
        for battle_id in finished_battle_ids:
            self.finish_battle(battle_id) 