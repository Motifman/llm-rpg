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


# === ロケーション依存の行動 ===

@dataclass(frozen=True)
class Movement(Action):
    """移動行動"""
    direction: str
    target_spot_id: str


@dataclass(frozen=True)
class Exploration(Action):
    """探索行動（spot依存）"""
    item_id: Optional[str] = None
    discovered_info: Optional[str] = None
    experience_points: int = 0
    money: int = 0


@dataclass(frozen=True)
class Interaction(Action):
    """相互作用行動（spot内のオブジェクト依存）"""
    object_id: str
    interaction_type: InteractionType
    state_changes: Dict[str, Any] = field(default_factory=dict)
    required_item_id: Optional[str] = None
    reward: ActionReward = field(default_factory=ActionReward)


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


# === 会話システム関連の行動 ===

@dataclass(frozen=True)
class Conversation(Action):
    """会話行動"""
    content: str  # 送信するメッセージ内容
    target_agent_id: Optional[str] = None  # 特定のエージェントに送信する場合（Noneは全体発言）
    
    def is_broadcast(self) -> bool:
        """全体発言かどうか"""
        return self.target_agent_id is None
    
    def get_target_agent_id(self) -> Optional[str]:
        """対象エージェントIDを取得"""
        return self.target_agent_id
    
    def get_content(self) -> str:
        """メッセージ内容を取得"""
        return self.content


# === 戦闘システム関連の行動 ===

@dataclass(frozen=True)
class StartBattle(Action):
    """戦闘開始行動"""
    monster_id: str
    
    def get_monster_id(self) -> str:
        """モンスターIDを取得"""
        return self.monster_id


@dataclass(frozen=True)
class JoinBattle(Action):
    """戦闘参加行動"""
    battle_id: str
    
    def get_battle_id(self) -> str:
        """戦闘IDを取得"""
        return self.battle_id


@dataclass(frozen=True)
class AttackMonster(Action):
    """モンスター攻撃行動"""
    monster_id: str
    
    def get_monster_id(self) -> str:
        """対象モンスターIDを取得"""
        return self.monster_id


@dataclass(frozen=True)
class DefendBattle(Action):
    """戦闘防御行動"""
    pass  # 現在は追加のパラメータ不要


@dataclass(frozen=True)
class EscapeBattle(Action):
    """戦闘逃走行動"""
    pass  # 現在は追加のパラメータ不要


# === 職業システム関連の行動 ===

@dataclass(frozen=True)
class CraftItem(Action):
    """アイテム合成行動（職人向け）"""
    recipe_id: str
    quantity: int = 1  # 作成回数
    
    def is_valid(self, agent: "Agent") -> bool:
        """合成可能かチェック"""
        from .job import JobAgent
        if not isinstance(agent, JobAgent):
            return False
        
        recipe = agent.get_recipe_by_id(self.recipe_id)
        if not recipe:
            return False
        
        return recipe.can_craft(agent)


@dataclass(frozen=True)
class EnhanceItem(Action):
    """アイテム強化行動（職人向け）"""
    item_id: str
    enhancement_materials: Dict[str, int]  # 強化材料
    enhancement_level: int = 1  # 強化レベル
    
    def is_valid(self, agent: "Agent") -> bool:
        """強化可能かチェック"""
        # 対象アイテムを所持しているかチェック
        if not agent.has_item(self.item_id):
            return False
        
        # 強化材料を所持しているかチェック
        for material_id, count in self.enhancement_materials.items():
            if agent.get_item_count(material_id) < count:
                return False
        
        return True


@dataclass(frozen=True)
class LearnRecipe(Action):
    """レシピ習得行動（職人向け）"""
    recipe_id: str
    teacher_agent_id: Optional[str] = None  # 教師エージェント
    required_materials: Dict[str, int] = field(default_factory=dict)  # 習得に必要な材料
    
    def is_valid(self, agent: "Agent") -> bool:
        """習得可能かチェック"""
        from .job import JobAgent
        if not isinstance(agent, JobAgent):
            return False
        
        # 必要材料のチェック
        for material_id, count in self.required_materials.items():
            if agent.get_item_count(material_id) < count:
                return False
        
        return True


@dataclass(frozen=True)
class SetupShop(Action):
    """店舗設営行動（商人向け）"""
    shop_name: str
    shop_type: str  # "item_shop", "service_shop", "restaurant" など
    offered_items: Dict[str, int] = field(default_factory=dict)  # item_id -> price
    offered_services: List[str] = field(default_factory=list)  # service_id のリスト


@dataclass(frozen=True)
class ProvideService(Action):
    """サービス提供行動（商人向け）"""
    service_id: str
    target_agent_id: str
    custom_price: Optional[int] = None  # カスタム価格（交渉結果）
    
    def is_valid(self, agent: "Agent") -> bool:
        """サービス提供可能かチェック"""
        from .job import JobAgent
        if not isinstance(agent, JobAgent):
            return False
        
        service = agent.get_service_by_id(self.service_id)
        if not service:
            return False
        
        return service.can_provide(agent)


@dataclass(frozen=True)
class PriceNegotiation(Action):
    """価格交渉行動（商人向け）"""
    target_agent_id: str
    item_or_service_id: str
    proposed_price: int
    original_price: int


@dataclass(frozen=True)
class GatherResource(Action):
    """資源採集行動（一次産業者向け）"""
    resource_type: str  # "wood", "ore", "herb", "fish" など
    tool_item_id: Optional[str] = None  # 使用する道具
    duration_minutes: int = 60  # 採集時間（分）
    
    def is_valid(self, agent: "Agent") -> bool:
        """採集可能かチェック"""
        # 道具が必要な場合のチェック
        if self.tool_item_id:
            if not agent.has_item(self.tool_item_id):
                return False
        
        return True


@dataclass(frozen=True)
class ProcessMaterial(Action):
    """材料加工行動（一次産業者向け）"""
    raw_material_id: str
    processed_item_id: str
    quantity: int = 1
    processing_time_minutes: int = 30
    
    def is_valid(self, agent: "Agent") -> bool:
        """加工可能かチェック"""
        return agent.get_item_count(self.raw_material_id) >= self.quantity


@dataclass(frozen=True)
class ManageFarm(Action):
    """農場管理行動（一次産業者向け）"""
    farm_action: str  # "plant", "water", "harvest"
    crop_type: str
    plot_id: str  # 畑の区画ID
    seed_item_id: Optional[str] = None  # 種のアイテムID（植える場合）
    
    def is_valid(self, agent: "Agent") -> bool:
        """農場管理可能かチェック"""
        if self.farm_action == "plant" and self.seed_item_id:
            return agent.has_item(self.seed_item_id)
        return True


@dataclass(frozen=True)
class AdvancedCombat(Action):
    """高度戦闘行動（冒険者向け）"""
    combat_skill: str  # "power_attack", "heal_ally", "magic_spell", "defend_ally"
    target_id: Optional[str] = None  # 対象（味方支援の場合）
    skill_level: int = 1
    
    def is_valid(self, agent: "Agent") -> bool:
        """スキル使用可能かチェック"""
        # MP消費などのチェックをここで行う
        mp_cost = self.skill_level * 10
        return agent.current_mp >= mp_cost


# === クエストシステム関連の行動 ===

@dataclass(frozen=True)
class ViewAvailableQuests(Action):
    """受注可能クエスト表示行動"""
    description: str = "受注可能なクエストを確認する"
    
    def is_valid(self, agent: "Agent") -> bool:
        """表示可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class AcceptQuest(Action):
    """クエスト受注行動"""
    description: str
    quest_id: str
    
    def is_valid(self, agent: "Agent") -> bool:
        """受注可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class CancelQuest(Action):
    """クエストキャンセル行動"""
    description: str
    quest_id: str
    
    def is_valid(self, agent: "Agent") -> bool:
        """キャンセル可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class ViewQuestProgress(Action):
    """クエスト進捗確認行動"""
    description: str = "クエストの進捗を確認する"
    
    def is_valid(self, agent: "Agent") -> bool:
        """確認可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class SubmitQuest(Action):
    """クエスト提出行動（完了報告）"""
    description: str
    quest_id: str
    
    def is_valid(self, agent: "Agent") -> bool:
        """提出可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class RegisterToGuild(Action):
    """ギルド登録行動"""
    description: str
    guild_id: str
    
    def is_valid(self, agent: "Agent") -> bool:
        """登録可能かチェック"""
        from .job import AdventurerAgent
        return isinstance(agent, AdventurerAgent)


@dataclass(frozen=True)
class PostQuestToGuild(Action):
    """ギルドへのクエスト依頼行動（NPCが使用）"""
    description: str
    guild_id: str
    quest_name: str
    quest_description: str
    quest_type: str  # "monster_hunt", "item_collection", "exploration"
    target: str      # モンスターID、アイテムID、場所IDなど
    target_count: int = 1
    difficulty: str = "D"  # "E", "D", "C", "B", "A", "S"
    reward_money: int = 100
    deadline_hours: int = 72
    
    def is_valid(self, agent: "Agent") -> bool:
        """依頼可能かチェック"""
        # 依頼料を所持しているかチェック
        return agent.get_money() >= self.reward_money