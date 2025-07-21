import pytest
from src.models.spot import Spot
from src.models.monster import Monster, MonsterType, MonsterDropReward
from src.models.item import Item
from src.models.job import AdventurerAgent
from src.models.quest import QuestDifficulty
from src.models.action import (
    RegisterToGuild, PostQuestToGuild, ViewAvailableQuests, 
    AcceptQuest, StartBattle, AttackMonster, SubmitQuest
)
from src.systems.world import World


class TestBattleQuestIntegration:
    """バトルシステムとクエストシステムの統合テスト"""
    
    def setup_method(self):
        """各テストの前に実行されるセットアップ"""
        self.world = World()
        
        # スポット作成
        self.forest = Spot("forest", "森", "モンスターが住む森")
        self.town = Spot("town", "町", "冒険者ギルドがある町")
        self.world.add_spot(self.forest)
        self.world.add_spot(self.town)
        
        # ギルド作成
        self.guild = self.world.get_quest_system().create_guild("guild_001", "冒険者ギルド", "town")
        
        # 冒険者作成
        self.adventurer = AdventurerAgent("adv_001", "勇者", "warrior")
        self.adventurer.set_current_spot_id("town")
        self.world.add_agent(self.adventurer)
        
        # 依頼者作成
        self.client = AdventurerAgent("client_001", "村長", "warrior")
        self.client.add_money(500)
        self.client.set_current_spot_id("town")
        self.world.add_agent(self.client)
        
        # ギルド登録
        register_action = RegisterToGuild(description="ギルドに登録する", guild_id="guild_001")
        self.world.execute_action("adv_001", register_action)
    
    def test_single_monster_hunt_quest_completion(self):
        """単体モンスター討伐クエストが正常に完了することをテスト"""
        # スライム作成
        slime = Monster(
            monster_id="slime_001",
            name="スライム",
            description="ぷるぷるした青いスライム",
            monster_type=MonsterType.PASSIVE,
            max_hp=30,
            attack=5,
            defense=2,
            speed=3,
            drop_reward=MonsterDropReward(
                items=[Item("slime_jelly", "スライムゼリー")],
                money=10,
                experience=5
            )
        )
        
        # モンスターを森に配置
        self.world.add_monster(slime, "forest")
        
        # スライム討伐クエストを依頼
        post_quest_action = PostQuestToGuild(
            description="ギルドにクエストを依頼する",
            guild_id="guild_001",
            quest_name="スライム討伐",
            quest_description="森に出現したスライムを討伐してください",
            quest_type="monster_hunt",
            target="slime_001",  # 特定のモンスターIDを指定
            target_count=1,
            difficulty="E",
            reward_money=100,
            deadline_hours=24
        )
        result = self.world.execute_action("client_001", post_quest_action)
        assert result["success"]
        
        # 受注可能クエストを確認
        view_action = ViewAvailableQuests(description="受注可能なクエストを確認する")
        result = self.world.execute_action("adv_001", view_action)
        assert result["success"]
        assert result["count"] == 1
        
        # クエストを受注
        quest_id = result["available_quests"][0]["quest_id"]
        accept_action = AcceptQuest(description="クエストを受注する", quest_id=quest_id)
        result = self.world.execute_action("adv_001", accept_action)
        assert result["success"]
        
        # 冒険者を森に移動
        self.adventurer.set_current_spot_id("forest")
        
        # 初期状態確認
        initial_money = self.adventurer.get_money()
        initial_exp = self.adventurer.get_experience_points()
        
        # バトル前のクエスト進捗確認
        quest_system = self.world.get_quest_system()
        active_quest = quest_system.get_active_quest("adv_001")
        assert active_quest is not None
        assert active_quest.status.value == "accepted"
        
        # スライムとバトルして倒す
        self._complete_battle("adv_001", "slime_001", slime)
        
        # スライムが倒されたことを確認
        assert not slime.is_alive
        
        # バトル後、クエストが自動的に完了されているかを確認
        # 注意：バトルでモンスターを倒すと自動的にクエストが完了される
        active_quest = quest_system.get_active_quest("adv_001")
        # アクティブクエストは None になっている（完了済みのため）
        assert active_quest is None
        
        # 完了済みクエストを確認
        guild = quest_system.get_guild("guild_001")
        completed_quests = guild.completed_quests
        completed_quest = completed_quests.get(quest_id)
        
        assert completed_quest is not None
        assert completed_quest.status.value == "completed"
        
        # 進捗が完了していることを確認
        for condition in completed_quest.conditions:
            if condition.condition_type == "kill_monster":
                assert condition.current_count == 1
                assert condition.required_count == 1
                assert condition.is_completed()
                break
        
        # バトルでクエストが自動完了された場合、報酬も自動配布される
        # そのため提出は必要ない（または既に処理済みとして扱われる）
        
        # 報酬が正しく配布されたことを確認
        final_money = self.adventurer.get_money()
        final_exp = self.adventurer.get_experience_points()
        
        # バトル報酬が反映されていることを確認（クエスト報酬は自動配布済み）
        assert final_money > initial_money  # バトル報酬分
        assert final_exp > initial_exp  # バトル経験値も加算されている
        
        # アイテム報酬も確認
        slime_jelly_count = self.adventurer.get_item_count("slime_jelly")
        assert slime_jelly_count >= 1  # スライムゼリーがドロップしている
        
        # 冒険者の完了クエスト数が更新されていることを確認
        assert self.adventurer.get_completed_quest_count() == 1
    
    def test_multiple_monster_hunt_quests(self):
        """複数のモンスター討伐クエストを順次完了するテスト"""
        # 2体のスライム作成
        slime1 = Monster(
            monster_id="slime_001",
            name="スライム",
            description="ぷるぷるした青いスライム",
            monster_type=MonsterType.PASSIVE,
            max_hp=25,
            attack=4,
            defense=1,
            speed=3,
            drop_reward=MonsterDropReward(money=10, experience=5)
        )
        
        slime2 = Monster(
            monster_id="slime_002",
            name="スライム",
            description="ぷるぷるした青いスライム",
            monster_type=MonsterType.PASSIVE,
            max_hp=25,
            attack=4,
            defense=1,
            speed=3,
            drop_reward=MonsterDropReward(money=10, experience=5)
        )
        
        self.world.add_monster(slime1, "forest")
        self.world.add_monster(slime2, "forest")
        
        # 1体目のスライム討伐クエスト
        post_quest_action1 = PostQuestToGuild(
            description="ギルドにクエストを依頼する",
            guild_id="guild_001",
            quest_name="スライム討伐1",
            quest_description="最初のスライムを討伐してください",
            quest_type="monster_hunt",
            target="slime_001",
            target_count=1,
            difficulty="E",
            reward_money=80
        )
        result = self.world.execute_action("client_001", post_quest_action1)
        assert result["success"]
        
        # 2体目のスライム討伐クエスト
        post_quest_action2 = PostQuestToGuild(
            description="ギルドにクエストを依頼する",
            guild_id="guild_001",
            quest_name="スライム討伐2",
            quest_description="2体目のスライムを討伐してください",
            quest_type="monster_hunt",
            target="slime_002",
            target_count=1,
            difficulty="E",
            reward_money=80
        )
        result = self.world.execute_action("client_001", post_quest_action2)
        assert result["success"]
        
        # 1体目のクエストを受注
        view_action = ViewAvailableQuests(description="受注可能なクエストを確認する")
        result = self.world.execute_action("adv_001", view_action)
        assert result["count"] == 2
        
        # 最初のクエストを受注
        quest1_id = result["available_quests"][0]["quest_id"]
        accept_action1 = AcceptQuest(description="クエストを受注する", quest_id=quest1_id)
        result = self.world.execute_action("adv_001", accept_action1)
        assert result["success"]
        
        # 冒険者を森に移動
        self.adventurer.set_current_spot_id("forest")
        
        # 1体目を倒す（自動的にクエスト完了）
        self._complete_battle("adv_001", "slime_001", slime1)
        
        # 1体目のクエスト提出 - 削除（自動完了のため不要）
        # 冒険者の完了クエスト数を確認
        assert self.adventurer.get_completed_quest_count() == 1
        
        # 2体目のクエストを受注
        view_action2 = ViewAvailableQuests(description="受注可能なクエストを確認する")
        result = self.world.execute_action("adv_001", view_action2)
        assert result["count"] == 1
        
        quest2_id = result["available_quests"][0]["quest_id"]
        accept_action2 = AcceptQuest(description="クエストを受注する", quest_id=quest2_id)
        result = self.world.execute_action("adv_001", accept_action2)
        assert result["success"]
        
        # 2体目を倒す（自動的にクエスト完了）
        self._complete_battle("adv_001", "slime_002", slime2)
        
        # 2体目のクエスト提出 - 削除（自動完了のため不要）
        
        # 両方のスライムが倒されていることを確認
        assert not slime1.is_alive
        assert not slime2.is_alive
        
        # 冒険者の統計確認
        assert self.adventurer.get_completed_quest_count() == 2
    
    def test_quest_progress_not_updated_for_wrong_monster(self):
        """異なるモンスターを倒してもクエストが進捗しないことをテスト"""
        # 対象のゴブリン
        goblin = Monster(
            monster_id="goblin_001",
            name="ゴブリン",
            description="小さな緑の怪物",
            monster_type=MonsterType.PASSIVE,
            max_hp=30,
            attack=6,
            defense=2,
            speed=4
        )
        
        # 関係ないオーク
        orc = Monster(
            monster_id="orc_001",
            name="オーク",
            description="強力な緑色の戦士",
            monster_type=MonsterType.PASSIVE,
            max_hp=50,
            attack=10,
            defense=5,
            speed=5
        )
        
        self.world.add_monster(goblin, "forest")
        self.world.add_monster(orc, "forest")
        
        # ゴブリン討伐クエストを依頼
        post_quest_action = PostQuestToGuild(
            description="ギルドにクエストを依頼する",
            guild_id="guild_001",
            quest_name="ゴブリン討伐",
            quest_description="ゴブリンを討伐してください",
            quest_type="monster_hunt",
            target="goblin_001",
            target_count=1,
            difficulty="D",
            reward_money=120
        )
        result = self.world.execute_action("client_001", post_quest_action)
        assert result["success"]
        
        # クエスト受注
        view_action = ViewAvailableQuests(description="受注可能なクエストを確認する")
        result = self.world.execute_action("adv_001", view_action)
        quest_id = result["available_quests"][0]["quest_id"]
        
        accept_action = AcceptQuest(description="クエストを受注する", quest_id=quest_id)
        result = self.world.execute_action("adv_001", accept_action)
        assert result["success"]
        
        # 冒険者を森に移動
        self.adventurer.set_current_spot_id("forest")
        
        # バトル前のクエスト状態確認
        quest_system = self.world.get_quest_system()
        active_quest = quest_system.get_active_quest("adv_001")
        assert active_quest is not None
        assert active_quest.quest_id == quest_id
        
        # 間違ったモンスター（オーク）を倒す
        self._complete_battle("adv_001", "orc_001", orc)
        
        # オークが倒されたことを確認
        assert not orc.is_alive
        
        # 間違ったモンスターを倒してもクエストは完了していないことを確認
        active_quest = quest_system.get_active_quest("adv_001")
        assert active_quest is not None  # まだアクティブ
        
        # クエスト進捗が変わっていないことを確認
        for condition in active_quest.conditions:
            if condition.condition_type == "kill_monster":
                # 進捗が0のままであることを確認
                assert condition.current_count == 0
                break
        
        assert not active_quest.check_completion()
        
        # 正しいモンスター（ゴブリン）を倒す
        self._complete_battle("adv_001", "goblin_001", goblin)
        
        # ゴブリンが倒されたことを確認
        assert not goblin.is_alive
        
        # 正しいモンスターを倒すとクエストが自動完了されることを確認
        active_quest = quest_system.get_active_quest("adv_001")
        assert active_quest is None  # 自動完了でアクティブではなくなった
        
        # クエスト提出 - 削除（自動完了のため不要）
        # 冒険者の完了クエスト数を確認
        assert self.adventurer.get_completed_quest_count() == 1
    
    def _complete_battle(self, agent_id: str, monster_id: str, monster: Monster):
        """バトルを完了するヘルパーメソッド"""
        # バトル開始
        start_battle_action = StartBattle(description="戦闘を開始する", monster_id=monster_id)
        battle_id = self.world.execute_action(agent_id, start_battle_action)
        
        battle_manager = self.world.get_battle_manager()
        battle = battle_manager.get_battle(battle_id)
        
        max_turns = 20  # 無限ループ防止
        turn_count = 0
        
        while battle.state.value == "active" and monster.is_alive and turn_count < max_turns:
            current_actor = battle.get_current_actor()
            
            if current_actor == agent_id:
                # プレイヤーの攻撃
                attack_action = AttackMonster(description="モンスターを攻撃する", monster_id=monster_id)
                result = self.world.execute_action(agent_id, attack_action)
                
                if "戦闘終了" in str(result):
                    break
            
            turn_count += 1
        
        # モンスターが倒されたことを確認
        assert not monster.is_alive, f"モンスター {monster.name} が倒されていません" 