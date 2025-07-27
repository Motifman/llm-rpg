#!/usr/bin/env python3
"""
ActionOrchestratorのSNS関連アクション統合テスト

このテストでは、ActionOrchestratorを使用してSNS関連のアクションの
行動候補の提示、選択、実行、結果取得をテストします。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from game.core.game_context import GameContext, GameContextBuilder
from game.player.player_manager import PlayerManager
from game.player.player import Player
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.sns.sns_manager import SnsManager
from game.action.action_orchestrator import ActionOrchestrator
from game.action.action_result import ActionResult
from game.enums import Role, PostVisibility


class TestActionOrchestratorSnsIntegration:
    """ActionOrchestratorのSNS関連アクション統合テストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        # プレイヤーマネージャーを初期化
        self.player_manager = PlayerManager()
        
        # テストプレイヤーを作成
        self.test_player = Player("test_player", "テストプレイヤー", Role.ADVENTURER)
        self.test_player.set_current_spot_id("test_spot")
        self.player_manager.add_player(self.test_player)
        
        # スポットマネージャーを初期化
        self.spot_manager = SpotManager()
        
        # テストスポットを作成
        self.test_spot = Spot("test_spot", "テストスポット", "テスト用のスポットです")
        self.spot_manager.add_spot(self.test_spot)
        
        # SNSマネージャーを初期化
        self.sns_manager = SnsManager()
        
        # テスト用SNSユーザーを作成
        self.sns_manager.create_user("test_player", "テストプレイヤー", "テスト用のユーザーです")
        self.sns_manager.create_user("alice", "アリス", "よろしくお願いします！")
        self.sns_manager.create_user("bob", "ボブ", "エンジニアです")
        
        # GameContextを作成
        self.game_context = GameContextBuilder()\
            .with_player_manager(self.player_manager)\
            .with_spot_manager(self.spot_manager)\
            .with_sns_manager(self.sns_manager)\
            .build()
        
        # ActionOrchestratorを初期化
        self.orchestrator = ActionOrchestrator(self.game_context)
    
    def test_get_sns_action_candidates(self):
        """SNS関連のアクション候補を取得するテスト"""
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        
        # SNS関連のアクションが含まれているかチェック
        sns_action_names = [
            "SNSユーザー情報取得",
            "SNSユーザー情報更新", 
            "SNS投稿",
            "SNSタイムライン取得",
            "SNS投稿にいいね",
            "SNS投稿のいいね解除",
            "SNS投稿に返信",
            "SNS通知取得",
            "SNS通知を既読にする"
        ]
        
        candidate_names = [candidate['action_name'] for candidate in candidates]
        
        for sns_action in sns_action_names:
            assert sns_action in candidate_names, f"SNSアクション '{sns_action}' が見つかりません"
        
        # 各SNSアクションの詳細をチェック
        for candidate in candidates:
            if candidate['action_name'] in sns_action_names:
                assert 'action_description' in candidate
                assert 'required_arguments' in candidate
                assert candidate['action_type'] == 'global'
    
    def test_sns_get_user_info_action(self):
        """SNSユーザー情報取得アクションのテスト"""
        # アクション候補を取得
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        
        # SNSユーザー情報取得アクションを見つける
        user_info_action = None
        for candidate in candidates:
            if candidate['action_name'] == "SNSユーザー情報取得":
                user_info_action = candidate
                break
        
        assert user_info_action is not None, "SNSユーザー情報取得アクションが見つかりません"
        
        # アクションを実行
        action_args = {"user_id": "alice"}
        result = self.orchestrator.execute_llm_action("test_player", "SNSユーザー情報取得", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert "アリス" in result.message or "alice" in result.message
    
    def test_sns_update_user_bio_action(self):
        """SNSユーザー情報更新アクションのテスト"""
        # アクションを実行
        action_args = {"bio": "新しい一言コメントに更新しました！"}
        result = self.orchestrator.execute_llm_action("test_player", "SNSユーザー情報更新", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        
        # 更新が反映されているかチェック
        updated_user = self.sns_manager.get_user("test_player")
        assert "新しい一言コメント" in updated_user.bio
    
    def test_sns_post_action(self):
        """SNS投稿アクションのテスト"""
        # アクションを実行
        action_args = {
            "content": "テスト投稿です！ #テスト",
            "hashtags": ["#テスト"],
            "visibility": "public",
            "allowed_users": []
        }
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert hasattr(result, 'post_id'), "投稿IDが返されていません"
        
        # 投稿が作成されているかチェック
        post = self.sns_manager.get_post(result.post_id)
        assert post is not None, "投稿が見つかりません"
        assert post.content == "テスト投稿です！ #テスト"
    
    def test_sns_get_timeline_action(self):
        """SNSタイムライン取得アクションのテスト"""
        # テスト用の投稿を作成
        self.sns_manager.create_post("alice", "アリスの投稿")
        self.sns_manager.create_post("bob", "ボブの投稿")
        
        # アクションを実行
        action_args = {
            "timeline_type": "global",
            "hashtag": ""
        }
        result = self.orchestrator.execute_llm_action("test_player", "SNSタイムライン取得", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert hasattr(result, 'posts'), "投稿リストが返されていません"
        assert len(result.posts) > 0, "投稿が取得されていません"
    
    def test_sns_like_action(self):
        """SNSいいねアクションのテスト"""
        # テスト用の投稿を作成
        post = self.sns_manager.create_post("alice", "いいねテスト投稿")
        
        # アクションを実行
        action_args = {"post_id": post.post_id}
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert hasattr(result, 'post_id'), "投稿IDが返されていません"
        
        # いいねが反映されているかチェック
        assert self.sns_manager.has_liked("test_player", post.post_id) is True
        assert self.sns_manager.get_post_likes_count(post.post_id) == 1
    
    def test_sns_unlike_action(self):
        """SNSいいね解除アクションのテスト"""
        # テスト用の投稿を作成していいね
        post = self.sns_manager.create_post("alice", "いいね解除テスト投稿")
        self.sns_manager.like_post("test_player", post.post_id)
        
        # アクションを実行
        action_args = {"post_id": post.post_id}
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿のいいね解除", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        
        # いいね解除が反映されているかチェック
        assert self.sns_manager.has_liked("test_player", post.post_id) is False
        assert self.sns_manager.get_post_likes_count(post.post_id) == 0
    
    def test_sns_reply_action(self):
        """SNS返信アクションのテスト"""
        # テスト用の投稿を作成
        post = self.sns_manager.create_post("alice", "返信テスト投稿")
        
        # アクションを実行
        action_args = {
            "post_id": post.post_id,
            "content": "テスト返信です"
        }
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿に返信", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert hasattr(result, 'post_id'), "投稿IDが返されていません"
        assert hasattr(result, 'reply_id'), "返信IDが返されていません"
        
        # 返信が作成されているかチェック
        replies = self.sns_manager.get_post_replies(post.post_id)
        assert len(replies) == 1, "返信が作成されていません"
        assert replies[0].content == "テスト返信です"
    
    def test_sns_get_notifications_action(self):
        """SNS通知取得アクションのテスト"""
        # 通知を生成するためのアクションを実行
        self.sns_manager.follow_user("alice", "test_player")
        post = self.sns_manager.create_post("alice", "通知テスト投稿")
        self.sns_manager.like_post("bob", post.post_id)
        
        # アクションを実行
        action_args = {"unread_only": "false"}
        result = self.orchestrator.execute_llm_action("test_player", "SNS通知取得", action_args)
        
        assert result.success is True, f"アクション実行に失敗: {result.message}"
        assert hasattr(result, 'notifications'), "通知リストが返されていません"
        assert len(result.notifications) > 0, "通知が取得されていません"
    
    def test_sns_mark_notification_read_action(self):
        """SNS通知既読アクションのテスト"""
        # 通知を生成
        self.sns_manager.follow_user("alice", "test_player")
        notifications = self.sns_manager.get_user_notifications("test_player")
        
        if notifications:
            notification_id = notifications[0].notification_id
            
            # アクションを実行
            action_args = {"notification_id": notification_id}
            result = self.orchestrator.execute_llm_action("test_player", "SNS通知を既読にする", action_args)
            
            assert result.success is True, f"アクション実行に失敗: {result.message}"
            assert hasattr(result, 'notification_id'), "通知IDが返されていません"
    
    def test_sns_action_error_handling(self):
        """SNSアクションのエラーハンドリングテスト"""
        # 存在しない投稿IDでいいねを試行
        action_args = {"post_id": "invalid_post_id"}
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", action_args)
        
        assert result.success is False, "エラーが発生すべきです"
        assert "見つかりません" in result.message or "失敗" in result.message
    
    def test_sns_action_argument_validation(self):
        """SNSアクションの引数バリデーションテスト"""
        # 空の返信内容で返信を試行
        post = self.sns_manager.create_post("alice", "バリデーションテスト投稿")
        action_args = {
            "post_id": post.post_id,
            "content": ""
        }
        result = self.orchestrator.execute_llm_action("test_player", "SNS投稿に返信", action_args)
        
        assert result.success is False, "空の内容での返信は失敗すべきです"
    
    def test_sns_action_help_info(self):
        """SNSアクションのヘルプ情報テスト"""
        help_info = self.orchestrator.get_action_help_for_llm("test_player")
        
        assert 'available_actions_count' in help_info
        assert 'action_types' in help_info
        assert 'usage_instructions' in help_info
        
        # SNSアクションが含まれているかチェック
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        sns_actions = [c for c in candidates if c['action_name'].startswith('SNS')]
        assert len(sns_actions) > 0, "SNSアクションが見つかりません"
    
    def test_sns_action_integration_flow(self):
        """SNSアクションの統合フローテスト"""
        # 1. 投稿を作成
        post_action_args = {
            "content": "統合テスト投稿です！ #テスト",
            "hashtags": ["#テスト"],
            "visibility": "public",
            "allowed_users": []
        }
        post_result = self.orchestrator.execute_llm_action("test_player", "SNS投稿", post_action_args)
        assert post_result.success is True
        
        # 2. タイムラインを取得
        timeline_action_args = {
            "timeline_type": "global",
            "hashtag": ""
        }
        timeline_result = self.orchestrator.execute_llm_action("test_player", "SNSタイムライン取得", timeline_action_args)
        assert timeline_result.success is True
        
        # 3. 投稿にいいね
        like_action_args = {"post_id": post_result.post_id}
        like_result = self.orchestrator.execute_llm_action("test_player", "SNS投稿にいいね", like_action_args)
        assert like_result.success is True
        
        # 4. 投稿に返信
        reply_action_args = {
            "post_id": post_result.post_id,
            "content": "統合テスト返信です"
        }
        reply_result = self.orchestrator.execute_llm_action("test_player", "SNS投稿に返信", reply_action_args)
        assert reply_result.success is True
        
        # 5. 通知を取得
        notification_action_args = {"unread_only": "false"}
        notification_result = self.orchestrator.execute_llm_action("test_player", "SNS通知取得", notification_action_args)
        assert notification_result.success is True
        
        # 結果の検証
        post = self.sns_manager.get_post(post_result.post_id)
        assert post is not None
        assert self.sns_manager.get_post_likes_count(post_result.post_id) == 1
        assert self.sns_manager.get_post_replies_count(post_result.post_id) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 