#!/usr/bin/env python3
"""
SNSシステムのデモンストレーション

エージェント同士のSNS機能を実際に動作させてみるデモスクリプト
"""

from src_old.systems.sns_system import SnsSystem
from src_old.systems.sns_adapter import SnsAdapter
from src_old.models.agent import Agent


def print_separator(title: str):
    """セクション区切りを表示"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def print_posts(posts, title: str):
    """投稿リストを表示"""
    print(f"\n--- {title} ---")
    if not posts:
        print("投稿がありません")
        return
    
    for i, post in enumerate(posts, 1):
        print(f"{i}. [{post.user_id}] {post.content}")
        if post.hashtags:
            print(f"   ハッシュタグ: {', '.join(post.hashtags)}")
        print(f"   投稿日時: {post.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def print_notifications(notifications, title: str):
    """通知リストを表示"""
    print(f"\n--- {title} ---")
    if not notifications:
        print("通知がありません")
        return
    
    for i, notification in enumerate(notifications, 1):
        status = "未読" if not notification.is_read else "既読"
        print(f"{i}. [{status}] {notification.content}")
        print(f"   種別: {notification.type.value}")
        print(f"   通知日時: {notification.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    """デモンストレーションのメイン関数"""
    print("🎉 SNSシステム デモンストレーション")
    
    # SNSシステムとアダプターを初期化
    sns_system = SnsSystem()
    sns_adapter = SnsAdapter(sns_system)
    
    # エージェントを作成
    alice = Agent("alice", "アリス")
    bob = Agent("bob", "ボブ")
    charlie = Agent("charlie", "チャーリー")
    
    print_separator("1. エージェントのSNS登録")
    
    # エージェントをSNSユーザーとして登録
    sns_adapter.register_agent_as_sns_user(alice, "こんにちは！アリスです。よろしくお願いします！")
    sns_adapter.register_agent_as_sns_user(bob, "エンジニアをしているボブです。")
    sns_adapter.register_agent_as_sns_user(charlie, "旅行が趣味のチャーリーです。")
    
    print("✅ エージェントをSNSユーザーとして登録しました")
    print(f"- {alice.name}: {sns_adapter.get_agent_sns_profile(alice).bio}")
    print(f"- {bob.name}: {sns_adapter.get_agent_sns_profile(bob).bio}")
    print(f"- {charlie.name}: {sns_adapter.get_agent_sns_profile(charlie).bio}")
    
    print_separator("2. 投稿機能のデモ")
    
    # 各エージェントが投稿
    post1 = sns_adapter.agent_post(alice, "初投稿です！みなさんよろしくお願いします 🎉 #初投稿 #よろしく")
    post2 = sns_adapter.agent_post(bob, "新しいプログラミング言語を学習中です #プログラミング #学習")
    post3 = sns_adapter.agent_post(charlie, "京都旅行に行ってきました！とても素敵な街でした #旅行 #京都")
    post4 = sns_adapter.agent_post(alice, "今日はお天気が良いですね ☀️ #天気 #日記")
    post5 = sns_adapter.agent_post(bob, "コードレビューって大事ですね #エンジニア #プログラミング")
    
    print("✅ 各エージェントが投稿しました")
    
    # グローバルタイムラインを表示
    global_timeline = sns_adapter.get_agent_timeline(alice, "global")
    print_posts(global_timeline, "グローバルタイムライン（最新順）")
    
    print_separator("3. フォロー機能のデモ")
    
    # フォロー関係を構築
    sns_adapter.agent_follow(alice, bob)
    sns_adapter.agent_follow(alice, charlie)
    sns_adapter.agent_follow(bob, alice)
    sns_adapter.agent_follow(charlie, alice)
    
    print("✅ フォロー関係を構築しました")
    
    # アリスのフォロー中タイムライン
    following_timeline = sns_adapter.get_agent_timeline(alice, "following")
    print_posts(following_timeline, "アリスのフォロー中タイムライン")
    
    # フォロー統計を表示
    alice_stats = sns_adapter.get_agent_social_stats(alice)
    print(f"\n📊 アリスのソーシャル統計:")
    print(f"- 投稿数: {alice_stats['posts_count']}")
    print(f"- フォロワー数: {alice_stats['followers_count']}")
    print(f"- フォロー中: {alice_stats['following_count']}")
    
    print_separator("4. いいね・返信機能のデモ")
    
    # いいねと返信を追加
    sns_adapter.agent_like_post(bob, post1.post_id)
    sns_adapter.agent_like_post(charlie, post1.post_id)
    sns_adapter.agent_like_post(alice, post2.post_id)
    
    sns_adapter.agent_reply_to_post(bob, post3.post_id, "京都いいですね！私も行ってみたいです")
    sns_adapter.agent_reply_to_post(alice, post5.post_id, "本当にそうですね！チームワークが大切です")
    
    print("✅ いいねと返信を追加しました")
    
    # 投稿の詳細情報を表示
    post_details = sns_adapter.get_post_with_interactions(post1.post_id)
    print(f"\n📝 投稿詳細（アリスの初投稿）:")
    print(f"内容: {post_details['post'].content}")
    print(f"いいね数: {post_details['likes_count']}")
    print(f"返信数: {post_details['replies_count']}")
    
    print_separator("5. 通知機能のデモ")
    
    # アリスの通知を表示
    alice_notifications = sns_adapter.get_agent_notifications(alice)
    print_notifications(alice_notifications, "アリスの通知")
    
    # 未読通知数を表示
    unread_count = sns_adapter.get_agent_unread_count(alice)
    print(f"📬 アリスの未読通知数: {unread_count}")
    
    print_separator("6. ハッシュタグ機能のデモ")
    
    # ハッシュタグ別タイムライン
    programming_posts = sns_adapter.get_hashtag_timeline("プログラミング")
    print_posts(programming_posts, "#プログラミング タイムライン")
    
    # トレンドハッシュタグ
    trending = sns_adapter.get_trending_hashtags()
    print("\n🔥 トレンドハッシュタグ:")
    for i, trend in enumerate(trending[:5], 1):
        print(f"{i}. {trend['hashtag']} ({trend['count']}投稿)")
    
    print_separator("7. 検索機能のデモ")
    
    # ユーザー検索
    users = sns_adapter.search_users("エンジニア")
    print(f"\n🔍 'エンジニア'で検索したユーザー:")
    for user in users:
        print(f"- {user.name} ({user.user_id}): {user.bio}")
    
    # 投稿検索
    posts = sns_adapter.search_posts("旅行")
    print_posts(posts, "'旅行'で検索した投稿")
    
    print_separator("8. エージェント関係性のデモ")
    
    # エージェント間の関係性
    alice_bob_relation = sns_adapter.get_agent_relationship_status(alice, bob)
    print(f"\n👥 アリスとボブの関係性:")
    print(f"- アリス → ボブ: {'フォロー中' if alice_bob_relation['is_following'] else 'フォローしていない'}")
    print(f"- ボブ → アリス: {'フォロー中' if alice_bob_relation['is_followed_by'] else 'フォローしていない'}")
    print(f"- 相互フォロー: {'はい' if alice_bob_relation['is_mutual'] else 'いいえ'}")
    
    print_separator("9. 詳細フィード機能のデモ")
    
    # 詳細情報付きフィードを表示
    feed = sns_adapter.get_agent_feed_with_details(alice, "global", limit=3)
    print(f"\n📱 アリスの詳細フィード（最新3件）:")
    for i, item in enumerate(feed, 1):
        post = item['post']
        print(f"{i}. [{item['author'].name}] {post.content}")
        print(f"   いいね: {item['likes_count']} | 返信: {item['replies_count']} | " +
              f"{'❤️' if item['liked_by_agent'] else '🤍'}")
        
        if item['recent_replies']:
            print(f"   最近の返信:")
            for reply in item['recent_replies'][:2]:
                print(f"     - {reply.content}")
        print()
    
    print_separator("10. システム統計情報")
    
    # システム全体の統計
    system_stats = sns_system.get_system_stats()
    print(f"\n📈 システム全体の統計:")
    print(f"- 総ユーザー数: {system_stats['total_users']}")
    print(f"- 総投稿数: {system_stats['total_posts']}")
    print(f"- 総フォロー数: {system_stats['total_follows']}")
    print(f"- 総いいね数: {system_stats['total_likes']}")
    print(f"- 総返信数: {system_stats['total_replies']}")
    print(f"- 総通知数: {system_stats['total_notifications']}")
    print(f"- 総ブロック数: {system_stats['total_blocks']}")
    
    print_separator("11. ブロック機能のデモ")
    
    # 問題ユーザーとしてダミーエージェントを作成
    david = Agent("david", "デイビッド")
    sns_adapter.register_agent_as_sns_user(david, "迷惑な投稿をするユーザー")
    
    # デイビッドが迷惑な投稿
    spam_post = sns_adapter.agent_post(david, "スパム投稿です！みんな無視してください！ #スパム")
    
    print("✅ 問題ユーザー（デイビッド）が迷惑投稿をしました")
    
    # アリスがデイビッドをブロック
    result = sns_adapter.agent_block_user(alice, david)
    print(f"📛 アリスがデイビッドをブロック: {result}")
    
    # ブロック後のタイムライン（デイビッドの投稿は表示されない）
    alice_timeline_after_block = sns_adapter.get_agent_timeline(alice, "global", limit=10)
    print(f"\n📱 ブロック後のアリスのタイムライン:")
    blocked_user_posts = [post for post in alice_timeline_after_block if post.user_id == "david"]
    print(f"- デイビッドの投稿数: {len(blocked_user_posts)} (ブロックにより非表示)")
    
    # デイビッドからのインタラクション試行（全て拒否される）
    alice_post_for_block_test = sns_adapter.agent_post(alice, "ブロックテスト用投稿")
    
    david_like_result = sns_adapter.agent_like_post(david, alice_post_for_block_test.post_id)
    david_reply_result = sns_adapter.agent_reply_to_post(david, alice_post_for_block_test.post_id, "返信試行")
    david_follow_result = sns_adapter.agent_follow(david, alice)
    
    print(f"\n🚫 ブロック制限の効果:")
    print(f"- デイビッドからのいいね: {'拒否' if not david_like_result else '許可'}")
    print(f"- デイビッドからの返信: {'拒否' if david_reply_result is None else '許可'}")
    print(f"- デイビッドからのフォロー: {'拒否' if not david_follow_result else '許可'}")
    
    # ブロックリストと関係性の表示
    alice_blocked_list = sns_adapter.get_agent_blocked_list(alice)
    alice_david_relation = sns_adapter.get_agent_relationship_status(alice, david)
    
    print(f"\n📋 アリスのブロックリスト:")
    for blocked_id in alice_blocked_list:
        blocked_user = sns_adapter.get_agent_sns_profile(Agent(blocked_id, blocked_id))
        print(f"- {blocked_user.name} ({blocked_id})")
    
    print(f"\n👥 アリスとデイビッドの関係性:")
    print(f"- アリス → デイビッド: {'ブロック中' if alice_david_relation['is_blocking'] else 'ブロックしていない'}")
    print(f"- デイビッド → アリス: {'ブロックされている' if alice_david_relation['is_blocked_by'] else 'ブロックされていない'}")
    
    # ブロック解除のデモ
    print(f"\n🔓 ブロック解除のテスト:")
    unblock_result = sns_adapter.agent_unblock_user(alice, david)
    print(f"- ブロック解除: {'成功' if unblock_result else '失敗'}")
    
    # ブロック解除後はインタラクションが再び可能
    david_like_after_unblock = sns_adapter.agent_like_post(david, alice_post_for_block_test.post_id)
    print(f"- ブロック解除後のいいね: {'成功' if david_like_after_unblock else '失敗'}")

    print_separator("デモ完了")
    print("🎊 SNSシステムのデモンストレーションが完了しました！")
    print("エージェント同士が投稿、フォロー、いいね、返信、通知、ブロックなどの")
    print("様々なSNS機能を利用できることが確認できました。")
    print("\n新機能：")
    print("✅ ブロック機能により迷惑ユーザーからの干渉を防止")
    print("✅ ブロック時の自動フォロー解除")
    print("✅ ブロック制限によるタイムラインフィルタリング")
    print("✅ ブロック/アンブロック機能")


if __name__ == "__main__":
    main() 