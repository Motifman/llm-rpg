from typing import List, Dict, Any, Optional
from datetime import datetime
from .interactable import InteractableObject
from .agent import Agent
from .action import Interaction, InteractionType
from .reward import ActionReward
from .home import HomePermission


class Bed(InteractableObject):
    """
    ベッドクラス - 睡眠による体力回復機能
    
    所有者権限を持つエージェントのみが使用可能。
    睡眠により体力・魔力を全回復する。
    """
    
    def __init__(self, object_id: str, name: str = "ベッド", 
                 description: str = "快適そうなベッド。ゆっくりと休むことができそうだ。"):
        super().__init__(object_id, name, description)
        self.set_state("is_occupied", False)
        self.set_state("last_used_by", None)
        self.set_state("last_used_time", None)
    
    def can_interact(self, agent: Agent, interaction_type: InteractionType) -> bool:
        """相互作用の実行可否をチェック"""
        if interaction_type == InteractionType.USE:
            # ベッドが使用中でないことを確認
            return not self.get_state("is_occupied")
        elif interaction_type == InteractionType.EXAMINE:
            return True
        return False
    
    def get_available_interactions(self) -> List[Interaction]:
        """利用可能な相互作用のリストを取得"""
        interactions = []
        
        # 調べる（常に可能）
        interactions.append(Interaction(
            description="ベッドを調べる",
            object_id=self.object_id,
            interaction_type=InteractionType.EXAMINE,
            reward=ActionReward(information=["快適そうなベッドだ。所有者なら休むことができるだろう。"])
        ))
        
        # 睡眠（使用中でない場合）
        if not self.get_state("is_occupied"):
            interactions.append(Interaction(
                description="ベッドで休む",
                object_id=self.object_id,
                interaction_type=InteractionType.USE,
                state_changes={"is_occupied": True},
                reward=ActionReward(
                    information=["ゆっくりと眠った。体力と魔力が全回復した。"],
                    experience=5
                )
            ))
        
        return interactions
    
    def sleep(self, agent: Agent) -> bool:
        """睡眠を実行（体力・魔力全回復）"""
        if self.can_interact(agent, InteractionType.USE):
            # 体力・魔力を全回復
            agent.current_hp = agent.max_hp
            agent.current_mp = agent.max_mp
            
            # ベッドの状態を更新
            self.set_state("is_occupied", True)
            self.set_state("last_used_by", agent.agent_id)
            self.set_state("last_used_time", datetime.now().isoformat())
            
            return True
        return False
    
    def wake_up(self, agent: Agent) -> bool:
        """起床（ベッドを空ける）"""
        if (self.get_state("is_occupied") and 
            self.get_state("last_used_by") == agent.agent_id):
            self.set_state("is_occupied", False)
            return True
        return False


class Desk(InteractableObject):
    """
    机クラス - 日記の読み書き機能
    
    所有者権限を持つエージェントは日記を書くことができる。
    立ち入り権限以上を持つエージェントは日記を読むことができる。
    """
    
    def __init__(self, object_id: str, name: str = "机", 
                 description: str = "木製の机。日記や書類を書くのに適している。"):
        super().__init__(object_id, name, description)
        self.set_state("is_in_use", False)
        self.set_state("current_user", None)
    
    def can_interact(self, agent: Agent, interaction_type: InteractionType) -> bool:
        """相互作用の実行可否をチェック"""
        if interaction_type in [InteractionType.USE, InteractionType.READ]:
            return not self.get_state("is_in_use")
        elif interaction_type == InteractionType.EXAMINE:
            return True
        return False
    
    def get_available_interactions(self) -> List[Interaction]:
        """利用可能な相互作用のリストを取得"""
        interactions = []
        
        # 調べる（常に可能）
        interactions.append(Interaction(
            description="机を調べる",
            object_id=self.object_id,
            interaction_type=InteractionType.EXAMINE,
            reward=ActionReward(information=["きれいに整理された机だ。日記を書いたり読んだりできそうだ。"])
        ))
        
        # 使用中でない場合
        if not self.get_state("is_in_use"):
            # 日記を書く
            interactions.append(Interaction(
                description="日記を書く",
                object_id=self.object_id,
                interaction_type=InteractionType.USE,
                state_changes={"is_in_use": True},
                reward=ActionReward(
                    information=["机に向かって日記を書いた。"],
                    experience=3
                )
            ))
            
            # 日記を読む
            interactions.append(Interaction(
                description="日記を読む",
                object_id=self.object_id,
                interaction_type=InteractionType.READ,
                state_changes={"is_in_use": True},
                reward=ActionReward(
                    information=["過去の日記を読み返した。"],
                    experience=1
                )
            ))
        
        return interactions
    
    def start_writing(self, agent: Agent) -> bool:
        """日記の書き込みを開始"""
        if self.can_interact(agent, InteractionType.USE):
            self.set_state("is_in_use", True)
            self.set_state("current_user", agent.agent_id)
            return True
        return False
    
    def finish_writing(self, agent: Agent) -> bool:
        """日記の書き込みを終了"""
        if (self.get_state("is_in_use") and 
            self.get_state("current_user") == agent.agent_id):
            self.set_state("is_in_use", False)
            self.set_state("current_user", None)
            return True
        return False
    
    def start_reading(self, agent: Agent) -> bool:
        """日記の読み取りを開始"""
        if self.can_interact(agent, InteractionType.READ):
            self.set_state("is_in_use", True)
            self.set_state("current_user", agent.agent_id)
            return True
        return False
    
    def finish_reading(self, agent: Agent) -> bool:
        """日記の読み取りを終了"""
        if (self.get_state("is_in_use") and 
            self.get_state("current_user") == agent.agent_id):
            self.set_state("is_in_use", False)
            self.set_state("current_user", None)
            return True
        return False 