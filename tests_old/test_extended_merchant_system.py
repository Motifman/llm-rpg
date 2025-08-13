import pytest
from src_old.models.job import ServiceProviderAgent, TraderAgent
from src_old.models.action import SellItem, BuyItem, SetItemPrice, ManageInventory, ProvideLodging, ProvideDance, ProvidePrayer
from src_old.models.item import Item
from src_old.systems.world import World


class TestServiceProviderAgent:
    """サービス提供者エージェントのテスト"""
    
    def test_innkeeper_creation(self):
        """宿屋経営者の作成テスト"""
        innkeeper = ServiceProviderAgent("innkeeper1", "親切な宿主", "innkeeper")
        assert innkeeper.service_type == "innkeeper"
        assert "宿泊サービス" in innkeeper.job_skills
        assert "接客術" in innkeeper.job_skills
        assert innkeeper.service_quality > 1.0
    
    def test_dancer_creation(self):
        """踊り子の作成テスト"""
        dancer = ServiceProviderAgent("dancer1", "優雅な踊り子", "dancer")
        assert dancer.service_type == "dancer"
        assert "舞踊技術" in dancer.job_skills
        assert "芸能知識" in dancer.job_skills
        assert dancer.max_mp >= 65  # ボーナスが適用されているか（基本50 + 15ボーナス）
    
    def test_priest_creation(self):
        """神官の作成テスト"""
        priest = ServiceProviderAgent("priest1", "慈悲深い神官", "priest")
        assert priest.service_type == "priest"
        assert "祈祷術" in priest.job_skills
        assert "治癒知識" in priest.job_skills
        assert priest.max_mp >= 70  # ボーナスが適用されているか（基本50 + 20ボーナス）
    
    def test_provide_lodging_service(self):
        """宿泊サービス提供テスト"""
        innkeeper = ServiceProviderAgent("innkeeper1", "親切な宿主", "innkeeper")
        
        # 宿泊サービス提供
        result = innkeeper.provide_lodging_service("guest1", 2, "deluxe")
        
        assert result["success"] is True
        assert result["nights"] == 2
        assert result["room_type"] == "deluxe"
        assert result["total_cost"] > 0
        assert "安全な宿泊" in result["services_provided"]
        assert "HP/MP全回復" in result["services_provided"]
        assert result["experience_gained"] > 0
        assert "guest1" in innkeeper.active_guests
    
    def test_provide_dance_service(self):
        """舞サービス提供テスト"""
        dancer = ServiceProviderAgent("dancer1", "優雅な踊り子", "dancer")
        
        # 舞サービス提供
        result = dancer.provide_dance_service("customer1", "energy_dance")
        
        assert result["success"] is True
        assert result["target_agent_id"] == "customer1"
        assert result["dance_type"] == "energy_dance"
        assert result["effects"]["mp_recovery"] == 60
        assert result["price"] > 0
        assert result["mp_consumed"] > 0
        assert result["experience_gained"] > 0
    
    def test_provide_prayer_service(self):
        """祈祷サービス提供テスト"""
        priest = ServiceProviderAgent("priest1", "慈悲深い神官", "priest")
        
        # 祈祷サービス提供
        result = priest.provide_prayer_service("customer1", "blessing")
        
        assert result["success"] is True
        assert result["target_agent_id"] == "customer1"
        assert result["prayer_type"] == "blessing"
        assert result["effects"]["hp_recovery"] == 30
        assert result["effects"]["mp_recovery"] == 30
        assert result["price"] > 0
        assert result["mp_consumed"] > 0
        assert result["experience_gained"] > 0
    
    def test_check_out_guest(self):
        """ゲストチェックアウトテスト"""
        innkeeper = ServiceProviderAgent("innkeeper1", "親切な宿主", "innkeeper")
        
        # 宿泊サービス提供
        innkeeper.provide_lodging_service("guest1", 1, "standard")
        
        # チェックアウト
        result = innkeeper.check_out_guest("guest1")
        
        assert result["success"] is True
        assert result["guest_agent_id"] == "guest1"
        assert result["final_bill"] > 0
        assert "guest1" not in innkeeper.active_guests


class TestTraderAgent:
    """商人エージェントのテスト"""
    
    def test_trader_creation(self):
        """商人の作成テスト"""
        trader = TraderAgent("trader1", "商売上手", "weapons")
        assert trader.trade_specialty == "weapons"
        assert "武器鑑定" in trader.job_skills
        assert "武器知識" in trader.job_skills
        assert "価格交渉" in trader.job_skills
        assert "商品管理" in trader.job_skills
    
    def test_sell_item_to_customer(self):
        """顧客への販売テスト"""
        trader = TraderAgent("trader1", "商売上手", "general")
        
        # 商品を追加
        sword = Item("sword", "鋭い剣")
        trader.add_item(sword)
        trader.set_item_price("sword", 50)
        
        # 販売実行
        result = trader.sell_item_to_customer("customer1", "sword", 1, 50)
        
        assert result["success"] is True
        assert result["customer_agent_id"] == "customer1"
        assert result["item_id"] == "sword"
        assert result["quantity"] == 1
        assert result["total_price"] == 50
        assert result["experience_gained"] > 0
        assert len(trader.sales_record) == 1
        assert trader.get_item_count("sword") == 0  # 販売後在庫なし
    
    def test_buy_item_from_customer(self):
        """顧客からの購入テスト"""
        trader = TraderAgent("trader1", "商売上手", "general")
        trader.add_money(100)  # 購入資金を追加
        
        # 購入実行
        result = trader.buy_item_from_customer("customer1", "herb", 2, 15)
        
        assert result["success"] is True
        assert result["customer_agent_id"] == "customer1"
        assert result["item_id"] == "herb"
        assert result["quantity"] == 2
        assert result["total_price"] == 30
        assert result["experience_gained"] > 0
        assert len(trader.purchase_record) == 1
        assert trader.get_item_count("herb") == 2
        assert trader.get_money() == 170  # 100 - 30 + 100（初期ボーナス）
    
    def test_set_item_price(self):
        """商品価格設定テスト"""
        trader = TraderAgent("trader1", "商売上手", "general")
        
        # 価格設定
        result = trader.set_item_price("sword", 75)
        
        assert result["success"] is True
        assert result["item_id"] == "sword"
        assert result["old_price"] == 0
        assert result["new_price"] == 75
        assert trader.item_prices["sword"] == 75
    
    def test_manage_shop_inventory(self):
        """店舗在庫管理テスト"""
        trader = TraderAgent("trader1", "商売上手", "general")
        
        # アイテムを追加
        potion = Item("potion", "回復薬")
        trader.add_item(potion)
        
        # 在庫表示（直接メソッド呼び出し）
        result = trader.manage_shop_inventory("view_inventory")
        
        assert result["success"] is True
        assert result["action_type"] == "view_inventory"
        assert "potion" in result["inventory_status"]
        assert result["inventory_status"]["potion"]["quantity"] == 1
    
    def test_get_sales_summary(self):
        """売上サマリーテスト"""
        trader = TraderAgent("trader1", "商売上手", "general")
        
        # 模擬売上記録追加
        trader.sales_record.append({
            "customer_id": "customer1",
            "item_id": "sword",
            "quantity": 1,
            "price_per_item": 50,
            "total_price": 50,
            "timestamp": "now"
        })
        
        trader.purchase_record.append({
            "seller_id": "customer2",
            "item_id": "herb",
            "quantity": 3,
            "price_per_item": 10,
            "total_cost": 30,
            "timestamp": "now"
        })
        
        summary = trader.get_sales_summary()
        
        assert summary["total_sales"] == 50
        assert summary["total_purchases"] == 30
        assert summary["net_profit"] == 20
        assert summary["sales_count"] == 1
        assert summary["purchase_count"] == 1


class TestWorldIntegration:
    """Worldシステムとの統合テスト"""
    
    def test_world_service_provider_integration(self):
        """Worldでのサービス提供者統合テスト"""
        world = World()
        
        # スポットとエージェントを追加
        from src_old.models.spot import Spot
        tavern = Spot("tavern", "賑やかな酒場", "町の中心にある酒場")
        world.add_spot(tavern)
        
        # サービス提供者とゲストを追加
        innkeeper = ServiceProviderAgent("innkeeper1", "親切な宿主", "innkeeper")
        innkeeper.set_current_spot_id("tavern")
        world.add_agent(innkeeper)
        
        from src_old.models.agent import Agent
        guest = Agent("guest1", "疲れた旅人")
        guest.set_current_spot_id("tavern")
        guest.add_money(200)
        world.add_agent(guest)
        
        # 宿泊サービス提供
        lodging_action = ProvideLodging("宿泊サービス提供", "guest1", 1, 50, "standard")
        result = world.execute_action("innkeeper1", lodging_action)
        
        assert result["success"] is True
        assert guest.current_hp == guest.max_hp  # HP全回復
        assert guest.current_mp == guest.max_mp  # MP全回復
        assert guest.get_money() == 150  # 50ゴールド支払い
    
    def test_world_trader_integration(self):
        """Worldでの商人統合テスト"""
        world = World()
        
        # スポットとエージェントを追加
        from src_old.models.spot import Spot
        market = Spot("market", "活気ある市場", "商人が集まる市場")
        world.add_spot(market)
        
        # 商人と顧客を追加
        trader = TraderAgent("trader1", "商売上手", "general")
        trader.set_current_spot_id("market")
        trader.add_item(Item("sword", "鋭い剣"))
        trader.set_item_price("sword", 60)
        world.add_agent(trader)
        
        from src_old.models.agent import Agent
        customer = Agent("customer1", "冒険者")
        customer.set_current_spot_id("market")
        customer.add_money(100)
        world.add_agent(customer)
        
        # アイテム販売
        sell_action = SellItem("剣を販売", "customer1", "sword", 1, 60)
        result = world.execute_action("trader1", sell_action)
        
        assert result["success"] is True
        assert customer.has_item("sword")  # 顧客がアイテムを取得
        assert customer.get_money() == 40  # 60ゴールド支払い
        assert trader.get_money() == 160  # 100（初期ボーナス）+ 60（売上）
    
    def test_invalid_service_provider_action(self):
        """無効なサービス提供者行動テスト"""
        world = World()
        
        # 通常のエージェントでサービス提供を試す
        from src_old.models.agent import Agent
        normal_agent = Agent("normal1", "普通の人")
        world.add_agent(normal_agent)
        
        lodging_action = ProvideLodging("宿泊サービス提供", "guest1", 1, 50, "standard")
        
        with pytest.raises(ValueError, match="サービス提供者ではありません"):
            world.execute_action("normal1", lodging_action)
    
    def test_invalid_trader_action(self):
        """無効な商人行動テスト"""
        world = World()
        
        # 通常のエージェントで販売を試す
        from src_old.models.agent import Agent
        normal_agent = Agent("normal1", "普通の人")
        world.add_agent(normal_agent)
        
        sell_action = SellItem("剣を販売", "customer1", "sword", 1, 50)
        
        with pytest.raises(ValueError, match="商人ではありません"):
            world.execute_action("normal1", sell_action)
    
    def test_cross_service_interaction(self):
        """複数サービス連携テスト"""
        world = World()
        
        # スポット設定
        from src_old.models.spot import Spot
        temple = Spot("temple", "静寂な神殿", "祈りを捧げる神殿")
        world.add_spot(temple)
        
        # サービス提供者たち
        priest = ServiceProviderAgent("priest1", "慈悲深い神官", "priest")
        priest.set_current_spot_id("temple")
        world.add_agent(priest)
        
        dancer = ServiceProviderAgent("dancer1", "優雅な踊り子", "dancer")
        dancer.set_current_spot_id("temple")
        world.add_agent(dancer)
        
        # 顧客
        from src_old.models.agent import Agent
        customer = Agent("customer1", "富裕な商人")
        customer.set_current_spot_id("temple")
        customer.add_money(500)
        customer.set_hp(50)  # 負傷状態
        customer.set_mp(30)  # MP減少状態
        world.add_agent(customer)
        
        # 祈祷サービス（HP回復）
        prayer_action = ProvidePrayer("祈祷サービス提供", "customer1", "healing_prayer", 56)
        result1 = world.execute_action("priest1", prayer_action)
        assert result1["success"] is True
        
        # 舞サービス（MP回復）
        dance_action = ProvideDance("舞サービス提供", "customer1", "healing_dance", 30)
        result2 = world.execute_action("dancer1", dance_action)
        assert result2["success"] is True
        
        # 両方のサービスで顧客が回復している
        assert customer.current_hp > 50  # HP回復
        assert customer.current_mp > 30  # MP回復
        assert customer.get_money() < 500  # 両方のサービス料金を支払い


if __name__ == "__main__":
    pytest.main([__file__]) 