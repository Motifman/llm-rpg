import pytest
from datetime import datetime, timedelta
from src_old.models.quest import Quest, QuestType, QuestDifficulty, QuestStatus, QuestCondition, create_monster_hunt_quest, create_item_collection_quest, create_exploration_quest
from src_old.models.guild import AdventurerGuild, GuildMember, GuildRank
from src_old.models.job import AdventurerAgent
from src_old.systems.quest_system import QuestSystem
from src_old.systems.world import World
from src_old.models.action import RegisterToGuild, ViewAvailableQuests, AcceptQuest, SubmitQuest, PostQuestToGuild
from src_old.models.spot import Spot


class TestQuest:
    """Questクラスのテスト"""
    
    def test_quest_creation(self):
        """クエストの作成テスト"""
        quest = Quest(
            quest_id="test_quest_001",
            name="ゴブリン討伐",
            description="村を荒らすゴブリンを討伐してください",
            quest_type=QuestType.MONSTER_HUNT,
            difficulty=QuestDifficulty.D,
            client_id="client_001",
            guild_id="guild_001",
            reward_money=100
        )
        
        assert quest.quest_id == "test_quest_001"
        assert quest.name == "ゴブリン討伐"
        assert quest.quest_type == QuestType.MONSTER_HUNT
        assert quest.difficulty == QuestDifficulty.D
        assert quest.status == QuestStatus.AVAILABLE
        assert quest.reward_money == 100
        assert quest.get_net_reward_money() == 90  # 10%手数料差引
        assert quest.get_guild_fee() == 10
    
    def test_quest_condition(self):
        """クエスト条件のテスト"""
        condition = QuestCondition(
            condition_type="kill_monster",
            target="goblin",
            required_count=3,
            description="ゴブリンを3体討伐"
        )
        
        assert not condition.is_completed()
        assert condition.get_progress_text() == "0/3"
        
        condition.update_progress(2)
        assert condition.current_count == 2
        assert not condition.is_completed()
        assert condition.get_progress_text() == "2/3"
        
        condition.update_progress(1)
        assert condition.current_count == 3
        assert condition.is_completed()
        assert condition.get_progress_text() == "3/3"
    
    def test_quest_acceptance(self):
        """クエスト受注テスト"""
        adventurer = AdventurerAgent("adv_001", "テスト冒険者")
        quest = Quest(
            quest_id="test_quest_002",
            name="テストクエスト",
            description="テスト用",
            quest_type=QuestType.EXPLORATION,
            difficulty=QuestDifficulty.E,
            client_id="client_001",
            guild_id="guild_001"
        )
        
        assert quest.can_be_accepted_by(adventurer)
        assert quest.accept_by("adv_001")
        assert quest.status == QuestStatus.ACCEPTED
        assert quest.accepted_by == "adv_001"
        assert quest.accepted_at is not None
    
    def test_quest_completion_check(self):
        """クエスト完了チェックテスト"""
        quest = create_monster_hunt_quest(
            "test_quest_003", "モンスターハント", "テスト用モンスター討伐",
            "goblin", 2, QuestDifficulty.D, "client_001", "guild_001", 100
        )
        
        quest.accept_by("adv_001")
        quest.start_progress()
        
        assert not quest.check_completion()
        
        # 1体討伐
        quest.update_condition_progress("kill_monster", "goblin", 1)
        assert not quest.check_completion()
        
        # 2体目を討伐
        quest.update_condition_progress("kill_monster", "goblin", 1)
        assert quest.check_completion()
        
        # 明示的にクエストを完了状態にする
        quest.complete_quest()
        assert quest.status == QuestStatus.COMPLETED


class TestAdventurerGuild:
    """AdventurerGuildクラスのテスト"""
    
    def test_guild_creation(self):
        """ギルド作成テスト"""
        guild = AdventurerGuild("guild_001", "テストギルド", "town_center")
        
        assert guild.guild_id == "guild_001"
        assert guild.name == "テストギルド"
        assert guild.location_spot_id == "town_center"
        assert len(guild.members) == 0
        assert guild.total_funds == 0
    
    def test_member_registration(self):
        """メンバー登録テスト"""
        guild = AdventurerGuild("guild_001", "テストギルド", "town_center")
        adventurer = AdventurerAgent("adv_001", "テスト冒険者")
        
        assert guild.register_member(adventurer)
        assert guild.is_member("adv_001")
        assert len(guild.members) == 1
        
        member = guild.get_member("adv_001")
        assert member.agent_id == "adv_001"
        assert member.name == "テスト冒険者"
        assert member.rank == GuildRank.F
        assert member.reputation == 0
    
    def test_quest_posting_and_acceptance(self):
        """クエスト掲示と受注テスト"""
        guild = AdventurerGuild("guild_001", "テストギルド", "town_center")
        adventurer = AdventurerAgent("adv_001", "テスト冒険者")
        guild.register_member(adventurer)
        
        quest = create_item_collection_quest(
            "test_quest_004", "薬草採集", "薬草を5個集めてください",
            "herb", 5, QuestDifficulty.E, "client_001", "guild_001", 50
        )
        
        # クエスト掲示
        assert guild.post_quest(quest, 50)
        available_quests = guild.get_available_quests()
        assert len(available_quests) == 1
        
        # クエスト受注
        assert guild.accept_quest("test_quest_004", "adv_001")
        assert len(guild.available_quests) == 0
        assert len(guild.active_quests) == 1
        
        active_quest = guild.get_active_quest_by_agent("adv_001")
        assert active_quest is not None
        assert active_quest.quest_id == "test_quest_004"


class TestQuestSystem:
    """QuestSystemクラスのテスト"""
    
    def test_quest_system_creation(self):
        """クエストシステム作成テスト"""
        quest_system = QuestSystem()
        
        assert len(quest_system.guilds) == 0
        assert quest_system.quest_id_counter == 0
    
    def test_guild_management(self):
        """ギルド管理テスト"""
        quest_system = QuestSystem()
        
        # ギルド作成
        guild = quest_system.create_guild("guild_001", "テストギルド", "town_center")
        assert guild.guild_id == "guild_001"
        assert len(quest_system.guilds) == 1
        
        # ギルド取得
        retrieved_guild = quest_system.get_guild("guild_001")
        assert retrieved_guild is not None
        assert retrieved_guild.guild_id == "guild_001"
    
    def test_agent_guild_integration(self):
        """エージェントとギルドの統合テスト"""
        quest_system = QuestSystem()
        guild = quest_system.create_guild("guild_001", "テストギルド", "town_center")
        adventurer = AdventurerAgent("adv_001", "テスト冒険者")
        
        # ギルド登録
        assert quest_system.register_agent_to_guild(adventurer, "guild_001")
        
        # 所属ギルド確認
        agent_guild = quest_system.get_agent_guild("adv_001")
        assert agent_guild is not None
        assert agent_guild.guild_id == "guild_001"
    
    def test_quest_lifecycle(self):
        """クエストのライフサイクルテスト"""
        quest_system = QuestSystem()
        guild = quest_system.create_guild("guild_001", "テストギルド", "town_center")
        adventurer = AdventurerAgent("adv_001", "テスト冒険者")
        client = AdventurerAgent("client_001", "依頼者")
        client.add_money(200)  # 依頼料を用意
        
        quest_system.register_agent_to_guild(adventurer, "guild_001")
        
        # クエスト生成と掲示
        quest = quest_system.create_monster_hunt_quest_for_guild(
            "guild_001", "ゴブリン討伐", "村を荒らすゴブリンを討伐",
            "goblin", 3, QuestDifficulty.D, "client_001", 150
        )
        
        assert quest_system.post_quest_to_guild("guild_001", quest, client)
        assert client.get_money() == 50  # 依頼料150が差し引かれている
        
        # 受注可能クエスト確認
        available_quests = quest_system.get_available_quests("adv_001")
        assert len(available_quests) == 1
        
        # クエスト受注
        assert quest_system.accept_quest("adv_001", quest.quest_id)
        active_quest = quest_system.get_active_quest("adv_001")
        assert active_quest is not None
        
        # 進捗更新
        quest_system.update_quest_progress("adv_001", "kill_monster", "goblin", 3)
        
        # クエスト完了チェック
        completion_result = quest_system.check_quest_completion("adv_001")
        assert completion_result is not None
        assert completion_result["success"]
        assert completion_result["reward_money"] == 135  # 150 - 10%手数料


class TestWorldQuestIntegration:
    """WorldシステムとQuestシステムの統合テスト"""
    
    def test_world_quest_integration(self):
        """WorldとQuestの統合テスト"""
        world = World()
        
        # スポット作成
        town = Spot("town_center", "町の中心", "冒険者ギルドがある町の中心部")
        world.add_spot(town)
        
        # ギルド作成
        guild = world.get_quest_system().create_guild("guild_001", "冒険者ギルド", "town_center")
        
        # 冒険者作成と追加
        adventurer = AdventurerAgent("adv_001", "勇者", "warrior")
        adventurer.set_current_spot_id("town_center")
        world.add_agent(adventurer)
        
        # ギルド登録アクション
        register_action = RegisterToGuild(description="ギルドに登録する", guild_id="guild_001")
        result = world.execute_action("adv_001", register_action)
        assert result["success"]
        
        # 依頼者作成
        client = AdventurerAgent("client_001", "村長")
        client.add_money(200)
        world.add_agent(client)
        
        # クエスト依頼アクション
        post_quest_action = PostQuestToGuild(
            description="ギルドにクエストを依頼する",
            guild_id="guild_001",
            quest_name="スライム討伐",
            quest_description="畑を荒らすスライムを討伐してください",
            quest_type="monster_hunt",
            target="slime",
            target_count=2,
            difficulty="E",
            reward_money=100
        )
        result = world.execute_action("client_001", post_quest_action)
        assert result["success"]
        
        # 受注可能クエスト確認
        view_quests_action = ViewAvailableQuests(description="受注可能なクエストを確認する")
        result = world.execute_action("adv_001", view_quests_action)
        assert result["success"]
        assert result["count"] == 1
        
        # クエスト受注
        quest_id = result["available_quests"][0]["quest_id"]
        accept_action = AcceptQuest(description="クエストを受注する", quest_id=quest_id)
        result = world.execute_action("adv_001", accept_action)
        assert result["success"]
        
        # クエスト進捗確認（テストではモンスター討伐をシミュレート）
        quest_system = world.get_quest_system()
        quest_system.update_quest_progress("adv_001", "kill_monster", "slime", 2)
        
        # クエスト提出
        submit_action = SubmitQuest(description="クエストを提出する", quest_id=quest_id)
        result = world.execute_action("adv_001", submit_action)
        assert result["success"]
        assert result["reward_money"] == 90  # 100 - 10%手数料
        
        # 冒険者の所持金確認
        assert adventurer.get_money() == 90 