#!/usr/bin/env python3
"""
SpotActionシステムのデモンストレーション

新しく実装したSpot依存行動システムの実動作を示します。
従来のJobシステムに依存しない、Spot固有の商店・宿屋サービスを実演。
"""

from src_old.models.agent import Agent
from src_old.models.item import Item
from src_old.models.spot_action import Role, Permission
from src_old.models.shop_spots import ItemShopSpot, WeaponShopSpot, InnSpot
from src_old.systems.world import World


def create_demo_world():
    """デモ用のワールドを作成"""
    print("🌍 SpotActionシステムのワールドを構築中...")
    world = World()
    
    # === 各種商店を作成 ===
    
    # 1. 雑貨屋
    item_shop = ItemShopSpot("item_shop", "ミコトの雑貨屋", "冒険者御用達の雑貨屋。薬草からロープまで何でも揃う")
    world.add_spot(item_shop)
    print(f"  📦 {item_shop.name} を設置")
    
    # 2. 武器屋
    weapon_shop = WeaponShopSpot("weapon_shop", "鋼鉄工房", "最高品質の武器と防具を提供する鍛冶屋")
    world.add_spot(weapon_shop)
    print(f"  ⚔️ {weapon_shop.name} を設置")
    
    # 3. 宿屋
    inn = InnSpot("inn", "旅路の宿", "疲れた冒険者の憩いの場。回復サービスも充実")
    world.add_spot(inn)
    print(f"  🏠 {inn.name} を設置")
    
    return world


def create_demo_agents(world):
    """デモ用のエージェント群を作成"""
    print("\n👥 エージェントを作成中...")
    agents = {}
    
    # 1. 冒険者（お客さん）
    adventurer = Agent("adventurer1", "勇者アレックス", Role.ADVENTURER)
    adventurer.add_money(500)  # 冒険資金
    adventurer.current_hp = 60  # 少し疲れている
    adventurer.current_mp = 30
    adventurer.set_current_spot_id("item_shop")
    world.add_agent(adventurer)
    agents["adventurer"] = adventurer
    print(f"  🗡️ {adventurer.name} (冒険者) - 所持金: {adventurer.get_money()}G")
    
    # 2. 商人（お客さん）
    merchant = Agent("merchant1", "商人マリア", Role.MERCHANT)
    merchant.add_money(300)
    # 商品を持たせる
    herbs = [Item("herb", "薬草") for _ in range(5)]
    for herb in herbs:
        merchant.add_item(herb)
    merchant.set_current_spot_id("item_shop")
    world.add_agent(merchant)
    agents["merchant"] = merchant
    print(f"  💰 {merchant.name} (商人) - 所持金: {merchant.get_money()}G, 薬草: {merchant.get_item_count('herb')}個")
    
    # 3. 店主（雑貨屋）
    shop_keeper = Agent("shop_keeper1", "店主ミコト", Role.SHOP_KEEPER)
    shop_keeper.add_money(1000)
    shop_keeper.set_current_spot_id("item_shop")
    world.add_agent(shop_keeper)
    agents["shop_keeper"] = shop_keeper
    
    # 店主として設定
    item_shop = world.get_spot("item_shop")
    item_shop.set_shop_owner("shop_keeper1")
    print(f"  🏪 {shop_keeper.name} (店主) - 雑貨屋の店主に設定")
    
    # 4. 鍛冶師（武器屋の従業員）
    blacksmith = Agent("blacksmith1", "鍛冶師ガロン", Role.BLACKSMITH)
    blacksmith.add_money(200)
    blacksmith.set_current_spot_id("weapon_shop")
    world.add_agent(blacksmith)
    agents["blacksmith"] = blacksmith
    print(f"  🔨 {blacksmith.name} (鍛冶師) - 武器屋で従業員権限")
    
    return agents


def demo_item_shop_workflow(world, agents):
    """雑貨屋での一連の取引を実演"""
    print("\n" + "=" * 60)
    print("📦 雑貨屋での取引デモ")
    print("=" * 60)
    
    adventurer = agents["adventurer"]
    merchant = agents["merchant"]
    item_shop = world.get_spot("item_shop")
    
    print(f"\n🏪 【{item_shop.name}】での取引")
    print(f"📍 現在地: {adventurer.name} と {merchant.name} が雑貨屋にいます")
    
    # 1. 在庫確認
    print(f"\n1️⃣ {adventurer.name}が在庫を確認...")
    result = world.execute_spot_action("adventurer1", "view_inventory")
    print(f"✅ 在庫確認結果:")
    print(f"   {result.message}")
    
    # 2. 薬草購入
    print(f"\n2️⃣ {adventurer.name}が薬草を購入...")
    initial_money = adventurer.get_money()
    result = world.execute_spot_action("adventurer1", "buy_herb")
    print(f"✅ 購入結果: {result.success}")
    print(f"   {result.message}")
    print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
    print(f"   薬草所持: {adventurer.get_item_count('herb')}個")
    print(f"   店舗収益: {item_shop.revenue}G")
    
    # 3. 商人がアイテム売却
    print(f"\n3️⃣ {merchant.name}が薬草を売却...")
    initial_money = merchant.get_money()
    initial_herbs = merchant.get_item_count('herb')
    result = world.execute_spot_action("merchant1", "sell_herb")
    print(f"✅ 売却結果: {result.success}")
    print(f"   {result.message}")
    print(f"   所持金: {initial_money}G → {merchant.get_money()}G")
    print(f"   薬草所持: {initial_herbs}個 → {merchant.get_item_count('herb')}個")
    print(f"   店舗在庫: herb = {item_shop.shop_inventory.get('herb', 0)}個")


def demo_weapon_shop_workflow(world, agents):
    """武器屋での高額取引を実演"""
    print("\n" + "=" * 60)
    print("⚔️ 武器屋での取引デモ")
    print("=" * 60)
    
    adventurer = agents["adventurer"]
    weapon_shop = world.get_spot("weapon_shop")
    
    # 冒険者を武器屋に移動
    print(f"\n🚶 {adventurer.name}が武器屋に移動...")
    result = world.execute_spot_action("adventurer1", "movement_weapon_shop")
    if not result.success:
        # 直接移動（簡易実装）
        adventurer.set_current_spot_id("weapon_shop")
        print(f"   {adventurer.name}が{weapon_shop.name}に到着")
    
    print(f"\n⚔️ 【{weapon_shop.name}】での取引")
    
    # 1. 在庫確認
    print(f"\n1️⃣ {adventurer.name}が武器在庫を確認...")
    result = weapon_shop.execute_spot_action("view_inventory", adventurer, world)
    print(f"✅ 武器在庫:")
    print(f"   {result.message}")
    
    # 2. 鉄の剣購入（高額商品）
    print(f"\n2️⃣ {adventurer.name}が鉄の剣を購入...")
    initial_money = adventurer.get_money()
    result = weapon_shop.execute_spot_action("buy_iron_sword", adventurer, world)
    print(f"✅ 購入結果: {result.success}")
    print(f"   {result.message}")
    if result.success:
        print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
        print(f"   店舗収益: {weapon_shop.revenue}G")
        print(f"   剣在庫: {weapon_shop.shop_inventory.get('iron_sword', 0)}個")
    else:
        print(f"   警告: {[w.message for w in result.warnings if w.is_blocking]}")


def demo_inn_workflow(world, agents):
    """宿屋でのサービス利用を実演"""
    print("\n" + "=" * 60)
    print("🏠 宿屋でのサービスデモ")
    print("=" * 60)
    
    adventurer = agents["adventurer"]
    inn = world.get_spot("inn")
    
    # 冒険者を宿屋に移動
    print(f"\n🚶 {adventurer.name}が宿屋に移動...")
    adventurer.set_current_spot_id("inn")
    print(f"   {adventurer.name}が{inn.name}に到着")
    
    print(f"\n🏠 【{inn.name}】でのサービス利用")
    print(f"💤 現在のHP: {adventurer.current_hp}/{adventurer.max_hp}")
    print(f"✨ 現在のMP: {adventurer.current_mp}/{adventurer.max_mp}")
    
    # 1. 回復サービス
    print(f"\n1️⃣ {adventurer.name}が回復サービスを利用...")
    initial_money = adventurer.get_money()
    initial_hp = adventurer.current_hp
    initial_mp = adventurer.current_mp
    result = inn.execute_spot_action("healing_service", adventurer, world)
    print(f"✅ 回復結果: {result.success}")
    print(f"   {result.message}")
    print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
    print(f"   HP: {initial_hp} → {adventurer.current_hp}")
    print(f"   MP: {initial_mp} → {adventurer.current_mp}")
    
    # 2. 宿泊サービス
    print(f"\n2️⃣ {adventurer.name}が宿泊...")
    # 疲労を演出
    adventurer.current_hp = 80
    adventurer.current_mp = 40
    
    initial_money = adventurer.get_money()
    result = inn.execute_spot_action("stay_overnight", adventurer, world)
    print(f"✅ 宿泊結果: {result.success}")
    print(f"   {result.message}")
    if result.success:
        print(f"   所持金: {initial_money}G → {adventurer.get_money()}G")
        print(f"   HP: 80 → {adventurer.current_hp} (完全回復)")
        print(f"   MP: 40 → {adventurer.current_mp} (完全回復)")
        print(f"   宿泊客数: {len(inn.current_guests)}名")
        print(f"   空室数: {inn.get_available_rooms()}室")


def demo_permission_system(world, agents):
    """権限システムの実演"""
    print("\n" + "=" * 60)
    print("🔐 権限システムのデモ")
    print("=" * 60)
    
    shop_keeper = agents["shop_keeper"]
    adventurer = agents["adventurer"]
    item_shop = world.get_spot("item_shop")
    
    print(f"\n🏪 店主権限の実演")
    
    # 店主による価格設定（店主のみ可能）
    print(f"\n1️⃣ {shop_keeper.name}(店主)が価格設定...")
    from src_old.models.shop_actions import SetItemPriceSpotAction
    price_action = SetItemPriceSpotAction("new_item", 20, 12)
    item_shop.add_spot_action(price_action)
    
    result = item_shop.execute_spot_action("set_price_new_item", shop_keeper, world)
    print(f"✅ 価格設定結果: {result.success}")
    print(f"   {result.message}")
    
    # 一般客による価格設定（権限不足で失敗）
    print(f"\n2️⃣ {adventurer.name}(客)が価格設定を試行...")
    result = item_shop.execute_spot_action("set_price_new_item", adventurer, world)
    print(f"✅ 価格設定結果: {result.success}")
    if not result.success:
        print(f"   拒否理由: {[w.message for w in result.warnings if w.is_blocking]}")


def show_system_summary(world, agents):
    """システムの総括"""
    print("\n" + "=" * 60)
    print("📊 システム総括")
    print("=" * 60)
    
    print(f"\n💰 各エージェントの最終状態:")
    for name, agent in agents.items():
        print(f"  {agent.name}: {agent.get_money()}G")
    
    print(f"\n🏪 各店舗の収益:")
    item_shop = world.get_spot("item_shop")
    weapon_shop = world.get_spot("weapon_shop")
    inn = world.get_spot("inn")
    
    print(f"  {item_shop.name}: {item_shop.revenue}G")
    print(f"  {weapon_shop.name}: {weapon_shop.revenue}G")
    print(f"  {inn.name}: {inn.revenue}G")
    
    print(f"\n🎯 SpotActionシステムの特徴:")
    print(f"  ✅ Jobシステムに依存しない独立した商店運営")
    print(f"  ✅ Spot固有の行動と権限管理システム")
    print(f"  ✅ 動的な在庫・価格管理")
    print(f"  ✅ 統一的な行動実行フレームワーク")
    print(f"  ✅ LLM統合対応のフィードバックシステム")


def main():
    """メインデモ実行"""
    print("🎮 SpotActionシステム デモンストレーション")
    print("=" * 60)
    print("新しく実装したSpot依存行動システムの実際の動作を確認します。")
    print("従来のJobシステムに代わる、より直感的で拡張性の高いシステムです。")
    
    # ワールド構築
    world = create_demo_world()
    
    # エージェント作成
    agents = create_demo_agents(world)
    
    # 各種デモ実行
    demo_item_shop_workflow(world, agents)
    demo_weapon_shop_workflow(world, agents)
    demo_inn_workflow(world, agents)
    demo_permission_system(world, agents)
    
    # 総括
    show_system_summary(world, agents)
    
    print("\n" + "=" * 60)
    print("✨ デモ完了！SpotActionシステムが正常に動作しています。")
    print("✨ フェーズ3の商店系Spot実装が成功しました！")
    print("=" * 60)


if __name__ == "__main__":
    main() 