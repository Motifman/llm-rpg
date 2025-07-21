from typing import Dict, List, Optional
from ..models.quest import Quest, QuestType, QuestDifficulty, QuestStatus, create_monster_hunt_quest, create_item_collection_quest, create_exploration_quest
from ..models.guild import AdventurerGuild
from ..models.agent import Agent


class QuestSystem:
    """
    クエストシステムの統合管理クラス
    
    ギルドの管理、クエストの生成・管理、進捗追跡などを行う
    """
    
    def __init__(self):
        self.guilds: Dict[str, AdventurerGuild] = {}  # guild_id -> AdventurerGuild
        self.quest_templates: Dict[str, Dict] = {}    # テンプレート管理用（将来拡張）
        
        # クエスト自動生成用カウンター
        self.quest_id_counter: int = 0
    
    def create_guild(self, guild_id: str, name: str, location_spot_id: str) -> AdventurerGuild:
        """新しいギルドを作成"""
        if guild_id in self.guilds:
            raise ValueError(f"ギルド {guild_id} は既に存在します")
        
        guild = AdventurerGuild(guild_id, name, location_spot_id)
        self.guilds[guild_id] = guild
        return guild
    
    def get_guild(self, guild_id: str) -> Optional[AdventurerGuild]:
        """ギルドを取得"""
        return self.guilds.get(guild_id)
    
    def get_all_guilds(self) -> List[AdventurerGuild]:
        """全ギルドを取得"""
        return list(self.guilds.values())
    
    def register_agent_to_guild(self, agent: Agent, guild_id: str) -> bool:
        """エージェントをギルドに登録"""
        guild = self.get_guild(guild_id)
        if not guild:
            return False
        
        return guild.register_member(agent)
    
    def unregister_agent_from_guild(self, agent_id: str, guild_id: str) -> bool:
        """エージェントをギルドから登録解除"""
        guild = self.get_guild(guild_id)
        if not guild:
            return False
        
        return guild.unregister_member(agent_id)
    
    def get_agent_guild(self, agent_id: str) -> Optional[AdventurerGuild]:
        """エージェントが所属するギルドを取得"""
        for guild in self.guilds.values():
            if guild.is_member(agent_id):
                return guild
        return None
    
    def generate_quest_id(self) -> str:
        """新しいクエストIDを生成"""
        self.quest_id_counter += 1
        return f"quest_{self.quest_id_counter:06d}"
    
    def post_quest_to_guild(self, guild_id: str, quest: Quest, client_agent: Agent) -> bool:
        """ギルドにクエストを依頼"""
        guild = self.get_guild(guild_id)
        if not guild:
            return False
        
        # 依頼者の資金チェック
        if client_agent.get_money() < quest.reward_money:
            return False
        
        # 依頼手数料を支払い
        client_agent.add_money(-quest.reward_money)
        
        # ギルドにクエストを掲示
        return guild.post_quest(quest, quest.reward_money)
    
    def get_available_quests(self, agent_id: str) -> List[Quest]:
        """エージェントが受注可能なクエストを取得"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return []
        
        return guild.get_available_quests(agent_id)
    
    def accept_quest(self, agent_id: str, quest_id: str) -> bool:
        """クエストを受注"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return False
        
        return guild.accept_quest(quest_id, agent_id)
    
    def cancel_quest(self, agent_id: str, quest_id: str) -> bool:
        """クエストをキャンセル"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return False
        
        return guild.cancel_quest(quest_id, agent_id)
    
    def get_active_quest(self, agent_id: str) -> Optional[Quest]:
        """エージェントのアクティブクエストを取得"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return None
        
        return guild.get_active_quest_by_agent(agent_id)
    
    def update_quest_progress(self, agent_id: str, condition_type: str, target: str, count: int = 1) -> Optional[Quest]:
        """クエスト進捗を更新"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return None
        
        return guild.update_quest_progress(agent_id, condition_type, target, count)
    
    def check_quest_completion(self, agent_id: str) -> Optional[Dict]:
        """クエスト完了をチェックし、完了していれば報酬を配布"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return None
        
        quest = guild.get_active_quest_by_agent(agent_id)
        if not quest:
            return None
        
        if quest.check_completion():
            return guild.complete_quest(quest.quest_id, agent_id)
        
        return None
    
    def handle_monster_kill(self, agent_id: str, monster_id: str, count: int = 1) -> Optional[Quest]:
        """モンスター討伐時の処理"""
        return self.update_quest_progress(agent_id, "kill_monster", monster_id, count)
    
    def handle_item_collection(self, agent_id: str, item_id: str, count: int = 1) -> Optional[Quest]:
        """アイテム収集時の処理"""
        return self.update_quest_progress(agent_id, "collect_item", item_id, count)
    
    def handle_location_visit(self, agent_id: str, spot_id: str) -> Optional[Quest]:
        """場所訪問時の処理"""
        return self.update_quest_progress(agent_id, "reach_location", spot_id, 1)
    
    def create_monster_hunt_quest_for_guild(self, guild_id: str, name: str, description: str,
                                          monster_id: str, monster_count: int,
                                          difficulty: QuestDifficulty, client_id: str,
                                          reward_money: int, deadline_hours: int = 72) -> Quest:
        """モンスター討伐クエストを生成してギルドに投稿"""
        quest_id = self.generate_quest_id()
        quest = create_monster_hunt_quest(
            quest_id, name, description, monster_id, monster_count,
            difficulty, client_id, guild_id, reward_money, deadline_hours
        )
        return quest
    
    def create_item_collection_quest_for_guild(self, guild_id: str, name: str, description: str,
                                             item_id: str, item_count: int,
                                             difficulty: QuestDifficulty, client_id: str,
                                             reward_money: int, deadline_hours: int = 48) -> Quest:
        """アイテム収集クエストを生成してギルドに投稿"""
        quest_id = self.generate_quest_id()
        quest = create_item_collection_quest(
            quest_id, name, description, item_id, item_count,
            difficulty, client_id, guild_id, reward_money, deadline_hours
        )
        return quest
    
    def create_exploration_quest_for_guild(self, guild_id: str, name: str, description: str,
                                         target_spot_id: str, difficulty: QuestDifficulty,
                                         client_id: str, reward_money: int, deadline_hours: int = 24) -> Quest:
        """探索クエストを生成してギルドに投稿"""
        quest_id = self.generate_quest_id()
        quest = create_exploration_quest(
            quest_id, name, description, target_spot_id,
            difficulty, client_id, guild_id, reward_money, deadline_hours
        )
        return quest
    
    def get_quest_by_id(self, quest_id: str) -> Optional[Quest]:
        """IDでクエストを検索（全ギルドから）"""
        for guild in self.guilds.values():
            quest = guild.get_quest_by_id(quest_id)
            if quest:
                return quest
        return None
    
    def get_guild_statistics(self) -> Dict:
        """全ギルドの統計情報を取得"""
        total_stats = {
            "total_guilds": len(self.guilds),
            "total_members": 0,
            "total_available_quests": 0,
            "total_active_quests": 0,
            "total_completed_quests": 0,
            "guild_details": []
        }
        
        for guild in self.guilds.values():
            stats = guild.get_guild_stats()
            total_stats["total_members"] += stats["total_members"]
            total_stats["total_available_quests"] += stats["available_quests"]
            total_stats["total_active_quests"] += stats["active_quests"]
            total_stats["total_completed_quests"] += stats["completed_quests"]
            total_stats["guild_details"].append(stats)
        
        return total_stats
    
    def check_all_quest_deadlines(self):
        """全ギルドのクエスト期限をチェック"""
        for guild in self.guilds.values():
            # 受注可能クエストの期限チェック
            expired_quests = []
            for quest_id, quest in guild.available_quests.items():
                if quest.check_deadline():
                    expired_quests.append(quest_id)
            
            for quest_id in expired_quests:
                guild._move_quest_to_failed(quest_id)
            
            # アクティブクエストの期限チェック
            expired_active = []
            for quest_id, quest in guild.active_quests.items():
                if quest.check_deadline():
                    expired_active.append(quest_id)
            
            for quest_id in expired_active:
                guild._move_quest_to_failed(quest_id)
    
    def get_agent_quest_history(self, agent_id: str) -> Dict:
        """エージェントのクエスト履歴を取得"""
        guild = self.get_agent_guild(agent_id)
        if not guild:
            return {"error": "ギルドに所属していません"}
        
        member = guild.get_member(agent_id)
        if not member:
            return {"error": "メンバー情報が見つかりません"}
        
        active_quest = guild.get_active_quest_by_agent(agent_id)
        
        return {
            "agent_id": agent_id,
            "guild_info": {
                "guild_id": guild.guild_id,
                "guild_name": guild.name
            },
            "member_info": member.to_dict(),
            "active_quest": active_quest.to_dict() if active_quest else None,
            "available_quests_count": len(guild.get_available_quests(agent_id))
        } 