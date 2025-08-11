import os
import tempfile
import time
from datetime import datetime
import pytest

from game.sns.new_sns_manager import SnsManager
from game.sns.new_sns_data import Post, Reply, Notification
from game.enums import PostVisibility, NotificationType


@pytest.fixture()
def db_path_tmp():
    fd, path = tempfile.mkstemp(prefix="sns_db_", suffix=".sqlite")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


@pytest.fixture()
def sns(db_path_tmp):
    mgr = SnsManager(db_path=db_path_tmp)
    # 基本ユーザー
    mgr.create_user("user1", "アリス", "よろしくお願いします")
    mgr.create_user("user2", "ボブ", "エンジニアです")
    mgr.create_user("user3", "チャーリー", "")
    mgr.create_user("user4", "デイビッド", "デザイナーです")
    return mgr


# === ユーザー ===

def test_user_crud(sns: SnsManager):
    assert sns.user_exists("user1")
    u = sns.get_user("user1")
    assert u is not None and u.name == "アリス"
    updated = sns.update_user_bio("user1", "新しい一言コメント")
    assert updated is not None and updated.bio.startswith("新しい一言")


def test_create_user_conflict_raises(sns: SnsManager):
    # 既に存在するIDで作成を試みると ValueError
    import pytest
    with pytest.raises(ValueError):
        sns.create_user("user1", "だぶり")


# === 投稿 ===

def test_create_post_and_get_user_posts(sns: SnsManager):
    p = sns.create_post("user1", "こんにちは、世界！")
    assert p is not None and p.user_id == "user1"
    posts = sns.get_user_posts("user1")
    assert len(posts) == 1 and posts[0].post_id == p.post_id


def test_create_post_with_hashtags_and_mentions(sns: SnsManager):
    p = sns.create_post("user1", "今日は良い天気 #天気 #日記 そして @user2 に挨拶", ["#初投稿"])
    assert p is not None
    # 抽出 + 指定で重複なく含まれる
    assert set(["#天気", "#日記", "#初投稿"]).issubset(set(p.hashtags))
    # mention 通知
    notifs = sns.fetch_notifications_mark_read("user2", limit=10)
    assert any(n.type == NotificationType.MENTION for n in notifs)


def test_create_post_specified_users_validation(sns: SnsManager):
    # 許可ユーザー未指定
    assert sns.create_post("user1", "x", visibility=PostVisibility.SPECIFIED_USERS) is None
    # 無効ユーザーのみ
    assert sns.create_post(
        "user1", "x", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=["nope"]
    ) is None
    # 有効ケース
    p = sns.create_post(
        "user1", "限定", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=["user2", "nope"]
    )
    assert p is not None and set(p.allowed_users) == {"user2"}


# === タイムライン ===

def _now_ts():
    return int(time.time())


def test_global_timeline_before_public_only_without_viewer(sns: SnsManager):
    sns.create_post("user1", "p1")
    sns.create_post("user2", "p2", visibility=PostVisibility.PRIVATE)
    tl = sns.get_global_timeline_before(viewer_id=None, limit=50, created_at=_now_ts())
    assert all(p.visibility == PostVisibility.PUBLIC for p in tl)


def test_global_timeline_before_with_viewer_visibility_and_blocks(sns: SnsManager):
    p_pub = sns.create_post("user1", "pub")
    p_prv = sns.create_post("user1", "prv", visibility=PostVisibility.PRIVATE)
    p_fol = sns.create_post("user1", "fol", visibility=PostVisibility.FOLLOWERS_ONLY)
    p_mut = sns.create_post("user1", "mut", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
    p_spc = sns.create_post(
        "user1", "spc", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=["user2"]
    )

    # ブロックすると見えない
    sns.block_user("user1", "user2")
    tl_blocked = sns.get_global_timeline_before(viewer_id="user2", limit=50, created_at=_now_ts())
    assert all(post.user_id != "user1" for post in tl_blocked)

    # 解除して可視性条件を順次満たす
    sns.unblock_user("user1", "user2")

    # followers_only は user2->user1 フォローで可視
    sns.follow_user("user2", "user1")

    # mutual は相互に
    sns.follow_user("user1", "user2")

    tl = sns.get_global_timeline_before(viewer_id="user2", limit=50, created_at=_now_ts())
    ids = {post.content for post in tl}
    assert "pub" in ids
    assert "prv" not in ids
    assert "fol" in ids
    assert "mut" in ids
    assert "spc" in ids


def test_following_timeline_before(sns: SnsManager):
    sns.follow_user("user2", "user1")
    sns.create_post("user1", "a")
    sns.create_post("user3", "b")
    tl = sns.get_following_timeline_before("user2", limit=50, created_at=_now_ts())
    contents = {p.content for p in tl}
    assert "a" in contents and "b" not in contents


def test_hashtag_timeline_before(sns: SnsManager):
    sns.create_post("user1", "天気 #天気")
    sns.create_post("user2", "雨 #天気")
    tl = sns.get_hashtag_timeline_before("#天気", viewer_id=None, limit=50, created_at=_now_ts())
    assert len(tl) == 2


# === フォロー/ブロック ===

def test_follow_and_counts_and_lists(sns: SnsManager):
    assert sns.follow_user("user1", "user2") is True
    assert sns.is_following("user1", "user2") is True
    assert sns.get_following_count("user1") == 1
    assert sns.get_followers_count("user2") == 1
    assert "user2" in sns.get_following_list("user1")


def test_block_and_lists_and_counts(sns: SnsManager):
    assert sns.block_user("user1", "user2") is True
    assert sns.is_blocked("user1", "user2") is True
    assert sns.get_blocked_count("user1") == 1
    assert sns.get_blocked_list("user1") == ["user2"]
    assert sns.get_blocked_by_list("user2") == ["user1"]
    assert sns.unblock_user("user1", "user2") is True
    assert sns.is_blocked("user1", "user2") is False


# === いいね ===

def test_like_unlike_flow_with_visibility(sns: SnsManager):
    pub = sns.create_post("user1", "pub")
    prv = sns.create_post("user1", "prv", visibility=PostVisibility.PRIVATE)

    # 自分の投稿は可視性に関係なくOK
    assert sns.like_post("user1", pub.post_id) is True
    assert sns.has_liked("user1", pub.post_id) is True
    assert sns.like_post("user1", prv.post_id) is True

    # 他人: private は不可
    assert sns.like_post("user2", prv.post_id) is False

    # followers_only: フォローでOK
    fol = sns.create_post("user1", "fol", visibility=PostVisibility.FOLLOWERS_ONLY)
    assert sns.like_post("user2", fol.post_id) is False
    sns.follow_user("user2", "user1")
    assert sns.like_post("user2", fol.post_id) is True

    # mutual: 相互のみ
    mut = sns.create_post("user1", "mut", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
    assert sns.like_post("user2", mut.post_id) is False
    sns.follow_user("user1", "user2")
    assert sns.like_post("user2", mut.post_id) is True

    # specified_users
    spc = sns.create_post("user1", "spc", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=["user2"])
    assert sns.like_post("user3", spc.post_id) is False
    assert sns.like_post("user2", spc.post_id) is True

    # 重複いいね不可
    assert sns.like_post("user2", spc.post_id) is False

    # 解除
    assert sns.unlike_post("user2", spc.post_id) is True
    assert sns.unlike_post("user2", spc.post_id) is False


# === 返信 ===

def test_reply_and_fetch_replies_and_count(sns: SnsManager):
    post = sns.create_post("user1", "元投稿")
    r1 = sns.reply_to_post("user2", post.post_id, "返信1 @user3")
    assert r1 is not None
    r2 = sns.reply_to_post("user3", post.post_id, "返信2")
    replies = sns.get_post_replies(post.post_id)
    assert [r.content for r in replies] == ["返信1 @user3", "返信2"]
    assert sns.get_post_replies_count(post.post_id) == 2


# === 通知 ===

def test_notifications_fetch_and_mark_read_and_unread_count(sns: SnsManager):
    # follow -> follow通知
    assert sns.follow_user("user2", "user1") is True
    # like -> like通知
    p = sns.create_post("user1", "n1")
    assert sns.like_post("user2", p.post_id) is True
    # reply -> reply通知
    assert sns.reply_to_post("user2", p.post_id, "r") is not None

    unread_before = sns.get_unread_notifications_count_db("user1")
    assert unread_before >= 2

    fetched = sns.fetch_notifications_mark_read("user1", limit=10)
    assert len(fetched) == unread_before or len(fetched) == 3
    # 既読化
    unread_after = sns.get_unread_notifications_count_db("user1")
    assert unread_after == max(0, unread_before - len(fetched))
