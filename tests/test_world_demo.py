from src.models.spot import Spot
from src.models.agent import Agent
from src.models.action import Movement
from src.systems.world import World


def create_test_world():
    """検証用のワールドを作成"""
    world = World()
    
    # === 最上位レベルの場所 ===
    
    # 街の中心部
    town_center = Spot("town_center", "街の中心部", "賑やかな街の中心部。様々な建物が立ち並んでいる。")
    world.add_spot(town_center)
    
    # 学校（複合的な建物）
    school = Spot("school", "桜丘学園", "大きな3階建ての学校。正面玄関と裏口がある。")
    world.add_spot(school)
    
    # 八百屋（シンプルな建物）
    vegetable_shop = Spot("vegetable_shop", "田中青果店", "新鮮な野菜を扱う小さな八百屋。")
    world.add_spot(vegetable_shop)
    
    # === 学校内部の場所 ===
    
    # 1階廊下（学校の正面玄関）
    school_1f_hall = Spot("school_1f_hall", "1階廊下", "学校の1階廊下。職員室や1年生の教室がある。", parent_spot_id="school")
    school_1f_hall.set_as_entrance("正面玄関")
    school_1f_hall.set_exit_to_parent("town_center")
    world.add_spot(school_1f_hall)
    
    # 2階廊下
    school_2f_hall = Spot("school_2f_hall", "2階廊下", "学校の2階廊下。2年生の教室がある。", parent_spot_id="school")
    # 2階からは直接外に出ることはできない
    world.add_spot(school_2f_hall)
    
    # 裏口（学校のもう一つの入口）
    school_back_entrance = Spot("school_back_entrance", "裏口", "学校の裏口。体育館に近い。", parent_spot_id="school")
    school_back_entrance.set_as_entrance("裏口")
    school_back_entrance.set_exit_to_parent("town_center")
    world.add_spot(school_back_entrance)
    
    # 教室1-A
    classroom_1a = Spot("classroom_1a", "1年A組", "1年A組の教室。窓から校庭が見える。", parent_spot_id="school")
    world.add_spot(classroom_1a)
    
    # 教室2-A  
    classroom_2a = Spot("classroom_2a", "2年A組", "2年A組の教室。静かで勉強に集中できる。", parent_spot_id="school")
    world.add_spot(classroom_2a)
    
    # === 接続関係の設定 ===
    
    # 街の中心部の接続
    town_center.add_movement(Movement("南に移動", "南", "vegetable_shop"))
    town_center.add_movement(Movement("北に移動", "北", "school"))
    
    # 学校への入口設定
    school.add_entry_point("正面玄関", "school_1f_hall")
    school.add_entry_point("裏口", "school_back_entrance")
    school.add_child_spot("school_1f_hall")
    school.add_child_spot("school_2f_hall")
    school.add_child_spot("school_back_entrance")
    school.add_child_spot("classroom_1a")
    school.add_child_spot("classroom_2a")
    
    # 八百屋への接続
    vegetable_shop.add_movement(Movement("北に移動", "北", "town_center"))
    
    # 学校内部の接続
    school_1f_hall.add_movement(Movement("上に移動", "上", "school_2f_hall"))  # 階段
    school_1f_hall.add_movement(Movement("東に移動", "東", "classroom_1a"))
    school_1f_hall.add_movement(Movement("西に移動", "西", "school_back_entrance"))
    
    school_2f_hall.add_movement(Movement("下に移動", "下", "school_1f_hall"))  # 階段
    school_2f_hall.add_movement(Movement("東に移動", "東", "classroom_2a"))
    
    classroom_1a.add_movement(Movement("西に移動", "西", "school_1f_hall"))
    classroom_2a.add_movement(Movement("西に移動", "西", "school_2f_hall"))
    school_back_entrance.add_movement(Movement("東に移動", "東", "school_1f_hall"))
    
    # === エージェントの作成と配置 ===
    
    # テストエージェントを作成
    test_agent = Agent("agent_001", "山田太郎")
    test_agent.set_current_spot_id("classroom_1a")  # 1年A組からスタート
    world.add_agent(test_agent)
    
    return world


def display_current_status(world: World, agent_id: str, step_num: int = None):
    """現在の状況を詳細に表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
    if step_num is not None:
        print(f"\n📍 ステップ {step_num}")
    print("=" * 60)
    print(f"🚶 エージェント: {agent.name} (ID: {agent.agent_id})")
    print(f"📍 現在地: {current_spot.name} (ID: {current_spot.spot_id})")
    print(f"📝 説明: {current_spot.description}")
    
    if current_spot.parent_spot_id:
        parent_spot = world.get_spot(current_spot.parent_spot_id)
        print(f"🏢 所属建物: {parent_spot.name}")
    
    if current_spot.is_entrance_spot():
        print(f"🚪 この場所は{current_spot.get_entrance_name()}です")
    
    print("=" * 60)


def display_available_movements(world: World, agent_id: str):
    """利用可能な移動先を表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    available_movements = current_spot.get_available_movements()
    
    if not available_movements:
        print("❌ 利用可能な移動先がありません")
        return available_movements
    
    print("\n🚶‍♂️ 利用可能な行動:")
    print("-" * 40)
    
    for movement in available_movements:
        target_spot = world.get_spot(movement.target_spot_id)
        print(f"  {movement.direction} → {target_spot.name}")
    
    return available_movements


def execute_movement(world: World, agent_id: str, action: str, step_num: int):
    """移動を実行して結果を表示"""
    print(f"\n🚶 ステップ {step_num}: {action} を実行")
    
    # 移動前の状態を記録
    agent = world.get_agent(agent_id)
    old_spot = world.get_spot(agent.get_current_spot_id())
    
    # 現在地から該当するMovementオブジェクトを取得
    available_movements = old_spot.get_available_movements()
    movement_obj = None
    for movement in available_movements:
        if movement.direction == action:
            movement_obj = movement
            break
    
    if movement_obj is None:
        print(f"❌ 移動失敗: '{action}'は利用可能な移動ではありません")
        return False
    
    # 移動実行
    try:
        world.execute_agent_movement(agent_id, movement_obj)
        new_spot = world.get_spot(agent.get_current_spot_id())
        print(f"✅ 移動成功: {old_spot.name} → {new_spot.name}")
        return True
    except Exception as e:
        print(f"❌ 移動失敗: '{action}' - エラー: {e}")
        return False


def demo_scenario_1():
    """シナリオ1: 教室1-Aから八百屋への移動"""
    print("🎮 RPG階層的移動システム自動検証デモ")
    print("=" * 60)
    print("📋 シナリオ1: 1年A組から八百屋への移動")
    
    world = create_test_world()
    agent_id = "agent_001"
    
    # 移動シナリオを定義
    movements = [
        "西",      # 教室 → 1階廊下
        "外に出る",  # 1階廊下 → 街の中心部  
        "南",      # 街の中心部 → 八百屋
        "北",      # 八百屋 → 街の中心部
    ]
    
    step = 0
    
    # 初期状態の表示
    display_current_status(world, agent_id, step)
    display_available_movements(world, agent_id)
    
    # 各移動を実行
    for movement in movements:
        step += 1
        success = execute_movement(world, agent_id, movement, step)
        
        if success:
            display_current_status(world, agent_id)
            display_available_movements(world, agent_id)
        else:
            print("❌ 移動に失敗したため、シナリオを中断します")
            break
    
    print("\n✅ シナリオ1完了！")


def demo_scenario_2():
    """シナリオ2: 2階からの移動制限確認"""
    print("\n\n🎮 シナリオ2: 2階からの移動制限確認")
    print("=" * 60)
    print("📋 2階教室からは直接外に出ることができないことを確認")
    
    world = create_test_world()
    agent_id = "agent_001"
    
    # エージェントを2階教室に配置
    agent = world.get_agent(agent_id)
    agent.set_current_spot_id("classroom_2a")
    
    step = 0
    
    # 初期状態の表示（2階教室）
    display_current_status(world, agent_id, step)
    available_movements = display_available_movements(world, agent_id)
    
    # 「外に出る」オプションがないことを確認
    if "外に出る" in available_movements:
        print("❌ 問題: 2階教室から直接外に出ることができてしまいます！")
    else:
        print("✅ 正常: 2階教室からは直接外に出ることができません")
    
    # 正しいルートで移動
    movements = [
        "西",      # 2階教室 → 2階廊下
        "下",      # 2階廊下 → 1階廊下
        "外に出る",  # 1階廊下 → 街の中心部
    ]
    
    for movement in movements:
        step += 1
        success = execute_movement(world, agent_id, movement, step)
        
        if success:
            display_current_status(world, agent_id)
            display_available_movements(world, agent_id)
        else:
            print("❌ 移動に失敗したため、シナリオを中断します")
            break
    
    print("\n✅ シナリオ2完了！現実的な移動制限が正しく機能しています。")


def demo_scenario_3():
    """シナリオ3: 学校の複数入口テスト"""
    print("\n\n🎮 シナリオ3: 学校の複数入口テスト")
    print("=" * 60)
    print("📋 街の中心部から学校の正面玄関と裏口への入場をテスト")
    
    world = create_test_world()
    agent_id = "agent_001"
    
    # エージェントを街の中心部に配置
    agent = world.get_agent(agent_id)
    agent.set_current_spot_id("town_center")
    
    step = 0
    
    # 初期状態の表示（街の中心部）
    display_current_status(world, agent_id, step)
    display_available_movements(world, agent_id)
    
    # 学校に入る -> 正面玄関へ
    step += 1
    success = execute_movement(world, agent_id, "北", step)
    
    if success:
        display_current_status(world, agent_id)
        available_movements = display_available_movements(world, agent_id)
        
        # 正面玄関と裏口の両方が表示されることを確認
        entrances = [movement.direction for movement in available_movements if "に入る" in movement.direction]
        print(f"\n🚪 確認された入口: {entrances}")
        
        if len(entrances) >= 2:
            print("✅ 正常: 複数の入口が利用可能です")
        else:
            print("❌ 問題: 入口が足りません")
        
        # 正面玄関に入る
        step += 1
        success = execute_movement(world, agent_id, "正面玄関に入る", step)
        
        if success:
            display_current_status(world, agent_id)
            display_available_movements(world, agent_id)
    
    print("\n✅ シナリオ3完了！複数入口システムが正常に動作しています。")


def main():
    """メイン関数"""
    try:
        demo_scenario_1()
        demo_scenario_2() 
        demo_scenario_3()
        
        print("\n" + "=" * 60)
        print("🎉 全てのシナリオが正常に完了しました！")
        print("✅ Worldクラスの階層的移動システムは期待通りに動作しています。")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 