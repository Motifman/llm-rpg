#!/usr/bin/env python3
"""
SNSいいね・返信・通知機能のデモ

このデモでは、新しく実装されたSNSのいいね・返信・通知機能を紹介します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.sns.sns_manager import SnsManager
from game.enums import PostVisibility, NotificationType
from datetime import datetime


def print_separator(title):
    """セパレーターを表示"""
    print("\n" + "="*60)
    print(f" {title} ")
    print("="*60)


def print_subsection(title):
    """サブセクションを表示"""
    print(f"\n--- {title} ---")


def demo_post_id_display():
    """投稿ID表示機能のデモ"""
    print_separator("投稿ID表示機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 投稿作成
    post1 = sns.create_post("alice", "こんにちは、世界！ #初投稿")
    post2 = sns.create_post("bob", "今日は良い天気です #天気 #日記")
    post3 = sns.create_post("charlie", "新しいデザインを考え中 #デザイン #アイデア")
    
    print_subsection("投稿ID付きタイムライン表示")
    print("投稿IDが表示されるようになりました:")
    
    # グローバルタイムラインを取得して表示
    timeline = sns.get_global_timeline()
    for i, post in enumerate(timeline, 1):
        print(f"\n投稿 {i}:")
        print(post.format_for_timeline())
    
    print(f"\n投稿ID一覧:")
    for i, post in enumerate(timeline, 1):
        print(f"  {i}. {post.post_id}")


def demo_like_functionality():
    """いいね機能のデモ"""
    print_separator("いいね機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 投稿作成
    post = sns.create_post("alice", "素晴らしい投稿です！ #感想")
    
    print_subsection("いいね機能のテスト")
    print(f"投稿内容: {post.content}")
    print(f"投稿ID: {post.post_id}")
    
    # いいねを実行
    print_subsection("いいねの実行")
    success1 = sns.like_post("bob", post.post_id)
    success2 = sns.like_post("charlie", post.post_id)
    
    print(f"ボブのいいね: {'成功' if success1 else '失敗'}")
    print(f"チャーリーのいいね: {'成功' if success2 else '失敗'}")
    
    # いいね状況の確認
    print_subsection("いいね状況の確認")
    print(f"投稿のいいね数: {sns.get_post_likes_count(post.post_id)}")
    print(f"ボブがいいね済み: {sns.has_liked('bob', post.post_id)}")
    print(f"チャーリーがいいね済み: {sns.has_liked('charlie', post.post_id)}")
    print(f"アリスがいいね済み: {sns.has_liked('alice', post.post_id)}")
    
    # いいね解除のテスト
    print_subsection("いいね解除のテスト")
    success3 = sns.unlike_post("bob", post.post_id)
    print(f"ボブのいいね解除: {'成功' if success3 else '失敗'}")
    print(f"ボブがいいね済み: {sns.has_liked('bob', post.post_id)}")
    print(f"投稿のいいね数: {sns.get_post_likes_count(post.post_id)}")


def demo_reply_functionality():
    """返信機能のデモ"""
    print_separator("返信機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 投稿作成
    post = sns.create_post("alice", "みなさん、こんにちは！ #挨拶")
    
    print_subsection("返信機能のテスト")
    print(f"投稿内容: {post.content}")
    print(f"投稿ID: {post.post_id}")
    
    # 返信を実行
    print_subsection("返信の実行")
    reply1 = sns.reply_to_post("bob", post.post_id, "こんにちは、アリス！")
    reply2 = sns.reply_to_post("charlie", post.post_id, "よろしくお願いします！")
    
    print(f"ボブの返信: {'成功' if reply1 else '失敗'}")
    print(f"チャーリーの返信: {'成功' if reply2 else '失敗'}")
    
    # 返信状況の確認
    print_subsection("返信状況の確認")
    print(f"投稿の返信数: {sns.get_post_replies_count(post.post_id)}")
    
    # 返信一覧を取得
    replies = sns.get_post_replies(post.post_id)
    print(f"返信一覧:")
    for i, reply in enumerate(replies, 1):
        print(f"  {i}. {reply.user_id}: {reply.content} (ID: {reply.reply_id})")


def demo_notification_functionality():
    """通知機能のデモ"""
    print_separator("通知機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # フォロー関係を作成
    sns.follow_user("bob", "alice")
    sns.follow_user("charlie", "alice")
    
    # 投稿作成
    post = sns.create_post("alice", "テスト投稿 @bob @charlie")
    
    print_subsection("通知の生成")
    print(f"投稿内容: {post.content}")
    print(f"投稿ID: {post.post_id}")
    
    # いいねと返信で通知を生成
    sns.like_post("bob", post.post_id)
    sns.reply_to_post("charlie", post.post_id, "返信テスト")
    
    print_subsection("通知の確認")
    alice_notifications = sns.get_user_notifications("alice")
    print(f"アリスの通知数: {len(alice_notifications)}")
    
    for i, notification in enumerate(alice_notifications, 1):
        status = "📬" if notification.is_read else "📨"
        print(f"  {i}. {status} {notification.content} (ID: {notification.notification_id})")
    
    print_subsection("未読通知の確認")
    unread_count = sns.get_unread_notifications_count("alice")
    print(f"アリスの未読通知数: {unread_count}")
    
    # 通知を既読にする
    if alice_notifications:
        notification_id = alice_notifications[0].notification_id
        print_subsection("通知を既読にする")
        success = sns.mark_notification_as_read(notification_id)
        print(f"通知既読処理: {'成功' if success else '失敗'}")
        
        unread_count_after = sns.get_unread_notifications_count("alice")
        print(f"既読後の未読通知数: {unread_count_after}")


def demo_integrated_functionality():
    """統合機能のデモ"""
    print_separator("統合機能デモ")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # フォロー関係を作成
    sns.follow_user("bob", "alice")
    sns.follow_user("charlie", "alice")
    
    # 投稿作成
    post = sns.create_post("alice", "新しい機能のテスト投稿です！ #テスト #新機能")
    
    print_subsection("投稿の作成")
    print(f"投稿内容: {post.content}")
    print(f"投稿ID: {post.post_id}")
    
    # いいねと返信を実行
    print_subsection("いいねと返信の実行")
    sns.like_post("bob", post.post_id)
    sns.like_post("charlie", post.post_id)
    reply = sns.reply_to_post("bob", post.post_id, "素晴らしい投稿ですね！")
    
    # 統計情報の確認
    print_subsection("統計情報の確認")
    print(f"投稿のいいね数: {sns.get_post_likes_count(post.post_id)}")
    print(f"投稿の返信数: {sns.get_post_replies_count(post.post_id)}")
    
    # 通知の確認
    alice_notifications = sns.get_user_notifications("alice")
    print(f"アリスの通知数: {len(alice_notifications)}")
    
    # タイムライン表示（投稿ID付き）
    print_subsection("投稿ID付きタイムライン")
    timeline = sns.get_global_timeline()
    for post in timeline:
        print(post.format_for_timeline())


def main():
    """メイン関数"""
    print("SNSいいね・返信・通知機能 デモ")
    print("このデモでは、新しく実装されたSNSのいいね・返信・通知機能を紹介します。")
    
    try:
        # 各機能のデモを実行
        demo_post_id_display()
        demo_like_functionality()
        demo_reply_functionality()
        demo_notification_functionality()
        demo_integrated_functionality()
        
        print_separator("デモ完了")
        print("SNSいいね・返信・通知機能のデモが完了しました！")
        print("\n実装された機能:")
        print("- 投稿IDの表示機能")
        print("- いいね・いいね解除機能")
        print("- 投稿への返信機能")
        print("- 通知の取得・既読機能")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 