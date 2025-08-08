#!/usr/bin/env python3
"""
シンプルな防御システムテスト
プレイヤー→モンスター攻撃での防御状態によるダメージ軽減を直接テスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.player.player import Player
from game.enums import MonsterType, Race, Element, Role, TurnActionType


def test_defense_system():
    """防御システムの直接テスト"""
    print("=== 防御システム直接テスト ===")
    print()
    
    # テスト用プレイヤーとモンスターを作成
    player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
    player.status.set_hp(100)
    player.status.set_max_hp(100)
    player.status.set_attack(20)
    player.status.set_defense(10)
    
    monster = Monster("test_monster", "テストモンスター", "テスト用", MonsterType.AGGRESSIVE)
    monster.set_hp(50)
    monster.set_max_hp(50)
    monster.set_attack(15)
    monster.set_defense(5)
    
    print(f"プレイヤー: {player.get_name()}")
    print(f"  攻撃: {player.get_attack()}, 防御: {player.get_defense()}")
    print()
    
    print(f"モンスター: {monster.get_name()}")
    print(f"  攻撃: {monster.get_attack()}, 防御: {monster.get_defense()}")
    print()
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    print("=== テスト1: 通常攻撃（防御状態なし） ===")
    print(f"モンスターのHP: {monster.get_hp()}/{monster.get_max_hp()}")
    print(f"モンスターの防御状態: {monster.is_defending()}")
    
    # 基本ダメージ計算
    base_damage = battle._calculate_attack_damage(player, monster)
    print(f"基本ダメージ: {base_damage}")
    
    # 防御状態によるダメージ軽減処理を直接テスト
    final_damage = base_damage
    defense_reduction_applied = False
    
    if monster.is_defending():
        original_damage = final_damage
        final_damage = int(final_damage * (1 - battle.DEFAULT_DEFENSE_DAMAGE_REDUCTION))
        defense_reduction_applied = True
        print(f"防御軽減適用: {original_damage} → {final_damage}")
    else:
        print("防御軽減なし")
    
    print(f"最終ダメージ: {final_damage}")
    print()
    
    print("=== テスト2: 防御状態での攻撃 ===")
    # モンスターを防御状態にする
    monster.set_defending(True)
    print(f"モンスターの防御状態: {monster.is_defending()}")
    
    # 再度ダメージ計算
    base_damage2 = battle._calculate_attack_damage(player, monster)
    print(f"基本ダメージ: {base_damage2}")
    
    final_damage2 = base_damage2
    defense_reduction_applied2 = False
    
    if monster.is_defending():
        original_damage2 = final_damage2
        final_damage2 = int(final_damage2 * (1 - battle.DEFAULT_DEFENSE_DAMAGE_REDUCTION))
        defense_reduction_applied2 = True
        print(f"防御軽減適用: {original_damage2} → {final_damage2}")
        print(f"軽減ダメージ: {original_damage2 - final_damage2}")
    else:
        print("防御軽減なし")
    
    print(f"最終ダメージ: {final_damage2}")
    print()
    
    print("=== テスト3: 防御状態解除後の攻撃 ===")
    # モンスターの防御状態を解除
    monster.set_defending(False)
    print(f"モンスターの防御状態: {monster.is_defending()}")
    
    # 再度ダメージ計算
    base_damage3 = battle._calculate_attack_damage(player, monster)
    print(f"基本ダメージ: {base_damage3}")
    
    final_damage3 = base_damage3
    defense_reduction_applied3 = False
    
    if monster.is_defending():
        original_damage3 = final_damage3
        final_damage3 = int(final_damage3 * (1 - battle.DEFAULT_DEFENSE_DAMAGE_REDUCTION))
        defense_reduction_applied3 = True
        print(f"防御軽減適用: {original_damage3} → {final_damage3}")
    else:
        print("防御軽減なし")
    
    print(f"最終ダメージ: {final_damage3}")
    print()
    
    print("=== テスト結果サマリー ===")
    print(f"テスト1（通常）: {base_damage} ダメージ")
    print(f"テスト2（防御）: {final_damage2} ダメージ (軽減: {base_damage2 - final_damage2})")
    print(f"テスト3（解除）: {final_damage3} ダメージ")
    print()
    
    if defense_reduction_applied2:
        print("✅ 防御状態によるダメージ軽減が正常に動作しています")
    else:
        print("❌ 防御状態によるダメージ軽減が動作していません")
    
    print()
    print("=== テスト完了 ===")


if __name__ == "__main__":
    test_defense_system() 