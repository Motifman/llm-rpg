from src.models.spot import Spot


def create_rpg_world_example():
    """RPGワールドの階層的な場所管理の使用例"""
    
    spots = {}
    
    # === 最上位レベルの場所 ===
    
    # 街の中心部
    town_center = Spot("town_center", "街の中心部", "賑やかな街の中心部。様々な建物が立ち並んでいる。")
    spots[town_center.spot_id] = town_center
    
    # 学校（複合的な建物）
    school = Spot("school", "桜丘学園", "大きな3階建ての学校。正面玄関と裏口がある。")
    spots[school.spot_id] = school
    
    # 八百屋（シンプルな建物）
    vegetable_shop = Spot("vegetable_shop", "田中青果店", "新鮮な野菜を扱う小さな八百屋。")
    spots[vegetable_shop.spot_id] = vegetable_shop
    
    # === 学校内部の場所 ===
    
    # 1階廊下（学校の正面玄関）
    school_1f_hall = Spot("school_1f_hall", "1階廊下", "学校の1階廊下。職員室や1年生の教室がある。", parent_spot_id="school")
    school_1f_hall.set_as_entrance("正面玄関")
    school_1f_hall.set_exit_to_parent("town_center")  # 学校から出ると街の中心部に
    spots[school_1f_hall.spot_id] = school_1f_hall
    
    # 2階廊下
    school_2f_hall = Spot("school_2f_hall", "2階廊下", "学校の2階廊下。2年生の教室がある。", parent_spot_id="school")
    # 2階からは直接外に出ることはできない
    spots[school_2f_hall.spot_id] = school_2f_hall
    
    # 裏口（学校のもう一つの入口）
    school_back_entrance = Spot("school_back_entrance", "裏口", "学校の裏口。体育館に近い。", parent_spot_id="school")
    school_back_entrance.set_as_entrance("裏口")
    school_back_entrance.set_exit_to_parent("town_center")
    spots[school_back_entrance.spot_id] = school_back_entrance
    
    # 教室1-A
    classroom_1a = Spot("classroom_1a", "1年A組", "1年A組の教室。窓から校庭が見える。", parent_spot_id="school")
    # 教室からは直接外に出ることはできない
    spots[classroom_1a.spot_id] = classroom_1a
    
    # 教室2-A  
    classroom_2a = Spot("classroom_2a", "2年A組", "2年A組の教室。静かで勉強に集中できる。", parent_spot_id="school")
    # 教室からは直接外に出ることはできない
    spots[classroom_2a.spot_id] = classroom_2a
    
    # === 接続関係の設定 ===
    
    # 街の中心部の接続
    town_center.add_connection("南", "vegetable_shop")
    town_center.add_connection("北", "school")
    
    # 学校への入口設定
    school.add_entry_point("正面玄関", "school_1f_hall")
    school.add_entry_point("裏口", "school_back_entrance")
    school.add_child_spot("school_1f_hall")
    school.add_child_spot("school_2f_hall")
    school.add_child_spot("school_back_entrance")
    school.add_child_spot("classroom_1a")
    school.add_child_spot("classroom_2a")
    
    # 八百屋への接続
    vegetable_shop.add_connection("北", "town_center")
    
    # 学校内部の接続
    school_1f_hall.add_connection("上", "school_2f_hall")  # 階段
    school_1f_hall.add_connection("東", "classroom_1a")
    school_1f_hall.add_connection("西", "school_back_entrance")
    
    school_2f_hall.add_connection("下", "school_1f_hall")  # 階段
    school_2f_hall.add_connection("東", "classroom_2a")
    
    classroom_1a.add_connection("西", "school_1f_hall")
    classroom_2a.add_connection("西", "school_2f_hall")
    school_back_entrance.add_connection("東", "school_1f_hall")
    
    return spots


def demonstrate_movement(spots):
    """移動システムのデモンストレーション"""
    
    print("=== RPG階層的移動システムのデモ ===\n")
    
    # シナリオ：教室1-Aから八百屋に行く
    current_spot_id = "classroom_1a"
    target_description = "八百屋に買い物に行く"
    
    print(f"目標: {target_description}")
    print(f"開始地点: {spots[current_spot_id].name}\n")
    
    # Step 1: 教室1-Aから利用可能な移動先を確認
    current_spot = spots[current_spot_id]
    print(f"現在地: {current_spot.name}")
    print(f"説明: {current_spot.description}")
    
    movements = current_spot.get_available_movements()
    print("利用可能な移動先:")
    for direction, target_id in movements.items():
        target_spot = spots[target_id]
        print(f"  {direction} -> {target_spot.name}")
    
    # Step 2: 廊下に移動
    current_spot_id = "school_1f_hall"
    print(f"\n移動: 西 -> {spots[current_spot_id].name}")
    
    # Step 3: 1階廊下から学校を出る（外に出ることができる場所）
    current_spot = spots[current_spot_id]
    movements = current_spot.get_available_movements()
    print("利用可能な移動先:")
    for direction, target_id in movements.items():
        target_spot = spots[target_id]
        print(f"  {direction} -> {target_spot.name}")
    
    # Step 4: 街の中心部に移動
    current_spot_id = "town_center"
    print(f"\n移動: 外に出る -> {spots[current_spot_id].name}")
    print("（1階廊下は学校の出口なので、ここから外に出ることができる）")
    
    # Step 5: 八百屋に移動
    current_spot = spots[current_spot_id]
    movements = current_spot.get_available_movements()
    print("利用可能な移動先:")
    for direction, target_id in movements.items():
        target_spot = spots[target_id]
        print(f"  {direction} -> {target_spot.name}")
    
    current_spot_id = "vegetable_shop"
    print(f"\n移動: 南 -> {spots[current_spot_id].name}")
    print(f"到着！{spots[current_spot_id].description}")


def demonstrate_blocked_movement(spots):
    """2階からの移動制限のデモンストレーション"""
    
    print("\n\n=== 移動制限のデモ（2階教室から） ===\n")
    
    # シナリオ：2階の教室から外に出ようとする
    current_spot_id = "classroom_2a"
    
    print(f"現在地: {spots[current_spot_id].name}")
    print(f"説明: {spots[current_spot_id].description}")
    
    current_spot = spots[current_spot_id]
    movements = current_spot.get_available_movements()
    print("利用可能な移動先:")
    
    if not movements:
        print("  （移動先がありません）")
    else:
        for direction, target_id in movements.items():
            target_spot = spots[target_id]
            print(f"  {direction} -> {target_spot.name}")
    
    print("\n👆 2階の教室からは直接外に出ることができません！")
    print("廊下に出て、階段で1階に降りてから外に出る必要があります。")
    
    # 正しいルートを示す
    print("\n=== 正しい移動ルート ===")
    print("2年A組 → 2階廊下 → 1階廊下 → 外に出る → 街の中心部")
    
    # Step 1: 2階廊下へ
    current_spot_id = "school_2f_hall"
    print(f"\n移動: 西 -> {spots[current_spot_id].name}")
    
    # Step 2: 1階廊下へ
    current_spot_id = "school_1f_hall"
    print(f"移動: 下 -> {spots[current_spot_id].name}")
    
    # Step 3: 外に出る
    current_spot_id = "town_center"
    print(f"移動: 外に出る -> {spots[current_spot_id].name}")
    print("✅ これで現実的な移動ルートが完成しました！")


if __name__ == "__main__":
    spots = create_rpg_world_example()
    demonstrate_movement(spots)
    demonstrate_blocked_movement(spots) 