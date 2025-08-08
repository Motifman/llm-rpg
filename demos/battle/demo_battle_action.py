#!/usr/bin/env python3
"""
戦闘関連の行動デモ
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.action.actions.battle_action import (
    BattleStartStrategy, BattleJoinStrategy, BattleActionStrategy,
    BattleStartCommand, BattleJoinCommand, BattleActionCommand
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.enums import TurnActionType, BattleState, MonsterType, Race, Element, Role
from game.world.spot import Spot


def create_demo_monster(monster_id: str, name: str) -> Monster:
    """デモ用のモンスターを作成"""
    monster = Monster(
        monster_id=monster_id,
        name=name,
        description=f"{name}の説明",
        monster_type=MonsterType.NORMAL,
        race=Race.MONSTER,
        element=Element.PHYSICAL
    )
    
    # ステータスを設定
    monster.set_hp(50)
    monster.set_max_hp(50)
    monster.set_attack(15)
    monster.set_defense(8)
    monster.set_speed(10)
    
    return monster


def create_demo_player(player_id: str, name: str) -> Player:
    """デモ用のプレイヤーを作成"""
    player = Player(player_id, name, Role.ADVENTURER)
    player.set_current_spot_id("demo_spot")
    return player


def demo_battle_start():
    """戦闘開始のデモ"""
    print("=== 戦闘開始デモ ===")
    
    # ゲームコンテキストの設定
    spot_manager = SpotManager()
    battle_manager = BattleManager()
    
    # デモスポットを作成
    demo_spot = Spot("demo_spot", "デモエリア", "戦闘デモ用のエリア")
    spot_manager.add_spot(demo_spot)
    
    # モンスターを追加
    monster = create_demo_monster("demo_monster_1", "ゴブリン")
    demo_spot.add_monster(monster)
    
    game_context = GameContext(
        player_manager=None,
        spot_manager=spot_manager,
        battle_manager=battle_manager
    )
    
    # プレイヤーを作成
    player = create_demo_player("demo_player", "デモプレイヤー")
    
    # 戦闘開始戦略をテスト
    strategy = BattleStartStrategy()
    
    print(f"プレイヤー位置: {player.get_current_spot_id()}")
    print(f"スポットのモンスター数: {len(demo_spot.get_visible_monsters())}")
    print(f"戦闘開始可能: {strategy.can_execute(player, game_context)}")
    
    if strategy.can_execute(player, game_context):
        command = strategy.build_action_command(player, game_context)
        result = command.execute(player, game_context)
        print(f"戦闘開始結果: {result.to_feedback_message(player.name)}")
        
        # 戦闘状態を確認
        battle = battle_manager.get_battle_by_spot("demo_spot")
        if battle:
            print(f"戦闘ID: {battle.battle_id}")
            print(f"戦闘状態: {battle.state}")
            print(f"参加者数: {len(battle.participants)}")
            print(f"モンスター数: {len(battle.monsters)}")


def demo_battle_join():
    """戦闘参加のデモ"""
    print("\n=== 戦闘参加デモ ===")
    
    # ゲームコンテキストの設定
    spot_manager = SpotManager()
    battle_manager = BattleManager()
    
    # デモスポットを作成
    demo_spot = Spot("demo_spot", "デモエリア", "戦闘デモ用のエリア")
    spot_manager.add_spot(demo_spot)
    
    # モンスターを追加
    monster = create_demo_monster("demo_monster_1", "ゴブリン")
    demo_spot.add_monster(monster)
    
    game_context = GameContext(
        player_manager=None,
        spot_manager=spot_manager,
        battle_manager=battle_manager
    )
    
    # 最初のプレイヤーで戦闘開始
    player1 = create_demo_player("demo_player_1", "デモプレイヤー1")
    battle_id = battle_manager.start_battle("demo_spot", [monster], player1)
    print(f"戦闘開始: {battle_id}")
    
    # 2番目のプレイヤーで戦闘参加
    player2 = create_demo_player("demo_player_2", "デモプレイヤー2")
    
    strategy = BattleJoinStrategy()
    
    print(f"プレイヤー2位置: {player2.get_current_spot_id()}")
    print(f"戦闘参加可能: {strategy.can_execute(player2, game_context)}")
    
    if strategy.can_execute(player2, game_context):
        command = strategy.build_action_command(player2, game_context)
        result = command.execute(player2, game_context)
        print(f"戦闘参加結果: {result.to_feedback_message(player2.name)}")
        
        # 戦闘状態を確認
        battle = battle_manager.get_battle_by_spot("demo_spot")
        if battle:
            print(f"参加者数: {len(battle.participants)}")
            for player_id, player in battle.participants.items():
                print(f"  - {player.name} (ID: {player_id})")


def demo_battle_action():
    """戦闘時の行動デモ"""
    print("\n=== 戦闘時の行動デモ ===")
    
    # ゲームコンテキストの設定
    spot_manager = SpotManager()
    battle_manager = BattleManager()
    
    # デモスポットを作成
    demo_spot = Spot("demo_spot", "デモエリア", "戦闘デモ用のエリア")
    spot_manager.add_spot(demo_spot)
    
    # モンスターを追加
    monster = create_demo_monster("demo_monster_1", "ゴブリン")
    demo_spot.add_monster(monster)
    
    game_context = GameContext(
        player_manager=None,
        spot_manager=spot_manager,
        battle_manager=battle_manager
    )
    
    # プレイヤーで戦闘開始
    player = create_demo_player("demo_player", "デモプレイヤー")
    battle_id = battle_manager.start_battle("demo_spot", [monster], player)
    print(f"戦闘開始: {battle_id}")
    
    # 戦闘時の行動戦略をテスト
    strategy = BattleActionStrategy()
    
    print(f"プレイヤー位置: {player.get_current_spot_id()}")
    print(f"戦闘行動可能: {strategy.can_execute(player, game_context)}")
    
    if strategy.can_execute(player, game_context):
        # 必要な引数を取得
        args = strategy.get_required_arguments(player, game_context)
        print("必要な引数:")
        for arg in args:
            print(f"  - {arg.name}: {arg.description}")
            if arg.candidates:
                print(f"    候補: {arg.candidates}")
        
        # 攻撃行動を実行
        command = strategy.build_action_command(player, game_context, "attack", "demo_monster_1")
        result = command.execute(player, game_context)
        print(f"攻撃行動結果: {result.to_feedback_message(player.name)}")
        
        # 防御行動を実行
        command = strategy.build_action_command(player, game_context, "defend", "")
        result = command.execute(player, game_context)
        print(f"防御行動結果: {result.to_feedback_message(player.name)}")


def main():
    """メイン関数"""
    print("戦闘関連の行動デモを開始します")
    
    try:
        demo_battle_start()
        demo_battle_join()
        demo_battle_action()
        
        print("\n=== デモ完了 ===")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 