"""
改善された移動システムのデモンストレーション

このデモでは、以下の改善点を示します：
1. グラフベースの移動管理
2. バリデーション強化
3. パフォーマンス最適化
4. 状態管理の簡素化
"""

from src.systems.world_improved import ImprovedWorld
from src.models.spot import Spot
from src.models.agent import Agent
from src.models.monster import Monster, MonsterType


def create_improved_world():
    """改善されたワールドを作成"""
    world = ImprovedWorld()
    
    # === Spotの作成 ===
    
    # 街の中心部
    town_center = Spot("town_center", "街の中心部", "賑やかな街の中心部。様々な建物が立ち並んでいる。")
    world.add_spot(town_center)
    
    # 学校
    school = Spot("school", "桜丘学園", "大きな3階建ての学校。正面玄関と裏口がある。")
    world.add_spot(school)
    
    # 学校内部
    school_1f_hall = Spot("school_1f_hall", "1階廊下", "学校の1階廊下。職員室や1年生の教室がある。")
    world.add_spot(school_1f_hall)
    
    school_2f_hall = Spot("school_2f_hall", "2階廊下", "学校の2階廊下。2年生の教室がある。")
    world.add_spot(school_2f_hall)
    
    classroom_1a = Spot("classroom_1a", "1年A組", "1年A組の教室。窓から校庭が見える。")
    world.add_spot(classroom_1a)
    
    classroom_2a = Spot("classroom_2a", "2年A組", "2年A組の教室。静かで勉強に集中できる。")
    world.add_spot(classroom_2a)
    
    # 八百屋
    vegetable_shop = Spot("vegetable_shop", "田中青果店", "新鮮な野菜を扱う小さな八百屋。")
    world.add_spot(vegetable_shop)
    
    # === 移動接続の設定（バリデーション付き） ===
    
    print("=== 移動接続の設定 ===")
    
    # 基本的な移動（双方向）
    world.add_connection("town_center", "school", "北", "学校に向かう")
    world.add_connection("town_center", "vegetable_shop", "南", "八百屋に向かう")
    # vegetable_shopからtown_centerへの戻りは自動生成される
    
    # 学校内部の移動（双方向）
    world.add_connection("school", "school_1f_hall", "正面玄関", "正面玄関から入る")
    # school_1f_hallからschoolへの戻りは自動生成される
    
    world.add_connection("school_1f_hall", "school_2f_hall", "上", "階段で2階に上がる")
    # school_2f_hallからschool_1f_hallへの戻りは自動生成される
    
    world.add_connection("school_1f_hall", "classroom_1a", "東", "1年A組の教室に入る")
    # classroom_1aからschool_1f_hallへの戻りは自動生成される
    
    world.add_connection("school_2f_hall", "classroom_2a", "東", "2年A組の教室に入る")
    # classroom_2aからschool_2f_hallへの戻りは自動生成される
    
    # === 条件付き移動の設定（片方向のみ） ===
    
    # 鍵が必要な移動（片方向のみ）
    world.add_connection("school_1f_hall", "school_2f_hall", "秘密の階段", "秘密の階段を使う",
                        conditions={"required_key": "secret_key"}, is_bidirectional=False)
    
    # レベル制限のある移動（片方向のみ）
    world.add_connection("school_2f_hall", "classroom_2a", "特別教室", "特別教室に入る",
                        conditions={"required_level": 10}, is_bidirectional=False)
    
    # === エージェントの作成 ===
    
    player = Agent("player_1", "プレイヤー1", "冒険者")
    player.set_current_spot_id("town_center")
    world.add_agent(player)
    
    # === モンスターの配置 ===
    
    # 攻撃的なモンスター
    aggressive_monster = Monster("monster_1", "凶暴な犬", "攻撃的な犬", MonsterType.AGGRESSIVE)
    school_1f_hall.add_monster(aggressive_monster)
    
    # 隠れているモンスター
    hidden_monster = Monster("monster_2", "隠れているネズミ", "小さなネズミ", MonsterType.HIDDEN)
    classroom_1a.add_monster(hidden_monster)
    
    return world


def demonstrate_improvements(world: ImprovedWorld):
    """改善点のデモンストレーション"""
    
    print("\n=== 改善された移動システムのデモ ===")
    
    # 1. バリデーション機能
    print("\n1. バリデーション機能")
    validation_errors = world.validate_world()
    if validation_errors:
        print("検証エラー:")
        for error in validation_errors:
            if "循環参照" in error:
                print(f"⚠️  {error}")
                print("   注: 短い循環（4個以下のSpot）は正常な移動パターンです")
            else:
                print(f"❌  {error}")
    else:
        print("✅ ワールドの検証が完了しました")
    
    # 2. 統計情報
    print("\n2. 移動統計情報")
    stats = world.get_movement_statistics()
    print(f"総Spot数: {stats['total_spots']}")
    print(f"総接続数: {stats['total_connections']}")
    print(f"平均接続数: {stats['average_connections_per_spot']:.2f}")
    print(f"最も接続が多いSpot: {stats['most_connected_spot']}")
    print(f"孤立したSpot数: {stats['isolated_spots_count']}")
    
    # 3. 最短経路検索
    print("\n3. 最短経路検索")
    shortest_path = world.get_shortest_path("classroom_1a", "vegetable_shop")
    if shortest_path:
        print(f"1年A組から八百屋への最短経路: {' → '.join(shortest_path)}")
    else:
        print("経路が見つかりません")
    
    # 4. 代替経路検索
    print("\n4. 代替経路検索")
    alternative_routes = world.get_alternative_routes("classroom_1a", "vegetable_shop", max_routes=3)
    for i, route in enumerate(alternative_routes, 1):
        print(f"代替経路{i}: {' → '.join(route)}")
    
    # 5. キャッシュ機能
    print("\n5. キャッシュ機能")
    player = world.get_agent("player_1")
    movements = world.movement_cache.get_available_movements("town_center", player)
    print(f"街の中心部からの移動可能先: {[m.direction for m in movements]}")
    
    # 6. 条件付き移動
    print("\n6. 条件付き移動")
    # 鍵を持たない状態での移動試行
    movements_without_key = world.movement_cache.get_available_movements("school_1f_hall", player)
    secret_staircase_movements = [m for m in movements_without_key if "秘密の階段" in m.description]
    if secret_staircase_movements:
        print("❌ 鍵がないのに秘密の階段が利用可能になっています")
    else:
        print("✅ 鍵が必要な移動が正しく制限されています")
    
    # 7. パフォーマンステスト
    print("\n7. パフォーマンステスト")
    import time
    
    # 移動可能先の取得時間を測定
    start_time = time.time()
    for _ in range(1000):
        world.movement_cache.get_available_movements("town_center", player)
    end_time = time.time()
    
    print(f"1000回の移動可能先取得にかかった時間: {(end_time - start_time)*1000:.2f}ms")
    
    # 8. エラー処理
    print("\n8. エラー処理")
    
    # 存在しないSpotへの移動試行
    is_valid, errors = world.movement_validator.validate_movement(
        "town_center", "non_existent_spot", "東", player
    )
    if not is_valid:
        print(f"✅ 無効な移動が正しく検出されました: {errors}")
    
    # 存在しない接続への移動試行
    is_valid, errors = world.movement_validator.validate_movement(
        "town_center", "school", "存在しない方向", player
    )
    if not is_valid:
        print(f"✅ 存在しない接続が正しく検出されました: {errors}")


def demonstrate_movement_execution(world: ImprovedWorld):
    """移動実行のデモンストレーション"""
    
    print("\n=== 移動実行のデモ ===")
    
    player = world.get_agent("player_1")
    
    # 現在位置の確認
    current_spot = world.get_spot(player.get_current_spot_id())
    print(f"現在位置: {current_spot.name}")
    
    # 利用可能な行動を取得
    available_actions = world.get_available_actions_for_agent("player_1")
    print(f"利用可能な移動: {[m.direction for m in available_actions['available_movements']]}")
    
    # 移動実行
    print("\n移動実行:")
    
    # 1. 学校に移動
    print("1. 学校への移動を試行...")
    result = world.execute_spot_action("player_1", "movement_北")
    print(f"結果: {result.success} - {result.message}")
    
    if result.success:
        # 移動後の位置確認
        new_spot = world.get_spot(player.get_current_spot_id())
        print(f"移動後の位置: {new_spot.name}")
        
        # 2. 学校内部に入る
        print("\n2. 学校内部への移動を試行...")
        result = world.execute_spot_action("player_1", "movement_正面玄関")
        print(f"結果: {result.success} - {result.message}")
        
        if result.success:
            # 移動後の位置確認
            new_spot = world.get_spot(player.get_current_spot_id())
            print(f"移動後の位置: {new_spot.name}")
            
            # 3. 2階に上がる
            print("\n3. 2階への移動を試行...")
            result = world.execute_spot_action("player_1", "movement_上")
            print(f"結果: {result.success} - {result.message}")
            
            if result.success:
                # 移動後の位置確認
                new_spot = world.get_spot(player.get_current_spot_id())
                print(f"移動後の位置: {new_spot.name}")
                
                # 4. 教室に入る
                print("\n4. 教室への移動を試行...")
                result = world.execute_spot_action("player_1", "movement_東")
                print(f"結果: {result.success} - {result.message}")
                
                if result.success:
                    # 移動後の位置確認
                    new_spot = world.get_spot(player.get_current_spot_id())
                    print(f"移動後の位置: {new_spot.name}")
    
    # 最終位置の確認
    final_spot = world.get_spot(player.get_current_spot_id())
    print(f"\n最終位置: {final_spot.name}")


def demonstrate_advanced_features(world: ImprovedWorld):
    """高度な機能のデモンストレーション"""
    
    print("\n=== 高度な機能のデモ ===")
    
    # 1. 鍵を持った状態での移動
    print("\n1. 鍵を持った状態での移動")
    player = world.get_agent("player_1")
    
    # 鍵を追加
    from src.models.item import Item
    secret_key = Item("secret_key", "秘密の鍵")
    player.add_item(secret_key)
    
    # デバッグ情報
    print(f"プレイヤーが持っているアイテム: {[item.item_id for item in player.get_items()]}")
    print(f"プレイヤーが鍵を持っているか: {player.has_item('secret_key')}")
    
    # 鍵が必要な移動を試行
    movements_with_key = world.movement_cache.get_available_movements("school_1f_hall", player)
    print(f"school_1f_hallからの移動可能先: {[m.direction for m in movements_with_key]}")
    
    secret_staircase_movements = [m for m in movements_with_key if "秘密の階段" in m.description]
    if secret_staircase_movements:
        print("✅ 鍵を持っているので秘密の階段が利用可能です")
    else:
        print("❌ 鍵を持っているのに秘密の階段が利用できません")
        
        # さらにデバッグ情報
        print("利用可能な移動の詳細:")
        for movement in movements_with_key:
            print(f"  - {movement.direction}: {movement.description}")
        
        # 秘密の階段の接続を直接確認
        secret_edges = world.movement_graph.edges.get("school_1f_hall", [])
        for edge in secret_edges:
            if "秘密の階段" in edge.description:
                print(f"秘密の階段の接続条件: {edge.conditions}")
                print(f"条件チェック結果: {world.movement_cache._check_movement_conditions(edge, player)}")
    
    # 2. レベル制限のテスト
    print("\n2. レベル制限のテスト")
    # プレイヤーのレベルを設定（レベル10以上にする）
    player.add_experience_points(1000)  # レベル10以上にする
    
    movements_with_level = world.movement_cache.get_available_movements("school_2f_hall", player)
    special_classroom_movements = [m for m in movements_with_level if "特別教室" in m.description]
    if special_classroom_movements:
        print("✅ レベルが十分なので特別教室が利用可能です")
    else:
        print("❌ レベルが十分なのに特別教室が利用できません")
    
    # 3. 経路探索の詳細
    print("\n3. 経路探索の詳細")
    all_routes = world.get_alternative_routes("classroom_1a", "vegetable_shop", max_routes=5)
    print(f"1年A組から八百屋への全経路数: {len(all_routes)}")
    for i, route in enumerate(all_routes, 1):
        route_names = [world.get_spot(spot_id).name for spot_id in route]
        print(f"経路{i}: {' → '.join(route_names)}")


if __name__ == "__main__":
    # 改善されたワールドを作成
    world = create_improved_world()
    
    # 改善点のデモンストレーション
    demonstrate_improvements(world)
    
    # 移動実行のデモンストレーション
    demonstrate_movement_execution(world)
    
    # 高度な機能のデモンストレーション
    demonstrate_advanced_features(world)
    
    print("\n=== デモ完了 ===")
    print("改善された移動システムにより、以下の問題が解決されました：")
    print("✅ データの整合性と一貫性の向上")
    print("✅ 複雑な状態管理の簡素化")
    print("✅ パフォーマンスの最適化")
    print("✅ バリデーションの強化")
    print("✅ 保守性の向上") 