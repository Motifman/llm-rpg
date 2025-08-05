#!/usr/bin/env python3
"""
貢献度に基づく報酬分配機能のデモ

このデモでは、戦闘の貢献度に応じた報酬分配機能をテストします。
攻撃ダメージ、クリティカルヒット、反撃、参加期間などを考慮して
各プレイヤーの貢献度を計算し、それに基づいて報酬を分配します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.battle.battle_manager import BattleManager, Battle
from game.monster.monster import Monster, MonsterDropReward
from game.player.player import Player
from game.item.item import Item
from game.enums import BattleState, TurnActionType, MonsterType, Race, Element


def create_test_monster(monster_id: str, name: str, money: int, exp: int, items: list = None) -> Monster:
    """テスト用モンスターを作成"""
    if items is None:
        items = [Item(f"item_{monster_id}", f"{name}のアイテム", f"{name}から入手できるアイテム")]
    
    return Monster(
        monster_id=monster_id,
        name=name,
        description=f"テスト用の{name}",
        monster_type=MonsterType.NORMAL,
        race=Race.MONSTER,
        element=Element.PHYSICAL,
        drop_reward=MonsterDropReward(
            items=items,
            money=money,
            experience=exp,
            information=[f"{name}に関する情報"]
        )
    )


def create_test_player(player_id: str, name: str, attack: int = 20, defense: int = 10, speed: int = 15) -> Player:
    """テスト用プレイヤーを作成"""
    from game.enums import Role
    player = Player(player_id, name, Role.ADVENTURER)
    player.status.set_attack(attack)
    player.status.set_defense(defense)
    player.status.set_speed(speed)
    player.status.set_hp(100)
    player.status.set_max_hp(100)
    return player


def simulate_battle_actions(battle: Battle, player_id: str, actions: list):
    """戦闘アクションをシミュレート"""
    for action in actions:
        # 現在のターンのプレイヤーが行動するまで待つ
        while battle.get_current_actor() != player_id and battle.state == BattleState.ACTIVE:
            battle.advance_turn()
        
        if battle.state != BattleState.ACTIVE:
            break
            
        if action["type"] == "attack":
            # 攻撃アクション
            target_monster_id = action.get("target")
            if target_monster_id:
                battle.execute_player_action(player_id, target_monster_id, TurnActionType.ATTACK)
        elif action["type"] == "defend":
            # 防御アクション
            battle.execute_player_action(player_id, None, TurnActionType.DEFEND)
        elif action["type"] == "escape":
            # 逃走アクション
            battle.execute_player_action(player_id, None, TurnActionType.ESCAPE)
        
        # ターンを進める
        battle.advance_turn()


def print_contribution_info(battle: Battle):
    """貢献度情報を表示"""
    print("\n=== 貢献度情報 ===")
    for player_id, contribution in battle.player_contributions.items():
        score = contribution.calculate_contribution_score()
        print(f"プレイヤー {player_id}:")
        print(f"  与えたダメージ: {contribution.total_damage_dealt}")
        print(f"  受けたダメージ: {contribution.total_damage_taken}")
        print(f"  参加ターン数: {contribution.turns_participated}")
        print(f"  クリティカルヒット: {contribution.critical_hits}")
        print(f"  成功した攻撃: {contribution.successful_attacks}")
        print(f"  成功した防御: {contribution.successful_defenses}")
        print(f"  反撃回数: {contribution.counter_attacks}")
        print(f"  状態異常適用: {contribution.status_effects_applied}")
        print(f"  貢献度スコア: {score:.2f}")


def print_reward_distribution(result):
    """報酬分配結果を表示"""
    print("\n=== 報酬分配結果 ===")
    print(f"戦闘結果: {'勝利' if result.victory else '敗北'}")
    print(f"倒されたモンスター数: {len(result.defeated_monsters)}")
    
    if result.total_rewards:
        print(f"\n合計報酬:")
        print(f"  お金: {result.total_rewards.money}")
        print(f"  経験値: {result.total_rewards.experience}")
        print(f"  アイテム数: {len(result.total_rewards.items)}")
        print(f"  情報数: {len(result.total_rewards.information)}")
    
    if result.distributed_rewards:
        print(f"\n分配された報酬:")
        for player_id, reward in result.distributed_rewards.items():
            print(f"\nプレイヤー {player_id}:")
            print(f"  貢献度: {reward.contribution_percentage:.1f}%")
            print(f"  貢献度スコア: {reward.contribution_score:.2f}")
            print(f"  お金: {reward.money}")
            print(f"  経験値: {reward.experience}")
            print(f"  アイテム数: {len(reward.items)}")
            print(f"  情報数: {len(reward.information)}")
            
            if reward.items:
                print(f"  アイテム:")
                for item in reward.items:
                    print(f"    - {item.name}")


def demo_basic_contribution_rewards():
    """基本的な貢献度報酬分配のデモ"""
    print("=== 基本的な貢献度報酬分配デモ ===")
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    
    # モンスターを作成
    monster1 = create_test_monster("monster1", "ゴブリン", 100, 50)
    monster2 = create_test_monster("monster2", "オーク", 150, 75)
    
    # プレイヤーを作成
    player1 = create_test_player("player1", "戦士", attack=25, defense=15)
    player2 = create_test_player("player2", "魔法使い", attack=20, defense=10)
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("test_spot", [monster1, monster2], player1)
    battle_manager.join_battle(battle_id, player2)
    
    battle = battle_manager.get_battle(battle_id)
    
    print("戦闘開始！")
    print(f"参加者: {[p.name for p in battle.get_participants()]}")
    print(f"モンスター: {[m.name for m in battle.monsters.values()]}")
    
    # 戦闘アクションをシミュレート
    print("\n=== 戦闘シミュレーション ===")
    
    # プレイヤー1のアクション（積極的に攻撃）
    simulate_battle_actions(battle, "player1", [
        {"type": "attack", "target": "monster1"},
        {"type": "attack", "target": "monster2"},
        {"type": "attack", "target": "monster1"},
        {"type": "defend"},
        {"type": "attack", "target": "monster2"}
    ])
    
    # プレイヤー2のアクション（控えめに攻撃）
    simulate_battle_actions(battle, "player2", [
        {"type": "defend"},
        {"type": "attack", "target": "monster1"},
        {"type": "defend"},
        {"type": "attack", "target": "monster2"}
    ])
    
    # モンスターを倒して戦闘を終了
    monster1.take_damage(1000)
    monster2.take_damage(1000)
    battle.state = BattleState.FINISHED
    
    # 貢献度情報を表示
    print_contribution_info(battle)
    
    # 戦闘結果を取得
    result = battle_manager.finish_battle(battle_id)
    
    # 報酬分配結果を表示
    print_reward_distribution(result)


def demo_unequal_contribution():
    """不平等な貢献度のデモ"""
    print("\n=== 不平等な貢献度デモ ===")
    
    battle_manager = BattleManager()
    
    # モンスターを作成
    monster = create_test_monster("boss", "ボスモンスター", 500, 200, [
        Item("rare_sword", "レアソード", "強力な剣"),
        Item("magic_ring", "魔法の指輪", "魔法効果のある指輪"),
        Item("healing_potion", "回復ポーション", "HPを回復する薬")
    ])
    
    # プレイヤーを作成（能力差あり）
    player1 = create_test_player("player1", "戦士", attack=30, defense=20)
    player2 = create_test_player("player2", "初心者", attack=10, defense=5)
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("boss_spot", [monster], player1)
    battle_manager.join_battle(battle_id, player2)
    
    battle = battle_manager.get_battle(battle_id)
    
    print("ボス戦闘開始！")
    
    # 戦闘アクションをシミュレート（能力差を反映）
    print("\n=== 戦闘シミュレーション ===")
    
    # プレイヤー1（積極的に攻撃）
    simulate_battle_actions(battle, "player1", [
        {"type": "attack", "target": "boss"},
        {"type": "attack", "target": "boss"},
        {"type": "attack", "target": "boss"},
        {"type": "attack", "target": "boss"},
        {"type": "attack", "target": "boss"}
    ])
    
    # プレイヤー2（控えめに攻撃）
    simulate_battle_actions(battle, "player2", [
        {"type": "defend"},
        {"type": "attack", "target": "boss"},
        {"type": "defend"},
        {"type": "attack", "target": "boss"},
        {"type": "defend"}
    ])
    
    # モンスターを倒して戦闘を終了
    monster.take_damage(1000)
    battle.state = BattleState.FINISHED
    
    # 貢献度情報を表示
    print_contribution_info(battle)
    
    # 戦闘結果を取得
    result = battle_manager.finish_battle(battle_id)
    
    # 報酬分配結果を表示
    print_reward_distribution(result)


def demo_equal_contribution():
    """平等な貢献度のデモ"""
    print("\n=== 平等な貢献度デモ ===")
    
    battle_manager = BattleManager()
    
    # モンスターを作成
    monster = create_test_monster("equal_monster", "平等モンスター", 200, 100)
    
    # 同じ能力のプレイヤーを作成
    player1 = create_test_player("player1", "プレイヤー1", attack=20, defense=10)
    player2 = create_test_player("player2", "プレイヤー2", attack=20, defense=10)
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("equal_spot", [monster], player1)
    battle_manager.join_battle(battle_id, player2)
    
    battle = battle_manager.get_battle(battle_id)
    
    print("平等な戦闘開始！")
    
    # 同じアクションを実行
    simulate_battle_actions(battle, "player1", [
        {"type": "attack", "target": "equal_monster"},
        {"type": "defend"},
        {"type": "attack", "target": "equal_monster"}
    ])
    
    simulate_battle_actions(battle, "player2", [
        {"type": "attack", "target": "equal_monster"},
        {"type": "defend"},
        {"type": "attack", "target": "equal_monster"}
    ])
    
    # モンスターを倒して戦闘を終了
    monster.take_damage(1000)
    battle.state = BattleState.FINISHED
    
    # 貢献度情報を表示
    print_contribution_info(battle)
    
    # 戦闘結果を取得
    result = battle_manager.finish_battle(battle_id)
    
    # 報酬分配結果を表示
    print_reward_distribution(result)


def main():
    """メイン関数"""
    print("貢献度に基づく報酬分配機能デモ")
    print("=" * 50)
    
    try:
        # 基本的なデモ
        demo_basic_contribution_rewards()
        
        # 不平等な貢献度デモ
        demo_unequal_contribution()
        
        # 平等な貢献度デモ
        demo_equal_contribution()
        
        print("\n=== デモ完了 ===")
        print("貢献度に基づく報酬分配機能が正常に動作しています。")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 