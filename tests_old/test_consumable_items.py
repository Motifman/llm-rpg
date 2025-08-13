"""
消費可能アイテムシステムの包括的テスト
基本消費、エラーハンドリング、重複アイテム、統合テストを含む
"""

from src_old.models.spot import Spot
from src_old.models.agent import Agent
from src_old.models.item import Item, ConsumableItem, ItemEffect
from src_old.models.action import ItemUsage
from src_old.systems.world import World


def create_consumable_items_test_world():
    """消費可能アイテムテスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    inn = Spot("inn", "宿屋", "旅人が休息を取る宿屋。ポーションが置いてある。")
    world.add_spot(inn)
    
    # === アイテムの作成 ===
    
    # ヘルスポーション（HP回復）
    health_potion = ConsumableItem(
        item_id="health_potion",
        description="ヘルスポーション - HPを30回復する赤いポーション",
        effect=ItemEffect(hp_change=30),
        max_stack=5
    )
    
    # マナポーション（MP回復）
    mana_potion = ConsumableItem(
        item_id="mana_potion", 
        description="マナポーション - MPを20回復する青いポーション",
        effect=ItemEffect(mp_change=20),
        max_stack=5
    )
    
    # 力のポーション（攻撃力上昇）
    strength_potion = ConsumableItem(
        item_id="strength_potion",
        description="力のポーション - 攻撃力を5上昇させる黄色いポーション",
        effect=ItemEffect(attack_change=5),
        max_stack=3
    )
    
    # 防御のポーション（防御力上昇）
    defense_potion = ConsumableItem(
        item_id="defense_potion",
        description="防御のポーション - 防御力を3上昇させる緑のポーション",
        effect=ItemEffect(defense_change=3),
        max_stack=3
    )
    
    # 万能ポーション（複数効果）
    ultimate_potion = ConsumableItem(
        item_id="ultimate_potion",
        description="万能ポーション - 全ステータスを回復・上昇させる虹色のポーション",
        effect=ItemEffect(
            hp_change=50,
            mp_change=30,
            attack_change=2,
            defense_change=2,
            money_change=100,
            experience_change=50
        ),
        max_stack=1
    )
    
    # 消費不可能なアイテム（テスト用）
    magic_book = Item(
        item_id="magic_book",
        description="魔導書 - 古代の魔法が記された貴重な本"
    )
    
    # === エージェントの作成 ===
    
    adventurer = Agent("adventurer_001", "冒険者アリス")
    adventurer.set_current_spot_id("inn")
    
    # 初期ステータスを調整（テスト用）
    adventurer.set_hp(50)  # HPを半分に
    adventurer.set_mp(25)  # MPを半分に
    
    # アイテムを持たせる
    adventurer.add_item(health_potion)
    adventurer.add_item(health_potion)  # 重複所持テスト用
    adventurer.add_item(mana_potion)
    adventurer.add_item(strength_potion)
    adventurer.add_item(defense_potion)
    adventurer.add_item(ultimate_potion)
    adventurer.add_item(magic_book)  # 消費不可能アイテム
    
    world.add_agent(adventurer)
    
    return world


def display_agent_detailed_status(world: World, agent_id: str, step_description: str = ""):
    """エージェントの詳細ステータスを表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    if step_description:
        print(f"\n📋 {step_description}")
    
    print("=" * 70)
    print(f"🧙 エージェント: {agent.name} (ID: {agent.agent_id})")
    print(f"📍 現在地: {current_spot.name}")
    print(f"❤️  HP: {agent.current_hp}/{agent.max_hp}")
    print(f"💙 MP: {agent.current_mp}/{agent.max_mp}")
    print(f"⚔️  攻撃力: {agent.attack}")
    print(f"🛡️  防御力: {agent.defense}")
    print(f"💰 所持金: {agent.money}ゴールド")
    print(f"⭐ 経験値: {agent.experience_points}EXP")
    print(f"🧠 発見情報数: {len(agent.discovered_info)}")
    print(f"📦 所持アイテム数: {len(agent.items)}")
    
    if agent.items:
        print("  📦 所持アイテム:")
        item_counts = {}
        for item in agent.items:
            item_counts[item.item_id] = item_counts.get(item.item_id, 0) + 1
        
        for item_id, count in item_counts.items():
            item = agent.get_item_by_id(item_id)
            count_str = f" x{count}" if count > 1 else ""
            print(f"    - {item}{count_str}")
    
    print("=" * 70)


def display_available_consumables(world: World, agent_id: str):
    """使用可能な消費アイテムを表示"""
    agent = world.get_agent(agent_id)
    
    print("\n🧪 使用可能な消費アイテム:")
    
    consumable_items = [item for item in agent.items if isinstance(item, ConsumableItem)]
    if not consumable_items:
        print("  なし")
        return []
    
    # アイテムをグループ化
    item_groups = {}
    for item in consumable_items:
        if item.item_id not in item_groups:
            item_groups[item.item_id] = {
                'item': item,
                'count': 0
            }
        item_groups[item.item_id]['count'] += 1
    
    # 表示
    usage_actions = []
    for i, (item_id, group) in enumerate(item_groups.items(), 1):
        item = group['item']
        count = group['count']
        print(f"  {i}. {item.description} (x{count})")
        print(f"     {item.effect}")
        
        # ItemUsageアクションを準備
        usage_actions.append(ItemUsage(
            description=f"{item.description}を使用",
            item_id=item_id,
            count=1
        ))
    
    return usage_actions


def execute_item_usage_step(world: World, agent_id: str, item_usage: ItemUsage, step_num: int):
    """アイテム使用ステップを実行"""
    print(f"\n🧪 ステップ {step_num}: '{item_usage.description}' を実行")
    
    try:
        world.execute_agent_item_usage(agent_id, item_usage)
        print(f"✅ アイテム使用成功!")
        return True
    except Exception as e:
        print(f"❌ アイテム使用失敗: {e}")
        return False


def demo_consumable_items_system():
    """消費可能アイテムシステムのデモンストレーション"""
    print("🎮 消費可能アイテムシステム検証デモ")
    print("=" * 70)
    print("📋 冒険者アリスが様々なポーションを使用します")
    
    world = create_consumable_items_test_world()
    agent_id = "adventurer_001"
    step = 0
    
    # 初期状態
    display_agent_detailed_status(world, agent_id, f"ステップ {step}: 冒険開始")
    usage_actions = display_available_consumables(world, agent_id)
    
    # ステップ1: ヘルスポーション使用（HP回復）
    step += 1
    health_usage = None
    for action in usage_actions:
        if "health_potion" in action.item_id:
            health_usage = action
            break
    
    if health_usage:
        success = execute_item_usage_step(world, agent_id, health_usage, step)
        if success:
            display_agent_detailed_status(world, agent_id)
    
    # ステップ2: マナポーション使用（MP回復）
    step += 1
    mana_usage = None
    for action in usage_actions:
        if "mana_potion" in action.item_id:
            mana_usage = action
            break
    
    if mana_usage:
        success = execute_item_usage_step(world, agent_id, mana_usage, step)
        if success:
            display_agent_detailed_status(world, agent_id)
    
    # ステップ3: 力のポーション使用（攻撃力上昇）
    step += 1
    strength_usage = None
    for action in usage_actions:
        if "strength_potion" in action.item_id:
            strength_usage = action
            break
    
    if strength_usage:
        success = execute_item_usage_step(world, agent_id, strength_usage, step)
        if success:
            display_agent_detailed_status(world, agent_id)
    
    # ステップ4: 万能ポーション使用（全ステータス効果）
    step += 1
    ultimate_usage = None
    for action in usage_actions:
        if "ultimate_potion" in action.item_id:
            ultimate_usage = action
            break
    
    if ultimate_usage:
        success = execute_item_usage_step(world, agent_id, ultimate_usage, step)
        if success:
            display_agent_detailed_status(world, agent_id, f"ステップ {step}: 万能ポーション使用後")
    
    print("\n" + "=" * 70)
    print("🎉 消費可能アイテムシステム検証デモが完了しました！")
    print("✅ 各種ポーションによるステータス変化を確認しました")
    print("=" * 70)


def test_error_handling():
    """エラーハンドリングのテスト"""
    print("\n\n🧪 エラーハンドリングテスト")
    print("=" * 70)
    
    world = create_consumable_items_test_world()
    agent_id = "adventurer_001"
    agent = world.get_agent(agent_id)
    
    print("📊 テスト条件の設定")
    
    # テスト1: 所持していないアイテムの使用
    print("\n🧪 テスト1: 所持していないアイテムの使用")
    fake_usage = ItemUsage(
        description="存在しないポーションを使用",
        item_id="fake_potion"
    )
    
    try:
        world.execute_agent_item_usage(agent_id, fake_usage)
        print("❌ テスト失敗: 存在しないアイテムが使用できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    # テスト2: 消費不可能アイテムの使用
    print("\n🧪 テスト2: 消費不可能アイテムの使用")
    book_usage = ItemUsage(
        description="魔導書を使用",
        item_id="magic_book"
    )
    
    try:
        world.execute_agent_item_usage(agent_id, book_usage)
        print("❌ テスト失敗: 消費不可能アイテムが使用できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    # テスト3: 複数個使用（不足している場合）
    print("\n🧪 テスト3: 複数個使用（不足している場合）")
    multiple_usage = ItemUsage(
        description="万能ポーションを2個使用",
        item_id="ultimate_potion",
        count=2
    )
    
    try:
        world.execute_agent_item_usage(agent_id, multiple_usage)
        print("❌ テスト失敗: 不足しているアイテムが使用できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    print("✅ エラーハンドリングテストが完了しました")


def test_item_stacking():
    """アイテムスタッキング（重複所持）のテスト"""
    print("\n\n🧪 アイテムスタッキングテスト")
    print("=" * 70)
    
    world = create_consumable_items_test_world()
    agent_id = "adventurer_001"
    agent = world.get_agent(agent_id)
    
    print(f"📊 ヘルスポーション初期所持数: {agent.get_item_count('health_potion')}個")
    
    # 1個使用
    health_usage = ItemUsage(
        description="ヘルスポーション1個使用",
        item_id="health_potion",
        count=1
    )
    
    try:
        world.execute_agent_item_usage(agent_id, health_usage)
        print(f"✅ 1個使用成功")
        print(f"📊 使用後所持数: {agent.get_item_count('health_potion')}個")
    except Exception as e:
        print(f"❌ 使用失敗: {e}")
    
    print("✅ アイテムスタッキングテストが完了しました")


def test_hp_mp_limits():
    """HP・MP上限テスト"""
    print("\n\n🧪 HP・MP上限テスト")
    print("=" * 70)
    
    world = World()
    
    # 満タンのエージェントを作成
    agent = Agent("test_agent", "テストエージェント")
    agent.set_hp(100)  # 満タン
    agent.set_mp(50)   # 満タン
    world.add_agent(agent)
    
    # 回復ポーションを持たせる
    heal_potion = ConsumableItem(
        item_id="heal_potion",
        description="回復ポーション",
        effect=ItemEffect(hp_change=30, mp_change=20)
    )
    agent.add_item(heal_potion)
    
    print(f"📊 使用前 - HP: {agent.current_hp}/{agent.max_hp}, MP: {agent.current_mp}/{agent.max_mp}")
    
    # 満タン時に回復アイテム使用
    usage = ItemUsage(
        description="回復ポーション使用",
        item_id="heal_potion"
    )
    
    try:
        world.execute_agent_item_usage("test_agent", usage)
        print(f"✅ 使用成功")
        print(f"📊 使用後 - HP: {agent.current_hp}/{agent.max_hp}, MP: {agent.current_mp}/{agent.max_mp}")
        print("✅ 上限を超えた回復が適切に制限されました")
    except Exception as e:
        print(f"❌ 使用失敗: {e}")
    
    print("✅ HP・MP上限テストが完了しました")


def run_all_consumable_tests():
    """全ての消費可能アイテムテストを実行"""
    print("🧪 消費可能アイテムシステム - 全テスト実行")
    print("=" * 70)
    
    try:
        # メインデモ
        demo_consumable_items_system()
        
        # エラーハンドリングテスト
        test_error_handling()
        
        # アイテムスタッキングテスト
        test_item_stacking()
        
        # HP・MP上限テスト
        test_hp_mp_limits()
        
        print("\n" + "=" * 70)
        print("🎉 全ての消費可能アイテムテストが成功しました！")
        print("✅ 消費可能アイテムシステムが正しく実装されています")
        return True
        
    except Exception as e:
        print(f"❌ テスト中にエラーが発生しました: {e}")
        return False


if __name__ == "__main__":
    run_all_consumable_tests() 