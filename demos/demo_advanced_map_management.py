#!/usr/bin/env python3
"""
高度なマップ管理機能のデモ
学校の例を使用して、SpotGroup、EntranceManager、MapBuilderの機能を実演
"""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.world.spot_manager import SpotManager
from game.world.spot_group import SpotGroupConfig
from game.world.entrance_manager import EntranceConfig
from game.world.spot import Spot


def create_school_map_config():
    """学校マップの設定を作成"""
    config = {
        "spots": [
            {"id": "school_gate", "name": "校門", "description": "学校の正門。警備員が立っている。"},
            {"id": "back_gate", "name": "裏門", "description": "学校の裏門。生徒の通学路として使われている。"},
            {"id": "playground", "name": "校庭", "description": "広い校庭。体育の授業や部活動で使用される。"},
            {"id": "corridor_1f", "name": "1階廊下", "description": "1階の廊下。教室への通路。"},
            {"id": "corridor_2f", "name": "2階廊下", "description": "2階の廊下。教室への通路。"},
            {"id": "classroom_1a", "name": "1年A組教室", "description": "1年A組の教室。机が整然と並んでいる。"},
            {"id": "classroom_1b", "name": "1年B組教室", "description": "1年B組の教室。机が整然と並んでいる。"},
            {"id": "classroom_2a", "name": "2年A組教室", "description": "2年A組の教室。机が整然と並んでいる。"},
            {"id": "classroom_2b", "name": "2年B組教室", "description": "2年B組の教室。机が整然と並んでいる。"},
            {"id": "staircase", "name": "階段", "description": "1階と2階を結ぶ階段。"},
            {"id": "library", "name": "図書館", "description": "静かな図書館。多くの本が並んでいる。"},
            {"id": "gym", "name": "体育館", "description": "大きな体育館。体育の授業や集会で使用される。"},
            {"id": "cafeteria", "name": "食堂", "description": "生徒が昼食を取る食堂。"},
            {"id": "teacher_room", "name": "職員室", "description": "先生たちが集まる職員室。"},
        ],
        "groups": [
            {
                "id": "school_grounds",
                "name": "学校敷地",
                "description": "学校の敷地全体",
                "spot_ids": ["school_gate", "back_gate", "playground", "corridor_1f", "corridor_2f", 
                            "classroom_1a", "classroom_1b", "classroom_2a", "classroom_2b", 
                            "staircase", "library", "gym", "cafeteria", "teacher_room"],
                "entrance_spot_ids": ["school_gate", "back_gate"],
                "tags": ["school", "main_area"]
            },
            {
                "id": "first_floor",
                "name": "1階",
                "description": "学校の1階部分",
                "spot_ids": ["corridor_1f", "classroom_1a", "classroom_1b", "library", "gym", "cafeteria", "teacher_room"],
                "tags": ["floor", "first_floor"]
            },
            {
                "id": "second_floor",
                "name": "2階",
                "description": "学校の2階部分",
                "spot_ids": ["corridor_2f", "classroom_2a", "classroom_2b"],
                "tags": ["floor", "second_floor"]
            },
            {
                "id": "classrooms",
                "name": "教室群",
                "description": "全ての教室",
                "spot_ids": ["classroom_1a", "classroom_1b", "classroom_2a", "classroom_2b"],
                "tags": ["academic", "classroom"]
            },
            {
                "id": "facilities",
                "name": "施設群",
                "description": "学校の主要施設",
                "spot_ids": ["library", "gym", "cafeteria", "teacher_room"],
                "tags": ["facility"]
            }
        ],
        "connections": [
            {"from": "school_gate", "to": "playground", "description": "校門から校庭へ"},
            {"from": "back_gate", "to": "playground", "description": "裏門から校庭へ"},
            {"from": "playground", "to": "corridor_1f", "description": "校庭から1階廊下へ"},
            {"from": "corridor_1f", "to": "classroom_1a", "description": "1階廊下から1年A組教室へ"},
            {"from": "corridor_1f", "to": "classroom_1b", "description": "1階廊下から1年B組教室へ"},
            {"from": "corridor_1f", "to": "library", "description": "1階廊下から図書館へ"},
            {"from": "corridor_1f", "to": "gym", "description": "1階廊下から体育館へ"},
            {"from": "corridor_1f", "to": "cafeteria", "description": "1階廊下から食堂へ"},
            {"from": "corridor_1f", "to": "teacher_room", "description": "1階廊下から職員室へ"},
            {"from": "corridor_1f", "to": "staircase", "description": "1階廊下から階段へ"},
            {"from": "staircase", "to": "corridor_2f", "description": "階段から2階廊下へ"},
            {"from": "corridor_2f", "to": "classroom_2a", "description": "2階廊下から2年A組教室へ"},
            {"from": "corridor_2f", "to": "classroom_2b", "description": "2階廊下から2年B組教室へ"},
        ]
    }
    return config


def demo_manual_construction():
    """手動でマップを構築するデモ"""
    print("=== 手動マップ構築デモ ===")
    
    # SpotManagerを作成
    spot_manager = SpotManager()
    
    # スポットを作成
    spots = {
        "school_gate": Spot("school_gate", "校門", "学校の正門。警備員が立っている。"),
        "playground": Spot("playground", "校庭", "広い校庭。体育の授業や部活動で使用される。"),
        "corridor_1f": Spot("corridor_1f", "1階廊下", "1階の廊下。教室への通路。"),
        "classroom_1a": Spot("classroom_1a", "1年A組教室", "1年A組の教室。机が整然と並んでいる。"),
    }
    
    # スポットをSpotManagerに追加
    for spot in spots.values():
        spot_manager.add_spot(spot)
    
    # 接続を追加
    spot_manager.movement_graph.add_connection("school_gate", "playground", "校門から校庭へ")
    spot_manager.movement_graph.add_connection("playground", "corridor_1f", "校庭から1階廊下へ")
    spot_manager.movement_graph.add_connection("corridor_1f", "classroom_1a", "1階廊下から1年A組教室へ")
    
    # グループを作成
    school_group_config = SpotGroupConfig(
        group_id="school_grounds",
        name="学校敷地",
        description="学校の敷地全体",
        spot_ids=["school_gate", "playground", "corridor_1f", "classroom_1a"],
        entrance_spot_ids=["school_gate"],
        tags=["school", "main_area"]
    )
    
    school_group = spot_manager.create_group(school_group_config)
    
    # グループにスポットを追加
    for spot in spots.values():
        spot_manager.add_spot_to_group(spot, "school_grounds")
    
    # 出入り口を追加
    entrance_config = EntranceConfig(
        entrance_id="main_entrance",
        name="正門",
        description="学校の正門",
        from_group_id="school_grounds",
        to_group_id="outside",
        from_spot_id="school_gate",
        to_spot_id="outside",
        is_bidirectional=True
    )
    spot_manager.add_entrance(entrance_config)
    
    print("手動でマップを構築しました")
    print(f"スポット数: {len(spot_manager.get_all_spots())}")
    print(f"グループ数: {len(spot_manager.get_all_groups())}")
    print(f"出入り口数: {len(spot_manager.entrance_manager.entrances)}")
    
    return spot_manager


def demo_config_file_construction():
    """設定ファイルからマップを構築するデモ"""
    print("\n=== 設定ファイルマップ構築デモ ===")
    
    # 設定を作成
    config = create_school_map_config()
    
    # 一時的なJSONファイルを作成
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        temp_file = f.name
    
    try:
        # SpotManagerを作成してJSONファイルから読み込み
        spot_manager = SpotManager()
        spot_manager.load_map_from_json(temp_file)
        
        print("設定ファイルからマップを構築しました")
        print(spot_manager.get_map_summary())
        
        # グループ機能のデモ
        print("\n=== グループ機能デモ ===")
        school_groups = spot_manager.get_groups_by_tag("school")
        print(f"学校タグを持つグループ: {len(school_groups)}個")
        for group in school_groups:
            print(f"- {group.config.name}: {group.config.description}")
        
        # 教室グループの詳細
        classroom_group = spot_manager.get_group("classrooms")
        if classroom_group:
            print(f"\n教室グループの詳細:")
            print(f"- スポット数: {len(classroom_group.get_all_spots())}")
            print(f"- スポット一覧: {[spot.spot_id for spot in classroom_group.get_all_spots()]}")
        
        # 出入り口機能のデモ
        print("\n=== 出入り口機能デモ ===")
        
        # 外部グループを作成（出入り口の検証用）
        outside_group_config = SpotGroupConfig(
            group_id="outside",
            name="外部",
            description="学校の外部",
            spot_ids=["outside"],
            tags=["external"]
        )
        spot_manager.create_group(outside_group_config)
        
        # 手動で出入り口を追加
        entrance_config = EntranceConfig(
            entrance_id="main_entrance",
            name="正門",
            description="学校の正門",
            from_group_id="school_grounds",
            to_group_id="outside",
            from_spot_id="school_gate",
            to_spot_id="outside",
            is_bidirectional=True
        )
        spot_manager.add_entrance(entrance_config)
        
        # 学校敷地の出入り口を取得
        school_entrances = spot_manager.get_entrances_for_group("school_grounds")
        print(f"学校敷地の出入り口: {len(school_entrances)}個")
        for entrance in school_entrances:
            status = "🔒" if spot_manager.is_entrance_locked(entrance.entrance_id) else "🔓"
            print(f"- {status} {entrance.name}: {entrance.description}")
        
        # マップの整合性チェック
        print("\n=== マップ整合性チェック ===")
        errors = spot_manager.validate_map()
        if errors:
            print("エラーが見つかりました:")
            for error in errors:
                print(f"- {error}")
        else:
            print("マップにエラーはありません")
        
        return spot_manager
        
    finally:
        # 一時ファイルを削除
        os.unlink(temp_file)


def demo_advanced_features():
    """高度な機能のデモ"""
    print("\n=== 高度な機能デモ ===")
    
    spot_manager = demo_config_file_construction()
    
    # スポットを含むグループの検索
    print("\n=== スポット検索機能 ===")
    classroom_1a_groups = spot_manager.get_groups_containing_spot("classroom_1a")
    print(f"classroom_1aを含むグループ: {len(classroom_1a_groups)}個")
    for group in classroom_1a_groups:
        print(f"- {group.config.name}: {group.config.description}")
    
    # 階層別グループの検索
    print("\n=== 階層別グループ検索 ===")
    first_floor_groups = spot_manager.get_groups_by_tag("first_floor")
    print(f"1階のグループ: {len(first_floor_groups)}個")
    for group in first_floor_groups:
        print(f"- {group.config.name}: {group.config.description}")
    
    # 出入り口のロック機能
    print("\n=== 出入り口ロック機能 ===")
    spot_manager.lock_entrance("main_entrance")
    print("正門をロックしました")
    
    if spot_manager.is_entrance_locked("main_entrance"):
        print("正門はロックされています")
    
    # ロックされた出入り口の一覧
    locked_entrances = spot_manager.entrance_manager.get_locked_entrances()
    print(f"ロックされた出入り口: {len(locked_entrances)}個")
    for entrance in locked_entrances:
        print(f"- {entrance.name}: {entrance.description}")
    
    # 出入り口のロック解除
    spot_manager.unlock_entrance("main_entrance")
    print("正門のロックを解除しました")
    
    if not spot_manager.is_entrance_locked("main_entrance"):
        print("正門はロックされていません")


def main():
    """メイン関数"""
    print("高度なマップ管理機能のデモ")
    print("=" * 50)
    
    # 手動構築デモ
    demo_manual_construction()
    
    # 設定ファイル構築デモ
    demo_config_file_construction()
    
    # 高度な機能デモ
    demo_advanced_features()
    
    print("\n=== デモ完了 ===")
    print("このデモでは以下の機能を実演しました:")
    print("- SpotGroup: 特定の役割を持つSpotの集合管理")
    print("- EntranceManager: 出入り口の管理とロック機能")
    print("- MapBuilder: 設定ファイルからのマップ構築")
    print("- SpotManager拡張: より豊富なマップ管理機能")


if __name__ == "__main__":
    main() 