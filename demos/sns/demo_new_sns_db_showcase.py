#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DB版 新SNSシステム ショーケースデモ

- ユーザー作成/更新
- 投稿（パブリック/フォロワー限定/相互/指定ユーザー/プライベート）
- ハッシュタグ/メンション
- タイムライン（グローバル/フォロー中/ハッシュタグ）
- フォロー/ブロック
- いいね/解除
- 返信/通知（取得と既読化）

実行方法:
    source venv/bin/activate
    python demos/sns/demo_new_sns_db_showcase.py
"""

import os
import sys
import tempfile
import time
from typing import Optional

# プロジェクトルートをsys.pathに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from game.sns.new_sns_manager import SnsManager
from game.sns.new_sns_data import Post
from game.enums import PostVisibility


def h(title: str) -> None:
    print("\n" + "=" * 20 + f" {title} " + "=" * 20)


def show_posts(title: str, posts: list[Post]) -> None:
    h(title)
    if not posts:
        print("(no posts)")
        return
    for p in posts:
        print(p.format_for_timeline())


def now_ts() -> int:
    return int(time.time())


def main(db_path: Optional[str] = None) -> None:
    # DBファイル
    tmp_created = False
    if not db_path:
        fd, db_path = tempfile.mkstemp(prefix="sns_demo_", suffix=".sqlite")
        os.close(fd)
        tmp_created = True
    print(f"Using DB: {db_path}")

    try:
        sns = SnsManager(db_path=db_path)

        # ユーザー
        h("Create users")
        sns.create_user("alice", "アリス", "よろしくお願いします！")
        sns.create_user("bob", "ボブ", "エンジニアです")
        sns.create_user("charlie", "チャーリー", "ゲーム好き")
        sns.create_user("dave", "デイブ", "デザイナーです")
        updated = sns.update_user_bio("alice", "新しい一言コメント")
        print("Updated:", updated)

        # 投稿（各種可視性）
        h("Create posts with various visibilities")
        pub = sns.create_post("alice", "パブリック投稿です！ #日常 #天気 @bob", ["#初投稿"])  # mention + hashtag
        fol = sns.create_post("alice", "フォロワー限定です", visibility=PostVisibility.FOLLOWERS_ONLY)
        mut = sns.create_post("alice", "相互フォロー限定です", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
        spc = sns.create_post(
            "alice", "指定ユーザー限定です", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=["bob"]
        )
        prv = sns.create_post("alice", "プライベートです", visibility=PostVisibility.PRIVATE)
        print("Created:", pub, fol, mut, spc, prv)

        # タイムライン: 非ログイン（None）
        show_posts("Global timeline (viewer=None)", sns.get_global_timeline_before(viewer_id=None, limit=50, created_at=now_ts()))

        # フォロー/相互フォローを設定
        h("Follow flow")
        sns.follow_user("bob", "alice")
        sns.follow_user("alice", "bob")  # 相互
        print("bob -> alice:", sns.is_following("bob", "alice"), "alice -> bob:", sns.is_following("alice", "bob"))

        # タイムライン: bob視点
        show_posts(
            "Global timeline (viewer=bob)",
            sns.get_global_timeline_before(viewer_id="bob", limit=50, created_at=now_ts()),
        )
        show_posts(
            "Following timeline (user=bob)",
            sns.get_following_timeline_before("bob", limit=50, created_at=now_ts()),
        )

        # ハッシュタグタイムライン
        show_posts(
            "Hashtag timeline #天気 (viewer=None)",
            sns.get_hashtag_timeline_before("#天気", viewer_id=None, limit=50, created_at=now_ts()),
        )

        # いいね
        h("Likes")
        if pub:
            print("bob likes pub:", sns.like_post("bob", pub.post_id))
            print("like count:", sns.get_post_likes_count(pub.post_id))
        if prv:
            print("charlie likes alice private (should False):", sns.like_post("charlie", prv.post_id))

        # 返信 + メンション
        h("Replies and mentions")
        if pub:
            reply = sns.reply_to_post("bob", pub.post_id, "面白いね！ @charlie")
            print("reply:", reply)

        # 通知（取得→既読化）
        h("Notifications for alice: unread count")
        print("unread:", sns.get_unread_notifications_count_db("alice"))
        notifs = sns.fetch_notifications_mark_read("alice", limit=20)
        print("fetched:", len(notifs))
        print("unread after:", sns.get_unread_notifications_count_db("alice"))

        # 指定ユーザー限定: bobは見えるがcharlieは見えない
        h("Specified users visibility check")
        tl_bob = sns.get_global_timeline_before(viewer_id="bob", limit=50, created_at=now_ts())
        tl_charlie = sns.get_global_timeline_before(viewer_id="charlie", limit=50, created_at=now_ts())
        print("spc in bob tl:", any(p.post_id == spc.post_id for p in tl_bob if spc))
        print("spc in charlie tl:", any(p.post_id == spc.post_id for p in tl_charlie if spc))

        # ブロック: alice -> charlie
        h("Blocks")
        print("alice blocks charlie:", sns.block_user("alice", "charlie"))
        tl_charlie_after = sns.get_global_timeline_before(viewer_id="charlie", limit=50, created_at=now_ts())
        print("charlie can see alice posts after block:", any(p.user_id == "alice" for p in tl_charlie_after))

        # Hashtag timeline viewer=bob
        show_posts(
            "Hashtag timeline #日常 (viewer=bob)",
            sns.get_hashtag_timeline_before("#日常", viewer_id="bob", limit=50, created_at=now_ts()),
        )

        h("Done")
        print("Demo finished successfully.")
    finally:
        if tmp_created:
            try:
                os.remove(db_path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
