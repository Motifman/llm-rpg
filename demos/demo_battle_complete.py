#!/usr/bin/env python3
"""
戦闘終了まで攻撃実行と報酬取得のデモ
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.action.actions.battle_action import BattleActionCommand
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.battle.battle_manager import BattleManager
from game.monster.monster import Monster
from game.enums import TurnActionType, MonsterType, Race, Element, Role
from game.world.spot import Spot


def create_demo_monster(monster_id: str, name: str) -> Monster:
    """デモ用のモンスターを作成"""
    from game.item.item import Item
    from game.monster.monster import MonsterDropReward
    
    # 報酬アイテムを作成
    reward_item = Item(
        item_id="demo_item_1",
        name="ゴブリンの宝",
        description="ゴブリンが持っていた宝物"
    )
    
    # 報酬を設定
    drop_reward = MonsterDropReward(
        items=[reward_item],
        money=50,
        experience=100
    )
    
    monster = Monster(
        monster_id=monster_id,
        name=name,
        description=f"{name}の説明",
        monster_type=MonsterType.NORMAL,
        race=Race.MONSTER,
        element=Element.PHYSICAL,
        drop_reward=drop_reward
    )
    
    # ステータスを設定（弱めにして戦闘を早く終了させる）
    monster.set_hp(20)
    monster.set_max_hp(20)
    monster.set_attack(8)
    monster.set_defense(5)
    monster.set_speed(8)
    
    return monster


def create_demo_player(player_id: str, name: str) -> Player:
    """デモ用のプレイヤーを作成"""
    player = Player(player_id, name, Role.ADVENTURER)
    player.set_current_spot_id("demo_spot")
    
    # プレイヤーのステータスを設定
    player.status.set_hp(50)
    player.status.set_max_hp(50)
    player.status.set_attack(15)
    player.status.set_defense(10)
    player.status.set_speed(12)
    
    return player


def demo_battle_complete():
    """戦闘終了まで攻撃実行のデモ"""
    print("=== 戦闘終了まで攻撃実行デモ ===")
    
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
    
    # 戦闘開始
    print("戦闘を開始します...")
    battle_id = battle_manager.start_battle("demo_spot", [monster], player)
    print(f"戦闘ID: {battle_id}")
    
    # 戦闘状態を確認
    battle = battle_manager.get_battle_by_spot("demo_spot")
    if not battle:
        print("戦闘の開始に失敗しました")
        return
    
    print(f"初期状態:")
    print(f"  プレイヤーHP: {player.get_hp()}/{player.get_max_hp()}")
    print(f"  モンスターHP: {monster.get_hp()}/{monster.get_max_hp()}")
    print(f"  戦闘状態: {battle.state}")
    
    # 戦闘が終了するまで攻撃を実行
    turn_count = 0
    max_turns = 20  # 無限ループ防止
    
    while not battle.is_battle_finished() and turn_count < max_turns:
        turn_count += 1
        print(f"\n--- ターン {turn_count} ---")
        
        # プレイヤーの攻撃
        print("プレイヤーの攻撃を実行...")
        command = BattleActionCommand(TurnActionType.ATTACK, "demo_monster_1")
        result = command.execute(player, game_context)
        print(f"攻撃結果: {result.message}")
        
        # 現在の状態を表示
        print(f"  プレイヤーHP: {player.get_hp()}/{player.get_max_hp()}")
        print(f"  モンスターHP: {monster.get_hp()}/{monster.get_max_hp()}")
        
        # 戦闘終了チェック
        if battle.is_battle_finished():
            print("戦闘が終了しました！")
            break
    
    if turn_count >= max_turns:
        print(f"最大ターン数({max_turns})に達しました")
    
    # 戦闘結果を取得
    battle_result = battle.get_battle_result()
    print(f"\n=== 戦闘結果 ===")
    print(f"勝利: {battle_result.victory}")
    print(f"逃走: {battle_result.escaped}")
    print(f"参加者: {battle_result.participants}")
    print(f"倒されたモンスター数: {len(battle_result.defeated_monsters)}")
    
    if battle_result.total_rewards:
        print(f"報酬:")
        print(f"  経験値: {battle_result.total_rewards.experience}")
        print(f"  ゴールド: {battle_result.total_rewards.money}")
        print(f"  アイテム数: {len(battle_result.total_rewards.items)}")
    else:
        print("報酬なし")
    
    # 報酬分配を実行
    print(f"\n=== 報酬分配 ===")
    battle_manager.cleanup_finished_battles()
    
    # プレイヤーの状態を確認
    print(f"\n=== プレイヤー最終状態 ===")
    print(f"HP: {player.get_hp()}/{player.get_max_hp()}")
    print(f"経験値: {player.get_experience_points()}")
    print(f"ゴールド: {player.get_gold()}")
    print(f"インベントリアイテム数: {len(player.get_inventory_items())}")
    
    # 戦闘ログを出力
    print(f"\n=== 戦闘ログ ===")
    events = battle.event_log.get_all_events()
    for i, event in enumerate(events, 1):
        print(f"{i:2d}. [{event.timestamp.strftime('%H:%M:%S')}] {event.message}")
        if event.structured_data:
            print(f"    データ: {event.structured_data}")
    
    # 構造化された戦闘ログも出力
    print(f"\n=== 構造化戦闘ログ ===")
    structured_log = battle.get_structured_context_for_player("demo_player")
    for key, value in structured_log.items():
        if key != "events":  # イベントは既に出力済み
            print(f"{key}: {value}")
    
    # イベントの詳細情報
    print(f"\n=== イベント詳細 ===")
    for i, event in enumerate(events[-10:], 1):  # 最後の10個のイベント
        print(f"{i}. イベントID: {event.event_id}")
        print(f"   タイプ: {event.event_type}")
        print(f"   アクター: {event.actor_id}")
        if event.target_id:
            print(f"   ターゲット: {event.target_id}")
        if event.action_type:
            print(f"   行動: {event.action_type}")
        if event.damage > 0:
            print(f"   ダメージ: {event.damage}")
        if event.critical:
            print(f"   クリティカル: はい")
        if event.evaded:
            print(f"   回避: はい")
        print(f"   メッセージ: {event.message}")
        print()


def main():
    """メイン関数"""
    print("戦闘終了まで攻撃実行デモを開始します")
    
    try:
        demo_battle_complete()
        
        print("\n=== デモ完了 ===")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 