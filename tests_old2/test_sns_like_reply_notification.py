#!/usr/bin/env python3
"""
SNSいいね・返信・通知機能のテスト

このテストでは、新しく実装されたSNSのいいね・返信・通知機能をテストします。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from game.sns.sns_manager import SnsManager
from game.sns.sns_data import Post, Reply, Notification
from game.enums import PostVisibility, NotificationType


class TestSnsLikeReplyNotification:
    """SNSいいね・返信・通知機能のテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.sns = SnsManager()
        
        # テストユーザーを作成
        self.sns.create_user("alice", "アリス", "よろしくお願いします！")
        self.sns.create_user("bob", "ボブ", "エンジニアです")
        self.sns.create_user("charlie", "チャーリー", "デザイナーです")
        
        # テスト投稿を作成
        self.post = self.sns.create_post("alice", "テスト投稿です！ #テスト")
    
    def test_post_id_display(self):
        """投稿ID表示機能のテスト"""
        # タイムライン表示で投稿IDが含まれているかチェック
        timeline = self.sns.get_global_timeline()
        assert len(timeline) > 0
        
        formatted_post = timeline[0].format_for_timeline()
        assert "ID:" in formatted_post
        assert self.post.post_id in formatted_post
    
    def test_like_functionality(self):
        """いいね機能のテスト"""
        # いいねの実行
        success = self.sns.like_post("bob", self.post.post_id)
        assert success is True
        
        # いいね状況の確認
        assert self.sns.has_liked("bob", self.post.post_id) is True
        assert self.sns.get_post_likes_count(self.post.post_id) == 1
        
        # 重複いいねの防止
        success2 = self.sns.like_post("bob", self.post.post_id)
        assert success2 is False
        
        # 別ユーザーのいいね
        success3 = self.sns.like_post("charlie", self.post.post_id)
        assert success3 is True
        assert self.sns.get_post_likes_count(self.post.post_id) == 2
    
    def test_unlike_functionality(self):
        """いいね解除機能のテスト"""
        # まずいいねを実行
        self.sns.like_post("bob", self.post.post_id)
        assert self.sns.has_liked("bob", self.post.post_id) is True
        
        # いいね解除
        success = self.sns.unlike_post("bob", self.post.post_id)
        assert success is True
        assert self.sns.has_liked("bob", self.post.post_id) is False
        assert self.sns.get_post_likes_count(self.post.post_id) == 0
        
        # いいねしていない投稿の解除
        success2 = self.sns.unlike_post("bob", self.post.post_id)
        assert success2 is False
    
    def test_reply_functionality(self):
        """返信機能のテスト"""
        # 返信の実行
        reply = self.sns.reply_to_post("bob", self.post.post_id, "返信テスト")
        assert reply is not None
        assert reply.user_id == "bob"
        assert reply.post_id == self.post.post_id
        assert reply.content == "返信テスト"
        
        # 返信数の確認
        assert self.sns.get_post_replies_count(self.post.post_id) == 1
        
        # 返信一覧の取得
        replies = self.sns.get_post_replies(self.post.post_id)
        assert len(replies) == 1
        assert replies[0].content == "返信テスト"
        
        # 複数の返信
        reply2 = self.sns.reply_to_post("charlie", self.post.post_id, "2番目の返信")
        assert reply2 is not None
        assert self.sns.get_post_replies_count(self.post.post_id) == 2
    
    def test_notification_functionality(self):
        """通知機能のテスト"""
        # フォロー関係を作成
        self.sns.follow_user("bob", "alice")
        self.sns.follow_user("charlie", "alice")
        
        # いいねで通知を生成
        self.sns.like_post("bob", self.post.post_id)
        
        # 通知の確認
        notifications = self.sns.get_user_notifications("alice")
        assert len(notifications) > 0
        
        # いいね通知の確認
        like_notifications = [n for n in notifications if n.type == NotificationType.LIKE]
        assert len(like_notifications) > 0
        
        # 返信で通知を生成
        self.sns.reply_to_post("charlie", self.post.post_id, "返信テスト")
        
        # 通知数の確認
        notifications_after = self.sns.get_user_notifications("alice")
        assert len(notifications_after) > len(notifications)
    
    def test_notification_read_status(self):
        """通知の既読機能のテスト"""
        # フォロー関係を作成
        self.sns.follow_user("bob", "alice")
        
        # いいねで通知を生成
        self.sns.like_post("bob", self.post.post_id)
        
        # 未読通知数の確認
        unread_count = self.sns.get_unread_notifications_count("alice")
        assert unread_count > 0
        
        # 通知を既読にする
        notifications = self.sns.get_user_notifications("alice")
        if notifications:
            notification_id = notifications[0].notification_id
            success = self.sns.mark_notification_as_read(notification_id)
            assert success is True
            
            # 既読後の未読通知数
            unread_count_after = self.sns.get_unread_notifications_count("alice")
            assert unread_count_after < unread_count
    
    def test_invalid_post_id(self):
        """無効な投稿IDのテスト"""
        invalid_post_id = "invalid-post-id"
        
        # 無効な投稿IDへのいいね
        success = self.sns.like_post("bob", invalid_post_id)
        assert success is False
        
        # 無効な投稿IDへの返信
        reply = self.sns.reply_to_post("bob", invalid_post_id, "返信テスト")
        assert reply is None
    
    def test_empty_reply_content(self):
        """空の返信内容のテスト"""
        # 空の内容での返信
        reply = self.sns.reply_to_post("bob", self.post.post_id, "")
        assert reply is None
        
        # 空白のみの内容での返信
        reply2 = self.sns.reply_to_post("bob", self.post.post_id, "   ")
        assert reply2 is None
    
    def test_notification_types(self):
        """通知タイプのテスト"""
        # フォロー関係を作成
        self.sns.follow_user("bob", "alice")
        
        # フォロー通知
        follow_notifications = self.sns.get_user_notifications("alice")
        follow_notifications = [n for n in follow_notifications if n.type == NotificationType.FOLLOW]
        assert len(follow_notifications) > 0
        
        # いいね通知
        self.sns.like_post("bob", self.post.post_id)
        like_notifications = self.sns.get_user_notifications("alice")
        like_notifications = [n for n in like_notifications if n.type == NotificationType.LIKE]
        assert len(like_notifications) > 0
        
        # 返信通知
        self.sns.reply_to_post("bob", self.post.post_id, "返信テスト")
        reply_notifications = self.sns.get_user_notifications("alice")
        reply_notifications = [n for n in reply_notifications if n.type == NotificationType.REPLY]
        assert len(reply_notifications) > 0
    
    def test_timeline_with_post_ids(self):
        """投稿ID付きタイムラインのテスト"""
        # 複数の投稿を作成
        post2 = self.sns.create_post("bob", "ボブの投稿")
        post3 = self.sns.create_post("charlie", "チャーリーの投稿")
        
        # タイムラインを取得
        timeline = self.sns.get_global_timeline()
        assert len(timeline) >= 3
        
        # 各投稿にIDが含まれているかチェック
        post_ids = [post.post_id for post in timeline]
        assert self.post.post_id in post_ids
        assert post2.post_id in post_ids
        assert post3.post_id in post_ids
        
        # フォーマットされた投稿にIDが含まれているかチェック
        for post in timeline:
            formatted = post.format_for_timeline()
            assert "ID:" in formatted
            assert post.post_id in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 