#!/usr/bin/env python3
"""
Jobシステムのデモプログラム

各職業の特徴的な行動を実演し、RPG世界での経済循環を示します。
"""

from src.models.job import (
    JobAgent, JobType, Recipe, Service,
    CraftsmanAgent, MerchantAgent, AdventurerAgent, ProducerAgent
)
from src.models.item import Item
from src.models.action import (
    CraftItem, EnhanceItem, SetupShop, ProvideService,
    GatherResource, ProcessMaterial, ManageFarm, AdvancedCombat
)
from src.models.spot import Spot
from src.systems.world import World


def create_demo_world():
    """デモ用の世界を作成"""
    world = World()
    
    # スポットの作成
    town = Spot("town", "町", "活気ある商業都市")
    forest = Spot("forest", "森", "資源豊富な森林")
    mine = Spot("mine", "鉱山", "鉱物が採れる鉱山")
    
    world.add_spot(town)
    world.add_spot(forest)
    world.add_spot(mine)
    
    return world


def create_demo_agents(world):
    """デモ用のエージェントを作成"""
    agents = {}
    
    # 職人エージェント（錬金術師）
    alchemist = CraftsmanAgent("alchemist1", "錬金術師ルナ", "alchemist")
    alchemist.set_current_spot_id("town")
    
    # ポーション作成レシピを習得
    potion_recipe = Recipe(
        recipe_id="health_potion",
        name="ヘルスポーション",
        description="薬草から作る回復薬",
        required_materials={"herb": 2},
        produced_item_id="health_potion",
        produced_count=1,
        job_experience_gain=15
    )
    alchemist.learn_recipe(potion_recipe)
    
    # 商人エージェント（道具屋）
    merchant = MerchantAgent("merchant1", "商人マルク", "trader")
    merchant.set_current_spot_id("town")
    
    # 鑑定サービスを追加
    appraisal_service = Service(
        service_id="item_appraisal",
        name="アイテム鑑定",
        description="アイテムの価値と品質を鑑定",
        price=30
    )
    merchant.add_service(appraisal_service)
    
    # 冒険者エージェント（戦士）
    adventurer = AdventurerAgent("adventurer1", "戦士アレックス", "warrior")
    adventurer.set_current_spot_id("town")
    adventurer.add_money(200)  # 購入資金
    
    # 一次産業者エージェント（薬草採取師）
    herbalist = ProducerAgent("herbalist1", "薬草採取師セイラ", "farmer")
    herbalist.set_current_spot_id("forest")
    
    # 採取道具を追加
    gathering_knife = Item("gathering_knife", "採取用ナイフ")
    herbalist.add_item(gathering_knife)
    
    # 世界にエージェントを追加
    for agent in [alchemist, merchant, adventurer, herbalist]:
        world.add_agent(agent)
    
    agents = {
        "alchemist": alchemist,
        "merchant": merchant,
        "adventurer": adventurer,
        "herbalist": herbalist
    }
    
    return agents


def demo_producer_workflow(world, agents):
    """一次産業者のワークフローデモ"""
    print("=" * 60)
    print("🌿 一次産業者（薬草採取師）のワークフロー")
    print("=" * 60)
    
    herbalist = agents["herbalist"]
    print(f"📍 {herbalist.name}は{herbalist.current_spot_id}にいます")
    print(f"💰 初期状態: {herbalist.get_job_status_summary()}")
    
    # 薬草採取
    print("\n🌱 薬草を採取しています...")
    gather_action = GatherResource("薬草採取", "herb", "gathering_knife", 60)
    result = world.execute_action("herbalist1", gather_action)
    
    print(f"✅ 採取結果: {result['success']}")
    print(f"📦 獲得アイテム: {len(result['gathered_items'])}個の薬草")
    print(f"⭐ 経験値獲得: {result['experience_gained']}")
    print(f"📊 更新後ステータス: {herbalist.get_job_status_summary()}")
    
    return result


def demo_craftsman_workflow(world, agents, herb_count):
    """職人のワークフローデモ"""
    print("\n" + "=" * 60)
    print("⚗️ 職人（錬金術師）のワークフロー")
    print("=" * 60)
    
    alchemist = agents["alchemist"]
    herbalist = agents["herbalist"]
    
    print(f"📍 {alchemist.name}は{alchemist.current_spot_id}にいます")
    print(f"💰 初期状態: {alchemist.get_job_status_summary()}")
    
    # 薬草採取師から材料を購入（簡易実装：直接譲渡）
    print(f"\n🤝 {herbalist.name}から薬草を購入...")
    herbs_to_transfer = min(4, herb_count)  # 最大4個
    for _ in range(herbs_to_transfer):
        herb = herbalist.get_item_by_id("herb")
        if herb:
            herbalist.remove_item(herb)
            alchemist.add_item(herb)
    
    payment = herbs_to_transfer * 10  # 1個10ゴールド
    alchemist.add_money(-payment)
    herbalist.add_money(payment)
    print(f"💳 {payment}ゴールドで{herbs_to_transfer}個の薬草を購入")
    
    # ポーション作成
    print(f"\n🧪 ヘルスポーションを作成しています...")
    print(f"📋 必要材料: 薬草2個（所持: {alchemist.get_item_count('herb')}個）")
    
    craft_action = CraftItem("ポーション作成", "health_potion", 1)
    result = world.execute_action("alchemist1", craft_action)
    
    print(f"✅ 作成結果: {result['success']}")
    if result['success']:
        print(f"🧪 作成されたポーション: {len(result['created_items'])}個")
        print(f"📦 消費材料: {result['consumed_materials']}")
        print(f"⭐ 経験値獲得: {result['experience_gained']}")
    
    print(f"📊 更新後ステータス: {alchemist.get_job_status_summary()}")
    
    return result


def demo_merchant_workflow(world, agents):
    """商人のワークフローデモ"""
    print("\n" + "=" * 60)
    print("🏪 商人（道具屋）のワークフロー")
    print("=" * 60)
    
    merchant = agents["merchant"]
    adventurer = agents["adventurer"]
    
    print(f"📍 {merchant.name}は{merchant.current_spot_id}にいます")
    print(f"💰 初期状態: {merchant.get_job_status_summary()}")
    
    # 店舗設営
    print(f"\n🏪 店舗を設営しています...")
    shop_action = SetupShop(
        "店舗設営",
        "マルクの道具屋",
        "item_shop",
        {"health_potion": 80, "weapon": 150},
        ["item_appraisal"]
    )
    result = world.execute_action("merchant1", shop_action)
    
    print(f"✅ 設営結果: {result['success']}")
    print(f"🏪 店舗名: {result['shop_info']['name']}")
    print(f"📦 販売商品: {result['shop_info']['offered_items']}")
    print(f"🛠️ 提供サービス: {result['shop_info']['offered_services']}")
    
    # アイテム鑑定サービス提供
    print(f"\n🔍 {adventurer.name}にアイテム鑑定サービスを提供...")
    print(f"💰 {adventurer.name}の所持金: {adventurer.get_money()}ゴールド")
    
    service_action = ProvideService("鑑定サービス", "item_appraisal", "adventurer1")
    result = world.execute_action("merchant1", service_action)
    
    print(f"✅ サービス提供結果: {result['success']}")
    if result['success']:
        print(f"🔍 提供サービス: {result['service_provided'].name}")
        print(f"💳 料金: {result['price_charged']}ゴールド")
        print(f"⭐ 経験値獲得: {result['experience_gained']}")
    
    print(f"💰 {merchant.name}の所持金: {merchant.get_money()}ゴールド")
    print(f"💰 {adventurer.name}の所持金: {adventurer.get_money()}ゴールド")
    print(f"📊 更新後ステータス: {merchant.get_job_status_summary()}")
    
    return result


def demo_adventurer_workflow(world, agents):
    """冒険者のワークフローデモ"""
    print("\n" + "=" * 60)
    print("⚔️ 冒険者（戦士）のワークフロー")
    print("=" * 60)
    
    adventurer = agents["adventurer"]
    
    print(f"📍 {adventurer.name}は{adventurer.current_spot_id}にいます")
    print(f"💰 初期状態: {adventurer.get_job_status_summary()}")
    print(f"🗡️ 戦闘ステータス: HP={adventurer.current_hp}/{adventurer.max_hp}, "
          f"MP={adventurer.current_mp}/{adventurer.max_mp}, 攻撃={adventurer.attack}")
    
    # 戦闘スキル使用
    print(f"\n⚔️ 強攻撃スキルを使用...")
    combat_action = AdvancedCombat("強攻撃発動", "強攻撃", None, 1)
    result = world.execute_action("adventurer1", combat_action)
    
    print(f"✅ スキル使用結果: {result['success']}")
    if result['success']:
        print(f"⚔️ 使用スキル: {result['skill_used']}")
        print(f"⚡ 効果: {result['effect']}")
        print(f"💙 MP消費: {result['mp_consumed']}")
    
    print(f"🗡️ スキル使用後ステータス: HP={adventurer.current_hp}/{adventurer.max_hp}, "
          f"MP={adventurer.current_mp}/{adventurer.max_mp}")
    print(f"📊 更新後ステータス: {adventurer.get_job_status_summary()}")
    
    return result


def demo_economic_cycle(world, agents):
    """経済循環のデモ"""
    print("\n" + "=" * 60)
    print("💰 RPG世界の経済循環")
    print("=" * 60)
    
    print("🔄 各職業が連携して価値を創造:")
    print("   1. 一次産業者 → 原材料採集")
    print("   2. 職人 → 原材料を加工して製品化")
    print("   3. 商人 → 製品・サービスの流通")
    print("   4. 冒険者 → 消費者として経済を回す")
    
    # 全エージェントの最終状態
    print("\n📊 各エージェントの最終状態:")
    for name, agent in agents.items():
        print(f"   {agent.name}: 所持金={agent.get_money()}ゴールド, {agent.get_job_status_summary()}")
        items = [item.item_id for item in agent.get_items()]
        if items:
            print(f"      所持アイテム: {items}")
    
    # 経済効果の分析
    total_money = sum(agent.get_money() for agent in agents.values())
    total_experience = sum(agent.job_experience for agent in agents.values())
    total_items = sum(len(agent.get_items()) for agent in agents.values())
    
    print(f"\n📈 経済指標:")
    print(f"   💰 総流通資金: {total_money}ゴールド")
    print(f"   ⭐ 総職業経験値: {total_experience}")
    print(f"   📦 総アイテム数: {total_items}")


def main():
    """メインデモ実行"""
    print("🎮 RPG世界 Jobシステム デモプログラム")
    print("=" * 60)
    print("各職業の特徴的な機能と、経済循環を実演します。")
    
    # 世界とエージェントの初期化
    world = create_demo_world()
    agents = create_demo_agents(world)
    
    # 各職業のワークフロー実演
    # 1. 一次産業者（薬草採取）
    producer_result = demo_producer_workflow(world, agents)
    herb_count = len(producer_result['gathered_items'])
    
    # 2. 職人（ポーション作成）
    craftsman_result = demo_craftsman_workflow(world, agents, herb_count)
    
    # 3. 商人（店舗運営・サービス）
    merchant_result = demo_merchant_workflow(world, agents)
    
    # 4. 冒険者（戦闘スキル）
    adventurer_result = demo_adventurer_workflow(world, agents)
    
    # 5. 経済循環の総括
    demo_economic_cycle(world, agents)
    
    print("\n" + "=" * 60)
    print("✨ デモ完了！Jobシステムが正常に動作しています。")
    print("=" * 60)


if __name__ == "__main__":
    main() 