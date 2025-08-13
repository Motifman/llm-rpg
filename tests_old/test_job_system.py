import pytest
from src_old.models.job import JobAgent, JobType, Recipe, Service, CraftsmanAgent, MerchantAgent, AdventurerAgent, ProducerAgent
from src_old.models.item import Item
from src_old.models.action import CraftItem, EnhanceItem, LearnRecipe, SetupShop, ProvideService, GatherResource, ProcessMaterial, ManageFarm, AdvancedCombat
from src_old.systems.world import World


class TestJobAgent:
    """JobAgentの基本機能テスト"""
    
    def test_job_agent_creation(self):
        """JobAgentの作成とステータス確認"""
        agent = JobAgent("test_job_agent", "テスト職業エージェント", JobType.CRAFTSMAN)
        
        assert agent.agent_id == "test_job_agent"
        assert agent.name == "テスト職業エージェント"
        assert agent.job_type == JobType.CRAFTSMAN
        assert agent.job_level == 1
        assert agent.job_experience == 0
        
        # 職人のステータスボーナス確認
        assert agent.max_mp == 70  # 基本50 + 職人ボーナス20
        assert agent.current_mp == 70
    
    def test_job_level_up(self):
        """職業レベルアップのテスト"""
        agent = JobAgent("test_agent", "テストエージェント", JobType.ADVENTURER)
        initial_hp = agent.max_hp
        initial_attack = agent.attack
        
        # レベルアップ分の経験値を獲得
        agent.add_job_experience(100)
        
        assert agent.job_level == 2
        assert agent.job_experience == 0  # 余剰経験値はリセット
        assert agent.max_hp > initial_hp  # HPが増加
        assert agent.attack > initial_attack  # 冒険者なので攻撃力も増加
    
    def test_recipe_learning(self):
        """レシピ習得のテスト"""
        agent = JobAgent("craftsman", "職人", JobType.CRAFTSMAN)
        
        recipe = Recipe(
            recipe_id="test_recipe",
            name="テストレシピ",
            description="テスト用レシピ",
            required_materials={"material": 2},
            produced_item_id="product",
            required_job_level=1
        )
        
        # レシピを習得
        success = agent.learn_recipe(recipe)
        assert success is True
        assert len(agent.known_recipes) == 1
        assert agent.get_recipe_by_id("test_recipe") == recipe
        
        # 同じレシピの重複習得は失敗
        success = agent.learn_recipe(recipe)
        assert success is False
        assert len(agent.known_recipes) == 1


class TestCraftsmanAgent:
    """職人エージェントのテスト"""
    
    def test_craftsman_creation(self):
        """職人エージェントの作成とボーナス確認"""
        blacksmith = CraftsmanAgent("blacksmith1", "鍛冶師ボブ", "blacksmith")
        
        assert blacksmith.specialty == "blacksmith"
        assert blacksmith.enhancement_success_rate > 0.8  # 鍛冶師ボーナス
        assert "武器強化" in blacksmith.job_skills
        assert "防具作成" in blacksmith.job_skills
    
    def test_item_crafting(self):
        """アイテム合成のテスト"""
        craftsman = CraftsmanAgent("craftsman1", "職人", "alchemist")
        
        # 材料を追加
        material = Item("herb", "薬草")
        craftsman.add_item(material)
        craftsman.add_item(material)
        
        # レシピを追加
        recipe = Recipe(
            recipe_id="potion_recipe",
            name="ポーション作成",
            description="薬草からポーションを作成",
            required_materials={"herb": 2},
            produced_item_id="health_potion",
            produced_count=1,
            job_experience_gain=15
        )
        craftsman.learn_recipe(recipe)
        
        # アイテム合成実行
        result = craftsman.craft_item(recipe, 1)
        
        assert result["success"] is True
        assert len(result["created_items"]) == 1
        assert result["created_items"][0].item_id == "health_potion"
        assert result["experience_gained"] > 0
        assert craftsman.get_item_count("herb") == 0  # 材料が消費された
    
    def test_item_enhancement(self):
        """アイテム強化のテスト"""
        blacksmith = CraftsmanAgent("blacksmith1", "鍛冶師", "blacksmith")
        
        # 強化対象と材料を追加
        weapon = Item("iron_sword", "鉄の剣")
        enhancement_material = Item("magic_stone", "魔法石")
        
        blacksmith.add_item(weapon)
        blacksmith.add_item(enhancement_material)
        
        # アイテム強化実行
        result = blacksmith.enhance_item("iron_sword", {"magic_stone": 1})
        
        # 強化は確率なので、成功/失敗どちらもありうる
        if result["success"]:
            assert result["enhanced_item"] is not None
            assert result["enhanced_item"].item_id == "iron_sword_enhanced"
            assert blacksmith.has_item("iron_sword_enhanced")
            assert not blacksmith.has_item("iron_sword")  # 元アイテムは削除
        
        # 材料は必ず消費される
        assert not blacksmith.has_item("magic_stone")


class TestMerchantAgent:
    """商人エージェントのテスト"""
    
    def test_merchant_creation(self):
        """商人エージェントの作成とボーナス確認"""
        trader = MerchantAgent("trader1", "商人アリス", "trader")
        
        assert trader.business_type == "trader"
        assert trader.money == 100  # 商人の初期ボーナス
        assert trader.negotiation_skill > 1.0  # トレーダーボーナス
        assert "価格交渉" in trader.job_skills
    
    def test_shop_setup(self):
        """店舗設営のテスト"""
        merchant = MerchantAgent("merchant1", "商人", "general")
        merchant.set_current_spot_id("town_square")
        
        # 店舗設営
        result = merchant.setup_shop(
            "アリスの道具屋",
            "item_shop",
            {"potion": 50, "sword": 100},
            ["repair_service"]
        )
        
        assert result["success"] is True
        assert merchant.active_shop is not None
        assert merchant.active_shop["name"] == "アリスの道具屋"
        assert merchant.active_shop["location"] == "town_square"
        assert "potion" in merchant.active_shop["offered_items"]
    
    def test_service_provision(self):
        """サービス提供のテスト"""
        innkeeper = MerchantAgent("innkeeper1", "宿屋の主人", "innkeeper")
        
        # サービスを追加
        lodging_service = Service(
            service_id="lodging",
            name="宿泊サービス",
            description="一晩の宿泊を提供",
            price=20
        )
        innkeeper.add_service(lodging_service)
        
        # サービス提供
        result = innkeeper.provide_service("lodging", "customer1")
        
        assert result["success"] is True
        assert result["service_provided"] == lodging_service
        assert result["price_charged"] == 20
        assert result["experience_gained"] > 0
    
    def test_price_negotiation(self):
        """価格交渉のテスト"""
        trader = MerchantAgent("trader1", "商人", "trader")
        
        original_price = 100
        negotiated_price = trader.negotiate_price(original_price, 1.0)
        
        # 交渉スキルにより価格が下がる
        assert negotiated_price <= original_price
        assert negotiated_price >= 1  # 最低価格保証


class TestAdventurerAgent:
    """冒険者エージェントのテスト"""
    
    def test_adventurer_creation(self):
        """冒険者エージェントの作成とボーナス確認"""
        warrior = AdventurerAgent("warrior1", "戦士", "warrior")
        
        assert warrior.combat_class == "warrior"
        assert warrior.max_hp == 120  # 基本100 + 冒険者ボーナス20
        assert warrior.attack >= 20  # 基本10 + 冒険者ボーナス5 + 戦士ボーナス5
        assert "強攻撃" in warrior.combat_skills
    
    def test_mage_creation(self):
        """魔法使いタイプの冒険者テスト"""
        mage = AdventurerAgent("mage1", "魔法使い", "mage")
        
        assert mage.combat_class == "mage"
        assert mage.max_mp == 80  # 基本50 + 魔法使いボーナス30
        assert "魔法攻撃" in mage.combat_skills
    
    def test_combat_skill_usage(self):
        """戦闘スキル使用のテスト"""
        warrior = AdventurerAgent("warrior1", "戦士", "warrior")
        initial_mp = warrior.current_mp
        
        # 強攻撃スキル使用
        result = warrior.use_combat_skill("強攻撃")
        
        assert result["success"] is True
        assert result["skill_used"] == "強攻撃"
        assert result["mp_consumed"] > 0
        assert warrior.current_mp < initial_mp  # MPが消費された
        assert "damage_multiplier" in result["effect"]
    
    def test_healing_skill(self):
        """回復スキルのテスト"""
        healer = AdventurerAgent("healer1", "ヒーラー", "healer")
        
        # 回復魔法スキル使用
        result = healer.use_combat_skill("回復魔法", "target_agent")
        
        assert result["success"] is True
        assert result["target"] == "target_agent"
        assert "heal_amount" in result["effect"]


class TestProducerAgent:
    """一次産業者エージェントのテスト"""
    
    def test_producer_creation(self):
        """一次産業者エージェントの作成とボーナス確認"""
        farmer = ProducerAgent("farmer1", "農家", "farmer")
        
        assert farmer.production_type == "farmer"
        assert "農業知識" in farmer.job_skills
        assert "hoe" in farmer.gathering_tools
    
    def test_resource_gathering(self):
        """資源採集のテスト"""
        woodcutter = ProducerAgent("woodcutter1", "木こり", "woodcutter")
        
        # 道具を追加
        axe = Item("axe", "斧")
        woodcutter.add_item(axe)
        
        # 資源採集実行
        result = woodcutter.gather_resource("wood", "axe", 30)
        
        assert result["success"] is True
        assert len(result["gathered_items"]) > 0
        assert result["experience_gained"] > 0
        assert all(item.item_id == "wood" for item in result["gathered_items"])
    
    def test_material_processing(self):
        """材料加工のテスト"""
        farmer = ProducerAgent("farmer1", "農家", "farmer")
        
        # 原材料を追加
        wheat = Item("wheat_raw", "生小麦")
        farmer.add_item(wheat)
        farmer.add_item(wheat)
        
        # 材料加工実行
        result = farmer.process_material("wheat_raw", "wheat_flour", 2)
        
        assert result["success"] is True
        assert len(result["processed_items"]) == 2
        assert farmer.get_item_count("wheat_raw") == 0  # 原材料が消費
        assert farmer.get_item_count("wheat_flour") == 2  # 加工品が生成


class TestJobSystemIntegration:
    """JobシステムとWorldクラスの統合テスト"""
    
    def test_craftsman_world_integration(self):
        """職人とWorldの統合テスト"""
        world = World()
        
        # 職人エージェントを作成・追加
        craftsman = CraftsmanAgent("craftsman1", "職人", "alchemist")
        world.add_agent(craftsman)
        
        # 材料を追加
        herb = Item("herb", "薬草")
        craftsman.add_item(herb)
        craftsman.add_item(herb)
        
        # レシピを習得
        recipe = Recipe(
            recipe_id="health_potion",
            name="ヘルスポーション",
            description="薬草から作る回復薬",
            required_materials={"herb": 2},
            produced_item_id="health_potion"
        )
        craftsman.learn_recipe(recipe)
        
        # Worldを通じてアイテム合成を実行
        craft_action = CraftItem("アイテム合成", "health_potion", 1)
        result = world.execute_action("craftsman1", craft_action)
        
        assert result["success"] is True
        assert craftsman.has_item("health_potion")
    
    def test_merchant_world_integration(self):
        """商人とWorldの統合テスト"""
        world = World()
        
        # 商人エージェントを作成・追加
        merchant = MerchantAgent("merchant1", "商人", "trader")
        customer = JobAgent("customer1", "客", JobType.ADVENTURER)
        customer.add_money(100)  # 客に購入資金を追加
        
        world.add_agent(merchant)
        world.add_agent(customer)
        
        # サービスを追加
        service = Service(
            service_id="item_appraisal",
            name="アイテム鑑定",
            description="アイテムの価値を鑑定",
            price=25
        )
        merchant.add_service(service)
        
        # Worldを通じてサービス提供を実行
        service_action = ProvideService("サービス提供", "item_appraisal", "customer1")
        result = world.execute_action("merchant1", service_action)
        
        assert result["success"] is True
        assert customer.get_money() == 75  # 25ゴールド支払い
        assert merchant.get_money() == 125  # 25ゴールド受取り（初期100 + 25）
    
    def test_producer_world_integration(self):
        """一次産業者とWorldの統合テスト"""
        world = World()
        
        # 一次産業者エージェントを作成・追加
        miner = ProducerAgent("miner1", "鉱夫", "miner")
        world.add_agent(miner)
        
        # 道具を追加
        pickaxe = Item("pickaxe", "ツルハシ")
        miner.add_item(pickaxe)
        
        # Worldを通じて資源採集を実行
        gather_action = GatherResource("資源採集", "ore", "pickaxe", 45)
        result = world.execute_action("miner1", gather_action)
        
        assert result["success"] is True
        assert miner.get_item_count("ore") > 0
        assert result["experience_gained"] > 0


if __name__ == "__main__":
    pytest.main([__file__]) 