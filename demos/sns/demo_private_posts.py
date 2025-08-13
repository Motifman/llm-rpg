#!/usr/bin/env python3
"""
プライベート投稿機能のデモンストレーション

このデモでは以下のプライベート投稿機能を紹介します：
1. 5つの可視性レベル（パブリック、プライベート、フォロワー限定、相互フォロー限定、指定ユーザー限定）
2. 可視性に基づくタイムラインフィルタリング
3. プライベート投稿への いいね・返信の制限
4. 可視性統計の表示
"""

from src_old.systems.sns_system import SnsSystem
from src_old.systems.sns_adapter import SnsAdapter
from src_old.models.agent import Agent
from src_old.models.sns import PostVisibility


def print_separator(title=""):
    """セクション区切り線を表示"""
    print("\n" + "="*80)
    if title:
        print(f" {title} ")
        print("="*80)


def print_posts_with_visibility(posts, viewer_name=""):
    """投稿を可視性情報とともに表示"""
    if not posts:
        print("  投稿はありません")
        return
    
    viewer_info = f" - {viewer_name}の視点" if viewer_name else ""
    print(f"  投稿一覧{viewer_info}:")
    for post in posts:
        print(f"    📝 {post.content[:50]}{'...' if len(post.content) > 50 else ''}")
        print(f"       {post.get_visibility_label()} - 投稿者: @{post.user_id}")
        if post.is_specified_users_only() and post.allowed_users:
            allowed_str = ", ".join([f"@{user}" for user in post.allowed_users])
            print(f"       🎯 許可ユーザー: {allowed_str}")
        print()


def demo_visibility_levels():
    """可視性レベルのデモンストレーション"""
    print_separator("1. 可視性レベルのデモンストレーション")
    
    # システム初期化
    sns_system = SnsSystem()
    sns_adapter = SnsAdapter(sns_system)
    
    # エージェント作成と登録
    alice = Agent("alice", "アリス")
    bob = Agent("bob", "ボブ")
    charlie = Agent("charlie", "チャーリー")
    david = Agent("david", "デイビッド")
    
    sns_adapter.register_agent_as_sns_user(alice)
    sns_adapter.register_agent_as_sns_user(bob)
    sns_adapter.register_agent_as_sns_user(charlie)
    sns_adapter.register_agent_as_sns_user(david)
    
    # フォロー関係設定
    sns_adapter.agent_follow(bob, alice)     # Bob → Alice
    sns_adapter.agent_follow(alice, bob)     # Alice → Bob (相互フォロー)
    sns_adapter.agent_follow(charlie, alice) # Charlie → Alice (一方向)
    
    print("フォロー関係:")
    print("  🤝 Alice ↔ Bob (相互フォロー)")
    print("  ➡️ Charlie → Alice (一方向フォロー)")
    print("  🚫 David (フォロー関係なし)")
    
    print("\nアリスが各可視性レベルで投稿を作成:")
    
    # 1. パブリック投稿
    public_post = sns_adapter.agent_post(alice, "皆さん、こんにちは！今日は良い天気ですね。")
    print(f"  ✅ {public_post.get_visibility_label()}: {public_post.content}")
    
    # 2. プライベート投稿
    private_post = sns_adapter.agent_create_private_post(alice, "今日の個人的なメモ：明日は大事な会議がある。")
    print(f"  ✅ {private_post.get_visibility_label()}: {private_post.content}")
    
    # 3. フォロワー限定投稿
    followers_post = sns_adapter.agent_create_followers_only_post(alice, "フォロワーの皆さんへ：新しいプロジェクトを始めました！")
    print(f"  ✅ {followers_post.get_visibility_label()}: {followers_post.content}")
    
    # 4. 相互フォロー限定投稿
    mutual_post = sns_adapter.agent_create_mutual_follows_post(alice, "親しい友人へ：今度一緒に映画を見ませんか？")
    print(f"  ✅ {mutual_post.get_visibility_label()}: {mutual_post.content}")
    
    # 5. 指定ユーザー限定投稿
    specified_post = sns_adapter.agent_create_specified_users_post(
        alice, "ボブとチャーリーへ：来週のミーティングの件で相談があります。", [bob, charlie]
    )
    print(f"  ✅ {specified_post.get_visibility_label()}: {specified_post.content}")
    print(f"       🎯 許可ユーザー: @bob, @charlie")
    
    return sns_adapter, alice, bob, charlie, david


def demo_timeline_filtering(sns_adapter, alice, bob, charlie, david):
    """タイムラインフィルタリングのデモンストレーション"""
    print_separator("2. タイムラインでの可視性フィルタリング")
    
    # 各ユーザーの視点でグローバルタイムラインを確認
    users = [
        (alice, "Alice（投稿者）"),
        (bob, "Bob（相互フォロー）"),
        (charlie, "Charlie（一方向フォロー）"),
        (david, "David（フォロー関係なし）")
    ]
    
    for user, description in users:
        print(f"\n📺 {description}のグローバルタイムライン:")
        timeline = sns_adapter.get_agent_timeline(user, "global")
        print_posts_with_visibility(timeline, user.name)


def demo_interaction_restrictions(sns_adapter, alice, bob, charlie, david):
    """プライベート投稿のインタラクション制限デモ"""
    print_separator("3. プライベート投稿のインタラクション制限")
    
    # アリスのプライベート投稿を取得
    alice_posts = sns_adapter.get_agent_posts_by_visibility(alice, PostVisibility.PRIVATE)
    if alice_posts:
        private_post = alice_posts[0]
        print(f"対象のプライベート投稿: \"{private_post.content}\"")
        
        # 各ユーザーがいいねを試行
        print("\nいいね試行結果:")
        users_to_test = [
            (alice, "Alice（投稿者本人）"),
            (bob, "Bob（相互フォロー）"),
            (charlie, "Charlie（一方向フォロー）"),
            (david, "David（フォロー関係なし）")
        ]
        
        for user, description in users_to_test:
            success = sns_adapter.agent_like_post(user, private_post.post_id)
            result = "✅ 成功" if success else "❌ 失敗（権限なし）"
            print(f"  {description}: {result}")
        
        # 返信を試行
        print("\n返信試行結果:")
        for user, description in users_to_test:
            reply = sns_adapter.agent_reply_to_post(user, private_post.post_id, f"{user.name}からの返信です")
            result = "✅ 成功" if reply else "❌ 失敗（権限なし）"
            print(f"  {description}: {result}")


def demo_visibility_statistics(sns_adapter, alice, bob, charlie, david):
    """可視性統計のデモンストレーション"""
    print_separator("4. 可視性統計の表示")
    
    # アリスの可視性別投稿統計
    alice_stats = sns_adapter.get_agent_visibility_stats(alice)
    print("📊 アリスの可視性別投稿統計:")
    for visibility, count in alice_stats.items():
        visibility_labels = {
            "public": "🌍 パブリック",
            "private": "🔒 プライベート",
            "followers_only": "👥 フォロワー限定",
            "mutual_follows_only": "🤝 相互フォロー限定",
            "specified_users": "🎯 指定ユーザー限定"
        }
        label = visibility_labels.get(visibility, visibility)
        print(f"  {label}: {count}件")
    
    # 各可視性レベルの投稿を表示
    print("\n📝 可視性別投稿一覧:")
    for visibility in [PostVisibility.PUBLIC, PostVisibility.PRIVATE, PostVisibility.FOLLOWERS_ONLY, 
                      PostVisibility.MUTUAL_FOLLOWS_ONLY, PostVisibility.SPECIFIED_USERS]:
        posts = sns_adapter.get_agent_posts_by_visibility(alice, visibility)
        if posts:
            print(f"\n{posts[0].get_visibility_label()}:")
            for post in posts:
                print(f"  📝 {post.content}")
                if post.is_specified_users_only() and post.allowed_users:
                    allowed_str = ", ".join([f"@{user}" for user in post.allowed_users])
                    print(f"     🎯 許可ユーザー: {allowed_str}")


def demo_advanced_scenarios(sns_adapter, alice, bob, charlie, david):
    """高度なシナリオのデモンストレーション"""
    print_separator("5. 高度なシナリオ")
    
    print("シナリオ1: ハッシュタグ付きプライベート投稿")
    # ハッシュタグ付きプライベート投稿
    private_hashtag_post = sns_adapter.agent_create_private_post(
        alice, "個人的なプロジェクト進捗 #プライベートプロジェクト #秘密開発"
    )
    print(f"  投稿: {private_hashtag_post.content}")
    print(f"  ハッシュタグ: {', '.join(private_hashtag_post.hashtags)}")
    
    # ハッシュタグタイムラインでの表示確認
    print("\n#プライベートプロジェクト タイムライン:")
    hashtag_timeline = sns_adapter.get_hashtag_timeline("#プライベートプロジェクト")
    print_posts_with_visibility(hashtag_timeline, "パブリック表示")
    
    # Aliceの視点でのハッシュタグタイムライン
    alice_hashtag_timeline = sns_adapter.get_hashtag_timeline("#プライベートプロジェクト", alice)
    print("Aliceの視点での #プライベートプロジェクト タイムライン:")
    print_posts_with_visibility(alice_hashtag_timeline, "Alice")
    
    print("\nシナリオ2: 指定ユーザー投稿の詳細管理")
    # 複数の指定ユーザー投稿
    team_post = sns_adapter.agent_create_specified_users_post(
        alice, "チーム限定情報：来週のリリースについて #チーム #重要", [bob, charlie]
    )
    print(f"  チーム投稿: {team_post.content}")
    print(f"  許可ユーザー: {', '.join([f'@{user}' for user in team_post.allowed_users])}")
    
    # 許可されたユーザーのタイムライン確認
    print(f"\nBob（許可ユーザー）のタイムライン:")
    bob_timeline = sns_adapter.get_agent_timeline(bob, "global", limit=10)
    print_posts_with_visibility(bob_timeline, "Bob")
    
    print(f"\nDavid（許可されていないユーザー）のタイムライン:")
    david_timeline = sns_adapter.get_agent_timeline(david, "global", limit=10)
    print_posts_with_visibility(david_timeline, "David")


def main():
    """メインデモ実行"""
    print("🚀 プライベート投稿機能 総合デモンストレーション")
    print("="*80)
    print("本デモでは、SNSシステムの5つの可視性レベルと")
    print("プライベート投稿機能の動作を確認します。")
    
    # 1. 可視性レベルのデモ
    sns_adapter, alice, bob, charlie, david = demo_visibility_levels()
    
    # 2. タイムラインフィルタリングのデモ
    demo_timeline_filtering(sns_adapter, alice, bob, charlie, david)
    
    # 3. インタラクション制限のデモ
    demo_interaction_restrictions(sns_adapter, alice, bob, charlie, david)
    
    # 4. 可視性統計のデモ
    demo_visibility_statistics(sns_adapter, alice, bob, charlie, david)
    
    # 5. 高度なシナリオのデモ
    demo_advanced_scenarios(sns_adapter, alice, bob, charlie, david)
    
    print_separator("✨ プライベート投稿機能デモ完了")
    print("プライベート投稿機能により、エージェントは以下が可能になりました：")
    print("  🌍 パブリック投稿 - 全員が閲覧可能")
    print("  🔒 プライベート投稿 - 本人のみ閲覧可能")
    print("  👥 フォロワー限定投稿 - フォロワーのみ閲覧可能")
    print("  🤝 相互フォロー限定投稿 - 相互フォローのみ閲覧可能")
    print("  🎯 指定ユーザー限定投稿 - 指定されたユーザーのみ閲覧可能")
    print("\nこれにより、エージェント間のより豊かでプライベートな")
    print("コミュニケーションが実現されます。")


if __name__ == "__main__":
    main() 