#!/usr/bin/env python3
"""
Questアクションシステムのデモ
QuestシステムのActionStrategy、ActionCommand、ActionResultの動作を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.player.player_manager import PlayerManager
from game.player.player import Player
from game.world.spot_manager import SpotManager
from game.quest.quest_manager import QuestSystem
from game.core.game_context import GameContext
from game.action.action_orchestrator import ActionOrchestrator
from game.action.actions.quest_action import (
    QuestGetGuildListStrategy, QuestCreateMonsterHuntStrategy, QuestCreateItemCollectionStrategy,
    QuestCreateExplorationStrategy, QuestGetAvailableQuestsStrategy, QuestAcceptQuestStrategy,
    QuestGetActiveQuestStrategy
)
from game.enums import Role


def demo_quest_action_system():
    """Questアクションシステムのデモ"""
    print("=== Questアクションシステムデモ ===")
    
    # システム初期化
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    quest_system = QuestSystem()
    
    # GameContext作成
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        quest_system=quest_system
    )
    
    # ActionOrchestrator作成
    orchestrator = ActionOrchestrator(game_context)
    
    # プレイヤー作成
    player = Player("demo_player", "デモプレイヤー", Role.ADVENTURER)
    player.add_money(1000)  # テスト用に資金を追加
    player.set_current_spot_id("guild_hall")  # 現在地を設定
    player_manager.add_player(player)
    
    # ギルド作成
    guild = quest_system.create_guild("demo_guild", "デモギルド", "guild_hall")
    quest_system.register_player_to_guild(player, "demo_guild")
    
    print(f"プレイヤー: {player.name} (ID: {player.get_player_id()})")
    print(f"所持金: {player.get_money()}G")
    print(f"ギルド: {guild.name} (ID: {guild.guild_id})")
    print()
    
    # 1. ギルド一覧確認
    print("--- 1. ギルド一覧確認 ---")
    strategy = QuestGetGuildListStrategy()
    command = strategy.build_action_command(player, game_context)
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 2. モンスタークエスト依頼
    print("--- 2. モンスタークエスト依頼 ---")
    strategy = QuestCreateMonsterHuntStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "demo_guild", "ゴブリン討伐", "ゴブリンを3体討伐してください",
        "goblin", "3", "E", "150", "72"
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print(f"残り所持金: {player.get_money()}G")
    print()
    
    # 3. アイテムクエスト依頼
    print("--- 3. アイテムクエスト依頼 ---")
    strategy = QuestCreateItemCollectionStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "demo_guild", "薬草収集", "薬草を5個収集してください",
        "herb", "5", "D", "200", "48"
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print(f"残り所持金: {player.get_money()}G")
    print()
    
    # 4. 探索クエスト依頼
    print("--- 4. 探索クエスト依頼 ---")
    strategy = QuestCreateExplorationStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "demo_guild", "古代遺跡探索", "古代遺跡を探索してください",
        "ancient_ruins", "C", "300", "24"
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print(f"残り所持金: {player.get_money()}G")
    print()
    
    # 5. 利用可能クエスト取得
    print("--- 5. 利用可能クエスト取得 ---")
    strategy = QuestGetAvailableQuestsStrategy()
    command = strategy.build_action_command(player, game_context)
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 6. クエスト受注（最初のクエストを受注）
    print("--- 6. クエスト受注 ---")
    available_quests = quest_system.get_available_quests(player.get_player_id())
    if available_quests:
        quest_to_accept = available_quests[0]
        strategy = QuestAcceptQuestStrategy()
        command = strategy.build_action_command(player, game_context, quest_to_accept.quest_id)
        result = command.execute(player, game_context)
        print(result.to_feedback_message(player.name))
        print()
        
        # 7. アクティブクエスト取得
        print("--- 7. アクティブクエスト取得 ---")
        strategy = QuestGetActiveQuestStrategy()
        command = strategy.build_action_command(player, game_context)
        result = command.execute(player, game_context)
        print(result.to_feedback_message(player.name))
        print()
        
        # 8. クエスト進捗更新（モンスター討伐）
        print("--- 8. クエスト進捗更新（モンスター討伐） ---")
        updated_quest = quest_system.handle_monster_kill(player.get_player_id(), "goblin", 2)
        if updated_quest:
            print(f"クエスト進捗が更新されました: {updated_quest.name}")
            print("進捗状況:")
            for condition in updated_quest.conditions:
                print(f"  {condition.description}: {condition.current_count}/{condition.required_count}")
        print()
        
        # 9. クエスト完了チェック
        print("--- 9. クエスト完了チェック ---")
        completion_result = quest_system.check_quest_completion(player.get_player_id())
        if completion_result:
            print(f"クエスト完了: {completion_result['quest_name']}")
            print(f"報酬: {completion_result['reward_money']}G")
            print(f"評判獲得: {completion_result['reputation_gained']}ポイント")
        else:
            print("クエストはまだ完了していません")
        print()
        
        # 10. 最終的なアクティブクエスト確認
        print("--- 10. 最終的なアクティブクエスト確認 ---")
        strategy = QuestGetActiveQuestStrategy()
        command = strategy.build_action_command(player, game_context)
        result = command.execute(player, game_context)
        print(result.to_feedback_message(player.name))
        print()
    else:
        print("利用可能なクエストがありません")
        print()
    
    # 11. プレイヤー情報確認
    print("--- 11. プレイヤー情報確認 ---")
    print(f"最終所持金: {player.get_money()}G")
    player_guild = quest_system.get_player_guild(player.get_player_id())
    if player_guild:
        member = player_guild.get_member(player.get_player_id())
        if member:
            print(f"ギルドランク: {member.rank}")
            print(f"評判: {member.reputation}")
            print(f"完了クエスト数: {member.quests_completed}")
            print(f"総収入: {member.total_earnings}G")
    print()
    
    # 12. ギルド統計確認
    print("--- 12. ギルド統計確認 ---")
    stats = quest_system.get_guild_statistics()
    print(f"総ギルド数: {stats['total_guilds']}")
    print(f"総メンバー数: {stats['total_members']}")
    print(f"総利用可能クエスト数: {stats['total_available_quests']}")
    print(f"総進行中クエスト数: {stats['total_active_quests']}")
    print(f"総完了クエスト数: {stats['total_completed_quests']}")
    print()


def demo_quest_action_error_handling():
    """Questアクションのエラーハンドリングデモ"""
    print("=== Questアクションエラーハンドリングデモ ===")
    
    # システム初期化
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    quest_system = QuestSystem()
    
    # GameContext作成
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        quest_system=quest_system
    )
    
    # プレイヤー作成
    player = Player("error_player", "エラーテストプレイヤー", Role.ADVENTURER)
    player.add_money(100)  # 少額でテスト
    player.set_current_spot_id("guild_hall")  # 現在地を設定
    player_manager.add_player(player)
    
    print(f"プレイヤー: {player.name} (ID: {player.get_player_id()})")
    print(f"所持金: {player.get_money()}G")
    print()
    
    # 1. 存在しないギルドでのクエスト作成
    print("--- 1. 存在しないギルドでのクエスト作成 ---")
    strategy = QuestCreateMonsterHuntStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "nonexistent_guild", "テストクエスト", "テスト説明",
        "goblin", "3", "E", "100", "72"
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 2. 資金不足でのクエスト作成
    print("--- 2. 資金不足でのクエスト作成 ---")
    # まずギルドを作成
    guild = quest_system.create_guild("test_guild", "テストギルド", "guild_hall")
    
    strategy = QuestCreateMonsterHuntStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "test_guild", "高額クエスト", "高額なクエスト",
        "dragon", "1", "S", "1000", "72"  # 所持金を超える報酬
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print(f"残り所持金: {player.get_money()}G")
    print()
    
    # 3. 存在しないクエストの受注
    print("--- 3. 存在しないクエストの受注 ---")
    strategy = QuestAcceptQuestStrategy()
    command = strategy.build_action_command(player, game_context, "nonexistent_quest")
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 4. 無効な引数でのクエスト作成
    print("--- 4. 無効な引数でのクエスト作成 ---")
    strategy = QuestCreateMonsterHuntStrategy()
    command = strategy.build_action_command(
        player, game_context,
        "test_guild", "テストクエスト", "テスト説明",
        "goblin", "invalid", "E", "invalid", "72"  # 無効な数値
    )
    result = command.execute(player, game_context)
    print(result.to_feedback_message(player.name))
    print()
    
    # 5. QuestSystemなしでのアクション実行
    print("--- 5. QuestSystemなしでのアクション実行 ---")
    game_context_without_quest = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager
    )
    
    strategy = QuestGetGuildListStrategy()
    command = strategy.build_action_command(player, game_context_without_quest)
    result = command.execute(player, game_context_without_quest)
    print(result.to_feedback_message(player.name))
    print()


def demo_quest_action_integration():
    """Questアクションの統合デモ"""
    print("=== Questアクション統合デモ ===")
    
    # システム初期化
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    
    # テスト用スポットを作成
    from game.world.spot import Spot
    guild_spot = Spot("guild_hall", "ギルドホール", "冒険者ギルドの本部")
    spot_manager.add_spot(guild_spot)
    
    quest_system = QuestSystem()
    
    # GameContext作成
    game_context = GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        quest_system=quest_system
    )
    
    # ActionOrchestrator作成
    orchestrator = ActionOrchestrator(game_context)
    
    # プレイヤー作成
    player = Player("integration_player", "統合テストプレイヤー", Role.ADVENTURER)
    player.add_money(2000)
    player.set_current_spot_id("guild_hall")  # 現在地を設定
    player_manager.add_player(player)
    
    # ギルド作成
    guild = quest_system.create_guild("integration_guild", "統合テストギルド", "guild_hall")
    quest_system.register_player_to_guild(player, "integration_guild")
    
    print(f"プレイヤー: {player.name} (ID: {player.get_player_id()})")
    print(f"所持金: {player.get_money()}G")
    print()
    
    # ActionOrchestratorを使用したアクション実行
    print("--- ActionOrchestratorを使用したアクション実行 ---")
    
    # 利用可能なアクションを取得
    available_actions = orchestrator.get_action_candidates_for_llm(player.get_player_id())
    quest_actions = [action for action in available_actions if 'quest' in action['action_name'].lower() or 'ギルド' in action['action_name']]
    
    print(f"利用可能なQuest関連アクション数: {len(quest_actions)}")
    for action in quest_actions:
        print(f"  - {action['action_name']}: {action['action_description']}")
    print()
    
    # ギルド一覧確認を実行
    print("--- ギルド一覧確認実行 ---")
    result = orchestrator.execute_llm_action(
        player.get_player_id(),
        "ギルド一覧確認",
        {}
    )
    print(result.to_feedback_message(player.name))
    print()
    
    # モンスタークエスト依頼を実行
    print("--- モンスタークエスト依頼実行 ---")
    result = orchestrator.execute_llm_action(
        player.get_player_id(),
        "モンスタークエスト依頼",
        {
            "guild_id": "integration_guild",
            "name": "統合テストクエスト",
            "description": "統合テスト用のクエスト",
            "monster_id": "goblin",
            "monster_count": "2",
            "difficulty": "E",
            "reward_money": "100",
            "deadline_hours": "72"
        }
    )
    print(result.to_feedback_message(player.name))
    print(f"残り所持金: {player.get_money()}G")
    print()
    
    # 利用可能クエスト取得を実行
    print("--- 利用可能クエスト取得実行 ---")
    result = orchestrator.execute_llm_action(
        player.get_player_id(),
        "利用可能クエスト取得",
        {}
    )
    print(result.to_feedback_message(player.name))
    print()
    
    # クエスト受注を実行（利用可能なクエストがある場合）
    available_quests = quest_system.get_available_quests(player.get_player_id())
    if available_quests:
        quest_to_accept = available_quests[0]
        print("--- クエスト受注実行 ---")
        result = orchestrator.execute_llm_action(
            player.get_player_id(),
            "クエスト受注",
            {"quest_id": quest_to_accept.quest_id}
        )
        print(result.to_feedback_message(player.name))
        print()
        
        # アクティブクエスト取得を実行
        print("--- アクティブクエスト取得実行 ---")
        result = orchestrator.execute_llm_action(
            player.get_player_id(),
            "アクティブクエスト取得",
            {}
        )
        print(result.to_feedback_message(player.name))
        print()
    
    print("=== 統合デモ完了 ===")
    print()


if __name__ == "__main__":
    print("Questアクションシステムデモを開始します...")
    print()
    
    # 基本デモ
    demo_quest_action_system()
    
    # エラーハンドリングデモ
    demo_quest_action_error_handling()
    
    # 統合デモ
    demo_quest_action_integration()
    
    print("Questアクションシステムデモが完了しました。") 