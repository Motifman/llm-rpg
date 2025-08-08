#!/usr/bin/env python3
"""
SNS投稿の整形機能のデモ

Postクラスの新しい整形メソッドの使用例を示します。
"""

from datetime import datetime
from game.sns.sns_data import Post
from game.enums import PostVisibility


def demo_basic_formatting():
    """基本的な投稿の整形デモ"""
    print("=== 基本的な投稿の整形 ===")
    
    post = Post.create(
        user_id="player1",
        content="今日は冒険に出かけました！新しいダンジョンを発見して、たくさんの宝を見つけました。",
        hashtags=["冒険", "ダンジョン", "宝"],
        visibility=PostVisibility.PUBLIC
    )
    
    print(post.format_post())
    print()


def demo_compact_formatting():
    """コンパクト形式の整形デモ"""
    print("=== コンパクト形式の整形 ===")
    
    # 短い投稿
    short_post = Post.create(
        user_id="player2",
        content="短い投稿です。",
        visibility=PostVisibility.PRIVATE
    )
    print("短い投稿:")
    print(short_post.format_compact())
    print()
    
    # 長い投稿
    long_content = "これは非常に長い投稿内容です。文字数制限を超えるような長い文章を投稿した場合、コンパクト形式では自動的に切り詰められて「...」が追加されます。"
    long_post = Post.create(
        user_id="player3",
        content=long_content,
        visibility=PostVisibility.FOLLOWERS_ONLY
    )
    print("長い投稿:")
    print(long_post.format_compact())
    print()


def demo_timeline_formatting():
    """タイムライン形式の整形デモ"""
    print("=== タイムライン形式の整形 ===")
    
    post = Post.create(
        user_id="player4",
        content="タイムラインに表示される投稿です。\n改行も含まれています。",
        hashtags=["タイムライン", "デモ"],
        visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY
    )
    
    print(post.format_for_timeline())
    print()


def demo_author_name_formatting():
    """投稿者名を指定した整形デモ"""
    print("=== 投稿者名を指定した整形 ===")
    
    post = Post.create(
        user_id="player5",
        content="投稿者名を指定して整形する例です。",
        hashtags=["デモ"],
        visibility=PostVisibility.SPECIFIED_USERS,
        allowed_users=["friend1", "friend2"]
    )
    
    print("投稿者名なし:")
    print(post.format_post())
    print()
    
    print("投稿者名あり:")
    print(post.format_post(author_name="冒険者アリス"))
    print()


def demo_metadata_options():
    """メタデータオプションのデモ"""
    print("=== メタデータオプション ===")
    
    post = Post.create(
        user_id="player6",
        content="メタデータの表示オプションをテストする投稿です。",
        hashtags=["メタデータ", "テスト"],
        visibility=PostVisibility.PUBLIC
    )
    
    print("メタデータあり:")
    print(post.format_post(include_metadata=True))
    print()
    
    print("メタデータなし:")
    print(post.format_post(include_metadata=False))
    print()


def demo_edited_post():
    """編集された投稿のデモ"""
    print("=== 編集された投稿 ===")
    
    # 作成日時と更新日時が異なる投稿を作成
    created_at = datetime(2024, 1, 15, 10, 30, 0)
    updated_at = datetime(2024, 1, 15, 14, 45, 0)
    
    post = Post(
        post_id="edited_post",
        user_id="player7",
        content="これは編集された投稿です。",
        hashtags=["編集"],
        visibility=PostVisibility.PUBLIC,
        allowed_users=[],
        created_at=created_at,
        updated_at=updated_at
    )
    
    print(post.format_post())
    print()


def demo_all_visibility_types():
    """すべての可視性タイプのデモ"""
    print("=== すべての可視性タイプ ===")
    
    visibilities = [
        (PostVisibility.PUBLIC, "パブリック投稿"),
        (PostVisibility.PRIVATE, "プライベート投稿"),
        (PostVisibility.FOLLOWERS_ONLY, "フォロワー限定投稿"),
        (PostVisibility.MUTUAL_FOLLOWS_ONLY, "相互フォロー限定投稿"),
        (PostVisibility.SPECIFIED_USERS, "指定ユーザー限定投稿")
    ]
    
    for visibility, content in visibilities:
        post = Post.create(
            user_id="player8",
            content=content,
            visibility=visibility,
            allowed_users=["user1", "user2"] if visibility == PostVisibility.SPECIFIED_USERS else []
        )
        
        print(f"可視性: {post.get_visibility_label()}")
        print(post.format_compact())
        print()


def main():
    """メイン関数"""
    print("SNS投稿の整形機能デモ")
    print("=" * 50)
    print()
    
    demo_basic_formatting()
    demo_compact_formatting()
    demo_timeline_formatting()
    demo_author_name_formatting()
    demo_metadata_options()
    demo_edited_post()
    demo_all_visibility_types()
    
    print("デモ完了！")


if __name__ == "__main__":
    main() 