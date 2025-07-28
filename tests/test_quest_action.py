import unittest
from unittest.mock import Mock, patch
from game.action.actions.quest_action import (
    QuestGetGuildListStrategy, QuestCreateMonsterHuntStrategy, QuestCreateItemCollectionStrategy,
    QuestCreateExplorationStrategy, QuestGetAvailableQuestsStrategy, QuestAcceptQuestStrategy,
    QuestGetActiveQuestStrategy,
    QuestGetGuildListCommand, QuestCreateMonsterHuntCommand, QuestCreateItemCollectionCommand,
    QuestCreateExplorationCommand, QuestGetAvailableQuestsCommand, QuestAcceptQuestCommand,
    QuestGetActiveQuestCommand
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.quest.quest_manager import QuestSystem
from game.quest.guild import AdventurerGuild
from game.quest.quest_data import Quest
from game.enums import QuestDifficulty, QuestType, Role


class TestQuestAction(unittest.TestCase):
    def setUp(self):
        self.player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
        self.player.add_money(1000)  # テスト用に資金を追加
        
        # Mock managers
        self.player_manager = Mock()
        self.player_manager.get_player.return_value = self.player
        
        self.spot_manager = Mock()
        self.quest_system = QuestSystem()
        
        # GameContext作成
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=self.spot_manager,
            quest_system=self.quest_system
        )
        
        # テスト用ギルドを作成
        self.guild = self.quest_system.create_guild("test_guild", "テストギルド", "guild_hall")
        self.quest_system.register_player_to_guild(self.player, "test_guild")

    def test_quest_get_guild_list_strategy(self):
        """ギルド一覧確認ストラテジーのテスト"""
        strategy = QuestGetGuildListStrategy()
        
        # 引数が不要であることを確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 0)
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(self.player, self.game_context)
        self.assertIsInstance(command, QuestGetGuildListCommand)

    def test_quest_get_guild_list_command(self):
        """ギルド一覧確認コマンドのテスト"""
        command = QuestGetGuildListCommand()
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsInstance(result.guilds, list)
        self.assertEqual(len(result.guilds), 1)
        self.assertEqual(result.guilds[0]['guild_id'], "test_guild")

    def test_quest_create_monster_hunt_strategy(self):
        """モンスタークエスト依頼ストラテジーのテスト"""
        strategy = QuestCreateMonsterHuntStrategy()
        
        # 必要な引数を確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 8)  # guild_id, name, description, monster_id, monster_count, difficulty, reward_money, deadline_hours
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(
            self.player, self.game_context,
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", "3", "E", "100", "72"
        )
        self.assertIsInstance(command, QuestCreateMonsterHuntCommand)

    def test_quest_create_monster_hunt_command(self):
        """モンスタークエスト依頼コマンドのテスト"""
        command = QuestCreateMonsterHuntCommand(
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", 3, QuestDifficulty.E, 100, 72
        )
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.quest_id)

    def test_quest_create_item_collection_strategy(self):
        """アイテムクエスト依頼ストラテジーのテスト"""
        strategy = QuestCreateItemCollectionStrategy()
        
        # 必要な引数を確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 8)
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(
            self.player, self.game_context,
            "test_guild", "テストクエスト", "テスト説明",
            "herb", "5", "E", "100", "48"
        )
        self.assertIsInstance(command, QuestCreateItemCollectionCommand)

    def test_quest_create_item_collection_command(self):
        """アイテムクエスト依頼コマンドのテスト"""
        command = QuestCreateItemCollectionCommand(
            "test_guild", "テストクエスト", "テスト説明",
            "herb", 5, QuestDifficulty.E, 100, 48
        )
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.quest_id)

    def test_quest_create_exploration_strategy(self):
        """探索クエスト依頼ストラテジーのテスト"""
        strategy = QuestCreateExplorationStrategy()
        
        # 必要な引数を確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 7)  # deadline_hoursがデフォルト値
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(
            self.player, self.game_context,
            "test_guild", "テストクエスト", "テスト説明",
            "ancient_ruins", "E", "100", "24"
        )
        self.assertIsInstance(command, QuestCreateExplorationCommand)

    def test_quest_create_exploration_command(self):
        """探索クエスト依頼コマンドのテスト"""
        command = QuestCreateExplorationCommand(
            "test_guild", "テストクエスト", "テスト説明",
            "ancient_ruins", QuestDifficulty.E, 100, 24
        )
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.quest_id)

    def test_quest_get_available_quests_strategy(self):
        """利用可能クエスト取得ストラテジーのテスト"""
        strategy = QuestGetAvailableQuestsStrategy()
        
        # 引数が不要であることを確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 0)
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(self.player, self.game_context)
        self.assertIsInstance(command, QuestGetAvailableQuestsCommand)

    def test_quest_get_available_quests_command(self):
        """利用可能クエスト取得コマンドのテスト"""
        # まずクエストを作成
        quest = self.quest_system.create_monster_hunt_quest_for_guild(
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", 3, QuestDifficulty.E, "client_001", 100, 72
        )
        self.quest_system.post_quest_to_guild("test_guild", quest, self.player)
        
        command = QuestGetAvailableQuestsCommand()
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsInstance(result.quests, list)
        self.assertEqual(len(result.quests), 1)

    def test_quest_accept_quest_strategy(self):
        """クエスト受注ストラテジーのテスト"""
        strategy = QuestAcceptQuestStrategy()
        
        # 必要な引数を確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0].name, "quest_id")
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(self.player, self.game_context, "quest_001")
        self.assertIsInstance(command, QuestAcceptQuestCommand)

    def test_quest_accept_quest_command(self):
        """クエスト受注コマンドのテスト"""
        # まずクエストを作成
        quest = self.quest_system.create_monster_hunt_quest_for_guild(
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", 3, QuestDifficulty.E, "client_001", 100, 72
        )
        self.quest_system.post_quest_to_guild("test_guild", quest, self.player)
        
        command = QuestAcceptQuestCommand(quest.quest_id)
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertEqual(result.quest_id, quest.quest_id)

    def test_quest_get_active_quest_strategy(self):
        """アクティブクエスト取得ストラテジーのテスト"""
        strategy = QuestGetActiveQuestStrategy()
        
        # 引数が不要であることを確認
        args = strategy.get_required_arguments(self.player, self.game_context)
        self.assertEqual(len(args), 0)
        
        # 実行可能であることを確認
        self.assertTrue(strategy.can_execute(self.player, self.game_context))
        
        # コマンドが正しく作成されることを確認
        command = strategy.build_action_command(self.player, self.game_context)
        self.assertIsInstance(command, QuestGetActiveQuestCommand)

    def test_quest_get_active_quest_command(self):
        """アクティブクエスト取得コマンドのテスト"""
        command = QuestGetActiveQuestCommand()
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        # 初期状態ではアクティブクエストがない
        self.assertIsNone(result.active_quest)

    def test_quest_get_active_quest_command_with_active_quest(self):
        """アクティブクエストがある場合のテスト"""
        # クエストを作成して受注
        quest = self.quest_system.create_monster_hunt_quest_for_guild(
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", 3, QuestDifficulty.E, "client_001", 100, 72
        )
        self.quest_system.post_quest_to_guild("test_guild", quest, self.player)
        self.quest_system.accept_quest(self.player.get_player_id(), quest.quest_id)
        
        command = QuestGetActiveQuestCommand()
        result = command.execute(self.player, self.game_context)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.active_quest)
        self.assertEqual(result.active_quest['quest_id'], quest.quest_id)

    def test_quest_action_without_quest_system(self):
        """QuestSystemがない場合のテスト"""
        # QuestSystemなしでGameContextを作成
        game_context_without_quest = GameContext(
            player_manager=self.player_manager,
            spot_manager=self.spot_manager
        )
        
        command = QuestGetGuildListCommand()
        result = command.execute(self.player, game_context_without_quest)
        
        self.assertFalse(result.success)
        self.assertIn("QuestSystemが利用できません", result.message)

    def test_quest_create_with_invalid_guild(self):
        """存在しないギルドでのクエスト作成テスト"""
        command = QuestCreateMonsterHuntCommand(
            "invalid_guild", "テストクエスト", "テスト説明",
            "goblin", 3, QuestDifficulty.E, 100, 72
        )
        result = command.execute(self.player, self.game_context)
        
        self.assertFalse(result.success)
        self.assertIn("ギルド invalid_guild が存在しません", result.message)

    def test_quest_accept_nonexistent_quest(self):
        """存在しないクエストの受注テスト"""
        command = QuestAcceptQuestCommand("nonexistent_quest")
        result = command.execute(self.player, self.game_context)
        
        self.assertFalse(result.success)

    def test_quest_action_error_handling(self):
        """エラーハンドリングのテスト"""
        # 無効な引数でストラテジーをテスト
        strategy = QuestCreateMonsterHuntStrategy()
        
        # 無効な数値を渡す
        command = strategy.build_action_command(
            self.player, self.game_context,
            "test_guild", "テストクエスト", "テスト説明",
            "goblin", "invalid", "E", "invalid", "72"
        )
        
        # デフォルト値が使用されることを確認
        self.assertIsInstance(command, QuestCreateMonsterHuntCommand)


if __name__ == '__main__':
    unittest.main() 