#!/usr/bin/env python3
"""
拡張商人システムのデモ

ServiceProviderAgent（サービス提供者）とTraderAgent（商人）の
機能を実演し、実際の経済活動が行われることを示します。
"""

from src_old.models.job import ServiceProviderAgent, TraderAgent, CraftsmanAgent, ProducerAgent
from src_old.models.action import (
    SellItem, BuyItem, SetItemPrice, ManageInventory,
    ProvideLodging, ProvideDance, ProvidePrayer
)
from src_old.models.item import Item, ConsumableItem, ItemEffect
from src_old.models.spot import Spot
from src_old.models.agent import Agent
from src_old.systems.world import World


def create_world_and_agents():
    """世界とエージェントを作成"""
    print("=== 拡張商人システムの世界を構築中... ===\n")
    
    world = World()
    
    # スポットを作成
    spots = {
        "town_square": Spot("town_square", "町の広場", "商人や旅人が行き交う町の中心地"),
        "tavern": Spot("tavern", "憩いの酒場", "冒険者たちが集う賑やかな酒場"),
        "temple": Spot("temple", "聖なる神殿", "静寂に包まれた神々への祈りの場"),
        "market": Spot("market", "活気ある市場", "様々な商品が並ぶ商業地区"),
        "workshop": Spot("workshop", "職人の工房", "熟練の職人たちが働く作業場")
    }
    
    for spot in spots.values():
        world.add_spot(spot)
    
    # === サービス提供者たち ===
    
    # 宿屋の主人
    innkeeper = ServiceProviderAgent("innkeeper1", "アリス", "innkeeper")
    innkeeper.set_current_spot_id("tavern")
    innkeeper.add_money(300)
    print(f"🏠 宿屋の主人 {innkeeper.name} を酒場に配置")
    print(f"   職業スキル: {', '.join(innkeeper.job_skills)}")
    world.add_agent(innkeeper)
    
    # 踊り子
    dancer = ServiceProviderAgent("dancer1", "セレナ", "dancer")
    dancer.set_current_spot_id("tavern")
    dancer.add_money(150)
    print(f"💃 踊り子 {dancer.name} を酒場に配置")
    print(f"   職業スキル: {', '.join(dancer.job_skills)}")
    print(f"   MP: {dancer.current_mp}/{dancer.max_mp}")
    world.add_agent(dancer)
    
    # 神官
    priest = ServiceProviderAgent("priest1", "ベネディクト", "priest")
    priest.set_current_spot_id("temple")
    priest.add_money(200)
    print(f"⛪ 神官 {priest.name} を神殿に配置")
    print(f"   職業スキル: {', '.join(priest.job_skills)}")
    print(f"   MP: {priest.current_mp}/{priest.max_mp}")
    world.add_agent(priest)
    
    # === 商人たち ===
    
    # 武器商人
    weapon_trader = TraderAgent("trader1", "ガルト", "weapons")
    weapon_trader.set_current_spot_id("market")
    weapon_trader.add_money(500)
    
    # 武器在庫を追加
    weapons = [
        Item("iron_sword", "鉄の剣"),
        Item("steel_sword", "鋼の剣"),
        Item("shield", "盾"),
        Item("armor", "鎧")
    ]
    for weapon in weapons:
        weapon_trader.add_item(weapon)
    
    # 価格設定
    weapon_trader.set_item_price("iron_sword", 80)
    weapon_trader.set_item_price("steel_sword", 150)
    weapon_trader.set_item_price("shield", 60)
    weapon_trader.set_item_price("armor", 200)
    
    print(f"⚔️ 武器商人 {weapon_trader.name} を市場に配置")
    print(f"   専門分野: {weapon_trader.trade_specialty}")
    print(f"   職業スキル: {', '.join(weapon_trader.job_skills)}")
    print(f"   在庫: {[item.item_id for item in weapon_trader.get_items()]}")
    world.add_agent(weapon_trader)
    
    # ポーション商人
    potion_trader = TraderAgent("trader2", "マリア", "potions")
    potion_trader.set_current_spot_id("market")
    potion_trader.add_money(400)
    
    # ポーション在庫を追加
    potions = [
        ConsumableItem("health_potion", "ヘルスポーション", ItemEffect(hp_change=50)),
        ConsumableItem("mana_potion", "マナポーション", ItemEffect(mp_change=30)),
        ConsumableItem("energy_potion", "エナジーポーション", ItemEffect(hp_change=20, mp_change=20))
    ]
    for potion in potions:
        potion_trader.add_item(potion)
    
    # 価格設定
    potion_trader.set_item_price("health_potion", 40)
    potion_trader.set_item_price("mana_potion", 30)
    potion_trader.set_item_price("energy_potion", 50)
    
    print(f"🧪 ポーション商人 {potion_trader.name} を市場に配置")
    print(f"   専門分野: {potion_trader.trade_specialty}")
    print(f"   職業スキル: {', '.join(potion_trader.job_skills)}")
    print(f"   在庫: {[item.item_id for item in potion_trader.get_items()]}")
    world.add_agent(potion_trader)
    
    # === 顧客たち ===
    
    # 冒険者（疲労困憊）
    adventurer = Agent("adventurer1", "リク")
    adventurer.set_current_spot_id("town_square")
    adventurer.add_money(800)
    adventurer.set_hp(30)  # 負傷状態
    adventurer.set_mp(20)  # MP減少状態
    print(f"🗡️ 冒険者 {adventurer.name} を町の広場に配置")
    print(f"   状態: HP {adventurer.current_hp}/{adventurer.max_hp}, MP {adventurer.current_mp}/{adventurer.max_mp}")
    print(f"   所持金: {adventurer.get_money()}ゴールド")
    world.add_agent(adventurer)
    
    # 富裕な商人（顧客）
    merchant_customer = Agent("customer1", "エドワード")
    merchant_customer.set_current_spot_id("town_square")
    merchant_customer.add_money(1200)
    print(f"💰 富裕な商人 {merchant_customer.name} を町の広場に配置")
    print(f"   所持金: {merchant_customer.get_money()}ゴールド")
    world.add_agent(merchant_customer)
    
    # 錬金術師（アイテム供給者）
    alchemist = CraftsmanAgent("alchemist1", "ローザ", "alchemist")
    alchemist.set_current_spot_id("workshop")
    alchemist.add_money(600)
    
    # 錬金術師が材料を持参
    materials = [Item("rare_herb", "珍しい薬草"), Item("magic_crystal", "魔法の結晶")]
    for material in materials:
        alchemist.add_item(material)
    
    print(f"🔬 錬金術師 {alchemist.name} を工房に配置")
    print(f"   材料: {[item.item_id for item in alchemist.get_items()]}")
    world.add_agent(alchemist)
    
    print("\n" + "="*60 + "\n")
    return world


def demonstrate_service_economy(world):
    """サービス経済のデモンストレーション"""
    print("=== サービス経済のデモンストレーション ===\n")
    
    adventurer = world.get_agent("adventurer1")
    innkeeper = world.get_agent("innkeeper1")
    dancer = world.get_agent("dancer1")
    priest = world.get_agent("priest1")
    
    print(f"🗡️ 冒険者 {adventurer.name} の状態:")
    print(f"   HP: {adventurer.current_hp}/{adventurer.max_hp}")
    print(f"   MP: {adventurer.current_mp}/{adventurer.max_mp}")
    print(f"   所持金: {adventurer.get_money()}ゴールド")
    print(f"   現在地: {adventurer.get_current_spot_id()}\n")
    
    # 1. 酒場で宿泊サービス
    print("--- 1. 宿泊サービスの利用 ---")
    adventurer.set_current_spot_id("tavern")
    print(f"🏃 {adventurer.name} が酒場に移動")
    
    lodging_action = ProvideLodging("宿泊サービス提供", "adventurer1", 1, 55, "standard")
    result = world.execute_action("innkeeper1", lodging_action)
    
    print(f"🏠 宿屋の主人 {innkeeper.name} が宿泊サービスを提供:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   料金: {result['total_cost']}ゴールド")
    print(f"   宿屋の主人の経験値: +{result['experience_gained']}")
    print(f"   {adventurer.name} の回復後状態: HP {adventurer.current_hp}/{adventurer.max_hp}, MP {adventurer.current_mp}/{adventurer.max_mp}")
    print(f"   {adventurer.name} の残金: {adventurer.get_money()}ゴールド\n")
    
    # 2. 舞サービス
    print("--- 2. 舞サービスの利用 ---")
    dance_action = ProvideDance("舞サービス提供", "adventurer1", "energy_dance", 40)
    result = world.execute_action("dancer1", dance_action)
    
    print(f"💃 踊り子 {dancer.name} が舞サービスを提供:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   料金: {result['price']}ゴールド")
    print(f"   効果: {result['effects']}")
    print(f"   踊り子のMP消費: {result['mp_consumed']}")
    print(f"   {adventurer.name} の残金: {adventurer.get_money()}ゴールド\n")
    
    # 3. 神殿で祈祷サービス
    print("--- 3. 祈祷サービスの利用 ---")
    adventurer.set_current_spot_id("temple")
    print(f"🏃 {adventurer.name} が神殿に移動")
    
    # 軽い負傷を設定
    adventurer.set_hp(adventurer.max_hp - 25)
    print(f"⚔️ {adventurer.name} が軽い負傷を負った（HP: {adventurer.current_hp}/{adventurer.max_hp}）")
    
    prayer_action = ProvidePrayer("祈祷サービス提供", "adventurer1", "blessing", 58)
    result = world.execute_action("priest1", prayer_action)
    
    print(f"⛪ 神官 {priest.name} が祈祷サービスを提供:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   料金: {result['price']}ゴールド")
    print(f"   効果: {result['effects']}")
    print(f"   神官のMP消費: {result['mp_consumed']}")
    print(f"   {adventurer.name} の回復後状態: HP {adventurer.current_hp}/{adventurer.max_hp}")
    print(f"   {adventurer.name} の残金: {adventurer.get_money()}ゴールド\n")
    
    print("サービス提供者たちの売上:")
    print(f"   🏠 宿屋の主人 {innkeeper.name}: {innkeeper.get_money()}ゴールド")
    print(f"   💃 踊り子 {dancer.name}: {dancer.get_money()}ゴールド")
    print(f"   ⛪ 神官 {priest.name}: {priest.get_money()}ゴールド")
    print("\n" + "="*60 + "\n")


def demonstrate_trading_economy(world):
    """商品売買経済のデモンストレーション"""
    print("=== 商品売買経済のデモンストレーション ===\n")
    
    adventurer = world.get_agent("adventurer1")
    merchant_customer = world.get_agent("customer1")
    weapon_trader = world.get_agent("trader1")
    potion_trader = world.get_agent("trader2")
    alchemist = world.get_agent("alchemist1")
    
    # 1. 冒険者が武器を購入
    print("--- 1. 冒険者による武器購入 ---")
    adventurer.set_current_spot_id("market")
    print(f"🗡️ {adventurer.name} が市場に移動")
    
    # 在庫確認
    inventory_action = ManageInventory("在庫管理", "view_inventory")
    inventory_result = world.execute_action("trader1", inventory_action)
    print(f"⚔️ 武器商人 {weapon_trader.name} の在庫:")
    for item_id, info in inventory_result["inventory_status"].items():
        print(f"   {item_id}: {info['quantity']}個, 価格: {info['price']}ゴールド")
    print()
    
    # 剣を購入
    sell_action = SellItem("剣の販売", "adventurer1", "steel_sword", 1, 150)
    result = world.execute_action("trader1", sell_action)
    
    print(f"💰 購入取引:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   {adventurer.name} の新しい装備: {[item.item_id for item in adventurer.get_items()]}")
    print(f"   {adventurer.name} の残金: {adventurer.get_money()}ゴールド")
    print(f"   武器商人の売上: {weapon_trader.get_money()}ゴールド\n")
    
    # 2. ポーション購入
    print("--- 2. ポーション購入 ---")
    merchant_customer.set_current_spot_id("market")
    print(f"💰 {merchant_customer.name} が市場に移動")
    
    sell_action = SellItem("ポーション販売", "customer1", "health_potion", 1, 40)
    result = world.execute_action("trader2", sell_action)
    
    print(f"🧪 ポーション取引:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   {merchant_customer.name} の購入品: {[item.item_id for item in merchant_customer.get_items()]}")
    print(f"   {merchant_customer.name} の残金: {merchant_customer.get_money()}ゴールド")
    print(f"   ポーション商人の売上: {potion_trader.get_money()}ゴールド\n")
    
    # 3. 商人が錬金術師から材料を購入
    print("--- 3. 材料の仕入れ ---")
    potion_trader.set_current_spot_id("workshop")
    alchemist.set_current_spot_id("workshop")
    print(f"🧪 ポーション商人 {potion_trader.name} が工房に移動")
    
    buy_action = BuyItem("材料購入", "alchemist1", "rare_herb", 1, 25)
    result = world.execute_action("trader2", buy_action)
    
    print(f"🔬 材料仕入れ取引:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   錬金術師 {alchemist.name} の残金: {alchemist.get_money()}ゴールド")
    print(f"   ポーション商人の新材料: {[item.item_id for item in potion_trader.get_items()]}")
    print(f"   ポーション商人の残金: {potion_trader.get_money()}ゴールド\n")
    
    # 4. 売上サマリー
    print("--- 4. 商人たちの売上サマリー ---")
    weapon_summary = weapon_trader.get_sales_summary()
    potion_summary = potion_trader.get_sales_summary()
    
    print(f"⚔️ 武器商人 {weapon_trader.name}:")
    print(f"   総売上: {weapon_summary['total_sales']}ゴールド")
    print(f"   総仕入: {weapon_summary['total_purchases']}ゴールド")
    print(f"   純利益: {weapon_summary['net_profit']}ゴールド")
    print(f"   取引回数: 売上{weapon_summary['sales_count']}回, 仕入{weapon_summary['purchase_count']}回")
    
    print(f"🧪 ポーション商人 {potion_trader.name}:")
    print(f"   総売上: {potion_summary['total_sales']}ゴールド")
    print(f"   総仕入: {potion_summary['total_purchases']}ゴールド")
    print(f"   純利益: {potion_summary['net_profit']}ゴールド")
    print(f"   取引回数: 売上{potion_summary['sales_count']}回, 仕入{potion_summary['purchase_count']}回")
    
    print("\n" + "="*60 + "\n")


def demonstrate_complex_interaction(world):
    """複合的な経済活動のデモンストレーション"""
    print("=== 複合的な経済活動のデモンストレーション ===\n")
    
    merchant_customer = world.get_agent("customer1")
    innkeeper = world.get_agent("innkeeper1")
    weapon_trader = world.get_agent("trader1")
    
    print("--- 富裕な商人による豪華な一夜 ---")
    merchant_customer.set_current_spot_id("tavern")
    print(f"💰 {merchant_customer.name} が酒場に移動")
    print(f"   所持金: {merchant_customer.get_money()}ゴールド\n")
    
    # 1. 豪華宿泊サービス
    lodging_action = ProvideLodging("豪華宿泊サービス", "customer1", 2, 120, "suite")
    result = world.execute_action("innkeeper1", lodging_action)
    
    print("🏰 豪華な宿泊サービス:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   料金: {result['total_cost']}ゴールド")
    print(f"   {merchant_customer.name} の残金: {merchant_customer.get_money()}ゴールド\n")
    
    # 2. 舞と祈祷の両方を楽しむ
    dancer = world.get_agent("dancer1")
    priest = world.get_agent("priest1")
    
    # 舞サービス
    dance_action = ProvideDance("霊的舞踊", "customer1", "spiritual_dance", 55)
    result = world.execute_action("dancer1", dance_action)
    print("💃 霊的な舞のパフォーマンス:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   効果: {result['effects']}")
    print(f"   料金: {result['price']}ゴールド\n")
    
    # 神官を酒場に招待
    priest.set_current_spot_id("tavern")
    print(f"⛪ 神官 {priest.name} が酒場に招かれる")
    
    # 祈祷サービス
    prayer_action = ProvidePrayer("浄化の祈り", "customer1", "purification", 70)
    result = world.execute_action("priest1", prayer_action)
    print("🙏 浄化の祈り:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   効果: {result['effects']}")
    print(f"   料金: {result['price']}ゴールド\n")
    
    # 3. 贈り物として武器を購入
    merchant_customer.set_current_spot_id("market")
    print(f"💰 {merchant_customer.name} が市場で贈り物を購入")
    
    sell_action = SellItem("鎧の販売", "customer1", "armor", 1, 200)
    result = world.execute_action("trader1", sell_action)
    
    print("🎁 贈り物購入:")
    for message in result["messages"]:
        print(f"   {message}")
    print(f"   {merchant_customer.name} の最終残金: {merchant_customer.get_money()}ゴールド\n")
    
    print("--- 経済活動による全体的な資金循環 ---")
    total_circulation = 0
    
    agents = [
        ("🏠 宿屋の主人", innkeeper),
        ("💃 踊り子", dancer),
        ("⛪ 神官", priest),
        ("⚔️ 武器商人", weapon_trader),
        ("🧪 ポーション商人", world.get_agent("trader2")),
        ("💰 富裕な商人", merchant_customer),
        ("🗡️ 冒険者", world.get_agent("adventurer1")),
        ("🔬 錬金術師", world.get_agent("alchemist1"))
    ]
    
    for name, agent in agents:
        money = agent.get_money()
        total_circulation += money
        print(f"   {name} {agent.name}: {money}ゴールド")
    
    print(f"\n💰 経済圏全体の資金総額: {total_circulation}ゴールド")
    print("   → 様々な職業間で活発な経済活動が行われました！")
    
    print("\n" + "="*60)


def main():
    """メイン実行関数"""
    print("🏛️ 拡張商人システム経済デモ 🏛️")
    print("=" * 60)
    print("サービス提供者と商人による実践的な経済システムを実演します")
    print("=" * 60 + "\n")
    
    # 世界構築
    world = create_world_and_agents()
    
    # サービス経済デモ
    demonstrate_service_economy(world)
    
    # 商品売買経済デモ
    demonstrate_trading_economy(world)
    
    # 複合的経済活動デモ
    demonstrate_complex_interaction(world)
    
    print("\n🎉 デモンストレーション完了！")
    print("\n【実現された機能】")
    print("✅ ServiceProviderAgent: 宿泊・舞・祈祷サービス")
    print("✅ TraderAgent: 商品売買・在庫管理・価格設定")
    print("✅ 実際の金銭・アイテム・効果の授受")
    print("✅ 職業間の経済循環システム")
    print("✅ HP/MP回復などの実用的サービス効果")
    print("\n💡 RPG世界における真の経済システムが稼働しています！")


if __name__ == "__main__":
    main() 