"""
ConsumableItem合成機能のデモンストレーション
CraftsmanAgentがConsumableItemを作成し、それを使用する一連の流れを実演
"""

from src.models.spot import Spot
from src.models.agent import Agent
from src.models.item import Item, ConsumableItem, ItemEffect
from src.models.job import CraftsmanAgent, AdventurerAgent, Recipe
from src.models.action import CraftItem, ItemUsage
from src.systems.world import World


def create_demo_world():
    """デモ用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    town = Spot("town", "魔法都市アルケミア", "錬金術師が多く住む魔法の街")
    forest = Spot("enchanted_forest", "魔法の森", "魔法の材料が採れる不思議な森")
    
    world.add_spot(town)
    world.add_spot(forest)
    
    return world


def create_demo_agents(world):
    """デモ用のエージェントを作成"""
    agents = {}
    
    # === 錬金術師エージェント ===
    alchemist = CraftsmanAgent("alchemist1", "錬金術師エリカ", "alchemist")
    alchemist.set_current_spot_id("town")
    alchemist.add_money(150)
    
    # === ConsumableItemレシピを習得 ===
    
    # 1. ヘルスポーション（HP回復）
    health_potion_recipe = Recipe(
        recipe_id="health_potion",
        name="ヘルスポーション",
        description="薬草から作る基本的な回復薬",
        required_materials={"herb": 2},
        produced_item_id="health_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(hp_change=30),
        produced_count=1,
        max_stack=5,
        job_experience_gain=15
    )
    alchemist.learn_recipe(health_potion_recipe)
    
    # 2. マナポーション（MP回復）
    mana_potion_recipe = Recipe(
        recipe_id="mana_potion",
        name="マナポーション",
        description="魔力草から作る魔力回復薬",
        required_materials={"magic_herb": 1, "crystal_powder": 1},
        produced_item_id="mana_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(mp_change=25),
        produced_count=1,
        max_stack=3,
        job_experience_gain=20
    )
    alchemist.learn_recipe(mana_potion_recipe)
    
    # 3. 力のポーション（攻撃力上昇）
    strength_potion_recipe = Recipe(
        recipe_id="strength_potion",
        name="力のポーション",
        description="戦士の筋力を向上させる薬",
        required_materials={"power_herb": 3, "beast_fang": 1},
        produced_item_id="strength_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(attack_change=8, hp_change=10),
        produced_count=1,
        max_stack=2,
        job_experience_gain=30
    )
    alchemist.learn_recipe(strength_potion_recipe)
    
    # 4. 万能エリクサー（全能力回復・強化） - 後でレベルアップ後に習得
    elixir_recipe = Recipe(
        recipe_id="grand_elixir",
        name="万能エリクサー",
        description="全ての能力を回復・強化する究極のポーション",
        required_materials={"rare_herb": 5, "dragon_scale": 1, "pure_water": 3},
        produced_item_id="grand_elixir",
        produced_item_type="consumable",
        item_effect=ItemEffect(
            hp_change=50,
            mp_change=40,
            attack_change=10,
            defense_change=5,
            experience_change=100
        ),
        produced_count=1,
        max_stack=1,
        required_job_level=3,
        job_experience_gain=100,
        success_rate=0.7
    )
    # レベル1では習得できないので、後でレベルアップ後に習得する
    # alchemist.learn_recipe(elixir_recipe)
    
    # === 冒険者エージェント ===
    adventurer = AdventurerAgent("warrior1", "戦士レオン", "warrior")
    adventurer.set_current_spot_id("town")
    adventurer.add_money(300)
    
    # 冒険者の初期状態（少し消耗した状態）
    adventurer.set_hp(60)  # HP減少
    adventurer.set_mp(30)  # MP減少
    
    # === 世界にエージェントを追加 ===
    world.add_agent(alchemist)
    world.add_agent(adventurer)
    
    agents = {
        "alchemist": alchemist,
        "adventurer": adventurer
    }
    
    return agents


def prepare_crafting_materials(agents):
    """合成用の材料を準備"""
    alchemist = agents["alchemist"]
    
    print("\n📦 錬金術師に材料を供給...")
    
    # 基本材料
    materials = [
        ("herb", 8, "薬草"),
        ("magic_herb", 4, "魔力草"),
        ("crystal_powder", 4, "クリスタルの粉"),
        ("power_herb", 6, "力の薬草"),
        ("beast_fang", 2, "獣の牙"),
        ("rare_herb", 10, "希少薬草"),
        ("dragon_scale", 2, "ドラゴンの鱗"),
        ("pure_water", 6, "聖水")
    ]
    
    for material_id, count, description in materials:
        for _ in range(count):
            item = Item(material_id, description)
            alchemist.add_item(item)
        print(f"  📋 {description}: {count}個")
    
    print(f"✅ 材料準備完了！")


def demo_potion_crafting_workflow(world, agents):
    """ポーション作成ワークフローのデモ"""
    print("\n" + "=" * 70)
    print("🧪 ConsumableItem合成デモ - ポーション工房")
    print("=" * 70)
    
    alchemist = agents["alchemist"]
    adventurer = agents["adventurer"]
    
    print(f"📍 {alchemist.name}（{alchemist.specialty}）が{alchemist.current_spot_id}の工房で作業中...")
    print(f"💰 初期ステータス: {alchemist.get_job_status_summary()}")
    
    # === ステップ1: ヘルスポーション作成 ===
    print(f"\n🧪 ステップ1: ヘルスポーション作成")
    print(f"📋 必要材料: 薬草2個（所持: {alchemist.get_item_count('herb')}個）")
    
    craft_action = CraftItem("ヘルスポーション作成", "health_potion", 2)  # 2個作成
    result = world.execute_action("alchemist1", craft_action)
    
    print(f"✅ 作成結果: {result['success']}")
    if result['success']:
        print(f"🧪 作成されたポーション: {len(result['created_items'])}個")
        print(f"📦 消費材料: {result['consumed_materials']}")
        print(f"⭐ 経験値獲得: {result['experience_gained']}")
        
        # 作成されたアイテムの詳細
        for item in result['created_items']:
            print(f"   💊 {item.item_id}: {item.effect}")
    
    # === ステップ2: マナポーション作成 ===
    print(f"\n🧪 ステップ2: マナポーション作成")
    print(f"📋 必要材料: 魔力草1個（{alchemist.get_item_count('magic_herb')}個）, クリスタル粉1個（{alchemist.get_item_count('crystal_powder')}個）")
    
    craft_action = CraftItem("マナポーション作成", "mana_potion", 2)
    result = world.execute_action("alchemist1", craft_action)
    
    print(f"✅ 作成結果: {result['success']}")
    if result['success']:
        print(f"🧪 作成されたポーション: {len(result['created_items'])}個")
        for item in result['created_items']:
            print(f"   💊 {item.item_id}: {item.effect}")
    
    # === ステップ3: 力のポーション作成 ===
    print(f"\n🧪 ステップ3: 力のポーション作成")
    print(f"📋 必要材料: 力の薬草3個（{alchemist.get_item_count('power_herb')}個）, 獣の牙1個（{alchemist.get_item_count('beast_fang')}個）")
    
    craft_action = CraftItem("力のポーション作成", "strength_potion", 1)
    result = world.execute_action("alchemist1", craft_action)
    
    print(f"✅ 作成結果: {result['success']}")
    if result['success']:
        print(f"🧪 作成されたポーション: {len(result['created_items'])}個")
        for item in result['created_items']:
            print(f"   💊 {item.item_id}: {item.effect}")
    
    print(f"\n📊 合成後ステータス: {alchemist.get_job_status_summary()}")
    
    return True


def demo_advanced_elixir_crafting(world, agents):
    """高級エリクサー作成のデモ"""
    print(f"\n🧪 高級エリクサー作成チャレンジ")
    print(f"📋 必要材料: 希少薬草5個, ドラゴン鱗1個, 聖水3個")
    
    alchemist = agents["alchemist"]
    
    # レベルアップして上級レシピを有効化
    alchemist.job_level = 3
    print(f"⬆️ 錬金術師レベルアップ: Lv.{alchemist.job_level}")
    
    # 高級レシピを習得
    elixir_recipe = Recipe(
        recipe_id="grand_elixir",
        name="万能エリクサー",
        description="全ての能力を回復・強化する究極のポーション",
        required_materials={"rare_herb": 5, "dragon_scale": 1, "pure_water": 3},
        produced_item_id="grand_elixir",
        produced_item_type="consumable",
        item_effect=ItemEffect(
            hp_change=50,
            mp_change=40,
            attack_change=10,
            defense_change=5,
            experience_change=100
        ),
        produced_count=1,
        max_stack=1,
        required_job_level=3,
        job_experience_gain=100,
        success_rate=0.7
    )
    
    # レベルアップ後にレシピ習得
    recipe_learned = alchemist.learn_recipe(elixir_recipe)
    if recipe_learned:
        print(f"📚 万能エリクサーのレシピを習得しました！")
    else:
        print(f"❌ レシピ習得に失敗しました...")
        return False
    
    # 材料チェック
    materials_needed = [
        ("rare_herb", 5, "希少薬草"),
        ("dragon_scale", 1, "ドラゴンの鱗"),
        ("pure_water", 3, "聖水")
    ]
    
    print(f"📦 材料確認:")
    for material_id, needed, name in materials_needed:
        have = alchemist.get_item_count(material_id)
        print(f"  {name}: {have}/{needed}個")
    
    # エリクサー作成（成功率70%）
    attempts = 3
    success_count = 0
    
    for attempt in range(1, attempts + 1):
        print(f"\n🎲 試行 {attempt}/{attempts}:")
        
        # 材料を補充（失敗時のため）
        for material_id, needed, name in materials_needed:
            while alchemist.get_item_count(material_id) < needed:
                item = Item(material_id, name)
                alchemist.add_item(item)
        
        craft_action = CraftItem("万能エリクサー作成", "grand_elixir", 1)
        result = world.execute_action("alchemist1", craft_action)
        
        if result['success']:
            success_count += 1
            print(f"🎉 成功! 万能エリクサーが完成！")
            for item in result['created_items']:
                print(f"   ✨ {item.item_id}: {item.effect}")
            print(f"⭐ 経験値獲得: {result['experience_gained']}")
            break
        else:
            print(f"💥 失敗... 材料は消費されました")
            print(f"📦 消費材料: {result['consumed_materials']}")
    
    if success_count == 0:
        print(f"😢 {attempts}回の試行すべてが失敗しました...")
    
    return success_count > 0


def demo_potion_usage(world, agents):
    """ポーション使用デモ"""
    print(f"\n" + "=" * 70)
    print("💊 ポーション使用デモ - 冒険者の回復")
    print("=" * 70)
    
    alchemist = agents["alchemist"]
    adventurer = agents["adventurer"]
    
    print(f"⚔️ {adventurer.name}は冒険で疲労困憊...")
    print(f"📊 現在の状態: {adventurer.get_status_summary()}")
    
    # 錬金術師から冒険者にポーションを渡す（簡易取引）
    print(f"\n🤝 {alchemist.name}からポーションを購入...")
    
    potions_to_transfer = [
        ("health_potion", "ヘルスポーション", 50),
        ("mana_potion", "マナポーション", 40),
        ("strength_potion", "力のポーション", 100),
    ]
    
    total_cost = 0
    for potion_id, potion_name, price in potions_to_transfer:
        potion = alchemist.get_item_by_id(potion_id)
        if potion:
            alchemist.remove_item(potion)
            adventurer.add_item(potion)
            adventurer.add_money(-price)
            alchemist.add_money(price)
            total_cost += price
            print(f"  💳 {potion_name}を{price}ゴールドで購入")
    
    print(f"💰 合計支払い: {total_cost}ゴールド")
    print(f"📊 購入後所持金: {adventurer.money}ゴールド")
    
    # === ポーション使用 ===
    
    # 1. ヘルスポーション使用
    print(f"\n💊 ヘルスポーション使用")
    print(f"📊 使用前: HP={adventurer.current_hp}/{adventurer.max_hp}")
    
    usage_action = ItemUsage("ヘルスポーション使用", "health_potion", 1)
    world.execute_action("warrior1", usage_action)
    
    print(f"📊 使用後: HP={adventurer.current_hp}/{adventurer.max_hp}")
    print(f"✅ HP回復効果を確認！")
    
    # 2. マナポーション使用
    print(f"\n💊 マナポーション使用")
    print(f"📊 使用前: MP={adventurer.current_mp}/{adventurer.max_mp}")
    
    usage_action = ItemUsage("マナポーション使用", "mana_potion", 1)
    world.execute_action("warrior1", usage_action)
    
    print(f"📊 使用後: MP={adventurer.current_mp}/{adventurer.max_mp}")
    print(f"✅ MP回復効果を確認！")
    
    # 3. 力のポーション使用
    print(f"\n💊 力のポーション使用")
    print(f"📊 使用前: 攻撃力={adventurer.attack}, HP={adventurer.current_hp}")
    
    usage_action = ItemUsage("力のポーション使用", "strength_potion", 1)
    world.execute_action("warrior1", usage_action)
    
    print(f"📊 使用後: 攻撃力={adventurer.attack}, HP={adventurer.current_hp}")
    print(f"✅ 攻撃力上昇＋HP回復効果を確認！")
    
    # 万能エリクサーがあれば使用
    if adventurer.has_item("grand_elixir"):
        print(f"\n✨ 万能エリクサー使用")
        print(f"📊 使用前: {adventurer.get_status_summary()}")
        
        usage_action = ItemUsage("万能エリクサー使用", "grand_elixir", 1)
        world.execute_action("warrior1", usage_action)
        
        print(f"📊 使用後: {adventurer.get_status_summary()}")
        print(f"🌟 全能力が大幅に向上しました！")
    
    print(f"\n🎉 {adventurer.name}は完全に回復し、さらに強化されました！")


def display_final_status(agents):
    """最終ステータス表示"""
    print(f"\n" + "=" * 70)
    print("📊 最終結果")
    print("=" * 70)
    
    alchemist = agents["alchemist"]
    adventurer = agents["adventurer"]
    
    print(f"🧪 {alchemist.name}:")
    print(f"  {alchemist.get_job_status_summary()}")
    print(f"  💰 所持金: {alchemist.money}ゴールド")
    print(f"  📦 レシピ数: {len(alchemist.known_recipes)}個")
    
    print(f"\n⚔️ {adventurer.name}:")
    print(f"  {adventurer.get_status_summary()}")
    print(f"  💰 所持金: {adventurer.money}ゴールド")
    
    # 残りアイテム
    consumable_items = [item for item in adventurer.items if isinstance(item, ConsumableItem)]
    if consumable_items:
        print(f"  💊 残りポーション:")
        for item in consumable_items:
            print(f"    - {item.item_id}: {item.effect}")


def main():
    """メインデモ実行"""
    print("🧪 ConsumableItem合成システム総合デモ")
    print("=" * 70)
    print("錬金術師がConsumableItemを作成し、冒険者が使用する経済循環を実演")
    
    try:
        # 1. ワールド作成
        world = create_demo_world()
        agents = create_demo_agents(world)
        
        # 2. 材料準備
        prepare_crafting_materials(agents)
        
        # 3. ポーション作成ワークフロー
        demo_potion_crafting_workflow(world, agents)
        
        # 4. 高級エリクサー作成
        demo_advanced_elixir_crafting(world, agents)
        
        # 5. ポーション使用
        demo_potion_usage(world, agents)
        
        # 6. 最終結果
        display_final_status(agents)
        
        print(f"\n🎉 ConsumableItem合成システムデモが完了しました！")
        print("✅ 錬金術師によるポーション作成、冒険者による使用、経済循環がすべて正常に動作")
        
    except Exception as e:
        print(f"❌ デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 