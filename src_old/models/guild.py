from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from .agent import Agent
from .quest import Quest, QuestStatus


class GuildRank(Enum):
    """ギルドランク"""
    F = "F"  # 初心者
    E = "E"  # 新人
    D = "D"  # 一般
    C = "C"  # 上級
    B = "B"  # エキスパート
    A = "A"  # ベテラン
    S = "S"  # マスター


@dataclass
class GuildMember:
    """ギルドメンバー情報"""
    agent_id: str
    name: str
    rank: GuildRank = GuildRank.F
    reputation: int = 0
    quests_completed: int = 0
    total_earnings: int = 0
    join_date: datetime = field(default_factory=datetime.now)
    
    def can_accept_quest(self, quest: Quest) -> bool:
        """クエストを受注可能かチェック（ランク制限など）"""
        # TODO: ランクによるクエスト制限を実装
        # 現在は基本的な実装のみ
        return True
    
    def complete_quest(self, quest: Quest):
        """クエスト完了時の処理"""
        self.quests_completed += 1
        self.total_earnings += quest.get_net_reward_money()
        self.reputation += self._calculate_reputation_gain(quest)
        self._check_rank_up()
    
    def _calculate_reputation_gain(self, quest: Quest) -> int:
        """評判上昇値を計算"""
        base_rep = 10
        # 危険度によるボーナス
        difficulty_bonus = {
            "E": 0, "D": 5, "C": 10, "B": 20, "A": 35, "S": 50
        }
        return base_rep + difficulty_bonus.get(quest.difficulty.value, 0)
    
    def _check_rank_up(self):
        """ランクアップ判定"""
        rank_requirements = {
            GuildRank.F: 0,
            GuildRank.E: 50,
            GuildRank.D: 150,
            GuildRank.C: 350,
            GuildRank.B: 700,
            GuildRank.A: 1200,
            GuildRank.S: 2000
        }
        
        for rank in reversed(list(GuildRank)):
            if self.reputation >= rank_requirements[rank]:
                self.rank = rank
                break
    
    def get_rank_name(self) -> str:
        """ランク名を取得"""
        return self.rank.value
    
    def to_dict(self) -> Dict:
        """辞書形式で情報を取得"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "rank": self.get_rank_name(),
            "reputation": self.reputation,
            "quests_completed": self.quests_completed,
            "total_earnings": self.total_earnings,
            "join_date": self.join_date.isoformat()
        }


class AdventurerGuild:
    """冒険者ギルド"""
    
    def __init__(self, guild_id: str, name: str, location_spot_id: str):
        self.guild_id = guild_id
        self.name = name
        self.location_spot_id = location_spot_id
        
        # メンバー管理
        self.members: Dict[str, GuildMember] = {}  # agent_id -> GuildMember
        
        # クエスト管理
        self.available_quests: Dict[str, Quest] = {}  # quest_id -> Quest
        self.active_quests: Dict[str, Quest] = {}    # quest_id -> Quest
        self.completed_quests: Dict[str, Quest] = {} # quest_id -> Quest
        
        # ギルド統計
        self.total_funds: int = 0  # ギルドの資金
        self.total_quests_completed: int = 0
        self.guild_reputation: int = 100  # ギルド評判
        
        # 依頼管理
        self.quest_counter: int = 0
    
    def register_member(self, agent: Agent) -> bool:
        """メンバーを登録"""
        from .job import AdventurerAgent
        
        if not isinstance(agent, AdventurerAgent):
            return False
        
        if agent.agent_id in self.members:
            return False  # 既に登録済み
        
        member = GuildMember(
            agent_id=agent.agent_id,
            name=agent.name
        )
        self.members[agent.agent_id] = member
        return True
    
    def unregister_member(self, agent_id: str) -> bool:
        """メンバー登録を解除"""
        if agent_id not in self.members:
            return False
        
        # アクティブなクエストがある場合は解除不可
        active_quest = self.get_active_quest_by_agent(agent_id)
        if active_quest:
            return False
        
        del self.members[agent_id]
        return True
    
    def is_member(self, agent_id: str) -> bool:
        """メンバーかどうかチェック"""
        return agent_id in self.members
    
    def get_member(self, agent_id: str) -> Optional[GuildMember]:
        """メンバー情報を取得"""
        return self.members.get(agent_id)
    
    def get_all_members(self) -> List[GuildMember]:
        """全メンバーを取得"""
        return list(self.members.values())
    
    def post_quest(self, quest: Quest, deposit_money: int) -> bool:
        """クエストを掲示"""
        if quest.quest_id in self.available_quests:
            return False  # 既に掲示済み
        
        # 依頼者の資金チェック（簡易実装）
        if deposit_money < quest.reward_money:
            return False
        
        quest.guild_id = self.guild_id
        self.available_quests[quest.quest_id] = quest
        return True
    
    def get_available_quests(self, agent_id: Optional[str] = None) -> List[Quest]:
        """受注可能なクエスト一覧を取得"""
        quests = []
        
        for quest in self.available_quests.values():
            # 期限切れチェック
            if quest.check_deadline():
                self._move_quest_to_failed(quest.quest_id)
                continue
            
            # 特定エージェント用のフィルタリング
            if agent_id and agent_id in self.members:
                member = self.members[agent_id]
                if not member.can_accept_quest(quest):
                    continue
            
            quests.append(quest)
        
        return quests
    
    def accept_quest(self, quest_id: str, agent_id: str) -> bool:
        """クエストを受注"""
        if quest_id not in self.available_quests:
            return False
        
        if not self.is_member(agent_id):
            return False
        
        quest = self.available_quests[quest_id]
        
        # 既にアクティブなクエストがある場合は受注不可
        if self.get_active_quest_by_agent(agent_id):
            return False
        
        # クエスト受注
        if quest.accept_by(agent_id):
            # アクティブクエストに移動
            self.active_quests[quest_id] = quest
            del self.available_quests[quest_id]
            return True
        
        return False
    
    def cancel_quest(self, quest_id: str, agent_id: str) -> bool:
        """クエストをキャンセル"""
        if quest_id not in self.active_quests:
            return False
        
        quest = self.active_quests[quest_id]
        if quest.accepted_by != agent_id:
            return False
        
        quest.cancel()
        # 受注可能クエストに戻す
        quest.status = QuestStatus.AVAILABLE
        quest.accepted_by = None
        quest.accepted_at = None
        
        self.available_quests[quest_id] = quest
        del self.active_quests[quest_id]
        return True
    
    def complete_quest(self, quest_id: str, agent_id: str) -> Dict:
        """クエストを完了"""
        if quest_id not in self.active_quests:
            return {"success": False, "message": "アクティブなクエストが見つかりません"}
        
        quest = self.active_quests[quest_id]
        if quest.accepted_by != agent_id:
            return {"success": False, "message": "このクエストを受注していません"}
        
        if not quest.check_completion():
            return {"success": False, "message": "クエストの条件が完了していません"}
        
        # クエストのステータスを完了に変更
        quest.complete_quest()
        
        # クエスト完了処理
        member = self.members[agent_id]
        member.complete_quest(quest)
        
        # ギルド資金処理
        guild_fee = quest.get_guild_fee()
        self.total_funds += guild_fee
        self.total_quests_completed += 1
        
        # 完了クエストに移動
        self.completed_quests[quest_id] = quest
        del self.active_quests[quest_id]
        
        return {
            "success": True,
            "message": "クエストが完了しました",
            "reward_money": quest.get_net_reward_money(),
            "guild_fee": guild_fee,
            "experience_gained": quest.reward_experience,
            "reputation_gained": member._calculate_reputation_gain(quest)
        }
    
    def update_quest_progress(self, agent_id: str, condition_type: str, 
                            target: str, count: int = 1) -> Optional[Quest]:
        """クエスト進捗を更新"""
        quest = self.get_active_quest_by_agent(agent_id)
        if not quest:
            return None
        
        quest.update_condition_progress(condition_type, target, count)
        
        # 進行中ステータスに変更
        if quest.status == QuestStatus.ACCEPTED:
            quest.start_progress()
        
        return quest
    
    def get_active_quest_by_agent(self, agent_id: str) -> Optional[Quest]:
        """エージェントのアクティブクエストを取得"""
        for quest in self.active_quests.values():
            if quest.accepted_by == agent_id:
                return quest
        return None
    
    def get_quest_by_id(self, quest_id: str) -> Optional[Quest]:
        """IDでクエストを取得"""
        # 全カテゴリから検索
        for quests in [self.available_quests, self.active_quests, self.completed_quests]:
            if quest_id in quests:
                return quests[quest_id]
        return None
    
    def _move_quest_to_failed(self, quest_id: str):
        """期限切れクエストを失敗に移動"""
        if quest_id in self.available_quests:
            quest = self.available_quests[quest_id]
            quest.status = QuestStatus.FAILED
            del self.available_quests[quest_id]
        elif quest_id in self.active_quests:
            quest = self.active_quests[quest_id]
            quest.status = QuestStatus.FAILED
            del self.active_quests[quest_id]
    
    def generate_quest_id(self) -> str:
        """新しいクエストIDを生成"""
        self.quest_counter += 1
        return f"{self.guild_id}_quest_{self.quest_counter:04d}"
    
    def get_guild_stats(self) -> Dict:
        """ギルド統計を取得"""
        return {
            "guild_id": self.guild_id,
            "name": self.name,
            "location": self.location_spot_id,
            "total_members": len(self.members),
            "available_quests": len(self.available_quests),
            "active_quests": len(self.active_quests),
            "completed_quests": len(self.completed_quests),
            "total_funds": self.total_funds,
            "guild_reputation": self.guild_reputation
        }
    
    def to_dict(self) -> Dict:
        """辞書形式でギルド情報を取得"""
        return {
            "guild_info": self.get_guild_stats(),
            "members": [member.to_dict() for member in self.members.values()],
            "available_quests": [quest.to_dict() for quest in self.available_quests.values()],
            "active_quests": [quest.to_dict() for quest in self.active_quests.values()]
        } 