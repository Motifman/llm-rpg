from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from abc import ABC
from enum import Enum
from .reward import ActionReward

if TYPE_CHECKING:
    from .agent import Agent
    from .trade import TradeType


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


# === Spot依存の行動 ===

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


# === Agent依存の行動 ===

@dataclass(frozen=True)
class ItemUsage(Action):
    """アイテム使用行動（Agent依存）"""
    item_id: str
    count: int = 1  # 使用個数
    
    def is_valid(self, agent: "Agent") -> bool:
        """使用可能かチェック"""
        if not agent.has_item(self.item_id):
            return False
        
        item_count = agent.get_item_count(self.item_id)
        return item_count >= self.count
    
    def get_required_item_count(self) -> int:
        """必要なアイテム数を取得"""
        return self.count


@dataclass(frozen=True)
class PostTrade(Action):
    """取引出品行動（Agent依存）"""
    offered_item_id: str
    offered_item_count: int = 1
    requested_money: int = 0
    requested_item_id: Optional[str] = None
    requested_item_count: int = 1
    trade_type: Optional["TradeType"] = None
    target_agent_id: Optional[str] = None
    
    def get_trade_type(self) -> "TradeType":
        """取引タイプを取得（デフォルト値対応）"""
        if self.trade_type is None:
            from .trade import TradeType
            return TradeType.GLOBAL
        return self.trade_type
    
    def is_money_trade(self) -> bool:
        """お金との取引かどうか"""
        return self.requested_item_id is None and self.requested_money > 0
    
    def is_item_trade(self) -> bool:
        """アイテム同士の取引かどうか"""
        return self.requested_item_id is not None
    
    def is_valid(self, agent: "Agent") -> bool:
        """出品可能かチェック"""
        # 出品するアイテムを所持しているかチェック
        if not agent.has_item(self.offered_item_id):
            return False
        
        item_count = agent.get_item_count(self.offered_item_id)
        if item_count < self.offered_item_count:
            return False
        
        # 取引内容が有効かチェック
        if not self.is_money_trade() and not self.is_item_trade():
            return False  # お金もアイテムも要求していない
        
        return True


@dataclass(frozen=True)
class ViewTrades(Action):
    """取引閲覧行動（Agent依存）"""
    filter_offered_item_id: Optional[str] = None
    filter_requested_item_id: Optional[str] = None
    max_price: Optional[int] = None
    min_price: Optional[int] = None
    trade_type: Optional["TradeType"] = None
    show_own_trades: bool = False
    
    def get_filters(self, agent_id: str) -> Dict[str, Any]:
        """フィルタ条件を辞書形式で取得"""
        filters = {}
        
        if self.filter_offered_item_id:
            filters["offered_item_id"] = self.filter_offered_item_id
        
        if self.filter_requested_item_id:
            filters["requested_item_id"] = self.filter_requested_item_id
        
        if self.max_price is not None:
            filters["max_price"] = self.max_price
        
        if self.min_price is not None:
            filters["min_price"] = self.min_price
        
        if self.trade_type is not None:
            filters["trade_type"] = self.trade_type
        
        if not self.show_own_trades:
            # 自分の出品を除外するフィルタ
            filters["buyer_id"] = agent_id
        
        return filters


@dataclass(frozen=True)
class AcceptTrade(Action):
    """取引受託行動（Agent依存）"""
    trade_id: str
    
    def get_trade_id(self) -> str:
        """取引IDを取得"""
        return self.trade_id


@dataclass(frozen=True)
class CancelTrade(Action):
    """取引キャンセル行動（Agent依存）"""
    trade_id: str
    
    def get_trade_id(self) -> str:
        """取引IDを取得"""
        return self.trade_id