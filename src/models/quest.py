from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from .agent import Agent
from .item import Item
from .reward import ActionReward


class QuestType(Enum):
    """クエストタイプ"""
    MONSTER_HUNT = "monster_hunt"      # モンスター討伐
    ITEM_COLLECTION = "item_collection" # アイテム収集
    EXPLORATION = "exploration"         # 探索
    DELIVERY = "delivery"              # 配達
    RESCUE = "rescue"                  # 救出
    CUSTOM = "custom"                  # カスタム（その他）


class QuestStatus(Enum):
    """クエストステータス"""
    AVAILABLE = "available"    # 受注可能
    ACCEPTED = "accepted"      # 受注済み
    IN_PROGRESS = "in_progress" # 進行中
    COMPLETED = "completed"    # 完了
    FAILED = "failed"          # 失敗
    CANCELLED = "cancelled"    # キャンセル済み


class QuestDifficulty(Enum):
    """クエスト危険度"""
    E = "E"  # 初心者向け
    D = "D"  # 易しい
    C = "C"  # 普通
    B = "B"  # 難しい
    A = "A"  # とても難しい
    S = "S"  # 極めて危険


@dataclass
class QuestCondition:
    """クエストクリア条件"""
    condition_type: str  # "kill_monster", "collect_item", "reach_location", etc.
    target: str          # 対象（モンスターID、アイテムID、場所IDなど）
    required_count: int = 1
    current_count: int = 0
    description: str = ""
    
    def is_completed(self) -> bool:
        """条件が完了しているかチェック"""
        return self.current_count >= self.required_count
    
    def update_progress(self, count: int = 1):
        """進捗を更新"""
        self.current_count = min(self.current_count + count, self.required_count)
    
    def get_progress_text(self) -> str:
        """進捗テキストを取得"""
        return f"{self.current_count}/{self.required_count}"


@dataclass
class Quest:
    """クエスト"""
    quest_id: str
    name: str
    description: str
    quest_type: QuestType
    difficulty: QuestDifficulty
    client_id: str  # 依頼者のエージェントID
    guild_id: str   # 所属ギルドID
    
    # クリア条件
    conditions: List[QuestCondition] = field(default_factory=list)
    
    # 報酬
    reward_money: int = 0
    reward_items: List[str] = field(default_factory=list)  # アイテムIDのリスト
    reward_experience: int = 0
    
    # ステータス管理
    status: QuestStatus = QuestStatus.AVAILABLE
    accepted_by: Optional[str] = None  # 受注したエージェントID
    accepted_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    
    # ギルド管理用
    guild_fee_rate: float = 0.1  # ギルド手数料率（10%）
    
    def can_be_accepted_by(self, agent: Agent) -> bool:
        """指定されたエージェントが受注可能かチェック"""
        from .job import AdventurerAgent
        
        # 冒険者のみ受注可能
        if not isinstance(agent, AdventurerAgent):
            return False
        
        # 受注可能状態かチェック
        if self.status != QuestStatus.AVAILABLE:
            return False
        
        # 期限切れチェック
        if self.deadline and datetime.now() > self.deadline:
            return False
        
        # TODO: 冒険者レベル、評判等の条件チェックを将来追加
        
        return True
    
    def accept_by(self, agent_id: str) -> bool:
        """クエストを受注"""
        if self.status != QuestStatus.AVAILABLE:
            return False
        
        self.status = QuestStatus.ACCEPTED
        self.accepted_by = agent_id
        self.accepted_at = datetime.now()
        return True
    
    def start_progress(self):
        """クエスト進行開始"""
        if self.status == QuestStatus.ACCEPTED:
            self.status = QuestStatus.IN_PROGRESS
    
    def update_condition_progress(self, condition_type: str, target: str, count: int = 1):
        """特定の条件の進捗を更新"""
        for condition in self.conditions:
            if condition.condition_type == condition_type and condition.target == target:
                condition.update_progress(count)
                break
    
    def check_completion(self) -> bool:
        """クエスト完了チェック（ステータス変更なし）"""
        if self.status != QuestStatus.IN_PROGRESS:
            return False
        
        # すべての条件が完了しているかチェック
        all_completed = all(condition.is_completed() for condition in self.conditions)
        return all_completed
    
    def complete_quest(self) -> bool:
        """クエストを完了状態にする"""
        if self.status != QuestStatus.IN_PROGRESS:
            return False
        
        if self.check_completion():
            self.status = QuestStatus.COMPLETED
            return True
        
        return False
    
    def check_deadline(self) -> bool:
        """期限切れチェック"""
        if self.deadline and datetime.now() > self.deadline:
            if self.status in [QuestStatus.ACCEPTED, QuestStatus.IN_PROGRESS]:
                self.status = QuestStatus.FAILED
                return True
        return False
    
    def cancel(self):
        """クエストをキャンセル"""
        if self.status in [QuestStatus.ACCEPTED, QuestStatus.IN_PROGRESS]:
            self.status = QuestStatus.CANCELLED
            self.accepted_by = None
            self.accepted_at = None
    
    def get_net_reward_money(self) -> int:
        """ギルド手数料を差し引いた報酬金額"""
        return int(self.reward_money * (1 - self.guild_fee_rate))
    
    def get_guild_fee(self) -> int:
        """ギルド手数料を取得"""
        return self.reward_money - self.get_net_reward_money()
    
    def get_progress_summary(self) -> str:
        """進捗サマリーを取得"""
        if not self.conditions:
            return "条件なし"
        
        progress_texts = [f"{condition.description}: {condition.get_progress_text()}" 
                         for condition in self.conditions]
        return " | ".join(progress_texts)
    
    def get_status_text(self) -> str:
        """ステータステキストを取得"""
        status_map = {
            QuestStatus.AVAILABLE: "受注可能",
            QuestStatus.ACCEPTED: "受注済み",
            QuestStatus.IN_PROGRESS: "進行中",
            QuestStatus.COMPLETED: "完了",
            QuestStatus.FAILED: "失敗",
            QuestStatus.CANCELLED: "キャンセル済み"
        }
        return status_map.get(self.status, "不明")
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式で情報を取得"""
        return {
            "quest_id": self.quest_id,
            "name": self.name,
            "description": self.description,
            "type": self.quest_type.value,
            "difficulty": self.difficulty.value,
            "status": self.get_status_text(),
            "client_id": self.client_id,
            "accepted_by": self.accepted_by,
            "reward_money": self.reward_money,
            "net_reward": self.get_net_reward_money(),
            "guild_fee": self.get_guild_fee(),
            "progress": self.get_progress_summary(),
            "deadline": self.deadline.isoformat() if self.deadline else None
        }


# === クエスト生成用のヘルパー関数 ===

def create_monster_hunt_quest(quest_id: str, name: str, description: str,
                             monster_id: str, monster_count: int,
                             difficulty: QuestDifficulty, client_id: str, guild_id: str,
                             reward_money: int, deadline_hours: int = 72) -> Quest:
    """モンスター討伐クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.MONSTER_HUNT,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 討伐条件を追加
    condition = QuestCondition(
        condition_type="kill_monster",
        target=monster_id,
        required_count=monster_count,
        description=f"{monster_id}を{monster_count}体討伐"
    )
    quest.conditions.append(condition)
    
    return quest


def create_item_collection_quest(quest_id: str, name: str, description: str,
                                item_id: str, item_count: int,
                                difficulty: QuestDifficulty, client_id: str, guild_id: str,
                                reward_money: int, deadline_hours: int = 48) -> Quest:
    """アイテム収集クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.ITEM_COLLECTION,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 収集条件を追加
    condition = QuestCondition(
        condition_type="collect_item",
        target=item_id,
        required_count=item_count,
        description=f"{item_id}を{item_count}個収集"
    )
    quest.conditions.append(condition)
    
    return quest


def create_exploration_quest(quest_id: str, name: str, description: str,
                           target_spot_id: str,
                           difficulty: QuestDifficulty, client_id: str, guild_id: str,
                           reward_money: int, deadline_hours: int = 24) -> Quest:
    """探索クエストを生成"""
    quest = Quest(
        quest_id=quest_id,
        name=name,
        description=description,
        quest_type=QuestType.EXPLORATION,
        difficulty=difficulty,
        client_id=client_id,
        guild_id=guild_id,
        reward_money=reward_money,
        deadline=datetime.now() + timedelta(hours=deadline_hours)
    )
    
    # 探索条件を追加
    condition = QuestCondition(
        condition_type="reach_location",
        target=target_spot_id,
        required_count=1,
        description=f"{target_spot_id}を探索"
    )
    quest.conditions.append(condition)
    
    return quest 