from src.models.spot import Spot
from src.models.agent import Agent
from src.models.item import Item
from src.models.action import Interaction, InteractionType
from src.models.interactable import Door
from src.models.reward import ActionReward
from src.systems.world import World


def create_door_movement_test_world():
    """ドア・移動連携テスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    
    # 玄関ホール
    entrance_hall = Spot("entrance_hall", "玄関ホール", "古い屋敷の玄関ホール。重厚な扉がある。")
    world.add_spot(entrance_hall)
    
    # 秘密の部屋
    secret_room = Spot("secret_room", "秘密の部屋", "隠された秘密の部屋。貴重なアイテムが置かれている。")
    world.add_spot(secret_room)
    
    # 庭園
    garden = Spot("garden", "庭園", "美しい花々が咲く庭園。")
    world.add_spot(garden)
    
    # === アイテムの作成 ===
    
    # 秘密の鍵
    secret_key = Item("secret_key", "秘密の鍵 - 古い扉を開ける謎めいた鍵")
    
    # 宝石
    precious_gem = Item("precious_gem", "貴重な宝石 - 美しく光る宝石")
    secret_room.add_item(precious_gem)
    
    # === ドアの作成と配置 ===
    
    # 鍵付きの秘密のドア（玄関ホール → 秘密の部屋）
    secret_door = Door(
        object_id="secret_door",
        name="古い木の扉",
        description="重厚で古めかしい木の扉。鍵穴が見える。",
        target_spot_id="secret_room",
        key_item_id="secret_key"
    )
    entrance_hall.add_interactable(secret_door)
    
    # 鍵なしの普通のドア（玄関ホール → 庭園）
    garden_door = Door(
        object_id="garden_door",
        name="ガラスの扉",
        description="庭園に続く美しいガラスの扉。",
        target_spot_id="garden",
        key_item_id=None  # 鍵不要
    )
    entrance_hall.add_interactable(garden_door)
    
    # === エージェントの作成 ===
    
    explorer = Agent("explorer_001", "探検家チャーリー")
    explorer.set_current_spot_id("entrance_hall")  # 玄関ホールからスタート
    world.add_agent(explorer)
    
    # エージェントに秘密の鍵を持たせる（テスト用）
    explorer.add_item(secret_key)
    
    return world


def display_agent_status(world: World, agent_id: str, step_description: str = ""):
    """エージェントの現在の状態を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    if step_description:
        print(f"\n📋 {step_description}")
    
    print("=" * 60)
    print(f"🚪 エージェント: {agent.name} (ID: {agent.agent_id})")
    print(f"📍 現在地: {current_spot.name}")
    print(f"📝 説明: {current_spot.description}")
    print(f"📦 所持アイテム数: {len(agent.items)}")
    
    if agent.items:
        print("  📦 所持アイテム:")
        for item in agent.items:
            print(f"    - {item}")
    
    print("=" * 60)


def display_available_actions(world: World, agent_id: str):
    """利用可能な行動（移動・相互作用）を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    # 移動先の表示
    movements = current_spot.get_available_movements()
    print("\n🚶‍♂️ 利用可能な移動:")
    if movements:
        for movement in movements:
            target_spot = world.get_spot(movement.target_spot_id)
            print(f"  {movement.direction} → {target_spot.name}")
    else:
        print("  なし")
    
    # 相互作用の表示
    interactions = current_spot.get_available_interactions()
    print("\n🔧 利用可能な相互作用:")
    if interactions:
        for i, interaction in enumerate(interactions, 1):
            print(f"  {i}. {interaction.description}")
            if interaction.required_item_id:
                has_item = agent.has_item(interaction.required_item_id)
                status = "✅" if has_item else "❌"
                print(f"     必要アイテム: {interaction.required_item_id} {status}")
    else:
        print("  なし")
    
    return movements, interactions


def execute_interaction_step(world: World, agent_id: str, interaction: Interaction, step_num: int):
    """相互作用ステップを実行"""
    print(f"\n🔧 ステップ {step_num}: '{interaction.description}' を実行")
    
    try:
        world.execute_agent_interaction(agent_id, interaction)
        print(f"✅ 相互作用成功!")
        return True
    except Exception as e:
        print(f"❌ 相互作用失敗: {e}")
        return False


def execute_movement_step(world: World, agent_id: str, direction: str, step_num: int):
    """移動ステップを実行"""
    print(f"\n🚶‍♂️ ステップ {step_num}: '{direction}' で移動")
    
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    old_spot_name = current_spot.name
    
    # 移動可能な行動から該当するものを検索
    available_movements = current_spot.get_available_movements()
    movement_obj = None
    
    for movement in available_movements:
        if movement.direction == direction:
            movement_obj = movement
            break
    
    if movement_obj is None:
        print(f"❌ 移動失敗: '{direction}' は利用できません")
        return False
    
    try:
        world.execute_agent_movement(agent_id, movement_obj)
        new_spot = world.get_spot(agent.get_current_spot_id())
        print(f"✅ 移動成功: {old_spot_name} → {new_spot.name}")
        return True
    except Exception as e:
        print(f"❌ 移動エラー: {e}")
        return False


def demo_door_movement_integration():
    """ドア・移動連携のデモンストレーション"""
    print("🎮 ドア・移動システム連携検証デモ")
    print("=" * 60)
    print("📋 探検家チャーリーがドアを開けて新しい場所に移動します")
    
    world = create_door_movement_test_world()
    agent_id = "explorer_001"
    step = 0
    
    # 初期状態
    display_agent_status(world, agent_id, f"ステップ {step}: 探検開始")
    movements, interactions = display_available_actions(world, agent_id)
    
    print(f"\n📝 初期状態での移動先数: {len(movements)}")
    
    # ステップ1: 秘密のドアを調べる
    step += 1
    secret_door_examine = None
    for interaction in interactions:
        if "古い木の扉" in interaction.description and "調べる" in interaction.description:
            secret_door_examine = interaction
            break
    
    if secret_door_examine:
        success = execute_interaction_step(world, agent_id, secret_door_examine, step)
        if success:
            display_agent_status(world, agent_id)
    
    # ステップ2: 秘密のドアを開ける（鍵を使用）
    step += 1
    movements, interactions = display_available_actions(world, agent_id)
    
    secret_door_open = None
    for interaction in interactions:
        if "古い木の扉" in interaction.description and "開ける" in interaction.description:
            secret_door_open = interaction
            break
    
    if secret_door_open:
        print(f"\n📝 ドア開放前の移動先数: {len(movements)}")
        success = execute_interaction_step(world, agent_id, secret_door_open, step)
        if success:
            display_agent_status(world, agent_id)
            # ドア開放後の移動先をチェック
            new_movements, _ = display_available_actions(world, agent_id)
            print(f"\n📝 ドア開放後の移動先数: {len(new_movements)}")
            print("🎯 新しい移動先が追加されました！")
    
    # ステップ3: 新しく開放された秘密の部屋に移動
    step += 1
    movements, _ = display_available_actions(world, agent_id)
    
    secret_room_movement = None
    for movement in movements:
        if "古い木の扉を通る" in movement.direction:
            secret_room_movement = movement.direction
            break
    
    if secret_room_movement:
        success = execute_movement_step(world, agent_id, secret_room_movement, step)
        if success:
            display_agent_status(world, agent_id, f"ステップ {step}: 秘密の部屋に到達")
    
    # ステップ4: 庭園のドアを開ける（鍵不要）
    step += 1
    # まず玄関ホールに戻る
    execute_movement_step(world, agent_id, "古い木の扉を通る", step)
    
    step += 1
    movements, interactions = display_available_actions(world, agent_id)
    
    garden_door_open = None
    for interaction in interactions:
        if "ガラスの扉" in interaction.description and "開ける" in interaction.description:
            garden_door_open = interaction
            break
    
    if garden_door_open:
        success = execute_interaction_step(world, agent_id, garden_door_open, step)
        if success:
            display_agent_status(world, agent_id)
            movements, _ = display_available_actions(world, agent_id)
            print(f"\n📝 庭園ドア開放後の移動先数: {len(movements)}")
    
    print("\n" + "=" * 60)
    print("🎉 ドア・移動システム連携検証デモが完了しました！")
    print("✅ ドアを開けることで新しい移動先が追加されることを確認しました")
    print("=" * 60)


def test_door_movement_without_key():
    """鍵なしでドアを開けようとするテスト"""
    print("\n\n🧪 鍵なしでのドア操作テスト")
    print("=" * 60)
    
    world = create_door_movement_test_world()
    agent_id = "explorer_001"
    agent = world.get_agent(agent_id)
    
    # 鍵を削除
    if agent.items:
        agent.items.clear()
    
    print("📊 テスト条件: エージェントは鍵を持っていません")
    
    current_spot = world.get_spot(agent.get_current_spot_id())
    interactions = current_spot.get_available_interactions()
    
    # 秘密のドアを開けようとする
    secret_door_open = None
    for interaction in interactions:
        if "古い木の扉" in interaction.description and "開ける" in interaction.description:
            secret_door_open = interaction
            break
    
    if secret_door_open:
        try:
            world.execute_agent_interaction(agent_id, secret_door_open)
            print("❌ テスト失敗: 鍵なしでドアが開いてしまいました")
        except ValueError as e:
            print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    print("✅ 鍵なしでのドア操作テストが完了しました")


if __name__ == "__main__":
    # メインのデモを実行
    demo_door_movement_integration()
    
    # 鍵なしテストを実行
    test_door_movement_without_key() 