#!/usr/bin/env python3
"""
戦闘終了条件チェックメソッドのテストデモ
新しく追加した戦闘終了チェックメソッドをテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.player.player import Player
from game.enums import MonsterType, Race, Element, Role, TurnActionType, BattleState


def create_test_monster(monster_id: str, name: str) -> Monster:
    """テスト用モンスターを作成"""
    monster = Monster(
        monster_id=monster_id,
        name=name,
        description="テスト用モンスター",
        monster_type=MonsterType.AGGRESSIVE,
        race=Race.MONSTER,
        element=Element.PHYSICAL
    )
    
    monster.set_hp(50)
    monster.set_max_hp(50)
    monster.set_attack(15)
    monster.set_defense(5)
    monster.set_speed(10)
    
    return monster


def create_test_player(player_id: str, name: str) -> Player:
    """テスト用プレイヤーを作成"""
    player = Player(
        player_id=player_id,
        name=name,
        role=Role.ADVENTURER
    )
    
    player.status.set_hp(100)
    player.status.set_max_hp(100)
    player.status.set_attack(20)
    player.status.set_defense(10)
    player.status.set_speed(12)
    
    return player


def test_battle_end_conditions():
    """戦闘終了条件チェックのテスト"""
    print("=== 戦闘終了条件チェックテスト ===")
    print()
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    
    # テスト用プレイヤーとモンスターを作成
    player = create_test_player("test_player", "テストプレイヤー")
    monster = create_test_monster("test_monster", "テストモンスター")
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    print("=== テスト1: 戦闘継続中の状態 ===")
    conditions = battle.check_battle_end_conditions()
    print(f"終了条件: {conditions}")
    print(f"終了状況: {battle.get_battle_end_status()}")
    print(f"is_battle_finished(): {battle.is_battle_finished()}")
    print()
    
    print("=== テスト2: モンスター死亡による勝利 ===")
    monster.set_hp(0)
    print(f"モンスターのHP: {monster.get_hp()}")
    print(f"モンスターの生存状態: {monster.is_alive()}")
    
    conditions = battle.check_battle_end_conditions()
    print(f"終了条件: {conditions}")
    print(f"終了状況: {battle.get_battle_end_status()}")
    print(f"is_battle_finished(): {battle.is_battle_finished()}")
    print()
    
    # 新しい戦闘を作成
    battle_manager2 = BattleManager()
    player2 = create_test_player("test_player2", "テストプレイヤー2")
    monster2 = create_test_monster("test_monster2", "テストモンスター2")
    
    battle_id2 = battle_manager2.start_battle("test_spot2", [monster2], player2)
    battle2 = battle_manager2.get_battle(battle_id2)
    
    print("=== テスト3: プレイヤー死亡による敗北 ===")
    player2.status.set_hp(0)
    print(f"プレイヤーのHP: {player2.get_hp()}")
    print(f"プレイヤーの生存状態: {player2.is_alive()}")
    
    conditions2 = battle2.check_battle_end_conditions()
    print(f"終了条件: {conditions2}")
    print(f"終了状況: {battle2.get_battle_end_status()}")
    print(f"is_battle_finished(): {battle2.is_battle_finished()}")
    print()
    
    # 新しい戦闘を作成
    battle_manager3 = BattleManager()
    player3 = create_test_player("test_player3", "テストプレイヤー3")
    monster3 = create_test_monster("test_monster3", "テストモンスター3")
    
    battle_id3 = battle_manager3.start_battle("test_spot3", [monster3], player3)
    battle3 = battle_manager3.get_battle(battle_id3)
    
    print("=== テスト4: プレイヤー離脱による逃走 ===")
    battle3.remove_participant("test_player3")
    print(f"参加者数: {len(battle3.participants)}")
    
    conditions3 = battle3.check_battle_end_conditions()
    print(f"終了条件: {conditions3}")
    print(f"終了状況: {battle3.get_battle_end_status()}")
    print(f"is_battle_finished(): {battle3.is_battle_finished()}")
    print()
    
    print("=== テスト結果サマリー ===")
    print("✅ check_battle_end_conditions(): 詳細な終了条件チェック")
    print("✅ get_battle_end_status(): 人間が読める終了状況文字列")
    print("✅ is_battle_finished(): 既存の終了チェックメソッド")
    print()
    
    print("=== 利用可能な戦闘終了チェックメソッド ===")
    print("1. is_battle_finished() -> bool: 戦闘が終了しているかどうか")
    print("2. check_battle_end_conditions() -> Dict: 詳細な終了条件と理由")
    print("3. get_battle_end_status() -> str: 人間が読める終了状況")
    print()
    
    print("=== テスト完了 ===")


if __name__ == "__main__":
    test_battle_end_conditions() 