"""
戦闘イベントシステムのデモ

- 新しいBattleEventとBattleEventLogの動作確認
- LLM統合を見据えたイベント管理システムのテスト
- プレイヤーの未読イベント取得機能の確認
"""

from game.battle.battle_manager import BattleManager
from game.player.player import Player
from game.monster.monster import Monster, MonsterDropReward
from game.enums import Role, TurnActionType, MonsterType
from game.item.item import Item


def create_test_monster():
    """テスト用モンスターを作成"""
    reward = MonsterDropReward(
        items=[Item("monster_claw", "モンスターの爪", "モンスターから得られる爪")],
        money=50,
        experience=30,
        information=["このモンスターは攻撃的な性質を持つ"]
    )
    
    monster = Monster(
        monster_id="test_goblin",
        name="テストゴブリン",
        description="テスト用のゴブリン",
        monster_type=MonsterType.NORMAL,
        drop_reward=reward
    )
    
    # ステータスを設定
    monster.status.set_hp(40)
    monster.status.set_max_hp(40)
    monster.status.set_attack(12)
    monster.status.set_defense(4)
    monster.status.set_speed(6)
    
    return monster


def demo_basic_event_system():
    """基本的なイベントシステムのデモ"""
    print("=== 戦闘イベントシステム 基本デモ ===")
    
    # 戦闘管理システムを作成
    battle_manager = BattleManager()
    
    # プレイヤーとモンスターを作成
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = create_test_monster()
    
    # 戦闘を開始
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    print(f"戦闘開始: {battle_id}")
    print(f"初期イベント数: {len(battle.event_log.get_all_events())}")
    
    # プレイヤーの未読イベントを確認
    unread_events = battle.get_unread_events_for_player("player1")
    print(f"プレイヤーの未読イベント数: {len(unread_events)}")
    
    for event in unread_events:
        print(f"  - [{event.timestamp.strftime('%H:%M:%S')}] {event.message}")
    
    # 既読マーク
    battle.mark_events_as_read_for_player("player1")
    print("既読マーク完了")
    
    # 攻撃行動を実行
    print("\n--- 攻撃行動実行 ---")
    turn_action = battle.execute_player_action("player1", "test_goblin", TurnActionType.ATTACK)
    print(f"攻撃結果: {turn_action.message}")
    
    # 新しい未読イベントを確認
    new_unread_events = battle.get_unread_events_for_player("player1")
    print(f"新しい未読イベント数: {len(new_unread_events)}")
    
    for event in new_unread_events:
        print(f"  - [{event.timestamp.strftime('%H:%M:%S')}] {event.message}")
        print(f"    イベントタイプ: {event.event_type}")
        print(f"    ダメージ: {event.damage}")
        print(f"    成功: {event.success}")
        if event.structured_data:
            print(f"    構造化データ: {event.structured_data}")


def demo_llm_integration():
    """LLM統合用の機能デモ"""
    print("\n=== LLM統合デモ ===")
    
    battle_manager = BattleManager()
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = create_test_monster()
    
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    # いくつかの行動を実行
    battle.execute_player_action("player1", "test_goblin", TurnActionType.ATTACK)
    battle.advance_turn()
    
    # モンスターのターン
    if battle.is_monster_turn():
        battle.execute_monster_turn()
        battle.advance_turn()
    
    # LLM用のコンテキストを取得
    print("--- LLM用コンテキスト文字列 ---")
    llm_context = battle.get_llm_context_for_player("player1")
    print(llm_context)
    
    print("\n--- LLM用構造化コンテキスト ---")
    structured_context = battle.get_structured_context_for_player("player1")
    print(f"未読イベント数: {structured_context['unread_events_count']}")
    for event_data in structured_context['events']:
        print(f"  - {event_data['event_type']}: {event_data['message']}")
        print(f"    ダメージ: {event_data['damage']}, 成功: {event_data['success']}")
    
    print("\n--- LLM用戦闘状況 ---")
    battle_status = battle.get_battle_status_for_llm("player1")
    print(f"現在のターン: {battle_status['current_turn']}")
    print(f"現在のアクター: {battle_status['current_actor']}")
    print(f"プレイヤーのターン: {battle_status['is_player_turn']}")
    print(f"モンスターのターン: {battle_status['is_monster_turn']}")
    print(f"未読イベント数: {battle_status['unread_events_count']}")
    
    print("\n--- プレイヤー情報 ---")
    for player_info in battle_status['players']:
        print(f"  {player_info['name']}: HP {player_info['current_hp']}/{player_info['max_hp']}")
    
    print("\n--- モンスター情報 ---")
    for monster_info in battle_status['monsters']:
        print(f"  {monster_info['name']}: HP {monster_info['current_hp']}/{monster_info['max_hp']}")


def demo_multi_player_events():
    """複数プレイヤーでのイベント管理デモ"""
    print("\n=== 複数プレイヤーイベント管理デモ ===")
    
    battle_manager = BattleManager()
    player1 = Player("player1", "勇者", Role.ADVENTURER)
    player2 = Player("player2", "魔法使い", Role.ADVENTURER)
    monster = create_test_monster()
    
    battle_id = battle_manager.start_battle("test_spot", [monster], player1)
    battle = battle_manager.get_battle(battle_id)
    
    # 2番目のプレイヤーが参加
    battle_manager.join_battle(battle_id, player2)
    
    # プレイヤー1の行動
    battle.execute_player_action("player1", "test_goblin", TurnActionType.ATTACK)
    battle.advance_turn()
    
    # プレイヤー2の未読イベントを確認
    print("プレイヤー2の未読イベント:")
    unread_events_p2 = battle.get_unread_events_for_player("player2")
    for event in unread_events_p2:
        print(f"  - {event.message}")
    
    # プレイヤー2の既読マーク
    battle.mark_events_as_read_for_player("player2")
    
    # プレイヤー2の行動
    battle.execute_player_action("player2", "test_goblin", TurnActionType.DEFEND)
    battle.advance_turn()
    
    # 両プレイヤーの未読イベントを確認
    print("\nプレイヤー1の未読イベント:")
    unread_events_p1 = battle.get_unread_events_for_player("player1")
    for event in unread_events_p1:
        print(f"  - {event.message}")
    
    print("\nプレイヤー2の未読イベント:")
    unread_events_p2 = battle.get_unread_events_for_player("player2")
    for event in unread_events_p2:
        print(f"  - {event.message}")


def demo_event_types():
    """様々なイベントタイプのデモ"""
    print("\n=== イベントタイプデモ ===")
    
    battle_manager = BattleManager()
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = create_test_monster()
    
    battle_id = battle_manager.start_battle("test_spot", [monster], player)
    battle = battle_manager.get_battle(battle_id)
    
    # 様々な行動を実行してイベントタイプを確認
    actions = [
        (TurnActionType.ATTACK, "攻撃"),
        (TurnActionType.DEFEND, "防御"),
        (TurnActionType.ESCAPE, "逃走")
    ]
    
    for action_type, action_name in actions:
        print(f"\n--- {action_name}行動 ---")
        turn_action = battle.execute_player_action("player1", "test_goblin", action_type)
        print(f"結果: {turn_action.message}")
        
        # 最新のイベントを確認
        all_events = battle.event_log.get_all_events()
        if all_events:
            latest_event = all_events[-1]
            print(f"イベントタイプ: {latest_event.event_type}")
            print(f"アクター: {latest_event.actor_id}")
            print(f"成功: {latest_event.success}")
            if latest_event.structured_data:
                print(f"構造化データ: {latest_event.structured_data}")


if __name__ == "__main__":
    demo_basic_event_system()
    demo_llm_integration()
    demo_multi_player_events()
    demo_event_types()
    
    print("\n=== デモ完了 ===")
    print("新しい戦闘イベントシステムが正常に動作しています。")
    print("LLM統合の準備が整いました。") 