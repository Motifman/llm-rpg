"""
商店系Spotシステムのテストケース

WeaponShopSpot、ItemShopSpot、InnSpotの動作を検証
"""

import pytest
from src.models.agent import Agent
from src.models.item import Item
from src.models.spot_action import Role, Permission
from src.models.shop_spots import ShopSpot, ItemShopSpot, WeaponShopSpot, InnSpot
from src.models.shop_actions import BuyItemSpotAction, SellItemSpotAction, ViewInventorySpotAction
from src.models.inn_actions import StayOvernightAction, HealingServiceAction
from src.systems.world import World


def test_shop_spot_basic():
    """基本的なShopSpotの機能テスト"""
    shop = ShopSpot("test_shop", "テスト商店", "テスト用の商店")
    
    # 基本属性の確認
    assert shop.shop_type == "general"
    assert shop.revenue == 0
    assert len(shop.shop_inventory) == 0
    
    # 在庫追加
    shop.add_inventory("herb", 10)
    assert shop.shop_inventory["herb"] == 10
    
    # 在庫削除
    removed = shop.remove_inventory("herb", 3)
    assert removed == 3
    assert shop.shop_inventory["herb"] == 7
    
    # 価格設定
    shop.set_item_price("herb", 15, 8)
    assert shop.item_prices["herb"]["buy_price"] == 15
    assert shop.item_prices["herb"]["sell_price"] == 8


def test_item_shop_spot():
    """ItemShopSpotの機能テスト"""
    shop = ItemShopSpot("item_shop", "雑貨屋", "何でも売っている雑貨屋")
    
    # 初期在庫の確認
    assert "herb" in shop.shop_inventory
    assert "bread" in shop.shop_inventory
    assert shop.shop_inventory["herb"] == 20
    
    # 初期価格の確認
    assert "herb" in shop.item_prices
    assert shop.item_prices["herb"]["buy_price"] == 15
    assert shop.item_prices["herb"]["sell_price"] == 8
    
    # 動的に生成された行動の確認
    assert "buy_herb" in shop.spot_actions
    assert "sell_herb" in shop.spot_actions


def test_buy_item_action():
    """アイテム購入行動のテスト"""
    world = World()
    shop = ItemShopSpot("item_shop", "雑貨屋", "何でも売っている雑貨屋")
    world.add_spot(shop)
    
    # 十分な資金を持つエージェント
    rich_agent = Agent("rich_agent", "金持ちエージェント", Role.ADVENTURER)
    rich_agent.add_money(100)
    rich_agent.set_current_spot_id("item_shop")
    world.add_agent(rich_agent)
    
    # 薬草購入
    result = shop.execute_spot_action("buy_herb", rich_agent, world)
    assert result.success
    assert rich_agent.get_money() == 85  # 100 - 15
    assert rich_agent.has_item("herb")
    assert shop.shop_inventory["herb"] == 19  # 20 - 1
    assert shop.revenue == 15
    
    # 資金不足のエージェント
    poor_agent = Agent("poor_agent", "貧乏エージェント", Role.CITIZEN)
    poor_agent.add_money(5)  # 薬草の価格15Gより少ない
    poor_agent.set_current_spot_id("item_shop")
    world.add_agent(poor_agent)
    
    result = shop.execute_spot_action("buy_herb", poor_agent, world)
    assert not result.success
    assert any("資金不足" in w.message for w in result.warnings)


def test_sell_item_action():
    """アイテム売却行動のテスト"""
    world = World()
    shop = ItemShopSpot("item_shop", "雑貨屋", "何でも売っている雑貨屋")
    world.add_spot(shop)
    
    # アイテムを持つエージェント
    agent = Agent("agent", "エージェント", Role.ADVENTURER)
    agent.add_money(50)
    herb = Item("herb", "薬草")
    agent.add_item(herb)
    agent.set_current_spot_id("item_shop")
    world.add_agent(agent)
    
    # 薬草売却
    result = shop.execute_spot_action("sell_herb", agent, world)
    assert result.success
    assert agent.get_money() == 58  # 50 + 8
    assert not agent.has_item("herb")
    assert shop.shop_inventory["herb"] == 21  # 20 + 1
    
    # アイテムを持たないエージェント
    result = shop.execute_spot_action("sell_herb", agent, world)
    assert not result.success
    assert any("アイテム不足" in w.message for w in result.warnings)


def test_view_inventory_action():
    """在庫確認行動のテスト"""
    world = World()
    shop = ItemShopSpot("item_shop", "雑貨屋", "何でも売っている雑貨屋")
    world.add_spot(shop)
    
    agent = Agent("agent", "エージェント", Role.ADVENTURER)
    agent.set_current_spot_id("item_shop")
    world.add_agent(agent)
    
    # 在庫確認
    result = shop.execute_spot_action("view_inventory", agent, world)
    assert result.success
    assert "herb" in result.message
    assert "bread" in result.message
    assert "在庫一覧" in result.message
    
    # 追加データの確認
    assert "inventory" in result.additional_data
    assert "prices" in result.additional_data
    assert result.additional_data["inventory"]["herb"] == 20


def test_weapon_shop_spot():
    """WeaponShopSpotの機能テスト"""
    shop = WeaponShopSpot("weapon_shop", "鍛冶屋", "武器と防具の専門店")
    
    # 武器屋の初期在庫確認
    assert "iron_sword" in shop.shop_inventory
    assert shop.shop_inventory["iron_sword"] == 3
    assert shop.item_prices["iron_sword"]["buy_price"] == 150
    
    # 鍛冶師の特別権限確認
    from src.models.spot_action import ActionPermissionChecker
    blacksmith = Agent("blacksmith", "鍛冶師", Role.BLACKSMITH)
    permission = shop.permission_checker.get_agent_permission(blacksmith)
    assert permission == Permission.EMPLOYEE


def test_inn_spot():
    """InnSpotの機能テスト"""
    inn = InnSpot("inn", "憩いの宿", "旅人の憩いの場")
    
    # 宿屋の基本属性確認
    assert inn.room_capacity == 10
    assert inn.room_rate == 50
    assert len(inn.current_guests) == 0
    assert inn.get_available_rooms() == 10
    
    # 部屋予約
    success = inn.book_room("agent1", 1)
    assert success
    assert "agent1" in inn.current_guests
    assert inn.get_available_rooms() == 9
    
    # 既に宿泊中のエージェントの重複予約
    success = inn.book_room("agent1", 1)
    assert not success  # 失敗
    
    # チェックアウト
    inn.checkout("agent1")
    assert "agent1" not in inn.current_guests
    assert inn.get_available_rooms() == 10


def test_inn_stay_overnight():
    """宿泊行動のテスト"""
    world = World()
    inn = InnSpot("inn", "憩いの宿", "旅人の憩いの場")
    world.add_spot(inn)
    
    # 疲れたエージェント（HP/MP減少）
    agent = Agent("agent", "疲れた冒険者", Role.ADVENTURER)
    agent.add_money(100)
    agent.current_hp = 50  # 最大100から減少
    agent.current_mp = 25  # 最大50から減少
    agent.set_current_spot_id("inn")
    world.add_agent(agent)
    
    # 宿泊
    result = inn.execute_spot_action("stay_overnight", agent, world)
    assert result.success
    assert agent.get_money() == 50  # 100 - 50
    assert agent.current_hp == agent.max_hp  # 完全回復
    assert agent.current_mp == agent.max_mp  # 完全回復
    assert "agent" in inn.current_guests
    assert inn.revenue == 50


def test_inn_healing_service():
    """回復サービスのテスト"""
    world = World()
    inn = InnSpot("inn", "憩いの宿", "旅人の憩いの場")
    world.add_spot(inn)
    
    # 負傷したエージェント
    agent = Agent("agent", "負傷した冒険者", Role.ADVENTURER)
    agent.add_money(50)
    agent.current_hp = 30
    agent.set_current_spot_id("inn")
    world.add_agent(agent)
    
    # 回復サービス
    result = inn.execute_spot_action("healing_service", agent, world)
    assert result.success
    assert agent.get_money() == 20  # 50 - 30
    assert agent.current_hp == agent.max_hp  # 完全回復
    assert inn.revenue == 30


def test_shop_permissions():
    """商店の権限システムのテスト"""
    shop = ItemShopSpot("item_shop", "雑貨屋", "何でも売っている雑貨屋")
    
    # 店主設定
    shop.set_shop_owner("shop_owner")
    assert shop.shop_owner_id == "shop_owner"
    
    # 店主権限確認
    owner = Agent("shop_owner", "店主", Role.SHOP_KEEPER)
    permission = shop.permission_checker.get_agent_permission(owner)
    assert permission == Permission.OWNER
    
    # 一般客権限確認
    customer = Agent("customer", "客", Role.CITIZEN)
    permission = shop.permission_checker.get_agent_permission(customer)
    assert permission == Permission.CUSTOMER


if __name__ == "__main__":
    # 基本テストを実行
    print("🧪 商店系Spotシステムのテスト開始")
    
    test_shop_spot_basic()
    print("✅ 基本ShopSpotテスト完了")
    
    test_item_shop_spot()
    print("✅ ItemShopSpotテスト完了")
    
    test_buy_item_action()
    print("✅ 購入行動テスト完了")
    
    test_sell_item_action()
    print("✅ 売却行動テスト完了")
    
    test_view_inventory_action()
    print("✅ 在庫確認行動テスト完了")
    
    test_weapon_shop_spot()
    print("✅ WeaponShopSpotテスト完了")
    
    test_inn_spot()
    print("✅ InnSpot基本テスト完了")
    
    test_inn_stay_overnight()
    print("✅ 宿泊行動テスト完了")
    
    test_inn_healing_service()
    print("✅ 回復サービステスト完了")
    
    test_shop_permissions()
    print("✅ 権限システムテスト完了")
    
    print("🎉 すべてのテストが完了しました！") 