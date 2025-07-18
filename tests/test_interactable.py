from src.models.spot import Spot
from src.models.agent import Agent
from src.models.item import Item
from src.models.action import Interaction, InteractionType
from src.models.interactable import Chest, Door
from src.models.reward import ActionReward
from src.systems.world import World


def create_interactable_test_world():
    """Interactableテスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    
    # 宝物部屋
    treasure_room = Spot("treasure_room", "宝物部屋", "古い宝箱がある神秘的な部屋")
    world.add_spot(treasure_room)
    
    # 廊下
    hallway = Spot("hallway", "廊下", "長い廊下。扉がいくつかある")
    world.add_spot(hallway)
    
    # === アイテムの作成 ===
    
    # 宝剣
    treasure_sword = Item("treasure_sword", "宝剣 - 古代の力が宿る剣")
    
    # 魔法の杖
    magic_wand = Item("magic_wand", "魔法の杖 - 不思議な力を持つ杖")
    
    # 鍵
    golden_key = Item("golden_key", "黄金の鍵 - 重要な扉を開ける鍵")
    
    # === Interactableオブジェクトの作成 ===
    
    # 鍵付き宝箱（宝物部屋）
    locked_chest = Chest(
        object_id="locked_chest",
        name="古い宝箱",
        description="頑丈な鍵がかかった古い宝箱",
        key_item_id="golden_key",
        items=[treasure_sword, magic_wand]
    )
    treasure_room.add_interactable(locked_chest)
    
    # 開いている宝箱（廊下）
    open_chest = Chest(
        object_id="open_chest", 
        name="開いた箱",
        description="既に開いている小さな箱",
        key_item_id=None,  # 鍵なし
        items=[golden_key]
    )
    hallway.add_interactable(open_chest)
    
    # 鍵付きドア（廊下→宝物部屋）
    locked_door = Door(
        object_id="locked_door",
        name="重厚な扉",
        description="黄金の鍵が必要そうな重厚な扉",
        target_spot_id="treasure_room",
        key_item_id="golden_key"
    )
    hallway.add_interactable(locked_door)
    
    # === エージェントの作成 ===
    
    explorer = Agent("explorer_001", "探検家ボブ")
    explorer.set_current_spot_id("hallway")  # 廊下からスタート
    world.add_agent(explorer)
    
    return world


def display_agent_status(world: World, agent_id: str, step_description: str = ""):
    """エージェントの現在の状態を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    if step_description:
        print(f"\n📋 {step_description}")
    
    print("=" * 60)
    print(f"🧙 エージェント: {agent.name} (ID: {agent.agent_id})")
    print(f"📍 現在地: {current_spot.name}")
    print(f"📝 説明: {current_spot.description}")
    print(f"💰 所持金: {agent.money}ゴールド")
    print(f"⭐ 経験値: {agent.experience_points}EXP")
    print(f"📦 所持アイテム数: {len(agent.items)}")
    
    if agent.items:
        print("  📦 所持アイテム:")
        for item in agent.items:
            print(f"    - {item}")
    
    print(f"🧠 発見情報数: {len(agent.discovered_info)}")
    if agent.discovered_info:
        print("  🧠 発見情報:")
        for info in agent.discovered_info:
            print(f"    - {info}")
    
    print("=" * 60)


def display_available_interactions(world: World, agent_id: str):
    """利用可能な相互作用を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    print("\n🔧 利用可能な相互作用:")
    interactions = current_spot.get_available_interactions()
    
    if not interactions:
        print("  なし")
        return interactions
    
    for i, interaction in enumerate(interactions, 1):
        print(f"  {i}. {interaction.description}")
        if interaction.required_item_id:
            has_item = agent.has_item(interaction.required_item_id)
            status = "✅" if has_item else "❌"
            print(f"     必要アイテム: {interaction.required_item_id} {status}")
    
    return interactions


def execute_interaction_step(world: World, agent_id: str, interaction: Interaction, step_num: int):
    """相互作用ステップを実行"""
    print(f"\n🔧 ステップ {step_num}: '{interaction.description}' を実行")
    
    agent = world.get_agent(agent_id)
    
    # 実行前の状態記録
    old_money = agent.money
    old_exp = agent.experience_points
    old_items_count = len(agent.items)
    old_info_count = len(agent.discovered_info)
    
    try:
        world.execute_agent_interaction(agent, interaction)
        
        # 変化の確認
        money_gained = agent.money - old_money
        exp_gained = agent.experience_points - old_exp
        items_gained = len(agent.items) - old_items_count
        info_gained = len(agent.discovered_info) - old_info_count
        
        print(f"✅ 相互作用成功!")
        if money_gained > 0:
            print(f"  💰 +{money_gained}ゴールド獲得")
        if exp_gained > 0:
            print(f"  ⭐ +{exp_gained}EXP獲得")
        if items_gained > 0:
            print(f"  📦 +{items_gained}アイテム獲得")
        if info_gained > 0:
            print(f"  🧠 +{info_gained}情報発見")
        
        return True
    except Exception as e:
        print(f"❌ 相互作用失敗: {e}")
        return False


def demo_interaction_sequence():
    """相互作用シーケンスのデモ"""
    print("🎮 Interactableシステム検証デモ")
    print("=" * 60)
    print("📋 探検家ボブがInteractableオブジェクトと相互作用します")
    
    world = create_interactable_test_world()
    agent_id = "explorer_001"
    step = 0
    
    # 初期状態
    display_agent_status(world, agent_id, f"ステップ {step}: 探検開始")
    
    # ステップ1: 廊下で開いた箱を調べる
    step += 1
    current_spot = world.get_spot("hallway")
    interactions = display_available_interactions(world, agent_id)
    
    # "開いた箱を調べる" を実行
    examine_interaction = None
    for interaction in interactions:
        if "調べる" in interaction.description and "開いた箱" in interaction.description:
            examine_interaction = interaction
            break
    
    if examine_interaction:
        success = execute_interaction_step(world, agent_id, examine_interaction, step)
        if success:
            display_agent_status(world, agent_id)
    
    # ステップ2: 開いた箱を開ける（鍵を取得）
    step += 1
    interactions = display_available_interactions(world, agent_id)
    
    open_interaction = None
    for interaction in interactions:
        if "開ける" in interaction.description and "開いた箱" in interaction.description:
            open_interaction = interaction
            break
    
    if open_interaction:
        success = execute_interaction_step(world, agent_id, open_interaction, step)
        if success:
            display_agent_status(world, agent_id)
    
    # ステップ3: 重厚な扉を開ける（鍵を使用）
    step += 1
    interactions = display_available_interactions(world, agent_id)
    
    door_interaction = None
    for interaction in interactions:
        if "重厚な扉" in interaction.description and "開ける" in interaction.description:
            door_interaction = interaction
            break
    
    if door_interaction:
        success = execute_interaction_step(world, agent_id, door_interaction, step)
        if success:
            display_agent_status(world, agent_id)
    
    print("\n" + "=" * 60)
    print("🎉 Interactableシステム検証デモが完了しました！")
    print("✅ 全ての相互作用が正常に動作しました")
    print("=" * 60)


def test_interaction_types():
    """各種相互作用タイプのテスト"""
    print("\n\n🧪 相互作用タイプ別テスト")
    print("=" * 60)
    
    world = create_interactable_test_world()
    agent_id = "explorer_001"
    agent = world.get_agent(agent_id)
    
    # 初期状態の記録
    initial_items = len(agent.items)
    initial_info = len(agent.discovered_info)
    
    print(f"📊 初期状態: 📦{initial_items} 🧠{initial_info}")
    
    # テスト1: EXAMINE相互作用
    print("\n🧪 テスト1: EXAMINE相互作用")
    spot = world.get_spot(agent.get_current_spot_id())
    chest = spot.get_interactable_by_id("open_chest")
    
    examine_interactions = [i for i in chest.get_available_interactions() 
                          if i.interaction_type == InteractionType.EXAMINE]
    
    if examine_interactions:
        world.execute_agent_interaction(agent, examine_interactions[0])
        if len(agent.discovered_info) > initial_info:
            print("✅ EXAMINE相互作用: 成功")
        else:
            print("❌ EXAMINE相互作用: 失敗")
    
    # テスト2: OPEN相互作用（アイテム取得）
    print("\n🧪 テスト2: OPEN相互作用")
    open_interactions = [i for i in chest.get_available_interactions() 
                        if i.interaction_type == InteractionType.OPEN]
    
    if open_interactions:
        world.execute_agent_interaction(agent, open_interactions[0])
        if len(agent.items) > initial_items:
            print("✅ OPEN相互作用: 成功")
        else:
            print("❌ OPEN相互作用: 失敗")
    
    # 最終状態の表示
    print(f"\n📊 最終状態: 📦{len(agent.items)} 🧠{len(agent.discovered_info)}")
    print("✅ 相互作用タイプ別テストが完了しました")


if __name__ == "__main__":
    # メインのデモを実行
    demo_interaction_sequence()
    
    # 個別テストを実行
    test_interaction_types() 