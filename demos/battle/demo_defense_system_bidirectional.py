#!/usr/bin/env python3
"""
双方向防御システムのデモ
プレイヤー→モンスター攻撃でも防御状態によるダメージ軽減をテスト
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


def demo_bidirectional_defense_system():
    """双方向防御システムのデモ"""
    print("=== 双方向防御システムデモ ===")
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
    
    # ターン1: プレイヤーが攻撃（通常攻撃）
    print("--- ターン1: プレイヤーが攻撃（通常攻撃） ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print(f"モンスターの防御状態: {monster.is_defending()}")
    print()
    
    # プレイヤーの攻撃
    attack_action1 = battle.execute_player_action(
        player.get_player_id(), 
        monster.get_monster_id(), 
        TurnActionType.ATTACK
    )
    print(f"プレイヤー行動: {attack_action1.message}")
    print()
    
    print(f"モンスターのHP: {monster.get_hp()}/{monster.get_max_hp()}")
    print()
    
    # ターンを進める
    battle.advance_turn()
    
    # ターン2: モンスターが防御
    print("--- ターン2: モンスターが防御 ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print()
    
    # モンスターの防御行動
    monster.set_defending(True)
    defend_event = battle._create_battle_event(
        event_type="monster_action",
        actor_id=monster.get_monster_id(),
        action_type=TurnActionType.MONSTER_ACTION,
        message=f"{monster.get_name()} は防御の構えを取った",
        structured_data={
            "monster_name": monster.get_name(),
            "is_defending": True
        }
    )
    print(f"モンスター行動: {defend_event.message}")
    print()
    
    # ターン3: プレイヤーが攻撃（防御状態のモンスター）
    print("--- ターン3: プレイヤーが攻撃（防御状態のモンスター） ---")
    print(f"現在のターン: {battle.current_turn}")
    print(f"現在のアクター: {battle.get_current_actor()}")
    print(f"モンスターの防御状態: {monster.is_defending()}")
    print()
    
    # プレイヤーの攻撃（防御状態のモンスターに対して）
    attack_action2 = battle.execute_player_action(
        player.get_player_id(), 
        monster.get_monster_id(), 
        TurnActionType.ATTACK
    )
    print(f"プレイヤー行動: {attack_action2.message}")
    print()
    
    print(f"モンスターのHP: {monster.get_hp()}/{monster.get_max_hp()}")
    print()
    
    # 防御状態の解除を確認
    print("--- 防御状態の解除確認 ---")
    print(f"攻撃後のモンスターの防御状態: {monster.is_defending()}")
    print()
    
    # ターンを進める
    battle.advance_turn()
    
    print("--- ターン進行後の防御状態確認 ---")
    print(f"ターン進行後のモンスターの防御状態: {monster.is_defending()}")
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
    demo_bidirectional_defense_system() 