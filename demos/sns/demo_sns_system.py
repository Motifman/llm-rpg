#!/usr/bin/env python3
"""
SNSシステムのデモ

このデモでは、SNSシステムの全機能を網羅的に紹介します。
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


def demo_user_management():
    """ユーザー管理機能のデモ"""
    print_separator("ユーザー管理機能")
    
    sns = SnsManager()
    
    # ユーザー作成
    print_subsection("ユーザー作成")
    user1 = sns.create_user("alice", "アリス", "よろしくお願いします！")
    user2 = sns.create_user("bob", "ボブ", "エンジニアです")
    user3 = sns.create_user("charlie", "チャーリー", "デザイナーです")
    user4 = sns.create_user("diana", "ダイアナ", "マーケターです")
    
    print(f"作成されたユーザー:")
    for user in [user1, user2, user3, user4]:
        print(f"  - {user.name} (@{user.user_id}): {user.bio}")
    
    # ユーザー情報更新
    print_subsection("ユーザー情報更新")
    updated_user = sns.update_user_bio("alice", "新しい一言コメントに更新しました！")
    print(f"アリスのプロフィール更新: {updated_user.bio}")
    
    # ユーザー取得
    print_subsection("ユーザー取得")
    retrieved_user = sns.get_user("bob")
    print(f"ボブの情報: {retrieved_user.name} - {retrieved_user.bio}")


def demo_post_creation():
    """投稿作成機能のデモ"""
    print_separator("投稿作成機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 基本的な投稿
    print_subsection("基本的な投稿")
    post1 = sns.create_post("alice", "こんにちは、世界！")
    print(f"投稿作成: {post1.content}")
    print(f"投稿ID: {post1.post_id}")
    print(f"可視性: {post1.get_visibility_label()}")
    
    # ハッシュタグ付き投稿
    print_subsection("ハッシュタグ付き投稿")
    post2 = sns.create_post("bob", "今日は良い天気 #天気 #日記 #初投稿", ["#プログラミング"])
    print(f"投稿作成: {post2.content}")
    print(f"ハッシュタグ: {post2.hashtags}")
    
    # 可視性設定付き投稿
    print_subsection("可視性設定付き投稿")
    private_post = sns.create_post("alice", "これはプライベート投稿です", visibility=PostVisibility.PRIVATE)
    followers_post = sns.create_post("bob", "フォロワー限定投稿です", visibility=PostVisibility.FOLLOWERS_ONLY)
    specified_post = sns.create_post("charlie", "指定ユーザー限定投稿です", 
                                   visibility=PostVisibility.SPECIFIED_USERS,
                                   allowed_users=["alice", "bob"])
    
    print(f"プライベート投稿: {private_post.get_visibility_label()}")
    print(f"フォロワー限定投稿: {followers_post.get_visibility_label()}")
    print(f"指定ユーザー限定投稿: {specified_post.get_visibility_label()}")


def demo_timeline_features():
    """タイムライン機能のデモ"""
    print_separator("タイムライン機能")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    sns.create_user("diana", "ダイアナ", "マーケターです")
    
    # 投稿作成
    sns.create_post("alice", "アリスの投稿 #初投稿")
    sns.create_post("bob", "ボブの投稿 #プログラミング")
    sns.create_post("charlie", "チャーリーの投稿 #デザイン")
    sns.create_post("diana", "ダイアナの投稿 #マーケティング")
    sns.create_post("alice", "アリスの2番目の投稿 #日記")
    
    # グローバルタイムライン
    print_subsection("グローバルタイムライン")
    global_timeline = sns.get_global_timeline()
    print(f"グローバルタイムライン ({len(global_timeline)}件):")
    for i, post in enumerate(global_timeline, 1):
        print(f"  {i}. {post.user_id}: {post.content[:30]}...")
    
    # ハッシュタグタイムライン
    print_subsection("ハッシュタグタイムライン")
    hashtag_timeline = sns.get_hashtag_timeline("#初投稿")
    print(f"#初投稿 の投稿 ({len(hashtag_timeline)}件):")
    for i, post in enumerate(hashtag_timeline, 1):
        print(f"  {i}. {post.user_id}: {post.content}")


def demo_follow_system():
    """フォローシステムのデモ"""
    print_separator("フォローシステム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    sns.create_user("diana", "ダイアナ", "マーケターです")
    
    # フォロー関係作成
    print_subsection("フォロー関係作成")
    sns.follow_user("alice", "bob")
    sns.follow_user("alice", "charlie")
    sns.follow_user("bob", "alice")
    sns.follow_user("diana", "alice")
    
    # フォロー情報表示
    print_subsection("フォロー情報")
    print(f"アリスのフォロー中: {sns.get_following_count('alice')}人")
    print(f"アリスのフォロワー: {sns.get_followers_count('alice')}人")
    
    following_list = sns.get_following_list("alice")
    followers_list = sns.get_followers_list("alice")
    
    print(f"アリスがフォローしている人: {following_list}")
    print(f"アリスをフォローしている人: {followers_list}")
    
    # フォロー中タイムライン
    print_subsection("フォロー中タイムライン")
    sns.create_post("bob", "ボブの投稿")
    sns.create_post("charlie", "チャーリーの投稿")
    sns.create_post("diana", "ダイアナの投稿")  # フォローしていない
    
    following_timeline = sns.get_following_timeline("alice")
    print(f"アリスのフォロー中タイムライン ({len(following_timeline)}件):")
    for i, post in enumerate(following_timeline, 1):
        print(f"  {i}. {post.user_id}: {post.content}")


def demo_block_system():
    """ブロックシステムのデモ"""
    print_separator("ブロックシステム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # フォロー関係作成
    sns.follow_user("alice", "bob")
    sns.follow_user("bob", "alice")
    
    print_subsection("ブロック前の状態")
    print(f"アリスがボブをフォロー: {sns.is_following('alice', 'bob')}")
    print(f"ボブがアリスをフォロー: {sns.is_following('bob', 'alice')}")
    
    # ブロック実行
    print_subsection("ブロック実行")
    sns.block_user("alice", "bob")
    
    print(f"アリスがボブをブロック: {sns.is_blocked('alice', 'bob')}")
    print(f"アリスがボブをフォロー: {sns.is_following('alice', 'bob')}")  # 自動アンフォロー
    print(f"ボブがアリスをフォロー: {sns.is_following('bob', 'alice')}")  # 自動アンフォロー
    
    # ブロックリスト
    print_subsection("ブロックリスト")
    blocked_list = sns.get_blocked_list("alice")
    blocked_by_list = sns.get_blocked_by_list("bob")
    
    print(f"アリスがブロックしている人: {blocked_list}")
    print(f"ボブをブロックしている人: {blocked_by_list}")


def demo_like_system():
    """いいねシステムのデモ"""
    print_separator("いいねシステム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 投稿作成
    post = sns.create_post("alice", "素晴らしい投稿です！")
    
    print_subsection("いいね機能")
    sns.like_post("bob", post.post_id)
    sns.like_post("charlie", post.post_id)
    
    print(f"投稿のいいね数: {sns.get_post_likes_count(post.post_id)}")
    print(f"ボブがいいね済み: {sns.has_liked('bob', post.post_id)}")
    print(f"チャーリーがいいね済み: {sns.has_liked('charlie', post.post_id)}")
    
    # いいね解除
    print_subsection("いいね解除")
    sns.unlike_post("bob", post.post_id)
    print(f"ボブがいいね解除後: {sns.has_liked('bob', post.post_id)}")
    print(f"投稿のいいね数: {sns.get_post_likes_count(post.post_id)}")


def demo_reply_system():
    """返信システムのデモ"""
    print_separator("返信システム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    # 投稿作成
    post = sns.create_post("alice", "みなさん、こんにちは！")
    
    print_subsection("返信機能")
    reply1 = sns.reply_to_post("bob", post.post_id, "こんにちは、アリス！")
    reply2 = sns.reply_to_post("charlie", post.post_id, "よろしくお願いします！")
    
    print(f"投稿の返信数: {sns.get_post_replies_count(post.post_id)}")
    
    # 返信一覧
    print_subsection("返信一覧")
    replies = sns.get_post_replies(post.post_id)
    for i, reply in enumerate(replies, 1):
        print(f"  {i}. {reply.user_id}: {reply.content}")


def demo_mention_system():
    """メンションシステムのデモ"""
    print_separator("メンションシステム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    print_subsection("投稿内メンション")
    post = sns.create_post("alice", "こんにちは @bob と @charlie！")
    
    # メンション情報
    mentions_for_bob = sns.get_mentions_for_user("bob")
    mentions_for_charlie = sns.get_mentions_for_user("charlie")
    
    print(f"ボブへのメンション: {len(mentions_for_bob)}件")
    print(f"チャーリーへのメンション: {len(mentions_for_charlie)}件")
    
    print_subsection("返信内メンション")
    reply = sns.reply_to_post("bob", post.post_id, "こんにちは @charlie！")
    
    mentions_for_charlie = sns.get_mentions_for_user("charlie")
    print(f"チャーリーへのメンション（返信含む）: {len(mentions_for_charlie)}件")
    
    print_subsection("メンション統計")
    mentions_by_alice = sns.get_mentions_by_user("alice")
    mentions_for_post = sns.get_mentions_for_post(post.post_id)
    
    print(f"アリスが行ったメンション: {len(mentions_by_alice)}件")
    print(f"投稿内のメンション: {len(mentions_for_post)}件")


def demo_notification_system():
    """通知システムのデモ"""
    print_separator("通知システム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    
    print_subsection("フォロー通知")
    sns.follow_user("bob", "alice")
    sns.follow_user("charlie", "alice")
    
    alice_notifications = sns.get_user_notifications("alice")
    print(f"アリスの通知数: {len(alice_notifications)}")
    for notification in alice_notifications:
        print(f"  - {notification.content}")
    
    print_subsection("いいね・返信・メンション通知")
    post = sns.create_post("alice", "テスト投稿 @bob")
    sns.like_post("bob", post.post_id)
    sns.reply_to_post("charlie", post.post_id, "返信です！")
    
    alice_notifications = sns.get_user_notifications("alice")
    print(f"アリスの通知数: {len(alice_notifications)}")
    for notification in alice_notifications:
        print(f"  - {notification.content}")
    
    print_subsection("未読通知")
    unread_count = sns.get_unread_notifications_count("alice")
    print(f"アリスの未読通知数: {unread_count}")
    
    # 通知を既読にする
    if alice_notifications:
        notification_id = alice_notifications[0].notification_id
        sns.mark_notification_as_read(notification_id)
        print(f"通知を既読にしました: {notification_id}")
        
        unread_count = sns.get_unread_notifications_count("alice")
        print(f"既読後の未読通知数: {unread_count}")


def demo_visibility_system():
    """可視性システムのデモ"""
    print_separator("可視性システム")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    sns.create_user("diana", "ダイアナ", "マーケターです")
    
    # フォロー関係作成
    sns.follow_user("bob", "alice")
    sns.follow_user("alice", "bob")  # 相互フォロー
    sns.follow_user("charlie", "alice")
    
    print_subsection("可視性別投稿作成")
    public_post = sns.create_post("alice", "パブリック投稿", visibility=PostVisibility.PUBLIC)
    private_post = sns.create_post("alice", "プライベート投稿", visibility=PostVisibility.PRIVATE)
    followers_post = sns.create_post("alice", "フォロワー限定投稿", visibility=PostVisibility.FOLLOWERS_ONLY)
    mutual_post = sns.create_post("alice", "相互フォロー限定投稿", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
    specified_post = sns.create_post("alice", "指定ユーザー限定投稿", 
                                   visibility=PostVisibility.SPECIFIED_USERS,
                                   allowed_users=["bob", "charlie"])
    
    print_subsection("可視性チェック")
    posts = [
        ("パブリック", public_post),
        ("プライベート", private_post),
        ("フォロワー限定", followers_post),
        ("相互フォロー限定", mutual_post),
        ("指定ユーザー限定", specified_post)
    ]
    
    viewers = ["alice", "bob", "charlie", "diana"]
    
    print("可視性チェック結果:")
    print("投稿タイプ\t\tアリス\tボブ\tチャーリー\tダイアナ")
    print("-" * 80)
    
    for post_name, post in posts:
        visibility_results = []
        for viewer in viewers:
            is_visible = sns._is_post_visible(post, viewer)
            visibility_results.append("✓" if is_visible else "✗")
        
        print(f"{post_name}\t\t" + "\t".join(visibility_results))


def demo_statistics():
    """統計機能のデモ"""
    print_separator("統計機能")
    
    sns = SnsManager()
    
    # テストデータ作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    sns.create_user("charlie", "チャーリー", "デザイナーです")
    sns.create_user("diana", "ダイアナ", "マーケターです")
    
    # フォロー関係
    sns.follow_user("alice", "bob")
    sns.follow_user("bob", "alice")
    sns.follow_user("charlie", "alice")
    
    # 投稿
    post1 = sns.create_post("alice", "投稿1")
    post2 = sns.create_post("bob", "投稿2", visibility=PostVisibility.PRIVATE)
    post3 = sns.create_post("charlie", "投稿3", visibility=PostVisibility.FOLLOWERS_ONLY)
    
    # いいね・返信
    sns.like_post("bob", post1.post_id)
    sns.like_post("charlie", post1.post_id)
    sns.reply_to_post("bob", post1.post_id, "返信1")
    sns.reply_to_post("charlie", post1.post_id, "返信2")
    
    # ブロック
    sns.block_user("alice", "diana")
    
    # 統計取得
    stats = sns.get_system_stats()
    
    print_subsection("システム統計")
    print(f"総ユーザー数: {stats['total_users']}")
    print(f"総投稿数: {stats['total_posts']}")
    print(f"総フォロー数: {stats['total_follows']}")
    print(f"総いいね数: {stats['total_likes']}")
    print(f"総返信数: {stats['total_replies']}")
    print(f"総通知数: {stats['total_notifications']}")
    print(f"総ブロック数: {stats['total_blocks']}")
    print(f"総メンション数: {stats['total_mentions']}")
    
    print_subsection("可視性別投稿数")
    for visibility, count in stats['posts_by_visibility'].items():
        print(f"  {visibility}: {count}件")


def demo_edge_cases():
    """エッジケースのデモ"""
    print_separator("エッジケース")
    
    sns = SnsManager()
    
    # テストユーザー作成
    sns.create_user("alice", "アリス", "よろしくお願いします！")
    sns.create_user("bob", "ボブ", "エンジニアです")
    
    print_subsection("特殊文字を含む投稿")
    special_post = sns.create_post("alice", "特殊文字テスト: @bob! #test-hash_tag #test@hash")
    print(f"投稿内容: {special_post.content}")
    print(f"ハッシュタグ: {special_post.hashtags}")
    
    print_subsection("長い投稿")
    long_content = "a" * 500
    long_post = sns.create_post("bob", long_content)
    print(f"長い投稿の長さ: {len(long_post.content)}文字")
    
    print_subsection("空の投稿")
    empty_post = sns.create_post("alice", "")
    print(f"空の投稿: '{empty_post.content}'")
    
    print_subsection("重複メンション")
    duplicate_mention_post = sns.create_post("bob", "こんにちは @alice と @alice")
    mentions = sns.get_mentions_for_user("alice")
    print(f"重複メンション後のメンション数: {len(mentions)}")


def main():
    """メイン関数"""
    print("SNSシステム デモ")
    print("このデモでは、SNSシステムの全機能を網羅的に紹介します。")
    
    try:
        # 各機能のデモを実行
        demo_user_management()
        demo_post_creation()
        demo_timeline_features()
        demo_follow_system()
        demo_block_system()
        demo_like_system()
        demo_reply_system()
        demo_mention_system()
        demo_notification_system()
        demo_visibility_system()
        demo_statistics()
        demo_edge_cases()
        
        print_separator("デモ完了")
        print("SNSシステムの全機能のデモが完了しました！")
        
    except Exception as e:
        print(f"デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 