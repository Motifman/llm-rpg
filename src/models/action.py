from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from abc import ABC
from enum import Enum
from .reward import ActionReward


class InteractionType(Enum):
    """相互作用の種類"""
    OPEN = "open"      # 開ける（宝箱、ドアなど）
    USE = "use"        # 使う（アイテム、装置など）
    TALK = "talk"      # 話す（NPCなど）
    EXAMINE = "examine" # 調べる（詳細情報取得）
    TAKE = "take"      # 取る（アイテム収集）
    GIVE = "give"      # 渡す（アイテム供与）


@dataclass(frozen=True)
class Action(ABC):
    """行動の基底クラス"""
    description: str


@dataclass(frozen=True)
class Movement(Action):
    """移動行動"""
    direction: str
    target_spot_id: str


@dataclass(frozen=True)
class Exploration(Action):
    """探索行動"""
    # 互換性のための個別フィールド（将来的には削除予定）
    item_id: Optional[str] = None
    discovered_info: Optional[str] = None
    experience_points: Optional[int] = None
    money: Optional[int] = None
    
    # 新しい統一報酬システム
    reward: Optional[ActionReward] = None
    
    def get_unified_reward(self) -> ActionReward:
        """統一報酬形式で取得（互換性維持）"""
        if self.reward:
            return self.reward
        
        # 旧形式から新形式への変換
        items = [self.item_id] if self.item_id else []
        information = [self.discovered_info] if self.discovered_info else []
        
        return ActionReward(
            items=items,
            money=self.money or 0,
            experience=self.experience_points or 0,
            information=information
        )


@dataclass(frozen=True)
class Interaction(Action):
    """オブジェクトとの相互作用行動"""
    object_id: str
    interaction_type: InteractionType
    reward: ActionReward = field(default_factory=ActionReward)
    required_item_id: Optional[str] = None  # 必要アイテム（簡易条件）
    state_changes: Dict[str, Any] = field(default_factory=dict)  # オブジェクトの状態変化