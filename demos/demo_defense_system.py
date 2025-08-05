#!/usr/bin/env python3
"""
防御システムのデモ
防御状態によるダメージ軽減とログ機能をテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster, MonsterDropReward
from game.player.player import Player
from game.enums import MonsterType, Race, Element, Role, TurnActionType
from game.item.item import Item


def create_test_monster() -> Monster:
    """テスト用モンスターを作成"""
    monster = Monster(
        monster_id="test_goblin",
        name="テストゴブリン",
        description="防御システムのテスト用モンスター",
        monster_type=MonsterType.AGGRESSIVE,
        race=Race.MONSTER,
        element=Element.PHYSICAL
    )
    
    # ステータス設定
    monster.set_hp(50)
    monster.set_max_hp(50)
    monster.set_attack(15)
    monster.set_defense(5)
    monster.set_speed(8)
    
    return monster


def create_test_player() -> Player:
    """テスト用プレイヤーを作成"""
    player = Player(
        player_id="test_player",
        name="テストプレイヤー",
        role=Role.ADVENTURER
    )
    
    # ステータス設定
    player.status.set_hp(100)
    player.status.set_max_hp(100)
    player.status.set_attack(20)
    player.status.set_defense(10)
    player.status.set_speed(12)
    
    return player


def demo_defense_system():
    """防御システムのデモ"""
    print("=== 防御システムデモ ===")
    print()
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    
    # テスト用プレイヤーとモンスターを作成
    player = create_test_player()
    monster = create_test_monster()
    
    print(f"プレイヤー: {player.get_name()}")
    print(f"  HP: {player.get_hp()}/{player.get_max_hp()}")
    print(f"  攻撃: {player.get_attack()}, 防御: {player.get_defense()}")
    print()
    
    print(f"モンスター: {monster.get_name()}")
    print(f"  HP: {monster.get_hp()}/{monster.get_max_hp()}")
    print(f"  攻撃: {monster.get_attack()}, 防御: {monster.get_defense()}")
    print()
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    print("戦闘開始！")
    print()
    
    # ターン1: プレイヤーが防御
    print("--- ターン1: プレイヤーが防御 ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print()
    
    # プレイヤーの防御行動
    defend_action = battle.execute_player_action(
        player.get_player_id(), 
        None, 
        TurnActionType.DEFEND
    )
    print(f"プレイヤー行動: {defend_action.message}")
    print()
    
    # ターンを進める
    battle.advance_turn()
    
    # ターン2: モンスターが攻撃
    print("--- ターン2: モンスターが攻撃（防御状態のプレイヤー） ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print(f"プレイヤーの防御状態: {player.is_defending()}")
    print()
    
    # モンスターの攻撃
    attack_action = battle.execute_monster_turn()
    print(f"モンスター行動: {attack_action.message}")
    print()
    
    print(f"プレイヤーのHP: {player.get_hp()}/{player.get_max_hp()}")
    print()
    
    # ターンを進める
    battle.advance_turn()
    
    # ターン3: モンスターが攻撃（防御状態解除後）
    print("--- ターン3: モンスターが攻撃（防御状態解除後） ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print(f"プレイヤーの防御状態: {player.is_defending()}")
    print()
    
    # モンスターの攻撃
    attack_action2 = battle.execute_monster_turn()
    print(f"モンスター行動: {attack_action2.message}")
    print()
    
    print(f"プレイヤーのHP: {player.get_hp()}/{player.get_max_hp()}")
    print()
    
    # イベントログを表示
    print("=== 戦闘イベントログ ===")
    events = battle.event_log.get_all_events()
    for i, event in enumerate(events, 1):
        print(f"{i}. [{event.event_type}] {event.message}")
        if event.structured_data:
            print(f"   データ: {event.structured_data}")
    print()
    
    # 防御軽減イベントを特別に表示
    print("=== 防御軽減イベント ===")
    defense_events = [e for e in events if e.event_type == "defense_reduction"]
    for event in defense_events:
        print(f"防御軽減: {event.message}")
        print(f"  元のダメージ: {event.structured_data.get('original_damage')}")
        print(f"  軽減ダメージ: {event.structured_data.get('reduced_damage')}")
        print(f"  最終ダメージ: {event.structured_data.get('final_damage')}")
        print(f"  軽減率: {event.structured_data.get('defense_reduction_rate')}")
    print()
    
    print("=== デモ完了 ===")


if __name__ == "__main__":
    demo_defense_system() 