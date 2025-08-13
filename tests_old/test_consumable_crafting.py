"""
ConsumableItem合成機能のテスト
CraftsmanAgentがConsumableItemを作成できることを確認
"""

from src_old.models.agent import Agent
from src_old.models.item import Item, ConsumableItem, ItemEffect
from src_old.models.job import JobAgent, CraftsmanAgent, Recipe, JobType
from src_old.models.action import CraftItem
from src_old.systems.world import World


def test_recipe_with_consumable_item():
    """ConsumableItem用レシピの作成テスト"""
    print("🧪 ConsumableItem用レシピテスト")
    
    # ヘルスポーションのレシピ
    health_potion_recipe = Recipe(
        recipe_id="health_potion",
        name="ヘルスポーション",
        description="薬草から作る回復薬",
        required_materials={"herb": 2},
        produced_item_id="health_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(hp_change=30),
        produced_count=1,
        max_stack=5,
        job_experience_gain=15
    )
    
    assert health_potion_recipe.produced_item_type == "consumable", "アイテムタイプが正しく設定されていません"
    assert health_potion_recipe.item_effect.hp_change == 30, "効果が正しく設定されていません"
    assert health_potion_recipe.max_stack == 5, "スタック数が正しく設定されていません"
    print("✅ ConsumableItem用レシピ作成")
    
    # マナポーションのレシピ（複合効果）
    mana_potion_recipe = Recipe(
        recipe_id="mana_potion",
        name="マナポーション",
        description="魔力草から作る魔力回復薬",
        required_materials={"magic_herb": 1, "water": 1},
        produced_item_id="mana_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(mp_change=25, experience_change=5),
        produced_count=1,
        max_stack=3,
        job_experience_gain=20
    )
    
    assert mana_potion_recipe.item_effect.mp_change == 25, "MP効果が正しく設定されていません"
    assert mana_potion_recipe.item_effect.experience_change == 5, "経験値効果が正しく設定されていません"
    print("✅ 複合効果ConsumableItem用レシピ作成")
    
    print("✅ ConsumableItem用レシピテスト完了\n")


def test_craftsman_consumable_crafting():
    """CraftsmanAgentによるConsumableItem合成テスト"""
    print("🧪 CraftsmanAgentのConsumableItem合成テスト")
    
    # 錬金術師を作成
    alchemist = CraftsmanAgent("alchemist1", "錬金術師ルナ", "alchemist")
    
    # ヘルスポーションのレシピを習得
    health_potion_recipe = Recipe(
        recipe_id="health_potion",
        name="ヘルスポーション",
        description="薬草から作る回復薬",
        required_materials={"herb": 2},
        produced_item_id="health_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(hp_change=30),
        produced_count=1,
        max_stack=5,
        job_experience_gain=15
    )
    alchemist.learn_recipe(health_potion_recipe)
    
    # 材料を与える
    herb1 = Item("herb", "薬草")
    herb2 = Item("herb", "薬草")
    alchemist.add_item(herb1)
    alchemist.add_item(herb2)
    
    print(f"📋 合成前: 薬草 {alchemist.get_item_count('herb')}個")
    print(f"💰 合成前の経験値: {alchemist.job_experience}")
    
    # ポーション合成
    result = alchemist.craft_item(health_potion_recipe, 1)
    
    print(f"✅ 合成結果: {result['success']}")
    print(f"🧪 作成されたアイテム数: {len(result['created_items'])}")
    print(f"📦 消費材料: {result['consumed_materials']}")
    print(f"⭐ 経験値獲得: {result['experience_gained']}")
    
    # 結果検証
    assert result['success'], "合成が失敗しました"
    assert len(result['created_items']) == 1, "作成アイテム数が正しくありません"
    
    created_item = result['created_items'][0]
    assert isinstance(created_item, ConsumableItem), "作成されたアイテムがConsumableItemではありません"
    assert created_item.item_id == "health_potion", "アイテムIDが正しくありません"
    assert created_item.effect.hp_change == 30, "HP回復効果が正しくありません"
    assert created_item.max_stack == 5, "スタック数が正しくありません"
    
    print(f"🧪 作成されたアイテム: {created_item}")
    print(f"💊 効果: {created_item.effect}")
    print(f"📦 消費後の薬草: {alchemist.get_item_count('herb')}個")
    print(f"💰 合成後の経験値: {alchemist.job_experience}")
    
    print("✅ CraftsmanAgentのConsumableItem合成テスト完了\n")


def test_world_integration_consumable_crafting():
    """WorldクラスでのConsumableItem合成統合テスト"""
    print("🧪 WorldクラスでのConsumableItem合成統合テスト")
    
    world = World()
    
    # 錬金術師エージェントを作成・追加
    alchemist = CraftsmanAgent("alchemist1", "錬金術師マリア", "alchemist")
    alchemist.set_current_spot_id("town")
    world.add_agent(alchemist)
    
    # マナポーションのレシピを習得
    mana_potion_recipe = Recipe(
        recipe_id="mana_potion",
        name="マナポーション",
        description="魔力草から作る魔力回復薬",
        required_materials={"magic_herb": 1, "water": 1},
        produced_item_id="mana_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(mp_change=25, attack_change=2),
        produced_count=1,
        max_stack=3,
        job_experience_gain=20
    )
    alchemist.learn_recipe(mana_potion_recipe)
    
    # 材料を与える
    magic_herb = Item("magic_herb", "魔力草")
    water = Item("water", "清水")
    alchemist.add_item(magic_herb)
    alchemist.add_item(water)
    
    print(f"📋 材料: 魔力草 {alchemist.get_item_count('magic_herb')}個, 水 {alchemist.get_item_count('water')}個")
    
    # World経由での合成実行
    craft_action = CraftItem("マナポーション作成", "mana_potion", 1)
    result = world.execute_action("alchemist1", craft_action)
    
    print(f"✅ World経由合成結果: {result['success']}")
    print(f"🧪 作成されたアイテム数: {len(result['created_items'])}")
    
    # 結果検証
    assert result['success'], "World経由の合成が失敗しました"
    assert len(result['created_items']) == 1, "作成アイテム数が正しくありません"
    
    created_item = result['created_items'][0]
    assert isinstance(created_item, ConsumableItem), "World経由で作成されたアイテムがConsumableItemではありません"
    assert created_item.effect.mp_change == 25, "MP回復効果が正しくありません"
    assert created_item.effect.attack_change == 2, "攻撃力上昇効果が正しくありません"
    
    print(f"🧪 作成されたマナポーション: {created_item}")
    print(f"💊 効果: {created_item.effect}")
    
    # 実際に使用してみる
    agent = world.get_agent("alchemist1")
    agent.set_mp(20)  # MPを減らしておく
    agent.set_attack(10)  # 攻撃力をリセット
    
    print(f"📊 使用前: MP={agent.current_mp}, 攻撃力={agent.attack}")
    
    # ConsumableItemを使用
    from src_old.models.action import ItemUsage
    usage_action = ItemUsage("マナポーション使用", "mana_potion", 1)
    world.execute_action("alchemist1", usage_action)
    
    print(f"📊 使用後: MP={agent.current_mp}, 攻撃力={agent.attack}")
    
    # 効果の確認
    assert agent.current_mp == 45, "MP回復効果が適用されていません"  # 20 + 25 = 45
    assert agent.attack == 12, "攻撃力上昇効果が適用されていません"  # 10 + 2 = 12
    
    print("✅ WorldクラスでのConsumableItem合成統合テスト完了\n")


def test_backward_compatibility():
    """既存レシピとの互換性テスト"""
    print("🧪 既存レシピとの互換性テスト")
    
    # 従来形式のレシピ（produced_item_typeなし）
    old_recipe = Recipe(
        recipe_id="iron_sword",
        name="鉄の剣",
        description="鉄から作る剣",
        required_materials={"iron": 3},
        produced_item_id="iron_sword",
        produced_count=1,
        job_experience_gain=25
        # produced_item_typeを指定しない（デフォルトで"item"）
    )
    
    craftsman = CraftsmanAgent("blacksmith1", "鍛冶師ジョン", "blacksmith")
    craftsman.learn_recipe(old_recipe)
    
    # 材料を与える
    for _ in range(3):
        iron = Item("iron", "鉄")
        craftsman.add_item(iron)
    
    # 従来のレシピで合成
    result = craftsman.craft_item(old_recipe, 1)
    
    assert result['success'], "従来レシピでの合成が失敗しました"
    assert len(result['created_items']) == 1, "作成アイテム数が正しくありません"
    
    created_item = result['created_items'][0]
    assert isinstance(created_item, Item), "従来レシピで作成されたアイテムがItemクラスではありません"
    assert not isinstance(created_item, ConsumableItem), "従来レシピでConsumableItemが作成されました"
    assert created_item.item_id == "iron_sword", "アイテムIDが正しくありません"
    
    print(f"🗡️ 作成された鉄の剣: {created_item}")
    print("✅ 既存レシピとの互換性が保たれています")
    
    print("✅ 既存レシピとの互換性テスト完了\n")


def test_complex_consumable_crafting():
    """複雑なConsumableItem合成テスト"""
    print("🧪 複雑なConsumableItem合成テスト")
    
    alchemist = CraftsmanAgent("alchemist2", "上級錬金術師エルザ", "alchemist")
    
    # 万能ポーション（複数効果）のレシピ
    ultimate_potion_recipe = Recipe(
        recipe_id="ultimate_potion",
        name="万能ポーション",
        description="全能力を回復・強化する究極のポーション",
        required_materials={"rare_herb": 5, "crystal": 2, "pure_water": 3},
        produced_item_id="ultimate_potion",
        produced_item_type="consumable",
        item_effect=ItemEffect(
            hp_change=50,
            mp_change=30,
            attack_change=5,
            defense_change=3,
            experience_change=25
        ),
        produced_count=1,
        max_stack=1,  # 貴重なので1個までスタック
        required_job_level=5,
        job_experience_gain=100,
        success_rate=0.8  # 難しいので成功率80%
    )
    
    # レベルアップ
    alchemist.job_level = 5
    alchemist.learn_recipe(ultimate_potion_recipe)
    
    # 材料を与える
    materials = [
        ("rare_herb", 5),
        ("crystal", 2),
        ("pure_water", 3)
    ]
    
    for material_id, count in materials:
        for _ in range(count):
            item = Item(material_id, f"貴重な{material_id}")
            alchemist.add_item(item)
    
    print(f"📋 高級材料準備完了")
    for material_id, count in materials:
        print(f"  {material_id}: {alchemist.get_item_count(material_id)}個")
    
    # 高難度合成実行（複数回試行）
    success_count = 0
    attempts = 5
    
    for attempt in range(attempts):
        # 材料を補充
        for material_id, count in materials:
            while alchemist.get_item_count(material_id) < count:
                item = Item(material_id, f"貴重な{material_id}")
                alchemist.add_item(item)
        
        result = alchemist.craft_item(ultimate_potion_recipe, 1)
        if result['success']:
            success_count += 1
            created_item = result['created_items'][0]
            print(f"🎉 試行{attempt + 1}: 成功! {created_item}")
            print(f"   効果: {created_item.effect}")
        else:
            print(f"💥 試行{attempt + 1}: 失敗...")
    
    print(f"\n📊 成功率: {success_count}/{attempts} = {success_count/attempts*100:.1f}%")
    
    # 少なくとも1回は成功するはず（確率的テスト）
    assert success_count > 0, "すべての合成が失敗しました（確率的に異常）"
    
    print("✅ 複雑なConsumableItem合成テスト完了\n")


def run_all_consumable_crafting_tests():
    """全てのConsumableItem合成テストを実行"""
    print("🧪 ConsumableItem合成機能 - 全テスト実行")
    print("=" * 70)
    
    try:
        # レシピテスト
        test_recipe_with_consumable_item()
        
        # 基本合成テスト
        test_craftsman_consumable_crafting()
        
        # World統合テスト
        test_world_integration_consumable_crafting()
        
        # 互換性テスト
        test_backward_compatibility()
        
        # 複雑な合成テスト
        test_complex_consumable_crafting()
        
        print("\n" + "=" * 70)
        print("🎉 全てのConsumableItem合成テストが成功しました！")
        print("✅ CraftsmanAgentによるConsumableItem合成機能が正しく実装されています")
        return True
        
    except Exception as e:
        print(f"❌ テスト中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    run_all_consumable_crafting_tests() 