#!/usr/bin/env python3
"""
ターン調査メソッドのテストデモ
現在のターンを調べるメソッドの一覧を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.player.player import Player
from game.enums import MonsterType, Race, Element, Role, TurnActionType


def test_turn_inspection_methods():
    """ターン調査メソッドのテスト"""
    print("=== ターン調査メソッドテスト ===")
    print()
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    
    # テスト用プレイヤーとモンスターを作成
    player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
    player.status.set_hp(100)
    player.status.set_max_hp(100)
    player.status.set_speed(12)
    
    monster = Monster("test_monster", "テストモンスター", "テスト用", MonsterType.AGGRESSIVE)
    monster.set_hp(50)
    monster.set_max_hp(50)
    monster.set_speed(10)
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    print("=== 利用可能なターン調査メソッド ===")
    print()
    
    # 1. get_current_actor()
    current_actor = battle.get_current_actor()
    print(f"1. get_current_actor(): {current_actor}")
    
    # 2. is_player_turn()
    is_player_turn = battle.is_player_turn()
    print(f"2. is_player_turn(): {is_player_turn}")
    
    # 3. is_monster_turn()
    is_monster_turn = battle.is_monster_turn()
    print(f"3. is_monster_turn(): {is_monster_turn}")
    
    # 4. get_current_monster()
    current_monster = battle.get_current_monster()
    print(f"4. get_current_monster(): {current_monster.get_name() if current_monster else None}")
    
    # 5. ターン順序の確認
    print(f"5. turn_order: {battle.turn_order}")
    
    # 6. 現在のターン番号
    print(f"6. current_turn: {battle.current_turn}")
    
    # 7. 現在のインデックス
    print(f"7. current_turn_index: {battle.current_turn_index}")
    
    print()
    
    # ターンを進めてモンスターのターンに
    print("=== ターン進行後の確認 ===")
    battle.advance_turn()
    
    current_actor2 = battle.get_current_actor()
    print(f"1. get_current_actor(): {current_actor2}")
    
    is_player_turn2 = battle.is_player_turn()
    print(f"2. is_player_turn(): {is_player_turn2}")
    
    is_monster_turn2 = battle.is_monster_turn()
    print(f"3. is_monster_turn(): {is_monster_turn2}")
    
    current_monster2 = battle.get_current_monster()
    print(f"4. get_current_monster(): {current_monster2.get_name() if current_monster2 else None}")
    
    print(f"5. turn_order: {battle.turn_order}")
    print(f"6. current_turn: {battle.current_turn}")
    print(f"7. current_turn_index: {battle.current_turn_index}")
    
    print()
    
    print("=== メソッドの用途 ===")
    print("✅ get_current_actor(): 現在のターンのアクターIDを取得")
    print("✅ is_player_turn(): 現在がプレイヤーのターンかどうか判定")
    print("✅ is_monster_turn(): 現在がモンスターのターンかどうか判定")
    print("✅ get_current_monster(): 現在のターンのモンスターオブジェクトを取得")
    print("✅ turn_order: ターン順序のリストを確認")
    print("✅ current_turn: 現在のターン番号を確認")
    print("✅ current_turn_index: 現在のターンインデックスを確認")
    print()
    
    print("=== テスト完了 ===")


if __name__ == "__main__":
    test_turn_inspection_methods() 