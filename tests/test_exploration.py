from src.models.spot import Spot
from src.models.agent import Agent
from src.models.item import Item
from src.models.action import Movement, Exploration
from src.systems.world import World


def create_exploration_test_world():
    """探索テスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    
    # 1. 中央広場（移動の拠点）
    town_square = Spot("town_square", "中央広場", "街の中心にある賑やかな広場。4方向に道が伸びている。")
    world.add_spot(town_square)
    
    # 2. 宝物庫（アイテム + お金）
    treasure_room = Spot("treasure_room", "古い宝物庫", "埃をかぶった宝箱がある薄暗い地下室。")
    world.add_spot(treasure_room)
    
    # 3. 図書館（情報 + 経験値）
    library = Spot("library", "古い図書館", "古い本や巻物で満たされた静かな図書館。")
    world.add_spot(library)
    
    # 4. 商店（お金のみ）
    shop = Spot("shop", "雑貨商店", "様々な商品が並ぶ小さな商店。")
    world.add_spot(shop)
    
    # === アイテムの作成と配置 ===
    
    # 宝物庫のアイテム
    golden_sword = Item("golden_sword", "黄金の剣 - 光る美しい剣")
    treasure_room.add_item(golden_sword)
    
    # 図書館のアイテム
    ancient_book = Item("ancient_book", "古代の書物 - 失われた知識が記された本")
    library.add_item(ancient_book)
    
    # 商店のアイテム
    coin_pouch = Item("coin_pouch", "コイン袋 - 重いコインの袋")
    shop.add_item(coin_pouch)
    
    # === 移動の設定 ===
    
    # 中央広場から各場所への移動
    town_square.add_movement(Movement("北へ移動", "北", "treasure_room"))
    town_square.add_movement(Movement("東へ移動", "東", "library"))
    town_square.add_movement(Movement("南へ移動", "南", "shop"))
    
    # 各場所から中央広場への帰還
    treasure_room.add_movement(Movement("南へ戻る", "南", "town_square"))
    library.add_movement(Movement("西へ戻る", "西", "town_square"))
    shop.add_movement(Movement("北へ戻る", "北", "town_square"))
    
    # === 探索行動の設定 ===
    
    # 宝物庫: 宝箱の探索（アイテム取得 + お金）
    treasure_exploration = Exploration(
        description="古い宝箱を調べる",
        item_id="golden_sword",
        money=100
    )
    treasure_room.add_exploration(treasure_exploration)
    
    # 図書館: 古い本の研究（アイテム取得 + 情報発見 + 経験値）
    library_exploration = Exploration(
        description="古代の書物を読む",
        item_id="ancient_book",
        discovered_info="古代の魔法に関する知識を得た",
        experience_points=50
    )
    library.add_exploration(library_exploration)
    
    # 商店: コイン袋の発見（アイテム取得 + お金）
    shop_exploration = Exploration(
        description="店の奥でコイン袋を見つける",
        item_id="coin_pouch",
        money=50
    )
    shop.add_exploration(shop_exploration)
    
    # 中央広場: 情報収集（情報のみ）
    square_exploration = Exploration(
        description="通行人から情報を聞く",
        discovered_info="近くに古い遺跡があるという噂を聞いた"
    )
    town_square.add_exploration(square_exploration)
    
    # === エージェントの作成 ===
    
    explorer = Agent("explorer_001", "冒険者アリス")
    explorer.set_current_spot_id("town_square")  # 中央広場からスタート
    world.add_agent(explorer)
    
    return world


def display_agent_status(world: World, agent_id: str, step_description: str = ""):
    """エージェントの現在の状態を詳細表示"""
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
        print("  📦 アイテム一覧:")
        for item in agent.items:
            print(f"    - {item}")
    
    print(f"🧠 発見情報数: {len(agent.discovered_info)}")
    if agent.discovered_info:
        print("  🧠 発見した情報:")
        for info in agent.discovered_info:
            print(f"    - {info}")
    
    print("=" * 60)


def display_available_actions(world: World, agent_id: str):
    """利用可能な行動を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    movements = current_spot.get_available_movements()
    explorations = current_spot.get_available_explorations()
    
    print("\n🚶‍♀️ 利用可能な移動:")
    if movements:
        for movement in movements:
            target_spot = world.get_spot(movement.target_spot_id)
            print(f"  {movement.direction} → {target_spot.name}")
    else:
        print("  なし")
    
    print("\n🔍 利用可能な探索:")
    if explorations:
        for exploration in explorations:
            print(f"  {exploration.description}")
    else:
        print("  なし")


def execute_movement_step(world: World, agent_id: str, direction: str, step_num: int):
    """移動ステップを実行"""
    print(f"\n🚶‍♀️ ステップ {step_num}: '{direction}' で移動")
    
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


def execute_exploration_step(world: World, agent_id: str, exploration_description: str, step_num: int):
    """探索ステップを実行"""
    print(f"\n🔍 ステップ {step_num}: '{exploration_description}' を実行")
    
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    # 探索可能な行動から該当するものを検索
    available_explorations = current_spot.get_available_explorations()
    exploration_obj = None
    
    for exploration in available_explorations:
        if exploration.description == exploration_description:
            exploration_obj = exploration
            break
    
    if exploration_obj is None:
        print(f"❌ 探索失敗: '{exploration_description}' は利用できません")
        return False
    
    # 探索前の状態を記録
    old_money = agent.money
    old_exp = agent.experience_points
    old_items_count = len(agent.items)
    old_info_count = len(agent.discovered_info)
    
    try:
        world.execute_agent_exploration(agent_id, exploration_obj)
        
        # 変化を確認
        money_gained = agent.money - old_money
        exp_gained = agent.experience_points - old_exp
        items_gained = len(agent.items) - old_items_count
        info_gained = len(agent.discovered_info) - old_info_count
        
        print(f"✅ 探索成功!")
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
        print(f"❌ 探索エラー: {e}")
        return False


def demo_exploration_sequence():
    """探索シーケンスのデモンストレーション"""
    print("🎮 探索行動検証デモ")
    print("=" * 60)
    print("📋 冒険者アリスが各場所を訪れて探索を行います")
    
    world = create_exploration_test_world()
    agent_id = "explorer_001"
    step = 0
    
    # 初期状態
    display_agent_status(world, agent_id, f"ステップ {step}: 冒険開始")
    display_available_actions(world, agent_id)
    
    # シナリオ1: 中央広場で情報収集
    step += 1
    success = execute_exploration_step(world, agent_id, "通行人から情報を聞く", step)
    if success:
        display_agent_status(world, agent_id)
    
    # シナリオ2: 宝物庫に移動して宝箱を探索
    step += 1
    success = execute_movement_step(world, agent_id, "北", step)
    if success:
        display_agent_status(world, agent_id, f"ステップ {step}: 宝物庫に到着")
        display_available_actions(world, agent_id)
        
        step += 1
        success = execute_exploration_step(world, agent_id, "古い宝箱を調べる", step)
        if success:
            display_agent_status(world, agent_id)
    
    # シナリオ3: 中央広場に戻り、図書館へ移動
    step += 1
    success = execute_movement_step(world, agent_id, "南", step)
    if success:
        step += 1
        success = execute_movement_step(world, agent_id, "東", step)
        if success:
            display_agent_status(world, agent_id, f"ステップ {step}: 図書館に到着")
            display_available_actions(world, agent_id)
            
            step += 1
            success = execute_exploration_step(world, agent_id, "古代の書物を読む", step)
            if success:
                display_agent_status(world, agent_id)
    
    # シナリオ4: 商店に移動してコイン袋を探索
    step += 1
    success = execute_movement_step(world, agent_id, "西", step)
    if success:
        step += 1
        success = execute_movement_step(world, agent_id, "南", step)
        if success:
            display_agent_status(world, agent_id, f"ステップ {step}: 商店に到着")
            display_available_actions(world, agent_id)
            
            step += 1
            success = execute_exploration_step(world, agent_id, "店の奥でコイン袋を見つける", step)
            if success:
                display_agent_status(world, agent_id, f"ステップ {step}: 探索完了 - 最終状態")
    
    print("\n" + "=" * 60)
    print("🎉 探索行動検証デモが完了しました！")
    print("✅ 全ての探索アクションが正常に動作しました")
    print("=" * 60)


def test_individual_exploration_types():
    """個別の探索タイプをテスト"""
    print("\n\n🧪 個別探索タイプの検証")
    print("=" * 60)
    
    world = create_exploration_test_world()
    agent_id = "explorer_001"
    agent = world.get_agent(agent_id)
    
    # 初期状態の記録
    initial_money = agent.money
    initial_exp = agent.experience_points
    initial_items = len(agent.items)
    initial_info = len(agent.discovered_info)
    
    print(f"📊 初期状態: 💰{initial_money} ⭐{initial_exp} 📦{initial_items} 🧠{initial_info}")
    
    # テスト1: 情報のみの探索
    print("\n🧪 テスト1: 情報のみの探索")
    exploration_info_only = Exploration(
        description="テスト用情報探索",
        discovered_info="テスト情報"
    )
    world.execute_agent_exploration(agent_id, exploration_info_only)
    
    if len(agent.discovered_info) == initial_info + 1:
        print("✅ 情報探索: 成功")
    else:
        print("❌ 情報探索: 失敗")
    
    # テスト2: 経験値のみの探索
    print("\n🧪 テスト2: 経験値のみの探索")
    exploration_exp_only = Exploration(
        description="テスト用経験値探索",
        experience_points=25
    )
    world.execute_agent_exploration(agent_id, exploration_exp_only)
    
    if agent.experience_points == initial_exp + 25:
        print("✅ 経験値探索: 成功")
    else:
        print("❌ 経験値探索: 失敗")
    
    # テスト3: お金のみの探索
    print("\n🧪 テスト3: お金のみの探索")
    exploration_money_only = Exploration(
        description="テスト用お金探索",
        money=75
    )
    world.execute_agent_exploration(agent_id, exploration_money_only)
    
    if agent.money == initial_money + 75:
        print("✅ お金探索: 成功")
    else:
        print("❌ お金探索: 失敗")
    
    # テスト4: アイテムのみの探索（事前にアイテムを配置）
    print("\n🧪 テスト4: アイテムのみの探索")
    test_item = Item("test_item", "テスト用アイテム")
    current_spot = world.get_spot(agent.get_current_spot_id())
    current_spot.add_item(test_item)
    
    exploration_item_only = Exploration(
        description="テスト用アイテム探索",
        item_id="test_item"
    )
    world.execute_agent_exploration(agent_id, exploration_item_only)
    
    if len(agent.items) == initial_items + 1:
        print("✅ アイテム探索: 成功")
    else:
        print("❌ アイテム探索: 失敗")
    
    # 最終状態の表示
    print(f"\n📊 最終状態: 💰{agent.money} ⭐{agent.experience_points} 📦{len(agent.items)} 🧠{len(agent.discovered_info)}")
    print("✅ 個別探索タイプの検証が完了しました")


if __name__ == "__main__":
    # メインの探索デモを実行
    demo_exploration_sequence()
    
    # 個別の探索タイプテストを実行
    test_individual_exploration_types() 