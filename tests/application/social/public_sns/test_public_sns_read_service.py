"""公開SNSの祖先検査・有限取得・参照先全文を保証する。"""

import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from ai_rpg_world.application.social.public_sns.access_policy import PublicSnsAccessPolicy
from ai_rpg_world.application.social.public_sns.contracts import (
    PublicSnsInvalidRequestError,
    PublicSnsUnavailableError,
)
from ai_rpg_world.application.social.public_sns.read_repository import PublicSnsContentRecord, PublicSnsUserRecord
from ai_rpg_world.application.social.public_sns.read_service import PublicSnsReadService
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId

NOW = datetime(2026, 1, 1)


class ReadRepository:
    def __init__(self):
        self.namespace = uuid4().hex
        self.users = {i: UserAggregate.create_new_user(UserId(i), f"user{i}", f"人物{i}", "") for i in range(1, 5)}
        self.records = {}
        self.notifications = []
        self.scans = []
        self.lookups = 0

    def find_user(self, user_id):
        user = self.users.get(user_id)
        return None if user is None else PublicSnsUserRecord(user_id, user.identity_token, user.profile.display_name)

    def has_block(self, blocker_user_id, blocked_user_id):
        return self.users[blocker_user_id].is_blocked(UserId(blocked_user_id))

    def find_content(self, kind, identity_token):
        return next((r for r in self.records.values() if r.kind == kind and r.identity_token == identity_token), None)

    def find_content_by_id(self, kind, local_id):
        self.lookups += 1
        return self.records.get((kind, local_id))

    def _scan(self, kind, before_id, limit, parent=None):
        self.scans.append((kind, before_id, limit))
        return sorted(
            (
                r
                for r in self.records.values()
                if r.kind == kind
                and (before_id is None or r.local_id < before_id)
                and (parent is None or (r.parent_kind, r.parent_id) == parent)
            ),
            key=lambda r: r.local_id,
            reverse=True,
        )[:limit]

    def scan_posts(self, before_id, limit):
        return self._scan("post", before_id, limit)

    def scan_replies(self, parent_kind, parent_id, before_id, limit):
        return self._scan("reply", before_id, limit, (parent_kind, parent_id))

    def scan_notifications(self, viewer_user_id, before_id, limit):
        return sorted(
            (
                n
                for n in self.notifications
                if n.user_id.value == viewer_user_id and (before_id is None or n.notification_id.value < before_id)
            ),
            key=lambda n: n.notification_id.value,
            reverse=True,
        )[:limit]

    def post(self, local_id=1, author=2, visibility=PostVisibility.PUBLIC):
        record = PublicSnsContentRecord(
            "post",
            local_id,
            uuid4().hex,
            author,
            "本文" * 130,
            visibility,
            False,
            NOW,
            author_identity_token=self.users[author].identity_token,
        )
        self.records[("post", local_id)] = record
        return record

    def reply(self, local_id, parent, author=3):
        record = PublicSnsContentRecord(
            "reply",
            local_id,
            uuid4().hex,
            author,
            "返信" * 135,
            PostVisibility.PUBLIC,
            False,
            NOW,
            parent.kind,
            parent.local_id,
            author_identity_token=self.users[author].identity_token,
            parent_identity_token=parent.identity_token,
        )
        self.records[("reply", local_id)] = record
        return record

    def replace(self, record, **changes):
        record = replace(record, **changes)
        self.records[(record.kind, record.local_id)] = record
        return record

    def target(self, record):
        return PublicSnsAccessPolicy(self).target_id(record)

    def notification(
        self,
        kind=NotificationType.REPLY,
        *,
        related_post_id=None,
        related_reply_id=None,
        actor=3,
        viewer=1,
        expires_at=None,
    ):
        value = Notification(
            NotificationId(len(self.notifications) + 1),
            UserId(viewer),
            kind,
            NotificationContent(
                "保存時題名",
                "保存時の秘密",
                UserId(actor),
                "昔の作者名",
                related_post_id=PostId(related_post_id) if related_post_id else None,
                related_reply_id=ReplyId(related_reply_id) if related_reply_id else None,
                content_text="保存時の秘密",
                actor_identity_token=self.users[actor].identity_token,
                related_target_id=self.target(self.records[("reply", related_reply_id)])
                if related_reply_id
                else self.target(self.records[("post", related_post_id)])
                if related_post_id
                else None,
            ),
            NOW,
            expires_at=expires_at,
            recipient_identity_token=self.users[viewer].identity_token,
        )
        self.notifications.append(value)
        return value


@pytest.fixture
def source():
    return ReadRepository()


@pytest.fixture
def reader(source):
    return PublicSnsReadService(source, now=lambda: NOW)


def test_target_returns_full_selected_reply_and_only_immediate_children(source, reader):
    """返信を直接選ぶと本文全体と直下の返信を返し、別枝を混ぜない。"""
    root = source.post()
    reply = source.reply(1, root)
    child = source.reply(2, reply)
    source.reply(3, root)
    thread = reader.read_target(1, source.target(reply))
    assert thread.selected.content == reply.content
    assert thread.selected.parent_target_id == source.target(root)
    assert [item.target_id for item in thread.ancestors] == [source.target(root)]
    assert thread.selected.author_target_id == f"sns:{source.namespace}:user:{source.users[3].identity_token}"
    assert [item.target_id for item in thread.replies.items] == [source.target(child)]


@pytest.mark.parametrize("visibility", [PostVisibility.PRIVATE, PostVisibility.FOLLOWERS_ONLY])
def test_even_authors_cannot_read_non_public_content(source, reader, visibility):
    """作者本人でも非公開投稿を公開専用入口へ出さない。"""
    record = source.post(author=1, visibility=visibility)
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(record))
    assert reader.read_posts(1).items == ()


@pytest.mark.parametrize("hidden", ["root", "parent", "selected"])
@pytest.mark.parametrize("reason", ["private", "deleted", "viewer_block", "author_block", "missing_author", "missing"])
def test_every_ancestor_and_selected_reply_are_checked(source, reader, hidden, reason):
    """選択返信・親返信・根投稿のどこに拒否条件があっても同じ不可視応答にする。"""
    records = {"root": source.post(author=2)}
    records["parent"] = source.reply(1, records["root"], author=3)
    records["selected"] = source.reply(2, records["parent"], author=4)
    record = records[hidden]
    if reason == "private":
        source.replace(record, visibility=PostVisibility.PRIVATE)
    elif reason == "deleted":
        source.replace(record, deleted=True)
    elif reason == "viewer_block":
        source.users[1].block(UserId(record.author_user_id))
    elif reason == "author_block":
        source.users[record.author_user_id].block(UserId(1))
    elif reason == "missing_author":
        del source.users[record.author_user_id]
    else:
        del source.records[(record.kind, record.local_id)]
    with pytest.raises(PublicSnsUnavailableError, match="この投稿は現在表示できません"):
        reader.read_target(1, source.target(records["selected"]))


def test_reference_has_no_navigation_or_viewer_ownership_binding(source, reader):
    """同じ公開投稿のIDは別画面取得後や別の閲覧者でも同じ投稿を指す。"""
    record = source.post()
    original = reader.read_posts(1).items[0].target_id
    source.post(2)
    reader.read_posts(1)
    assert reader.read_target(3, original).selected.content == record.content
    assert reader.read_target(3, original).selected.target_id == original


@pytest.mark.parametrize("target", ["1", "post:1", "sns_post_ref:1", "sns:" + "a" * 32 + ":post:" + "b" * 32, None, ""])
def test_invalid_missing_and_foreign_scope_targets_use_same_safe_error(source, reader, target):
    """生整数・画面参照・別保存領域・欠落を区別する情報をエラーに含めない。"""
    source.post()
    with pytest.raises(PublicSnsUnavailableError) as error:
        reader.read_target(1, target)
    assert str(error.value) == "この投稿は現在表示できません"


def test_old_reference_never_resolves_to_replacement_integer(source, reader):
    """同じ整数IDを新しい投稿が使っても古い不変IDは解決しない。"""
    record = source.post()
    target = source.target(record)
    source.post()
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, target)


def test_parent_cycle_fails_closed_without_unbounded_reads(source, reader):
    """返信の親が循環していても有限回の検査で不可視にする。"""
    root = source.post()
    reply = source.reply(1, root)
    source.replace(reply, parent_kind="reply", parent_id=1)
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(reply))
    assert source.lookups <= 2


def test_excessive_ancestry_fails_closed(source, reader):
    """祖先が64段を超える投稿は無制限に取得せず不可視にする。"""
    current = source.post()
    for i in range(1, 100):
        current = source.reply(i, current)
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(current))
    assert source.lookups <= 64


def test_keyset_keeps_progress_when_new_post_arrives_and_old_one_disappears(source, reader):
    """ページ間の追加と削除によって既読投稿を重複させず、未読投稿を飛ばさない。"""
    originals = [source.post(i) for i in range(1, 6)]
    first = reader.read_posts(1, limit=2)
    source.post(6)
    del source.records[("post", 5)]
    second = reader.read_posts(1, limit=2, cursor=first.next_cursor)
    assert [item.target_id for item in second.items] == [source.target(originals[2]), source.target(originals[1])]
    third = reader.read_posts(1, limit=2, cursor=second.next_cursor)
    assert [item.target_id for item in third.items] == [source.target(originals[0])]
    assert third.next_cursor is None


def test_hidden_candidate_window_returns_continuation_without_large_hydration(source, reader):
    """100件が非公開でも古い公開投稿への継続位置を返し、巨大な一括取得をしない。"""
    visible = source.post(1)
    for i in range(2, 103):
        source.post(i, visibility=PostVisibility.PRIVATE)
    first = reader.read_posts(1)
    assert first.items == ()
    assert first.next_cursor
    assert source.scans == [("post", None, 101)]
    second = reader.read_posts(1, cursor=first.next_cursor)
    assert [item.target_id for item in second.items] == [source.target(visible)]
    assert second.next_cursor is None


@pytest.mark.parametrize("limit", [0, -1, 21, True, "10"])
def test_page_limit_is_validated_before_reading_rows(source, reader, limit):
    """上限外や整数以外の件数でリポジトリ取得を実行しない。"""
    with pytest.raises(PublicSnsInvalidRequestError):
        reader.read_posts(1, limit=limit)
    assert not source.scans


@pytest.mark.parametrize("binding", ["viewer", "scope", "view", "target"])
def test_cursor_cannot_be_reused_for_another_query(source, reader, binding):
    """閲覧者・保存領域・一覧種類・選択対象の違う継続位置は受け付けない。"""
    root = source.post(1)
    other = source.post(2)
    source.reply(1, root)
    source.reply(2, root)
    cursor = reader.read_target(1, source.target(root), limit=1).replies.next_cursor
    with pytest.raises(PublicSnsInvalidRequestError):
        if binding == "viewer":
            reader.read_target(2, source.target(root), cursor=cursor)
        elif binding == "scope":
            source.namespace = uuid4().hex
            reader.read_target(1, source.target(root), cursor=cursor)
        elif binding == "view":
            reader.read_posts(1, cursor=cursor)
        else:
            reader.read_target(1, source.target(other), cursor=cursor)


@pytest.mark.parametrize("cursor", ["broken", "sns-page:%%%", "sns-page:W10=", "x" * 3000])
def test_malformed_cursors_fail_without_reading_candidates(source, reader, cursor):
    """壊れた継続位置を候補照会へ渡さない。"""
    with pytest.raises(PublicSnsInvalidRequestError):
        reader.read_posts(1, cursor=cursor)
    assert not source.scans


def test_notice_uses_current_visible_body_instead_of_saved_body(source, reader):
    """通知の保存済み本文を露出せず、現在の返信全文と不変IDを返す。"""
    root = source.post()
    reply = source.reply(1, root)
    source.notification(related_reply_id=1)
    notice = reader.read_notifications(1).items[0]
    assert notice.content == reply.content
    assert notice.target_id == source.target(reply)
    assert "秘密" not in str(notice)


def test_notice_disappears_after_ancestor_becomes_private(source, reader):
    """取得後に根投稿が非公開になれば次の通知取得や配送でも返信本文を出さない。"""
    root = source.post()
    source.reply(1, root)
    notice = source.notification(related_reply_id=1)
    assert reader.visible_notification(1, notice) is not None
    source.replace(root, visibility=PostVisibility.PRIVATE)
    assert reader.visible_notification(1, notice) is None
    assert reader.read_notifications(1).items == ()


@pytest.mark.parametrize(
    "reason", ["actor_block", "viewer_block", "missing_actor", "missing_target", "expired", "wrong_owner"]
)
def test_unsafe_notifications_are_omitted(source, reader, reason):
    """期限・所有者・双方のブロック・対象欠落の通知を本文も件数も含めず除外する。"""
    root = source.post()
    source.reply(1, root)
    notice = source.notification(
        related_reply_id=1,
        viewer=2 if reason == "wrong_owner" else 1,
        expires_at=NOW - timedelta(seconds=1) if reason == "expired" else None,
    )
    if reason == "actor_block":
        source.users[3].block(UserId(1))
    elif reason == "viewer_block":
        source.users[1].block(UserId(3))
    elif reason == "missing_actor":
        del source.users[3]
    elif reason == "missing_target":
        del source.records[("reply", 1)]
    assert reader.visible_notification(1, notice) is None
    assert reader.read_notifications(1).items == ()


@pytest.mark.parametrize("kind", [NotificationType.FOLLOW, NotificationType.LIKE])
def test_follow_and_like_do_not_include_stored_or_target_body(source, reader, kind):
    """フォローといいねの通知には本文を付けず、参照先は現在見えるときだけ付ける。"""
    source.post()
    source.notification(kind, related_post_id=1 if kind is NotificationType.LIKE else None)
    assert reader.read_notifications(1).items[0].content is None


@pytest.mark.parametrize("party", ["actor", "recipient"])
def test_reused_user_integer_does_not_rebind_old_notice(source, reader, party):
    """同じ利用者整数を新アカウントが使っても通知を引き継がない。"""
    source.post()
    source.notification(NotificationType.MENTION, related_post_id=1)
    replaced_id = 3 if party == "actor" else 1
    source.users[replaced_id] = UserAggregate.create_new_user(UserId(replaced_id), "other", "新人物", "")
    assert reader.read_notifications(1).items == ()


def test_reused_content_integer_does_not_rebind_old_notice(source, reader):
    """参照先の整数が再利用されても通知から新投稿へ飛ばない。"""
    source.post()
    source.notification(NotificationType.MENTION, related_post_id=1)
    source.post()
    assert reader.read_notifications(1).items == ()


def test_legacy_notification_without_immutable_identity_is_not_exposed(source, reader):
    """旧整数だけの通知は旧画面へ残し、新しい公開入口からは除外する。"""
    source.notifications.append(
        Notification(
            NotificationId(1),
            UserId(1),
            NotificationType.FOLLOW,
            NotificationContent.create_follow_notification(UserId(2), "人物2"),
            NOW,
        )
    )
    assert reader.read_notifications(1).items == ()


def test_selected_thread_ancestors_are_root_first_and_complete(source, reader):
    """枝の返信を選んだとき、根から親までの文脈が全文で得られる。"""
    root = source.post()
    parent = source.reply(1, root)
    selected = source.reply(2, parent)
    thread = reader.read_target(1, source.target(selected))
    assert [row.target_id for row in thread.ancestors] == [source.target(root), source.target(parent)]
    assert [row.content for row in thread.ancestors] == [root.content, parent.content]


@pytest.mark.parametrize("which", ["root_author", "parent_author", "selected_author"])
def test_replaced_author_account_hides_old_content(source, reader, which):
    """同じ作者整数に別アカウントが入っても過去投稿の作者として扱わない。"""
    root = source.post(author=2)
    parent = source.reply(1, root, author=3)
    selected = source.reply(2, parent, author=4)
    replaced_id = {"root_author": 2, "parent_author": 3, "selected_author": 4}[which]
    source.users[replaced_id] = UserAggregate.create_new_user(UserId(replaced_id), "other", "別作者", "")
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(selected))


@pytest.mark.parametrize("which", ["root", "parent"])
def test_replaced_parent_never_adopts_existing_reply(source, reader, which):
    """根または親の整数が再利用されても既存返信を新スレッドへ接続しない。"""
    root = source.post()
    parent = source.reply(1, root)
    selected = source.reply(2, parent)
    if which == "root":
        source.post()
    else:
        source.reply(1, root)
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(selected))


@pytest.mark.parametrize("missing", ["author", "parent"])
def test_unbound_legacy_content_is_hidden_in_public_reader(source, reader, missing):
    """作者または親の不変識別子を持たない旧データを読取り時に補完しない。"""
    root = source.post()
    selected = source.reply(1, root)
    source.replace(selected, **{missing + "_identity_token": None})
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, source.target(selected))


@pytest.mark.parametrize("before", [True, 0, -1, 2**63, "1", None])
def test_cursor_rejects_invalid_or_unrepresentable_integer(source, reader, before):
    """継続位置をSQLiteへ渡す前に整数の型と範囲を検査する。"""
    data = [[source.namespace, source.users[1].identity_token, "posts", None], before]
    cursor = "sns-page:" + base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(PublicSnsInvalidRequestError):
        reader.read_posts(1, cursor=cursor)
    assert not source.scans


def test_visibility_is_rechecked_after_successful_read(source, reader):
    """一度読めた不変IDでも後のブロックを毎回調べ、保存済み許可を使い回さない。"""
    record = source.post()
    target = source.target(record)
    assert reader.read_target(1, target).selected.content == record.content
    source.users[2].block(UserId(1))
    with pytest.raises(PublicSnsUnavailableError):
        reader.read_target(1, target)
    assert reader.read_posts(1).items == ()


def test_notification_integer_link_cannot_override_immutable_target(source, reader):
    """通知の整数参照が別投稿を指しても不変参照を優先して矛盾を拒む。"""
    source.post(1)
    source.post(2)
    notice = source.notification(NotificationType.MENTION, related_post_id=1)
    notice._content = replace(notice.content, related_post_id=PostId(2))
    assert reader.visible_notification(1, notice) is None


def test_notification_optional_root_must_match_reply_ancestry(source, reader):
    """返信通知に根投稿も記録する場合、別の公開投稿の根を混ぜられない。"""
    root = source.post(1)
    source.post(2)
    source.reply(1, root)
    notice = source.notification(related_reply_id=1)
    notice._content = replace(notice.content, related_post_id=PostId(2))
    assert reader.visible_notification(1, notice) is None


def test_notification_identity_is_stable_and_read_does_not_mark_it(source, reader):
    """再取得しても通知IDは同じで、読取り自体で既読へ変更しない。"""
    source.post()
    notice = source.notification(NotificationType.LIKE, related_post_id=1)
    first = reader.read_notifications(1).items[0]
    second = reader.read_notifications(1).items[0]
    assert first.notification_id == second.notification_id
    assert first.actor_target_id == f"sns:{source.namespace}:user:{source.users[3].identity_token}"
    assert notice.is_read is False


def test_notification_hidden_window_can_continue_to_older_visible_notice(source, reader):
    """非公開対象の通知が100件続いても古い公開通知への継続位置を失わない。"""
    visible = source.post(1)
    source.notification(NotificationType.MENTION, related_post_id=1)
    source.post(2, visibility=PostVisibility.PRIVATE)
    for _ in range(101):
        source.notification(NotificationType.MENTION, related_post_id=2)
    first = reader.read_notifications(1)
    assert first.items == ()
    assert first.next_cursor is not None
    second = reader.read_notifications(1, cursor=first.next_cursor)
    assert [row.target_id for row in second.items] == [source.target(visible)]
    assert second.next_cursor is None


def test_reused_viewer_integer_cannot_continue_previous_account_page(source, reader):
    """同じ閲覧者整数を再利用した新アカウントへ以前の継続位置を引き継がない。"""
    source.post(1)
    source.post(2)
    cursor = reader.read_posts(1, limit=1).next_cursor
    source.users[1] = UserAggregate.create_new_user(UserId(1), "other", "新閲覧者", "")
    with pytest.raises(PublicSnsInvalidRequestError):
        reader.read_posts(1, cursor=cursor)
