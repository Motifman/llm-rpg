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


@dataclass
class TurnAction:
    """ターン行動情報"""
    actor_id: str  # エージェントIDまたはモンスターID
    action_type: TurnActionType
    target_id: Optional[str] = None  # 攻撃対象のID
    damage: int = 0
    success: bool = True
    message: str = ""


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
        
        if isinstance(action, AttackMonster):
            return self._execute_attack(agent, self.monster)
        elif isinstance(action, DefendBattle):
            return self._execute_defend(agent)
        elif isinstance(action, EscapeBattle):
            return self._execute_escape(agent)
        else:
            raise ValueError(f"不明な戦闘行動: {action}")
    
    def _execute_attack(self, attacker: Agent, target: Monster) -> TurnAction:
        """攻撃行動を実行"""
        damage = max(1, attacker.get_attack() - target.defense)
        target.take_damage(damage)
        
        action = TurnAction(
            actor_id=attacker.agent_id,
            action_type=TurnActionType.ATTACK,
            target_id=target.monster_id,
            damage=damage,
            message=f"{attacker.name} が {target.name} に {damage} のダメージを与えた"
        )
        
        self.log_message(action.message)
        
        # モンスターが倒された場合
        if not target.is_alive:
            self.log_message(f"{target.name} を倒した！")
            self.state = BattleState.FINISHED
        
        return action
    
    def _execute_defend(self, defender: Agent) -> TurnAction:
        """防御行動を実行"""
        # TODO: 防御効果の実装（ダメージ軽減など）
        action = TurnAction(
            actor_id=defender.agent_id,
            action_type=TurnActionType.DEFEND,
            message=f"{defender.name} は身を守っている"
        )
        
        self.log_message(action.message)
        return action
    
    def _execute_escape(self, escaper: Agent) -> TurnAction:
        """逃走行動を実行"""
        # TODO: 逃走成功率の計算
        escape_success = random.random() < 0.8  # 80%の成功率
        
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
        """モンスターのターンを実行"""
        if self.state != BattleState.ACTIVE or not self.monster.is_alive:
            raise ValueError("モンスターは行動できません")
        
        if not self.participants:
            # 参加者がいない場合は何もしない
            return TurnAction(
                actor_id=self.monster.monster_id,
                action_type=TurnActionType.MONSTER_ACTION,
                message=f"{self.monster.name} は様子を見ている"
            )
        
        # 固定パターンで行動決定
        monster_action = self.monster.get_battle_action()
        
        if monster_action == "attack":
            # ランダムなエージェントを攻撃
            target_agent = random.choice(list(self.participants.values()))
            return self._execute_monster_attack(target_agent)
        else:
            # 防御
            return self._execute_monster_defend()
    
    def _execute_monster_attack(self, target: Agent) -> TurnAction:
        """モンスターの攻撃を実行"""
        damage = max(1, self.monster.attack - target.get_defense())
        new_hp = target.current_hp - damage
        target.set_hp(new_hp)
        
        action = TurnAction(
            actor_id=self.monster.monster_id,
            action_type=TurnActionType.MONSTER_ACTION,
            target_id=target.agent_id,
            damage=damage,
            message=f"{self.monster.name} が {target.name} に {damage} のダメージを与えた"
        )
        
        self.log_message(action.message)
        
        # エージェントが倒された場合
        if not target.is_alive():
            self.log_message(f"{target.name} は倒れてしまった...")
            # TODO: エージェントの戦闘不能処理
        
        return action
    
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
        """ターンを進める"""
        if self.state == BattleState.ACTIVE and self.turn_order:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            if self.current_turn_index == 0:
                self.current_turn += 1
    
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