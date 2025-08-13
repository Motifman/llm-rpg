from src_old.models.spot import Spot
from src_old.models.agent import Agent
from src_old.models.action import Movement
from src_old.systems.world import World


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


def display_current_status(world: World, agent_id: str):
    """現在の状況を詳細に表示"""
    agent = world.get_agent(agent_id)
    current_spot = world.get_spot(agent.get_current_spot_id())
    
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
    
    for i, movement in enumerate(available_movements, 1):
        target_spot = world.get_spot(movement.target_spot_id)
        print(f"{i}. {movement.direction} → {target_spot.name}")
    
    return available_movements


def get_user_choice(available_movements: list) -> str:
    """ユーザーから移動選択を取得"""
    if not available_movements:
        return None
    
    actions = [movement.direction for movement in available_movements]
    
    while True:
        try:
            print("\n移動したい行動の番号を入力してください (0: 終了):")
            choice = input("選択 > ").strip()
            
            if choice == "0":
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(actions):
                return actions[choice_num - 1]
            else:
                print(f"❌ 1〜{len(actions)}の番号を入力してください")
        
        except ValueError:
            print("❌ 有効な番号を入力してください")
        except KeyboardInterrupt:
            print("\n終了します...")
            return None


def execute_movement(world: World, agent_id: str, action: str):
    """移動を実行して結果を表示"""
    print(f"\n🚶 実行: {action}")
    
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
        print(f"✅ 移動成功!")
        print(f"   {old_spot.name} → {new_spot.name}")
        return True
    except Exception as e:
        print(f"❌ 移動失敗: '{action}' - エラー: {e}")
        return False


def main():
    """メイン関数"""
    print("🎮 RPG階層的移動システム検証ツール")
    print("=" * 60)
    
    # ワールドとエージェントを作成
    world = create_test_world()
    agent_id = "agent_001"
    
    print("🌟 ワールドが作成されました!")
    print("テストエージェント「山田太郎」が1年A組からスタートします。")
    
    # メインループ
    while True:
        try:
            # 現在の状況を表示
            display_current_status(world, agent_id)
            
            # 利用可能な移動先を表示
            available_movements = display_available_movements(world, agent_id)
            
            # ユーザーの選択を取得
            chosen_action = get_user_choice(available_movements)
            
            if chosen_action is None:
                print("\n👋 ゲームを終了します。お疲れ様でした！")
                break
            
            # 移動を実行
            execute_movement(world, agent_id, chosen_action)
            
            # 少し間を置く
            input("\nEnterキーを押して続行...")
            print("\n")
            
        except KeyboardInterrupt:
            print("\n👋 ゲームを終了します。お疲れ様でした！")
            break
        except Exception as e:
            print(f"❌ エラーが発生しました: {e}")
            break


if __name__ == "__main__":
    main() 