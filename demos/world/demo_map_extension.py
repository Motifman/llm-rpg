#!/usr/bin/env python3
"""
マップ拡張機能のデモ
複数のファイルに分かれたマップデータを段階的に読み込んでマップを拡張する機能を実演
"""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.world.spot_manager import SpotManager
from game.world.entrance_manager import EntranceConfig


def demo_map_extension():
    """マップ拡張機能のデモ"""
    print("=== マップ拡張機能デモ ===")
    print("複数のファイルから段階的にマップを構築します")
    print("=" * 50)
    
    # SpotManagerを作成
    spot_manager = SpotManager()
    
    # ステップ1: 学校マップを読み込み
    print("\nステップ1: 学校マップを読み込み")
    print("-" * 30)
    spot_manager.load_map_from_json("data/maps/school.json")
    print("学校マップを読み込みました")
    print(spot_manager.get_map_extension_summary())
    
    # ステップ2: ショッピングモールマップを拡張
    print("\nステップ2: ショッピングモールマップを拡張")
    print("-" * 30)
    spot_manager.extend_map_from_json("data/maps/shopping_mall.json")
    print("ショッピングモールマップを拡張しました")
    print(spot_manager.get_map_extension_summary())
    
    # ステップ3: 市街地マップを拡張
    print("\nステップ3: 市街地マップを拡張")
    print("-" * 30)
    spot_manager.extend_map_from_json("data/maps/city_street.json")
    print("市街地マップを拡張しました")
    print(spot_manager.get_map_extension_summary())
    
    # ステップ4: 都市全体の接続を追加
    print("\nステップ4: 都市全体の接続を追加")
    print("-" * 30)
    spot_manager.load_connections_from_json("data/maps/city_connections.json")
    print("都市全体の接続を追加しました")
    print(spot_manager.get_map_extension_summary())
    
    # 最終的なマップの概要
    print("\n=== 最終的なマップ概要 ===")
    print("=" * 50)
    print(spot_manager.get_map_summary())
    
    # 位置情報の確認
    print("\n=== 位置情報の確認 ===")
    print("=" * 50)
    
    # 校門の位置情報
    print("校門の位置情報:")
    print(spot_manager.get_spot_location_summary("school_gate"))
    
    # モール入口の位置情報
    print("\nモール入口の位置情報:")
    print(spot_manager.get_spot_location_summary("mall_entrance"))
    
    # 市街地の位置情報
    print("\n市街地の位置情報:")
    print(spot_manager.get_spot_location_summary("city_street"))
    
    # グループ間の移動経路を確認
    print("\n=== グループ間の移動経路確認 ===")
    print("=" * 50)
    
    # 学校からモールへの経路
    print("学校からモールへの経路:")
    school_to_mall = spot_manager.get_entrances_between_groups("school_grounds", "shopping_mall")
    if school_to_mall:
        for entrance in school_to_mall:
            print(f"- {entrance.name}: {entrance.description}")
    else:
        print("- 直接の接続はありません（市街地経由）")
    
    # 学校から市街地への経路
    print("\n学校から市街地への経路:")
    school_to_city = spot_manager.get_entrances_between_groups("school_grounds", "city_area")
    if school_to_city:
        for entrance in school_to_city:
            print(f"- {entrance.name}: {entrance.description}")
    else:
        print("- 直接の接続はありません")
    
    # 利用可能な出口の確認
    print("\n=== 利用可能な出口の確認 ===")
    print("=" * 50)
    
    # 校門から利用可能な出口
    print("校門から利用可能な出口:")
    available_exits = spot_manager.get_available_exits_from_spot("school_gate")
    for exit_entrance in available_exits:
        print(f"- {exit_entrance.name}: {exit_entrance.description}")
    
    # モール入口から利用可能な出口
    print("\nモール入口から利用可能な出口:")
    available_exits = spot_manager.get_available_exits_from_spot("mall_entrance")
    for exit_entrance in available_exits:
        print(f"- {exit_entrance.name}: {exit_entrance.description}")
    
    # マップの整合性チェック
    print("\n=== マップの整合性チェック ===")
    print("=" * 50)
    errors = spot_manager.validate_map()
    if errors:
        print("エラーが見つかりました:")
        for error in errors:
            print(f"- {error}")
    else:
        print("マップにエラーはありません")
    
    return spot_manager


def demo_incremental_loading():
    """段階的な読み込みデモ"""
    print("\n=== 段階的な読み込みデモ ===")
    print("=" * 50)
    
    spot_manager = SpotManager()
    
    # 段階的にスポットを追加
    print("\n1. 基本スポットを追加")
    spot_manager.extend_map_from_json("data/maps/city_street.json")
    print(f"スポット数: {len(spot_manager.get_all_spots())}")
    
    print("\n2. 学校を追加")
    spot_manager.extend_map_from_json("data/maps/school.json")
    print(f"スポット数: {len(spot_manager.get_all_spots())}")
    
    print("\n3. ショッピングモールを追加")
    spot_manager.extend_map_from_json("data/maps/shopping_mall.json")
    print(f"スポット数: {len(spot_manager.get_all_spots())}")
    
    print("\n4. 接続を追加")
    spot_manager.load_connections_from_json("data/maps/city_connections.json")
    print(f"接続数: {sum(len(edges) for edges in spot_manager.movement_graph.edges.values())}")
    
    print("\n最終結果:")
    print(spot_manager.get_map_extension_summary())


def demo_connection_only_loading():
    """接続のみの読み込みデモ"""
    print("\n=== 接続のみの読み込みデモ ===")
    print("=" * 50)
    
    # 既存のマップを作成
    spot_manager = demo_map_extension()
    
    # 新しい接続を追加
    print("\n新しい接続を追加:")
    new_connections = {
        "connections": [
            {"from": "library", "to": "bookstore", "description": "図書館から書店へ（本の貸し出し）"},
            {"from": "cafeteria", "to": "food_court", "description": "食堂からフードコートへ（食事の選択肢）"},
            {"from": "park", "to": "playground", "description": "公園から校庭へ（子供の遊び場）"}
        ]
    }
    
    # 一時ファイルを作成
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(new_connections, f, ensure_ascii=False, indent=2)
        temp_file = f.name
    
    try:
        spot_manager.load_connections_from_json(temp_file)
        print("新しい接続を追加しました")
        print(f"接続数: {sum(len(edges) for edges in spot_manager.movement_graph.edges.values())}")
        
        # 新しい接続の確認
        print("\n追加された接続:")
        for spot_id in ["library", "cafeteria", "park"]:
            destinations = spot_manager.get_destination_spot_ids(spot_id)
            if destinations:
                print(f"{spot_id}から移動可能: {destinations}")
        
    finally:
        os.unlink(temp_file)


def main():
    """メイン関数"""
    print("マップ拡張機能のデモ")
    print("複数のファイルに分かれたマップデータを段階的に読み込んでマップを拡張する機能を実演します")
    
    # 基本的なマップ拡張デモ
    demo_map_extension()
    
    # 段階的な読み込みデモ
    demo_incremental_loading()
    
    # 接続のみの読み込みデモ
    demo_connection_only_loading()
    
    print("\n=== デモ完了 ===")
    print("このデモでは以下の機能を実演しました:")
    print("- 複数ファイルからの段階的なマップ構築")
    print("- 既存マップへの拡張機能")
    print("- 接続のみの追加機能")
    print("- マップの整合性チェック")


if __name__ == "__main__":
    main() 