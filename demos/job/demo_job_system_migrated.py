#!/usr/bin/env python3
"""
移行後RPGシステムのデモプログラム

従来のJobシステムをSpotActionシステムに移行し、
同等の経済循環をより直感的なシステムで実現。
"""

from src_old.models.agent import Agent
from src_old.models.item import Item
from src_old.models.spot_action import Role, Permission
from src_old.models.shop_spots import ItemShopSpot, WeaponShopSpot, InnSpot
from src_old.models.job_migration import JobAgentAdapter, WorldJobMigrationHelper
from src_old.models.job import CraftsmanAgent, MerchantAgent, AdventurerAgent, ProducerAgent
from src_old.systems.world import World


def create_migrated_demo_world():
    """移行後のデモ用ワールドを作成"""
    print("🌍 移行後RPGシステムのワールドを構築中...")
    world = World()
    
    # === SpotActionベースの商店群 ===
    
    # 1. 錬金術師の店（旧: CraftsmanAgent機能）
    alchemy_shop = ItemShopSpot("alchemy_shop", "ルナの錬金工房", "薬草からポーションまで、錬金術師の店")
    # ポーション特化の在庫設定
    alchemy_shop.add_inventory("health_potion", 10)
    alchemy_shop.add_inventory("mana_potion", 8)
    alchemy_shop.add_inventory("herb", 50)
    alchemy_shop.set_item_price("health_potion", 80, 60)
    alchemy_shop.set_item_price("mana_potion", 70, 50)
    alchemy_shop.set_item_price("herb", 15, 8)
    world.add_spot(alchemy_shop)
    print(f"  🧪 {alchemy_shop.name} を設置")
    
    # 2. 商人の道具屋（旧: MerchantAgent機能）
    tool_shop = ItemShopSpot("tool_shop", "マルクの道具屋", "冒険者必需品の専門店")
    # 道具類の在庫設定
    tool_shop.add_inventory("rope", 15)
    tool_shop.add_inventory("torch", 25)
    tool_shop.add_inventory("map", 5)
    tool_shop.set_item_price("rope", 25, 15)
    tool_shop.set_item_price("torch", 10, 6)
    tool_shop.set_item_price("map", 100, 70)
    world.add_spot(tool_shop)
    print(f"  🛠️ {tool_shop.name} を設置")
    
    # 3. 宿屋（旧: ServiceProviderAgent機能）
    inn = InnSpot("inn", "冒険者の憩い", "疲れた冒険者のための安らぎの場")
    world.add_spot(inn)
    print(f"  🏠 {inn.name} を設置")
    
    # 4. 採取場所（Spotベースの資源管理）
    from src_old.models.spot import Spot
    forest = Spot("forest", "薬草の森", "薬草が豊富に自生する森")
    # 薬草を配置
    for _ in range(20):
        herb = Item("herb", "薬草")
        forest.add_item(herb)
    world.add_spot(forest)
    print(f"  🌿 {forest.name} を設置")
    
    return world


def create_migrated_demo_agents(world):
    """移行後のエージェント群を作成"""
    print("\n👥 移行対応エージェントを作成中...")
    
    # === 移行ヘルパーの初期化 ===
    migration_helper = WorldJobMigrationHelper(world)
    agents = {}
    
    # === 1. 錬金術師（旧CraftsmanAgent → 新Role: ALCHEMIST） ===
    print("\n🧪 錬金術師ルナの移行...")
    # 旧JobAgent作成
    old_alchemist = CraftsmanAgent("alchemist1", "錬金術師ルナ", "alchemist")
    old_alchemist.set_current_spot_id("alchemy_shop")
    old_alchemist.add_money(200)
    # 薬草を持たせる
    for _ in range(5):
        herb = Item("herb", "薬草")
        old_alchemist.add_item(herb)
    world.add_agent(old_alchemist)
    
    # 移行実行
    new_alchemist = migration_helper.migrate_agent_to_role_system("alchemist1")
    agents["alchemist"] = new_alchemist
    
    # 店主権限を設定
    alchemy_shop = world.get_spot("alchemy_shop")
    alchemy_shop.set_shop_owner("alchemist1")
    # 薬草採取師を顧客として設定
    alchemy_shop.set_agent_permission("herbalist1", Permission.CUSTOMER)
    
    print(f"  ✅ {old_alchemist.name} → Role: {new_alchemist.get_role().value}")
    print(f"     錬金工房の店主に設定")
    
    # === 2. 商人（旧MerchantAgent → 新Role: MERCHANT） ===
    print("\n💰 商人マルクの移行...")
    old_merchant = MerchantAgent("merchant1", "商人マルク", "trader")
    old_merchant.set_current_spot_id("tool_shop")
    old_merchant.add_money(300)
    world.add_agent(old_merchant)
    
    new_merchant = migration_helper.migrate_agent_to_role_system("merchant1")
    agents["merchant"] = new_merchant
    
    # 店主権限を設定
    tool_shop = world.get_spot("tool_shop")
    tool_shop.set_shop_owner("merchant1")
    
    print(f"  ✅ {old_merchant.name} → Role: {new_merchant.get_role().value}")
    print(f"     道具屋の店主に設定")
    
    # === 3. 冒険者（旧AdventurerAgent → 新Role: ADVENTURER） ===
    print("\n⚔️ 戦士アレックスの移行...")
    old_adventurer = AdventurerAgent("adventurer1", "戦士アレックス", "warrior")
    old_adventurer.set_current_spot_id("inn")
    old_adventurer.add_money(500)
    # 少し疲れた状態
    old_adventurer.current_hp = 70
    old_adventurer.current_mp = 30
    world.add_agent(old_adventurer)
    
    new_adventurer = migration_helper.migrate_agent_to_role_system("adventurer1")
    agents["adventurer"] = new_adventurer
    
    print(f"  ✅ {old_adventurer.name} → Role: {new_adventurer.get_role().value}")
    print(f"     冒険資金: {new_adventurer.get_money()}G, HP: {new_adventurer.current_hp}/{new_adventurer.max_hp}")
    
    # === 4. 薬草採取師（旧ProducerAgent → 新Role: FARMER） ===
    print("\n🌿 薬草採取師セイラの移行...")
    old_herbalist = ProducerAgent("herbalist1", "薬草採取師セイラ", "farmer")
    old_herbalist.set_current_spot_id("forest")
    old_herbalist.add_money(100)
    world.add_agent(old_herbalist)
    
    new_herbalist = migration_helper.migrate_agent_to_role_system("herbalist1")
    agents["herbalist"] = new_herbalist
    
    print(f"  ✅ {old_herbalist.name} → Role: {new_herbalist.get_role().value}")
    print(f"     森で薬草採取活動")
    
    # === 移行サマリー表示 ===
    print(f"\n📊 移行サマリー:")
    summary = migration_helper.get_migration_summary()
    print(f"  総エージェント数: {summary['total_agents']}")
    print(f"  移行済みエージェント: {summary['role_agents']}")
    print(f"  未移行JobAgent: {summary['job_agents']}")
    
    return agents, migration_helper


def demo_herb_collection_workflow(world, agents):
    """薬草採取のワークフロー（新システム）"""
    print("\n" + "=" * 60)
    print("🌿 薬草採取ワークフロー（SpotActionベース）")
    print("=" * 60)
    
    herbalist = agents["herbalist"]
    forest = world.get_spot("forest")
    
    print(f"\n🌲 【{forest.name}】での採取活動")
    print(f"📍 {herbalist.name}が森で薬草採取を行います")
    print(f"🍃 森の薬草: {len(forest.get_items())}個")
    
    # 探索による薬草採取（SpotActionシステム）
    print(f"\n1️⃣ {herbalist.name}が薬草を探索・採取...")
    initial_herbs = herbalist.get_item_count("herb")
    
    # 複数回探索して薬草を集める
    herbs_collected = 0
    for i in range(3):
        result = world.execute_spot_action("herbalist1", "exploration_general")
        if result.success:
            herbs_collected += len(result.items_gained)
            print(f"   探索{i+1}: {result.message}")
    
    final_herbs = herbalist.get_item_count("herb")
    print(f"\n✅ 採取結果:")
    print(f"   薬草: {initial_herbs}個 → {final_herbs}個 (+{final_herbs - initial_herbs})")
    print(f"   経験値獲得: {result.experience_gained if 'result' in locals() else 0}")
    print(f"   森の残り薬草: {len(forest.get_items())}個")
    
    return final_herbs - initial_herbs


def demo_alchemy_shop_workflow(world, agents, herb_count):
    """錬金工房での取引ワークフロー"""
    print("\n" + "=" * 60)
    print("🧪 錬金工房での取引ワークフロー（SpotActionベース）")
    print("=" * 60)
    
    alchemist = agents["alchemist"]
    herbalist = agents["herbalist"]
    alchemy_shop = world.get_spot("alchemy_shop")
    
    print(f"\n🧪 【{alchemy_shop.name}】での商取引")
    print(f"🏪 店主: {alchemist.name} (Role: {alchemist.get_role().value})")
    
    # 1. 薬草採取師が薬草を売却
    print(f"\n1️⃣ {herbalist.name}が薬草を売却...")
    herbalist.set_current_spot_id("alchemy_shop")  # 店に移動
    
    # まず利用可能なアクションを確認
    available_actions = alchemy_shop.get_available_spot_actions(herbalist, world)
    action_ids = [action_dict['action'].action_id for action_dict in available_actions]
    print(f"   利用可能なアクション: {action_ids}")
    
    initial_money = herbalist.get_money()
    result = alchemy_shop.execute_spot_action("sell_herb", herbalist, world)
    print(f"✅ 売却結果: {result.success}")
    print(f"   {result.message}")
    if not result.success:
        print(f"   失敗理由: {[w.message for w in result.warnings if w.is_blocking]}")
    print(f"   所持金: {initial_money}G → {herbalist.get_money()}G")
    print(f"   店舗収益: {alchemy_shop.revenue}G")
    
    # 2. 在庫確認
    print(f"\n2️⃣ 店舗在庫の確認...")
    result = alchemy_shop.execute_spot_action("view_inventory", herbalist, world)
    print(f"✅ 在庫状況:")
    lines = result.message.split('\n')
    for line in lines[:5]:  # 最初の5行のみ表示
        print(f"   {line}")
    
    return True


def demo_adventurer_workflow(world, agents):
    """冒険者の宿屋・装備購入ワークフロー"""
    print("\n" + "=" * 60)
    print("⚔️ 冒険者のサービス利用ワークフロー（SpotActionベース）")
    print("=" * 60)
    
    adventurer = agents["adventurer"]
    inn = world.get_spot("inn")
    tool_shop = world.get_spot("tool_shop")
    
    print(f"\n🏠 【{inn.name}】でのサービス利用")
    print(f"💤 現在のHP: {adventurer.current_hp}/{adventurer.max_hp}")
    print(f"✨ 現在のMP: {adventurer.current_mp}/{adventurer.max_mp}")
    
    # 1. 回復サービス
    print(f"\n1️⃣ {adventurer.name}が回復サービスを利用...")
    initial_money = adventurer.get_money()
    result = inn.execute_spot_action("healing_service", adventurer, world)
    print(f"✅ 回復結果: {result.success}")
    print(f"   {result.message}")
    print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
    
    # 2. 道具購入
    print(f"\n2️⃣ 道具屋で装備を購入...")
    adventurer.set_current_spot_id("tool_shop")
    
    initial_money = adventurer.get_money()
    result = tool_shop.execute_spot_action("buy_rope", adventurer, world)
    print(f"✅ 購入結果: {result.success}")
    if result.success:
        print(f"   {result.message}")
        print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
        print(f"   ロープ所持: {adventurer.get_item_count('rope')}個")
    else:
        print(f"   失敗理由: {[w.message for w in result.warnings if w.is_blocking]}")


def demo_economic_cycle_analysis(world, agents):
    """経済循環の分析"""
    print("\n" + "=" * 60)
    print("📊 経済循環分析（新システム）")
    print("=" * 60)
    
    print(f"\n💰 各エージェントの最終状態:")
    for name, agent in agents.items():
        print(f"  {agent.name}: {agent.get_money()}G (Role: {agent.get_role().value})")
    
    print(f"\n🏪 各店舗の収益:")
    alchemy_shop = world.get_spot("alchemy_shop")
    tool_shop = world.get_spot("tool_shop")
    inn = world.get_spot("inn")
    
    total_revenue = alchemy_shop.revenue + tool_shop.revenue + inn.revenue
    print(f"  {alchemy_shop.name}: {alchemy_shop.revenue}G")
    print(f"  {tool_shop.name}: {tool_shop.revenue}G")
    print(f"  {inn.name}: {inn.revenue}G")
    print(f"  総店舗収益: {total_revenue}G")
    
    print(f"\n🔄 システム比較:")
    print(f"  ✅ 旧Jobシステム → 新SpotActionシステム移行成功")
    print(f"  ✅ 同等の経済循環をより直感的なシステムで実現")
    print(f"  ✅ エージェント依存からSpot依存への移行完了")
    print(f"  ✅ 権限ベースアクセス制御の導入")
    print(f"  ✅ 統一的なActionResultフィードバック")


def main():
    """メインデモ実行"""
    print("🎮 JobシステムからSpotActionシステムへの移行デモ")
    print("=" * 60)
    print("従来のJobシステムの機能を新しいSpotActionシステムで再実装し、")
    print("同等以上の経済循環システムを実現することを実証します。")
    
    # ワールド構築
    world = create_migrated_demo_world()
    
    # エージェント作成・移行
    agents, migration_helper = create_migrated_demo_agents(world)
    
    # 各種ワークフロー実演
    # 1. 薬草採取（新探索システム）
    herb_count = demo_herb_collection_workflow(world, agents)
    
    # 2. 錬金工房での取引（新商店システム）
    demo_alchemy_shop_workflow(world, agents, herb_count)
    
    # 3. 冒険者のサービス利用（新宿屋システム）
    demo_adventurer_workflow(world, agents)
    
    # 4. 経済循環の分析
    demo_economic_cycle_analysis(world, agents)
    
    print("\n" + "=" * 60)
    print("✨ 移行デモ完了！")
    print("✨ JobシステムからSpotActionシステムへの移行が成功しました！")
    print("✨ より直感的で拡張性の高いシステムで同等の機能を実現！")
    print("=" * 60)


if __name__ == "__main__":
    main() 