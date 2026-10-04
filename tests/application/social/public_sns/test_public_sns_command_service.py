"""公開SNSの投稿・親更新・通知が両保存方式で一度に確定することを検査する。"""
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.common.exceptions import CommandPostCommitException, CommandScopeStateException
from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance, execution_provenance_scope
from ai_rpg_world.application.social.public_sns.command_service import PublicSnsCommandService
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsInvalidRequestError, PublicSnsUnavailableError
from ai_rpg_world.application.social.public_sns.notification_delivery import PublicSnsNotificationDeliveryError
from ai_rpg_world.application.social.public_sns.notification_events import (
    PublicSnsActivityEvent,
    PublicSnsNotificationReadyEvent,
)
from ai_rpg_world.application.social.public_sns.read_service import PublicSnsReadService
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.event.post_event import SnsContentLikedEvent
from ai_rpg_world.domain.sns.event.sns_user_event import SnsUserFollowedEvent
from ai_rpg_world.domain.sns.value_object.post_content import PostContent
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_public_sns_read_repository import InMemoryPublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import (
    InMemorySnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_public_sns_read_repository import SqlitePublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import SqliteSnsNotificationRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository
from ai_rpg_world.infrastructure.social.public_sns_factory import (
    create_in_memory_public_sns_command_service,
    create_sqlite_public_sns_command_service,
)


@pytest.fixture(params=["memory", "sqlite"])
def h(request, tmp_path):
    """両保存方式に同じコマンド仕様を適用する。"""
    deliveries = []
    connection = None
    if request.param == "memory":
        store = InMemoryDataStore()
        store.sns_users.clear(); store.sns_username_to_user_id.clear()
        store.posts.clear(); store.replies.clear(); store.sns_notifications.clear()
        store.next_post_id = store.next_reply_id = store.next_sns_notification_id = 1
        repos = [cls(store) for cls in (InMemoryPostRepository, InMemoryReplyRepository, InMemorySnsUserRepository, InMemorySnsNotificationRepository)]
        read = InMemoryPublicSnsReadRepository(store)
        create = lambda deliver: create_in_memory_public_sns_command_service(store, deliver_notification=deliver)
    else:
        path = tmp_path / "game.sqlite3"
        connection = sqlite3.connect(path)
        repos = [cls.for_standalone_connection(connection) for cls in (SqlitePostRepository, SqliteReplyRepository, SqliteSnsUserRepository, SqliteSnsNotificationRepository)]
        read = SqlitePublicSnsReadRepository(connection)
        create = lambda deliver: create_sqlite_public_sns_command_service(path, deliver_notification=deliver)
    posts, replies, users, notifications = repos
    for number in (1, 2, 3, 4):
        users.save(UserAggregate.create_new_user(UserId(number), f"user{number}", f"User{number}", ""))
    result = SimpleNamespace(posts=posts, replies=replies, users=users, notifications=notifications,
                             read=read, create=create, deliveries=deliveries, connection=connection)
    result.service = create(lambda *args: deliveries.append(args))
    yield result
    if connection is not None:
        connection.close()


def get_post(h, dto):
    row = h.read.find_content("post", dto.target_id.rsplit(":", 1)[1])
    return h.posts.find_by_id(PostId(row.local_id))


def get_reply(h, dto):
    row = h.read.find_content("reply", dto.target_id.rsplit(":", 1)[1])
    return h.replies.find_by_id(ReplyId(row.local_id))


def test_public_post_reply_nested_reply_and_notifications_are_committed(h):
    """投稿と返信と孫返信は公開で保存され、直接の親だけの返信数と本文付き通知が確定する。"""
    post = h.service.publish(1, "公開投稿")
    reply = h.service.publish(2, "返信全文", post.target_id)
    nested = h.service.publish(3, "孫返信全文", reply.target_id)
    assert get_post(h, post).get_reply_count() == 1
    assert get_reply(h, reply).get_reply_count() == 1
    assert get_reply(h, nested).content.visibility is PostVisibility.PUBLIC
    assert [(recipient, dto.content, dto.target_id) for recipient, dto, _ in h.deliveries] == [
        (1, "返信全文", reply.target_id), (2, "孫返信全文", nested.target_id)]
    assert len(h.notifications.find_all()) == 2
    assert all(n.observation_delivered for n in h.notifications.find_all())


def test_mention_and_reply_to_same_person_create_one_notice_and_self_is_excluded(h):
    """返信先への同時メンションは重複せず、自分自身には届かない。"""
    post = h.service.publish(1, "@user1 自分へのメンション")
    h.service.publish(2, "@user1 @user2 返信", post.target_id)
    assert len(h.deliveries) == 1
    assert h.deliveries[0][0] == 1
    assert h.deliveries[0][1].kind == "reply"


@pytest.mark.parametrize("visibility", [PostVisibility.PRIVATE, PostVisibility.FOLLOWERS_ONLY])
def test_nonpublic_target_is_indistinguishable_from_unknown_even_for_author(h, visibility):
    """本人やフォロワーにも公開以外は存在しない対象と同じ失敗になり、返信は保存されない。"""
    post = h.service.publish(1, "本文")
    aggregate = get_post(h, post)
    aggregate._content = PostContent.create("秘密", visibility)
    h.posts.save(aggregate)
    with pytest.raises(PublicSnsUnavailableError) as error:
        h.service.publish(1, "応答", post.target_id)
    with pytest.raises(PublicSnsUnavailableError) as unknown:
        h.service.publish(1, "応答", "sns:unknown")
    assert str(error.value) == str(unknown.value)
    assert not h.replies.find_all()


@pytest.mark.parametrize("blocker,blocked", [(1, 3), (3, 1)])
def test_blocked_ancestor_rejects_nested_reply_in_both_directions(h, blocker, blocked):
    """直接の親と交流できても、祖先の作者との双方向ブロックがあれば返信できない。"""
    post = h.service.publish(1, "根")
    reply = h.service.publish(2, "親", post.target_id)
    user = h.users.find_by_id(UserId(blocker)); user.block(UserId(blocked)); h.users.save(user)
    with pytest.raises(PublicSnsUnavailableError):
        h.service.publish(3, "漏らさない", reply.target_id)
    assert get_reply(h, reply).get_reply_count() == 0


def test_mention_recipient_must_see_every_ancestor(h):
    """投稿者には見える返信でもメンション先が祖先にブロックされていれば通知本文を漏らさない。"""
    post = h.service.publish(1, "根")
    reply = h.service.publish(2, "親", post.target_id)
    user = h.users.find_by_id(UserId(1)); user.block(UserId(4)); h.users.save(user)
    h.service.publish(3, "@user4 宛先が読めない返信", reply.target_id)
    assert all(recipient != 4 for recipient, _, _ in h.deliveries)
    assert not h.notifications.find_by_user_id(UserId(4))


def test_sync_failure_rolls_back_reply_parent_count_notification_and_delivery(h):
    """通知を保存した後の同期処理失敗でも返信と親と通知をすべて元に戻す。"""
    post = h.service.publish(1, "根")
    dispatcher = h.service._scope_factory._sync_dispatcher
    original = dispatcher.dispatch
    def fail_after_notice(event, context):
        original(event, context)
        if isinstance(event, PublicSnsNotificationReadyEvent):
            raise RuntimeError("通知後の失敗")
    dispatcher.dispatch = fail_after_notice
    with pytest.raises(RuntimeError, match="通知後"):
        h.service.publish(2, "応答", post.target_id)
    assert get_post(h, post).get_reply_count() == 0
    assert not h.replies.find_all()
    assert not h.notifications.find_all()
    assert not h.deliveries


def test_commit_failure_never_delivers_and_rolls_back_all_state(h):
    """確定処理の失敗は通知を外へ渡さず、保存済みに見える作業中の変更も破棄する。"""
    post = h.service.publish(1, "根")
    factory = h.service._scope_factory._transaction_factory
    original = factory.create
    def create_failed():
        transaction = original()
        def fail(): raise RuntimeError("commit失敗")
        transaction.commit = fail
        return transaction
    factory.create = create_failed
    with pytest.raises(RuntimeError, match="commit失敗"):
        h.service.publish(2, "応答", post.target_id)
    assert get_post(h, post).get_reply_count() == 0
    assert not h.replies.find_all()
    assert not h.notifications.find_all()
    assert not h.deliveries


def test_callback_sees_committed_reply_and_notice(h):
    """外部配送を呼ぶ時点では返信と親更新と永続通知がすべて読める。"""
    post = h.service.publish(1, "根")
    checked = []
    def deliver(recipient, dto, provenance):
        assert get_post(h, post).get_reply_count() == 1
        assert h.read.find_content("reply", dto.target_id.rsplit(":", 1)[1]) is not None
        assert len(h.notifications.find_all()) == 1
        checked.append(dto)
    h.create(deliver).publish(2, "確定後", post.target_id)
    assert len(checked) == 1


def test_delivery_failure_is_committed_and_retries_with_original_provenance(h):
    """配送失敗を投稿失敗と誤認させず、再作成したサービスでも保存済み出典で再送できる。"""
    post = h.service.publish(1, "根")
    provenance = ExecutionProvenance("request-one", 2, 9, "call-one", "llm-one")
    def fail(*args): raise RuntimeError("配送先停止")
    with execution_provenance_scope(provenance):
        with pytest.raises(CommandPostCommitException) as error:
            h.create(fail).publish(2, "保留中の全文", post.target_id)
    assert error.value.result.target_id.startswith("sns:")
    assert get_post(h, post).get_reply_count() == 1
    assert len(h.notifications.find_all()) == 1
    assert not h.notifications.find_all()[0].observation_delivered
    assert h.service.retry_pending_notifications() == 1
    assert h.service.retry_pending_notifications() == 0
    assert h.deliveries[0][1].content == "保留中の全文"
    assert h.deliveries[0][2] == provenance


def test_visibility_is_rechecked_before_delayed_delivery(h):
    """配送保留中に根が非公開になった場合、保存済み本文を外部へ渡さない。"""
    post = h.service.publish(1, "根")
    no_delivery = h.create(None)
    no_delivery.publish(2, "後から秘密", post.target_id)
    aggregate = get_post(h, post); aggregate._content = PostContent.create("秘密", PostVisibility.PRIVATE); h.posts.save(aggregate)
    assert h.service.retry_pending_notifications() == 0
    assert not h.deliveries


def test_replayed_event_cannot_duplicate_notification(h):
    """同じ受信イベントを別の確定境界へ再投入しても通知は一件だけである。"""
    post = h.service.publish(1, "根")
    actor = h.users.find_by_id(UserId(2)); recipient = h.users.find_by_id(UserId(1))
    event = PublicSnsActivityEvent.create(aggregate_id=post.target_id, aggregate_type="PublicSnsActivity",
        actor_user_id=2, actor_identity_token=actor.identity_token, target_id=post.target_id,
        recipients=((1, recipient.identity_token, "like"),))
    h.service.record_activity(event); h.service.record_activity(event)
    assert len(h.notifications.find_all()) == len(h.deliveries) == 1


def test_domain_follow_and_like_events_create_incoming_notifications(h):
    """実際の集約から発生したフォローといいねを既存イベント型のまま受信できる。"""
    post = h.service.publish(1, "根")
    actor = h.users.find_by_id(UserId(2)); recipient = h.users.find_by_id(UserId(1))
    actor.follow(recipient.user_id, followee_identity_token=recipient.identity_token)
    follow = next(e for e in actor.get_events() if isinstance(e, SnsUserFollowedEvent))
    aggregate = get_post(h, post)
    aggregate.like_post(actor.user_id, liker_identity_token=actor.identity_token)
    like = next(e for e in aggregate.get_events() if isinstance(e, SnsContentLikedEvent))
    h.service.record_event(follow); h.service.record_event(like); h.service.record_event(like)
    assert [dto.kind for _, dto, _ in h.deliveries] == ["follow", "like"]
    assert h.deliveries[1][1].target_id == post.target_id
    aggregate.clear_events(); aggregate.like_post(actor.user_id, liker_identity_token=actor.identity_token)
    h.service.record_event(aggregate.get_events()[0])
    assert len(h.deliveries) == 2


@pytest.mark.parametrize("replacement", ["actor", "recipient", "target"])
def test_actual_domain_event_cannot_rebind_reused_identifiers(h, replacement):
    """発生後に人または投稿が同じ整数IDで置き換わっても旧いいねを新しい対象へ通知しない。"""
    post = h.service.publish(1, "根")
    actor = h.users.find_by_id(UserId(2)); aggregate = get_post(h, post)
    aggregate.like_post(actor.user_id, liker_identity_token=actor.identity_token)
    event = next(e for e in aggregate.get_events() if isinstance(e, SnsContentLikedEvent))
    if replacement == "target":
        author = h.users.find_by_id(UserId(1))
        h.posts.save(PostAggregate.create(aggregate.post_id, author.user_id, PostContent.create("別物"), author_identity_token=author.identity_token))
    else:
        number = 2 if replacement == "actor" else 1
        h.users.save(UserAggregate.create_new_user(UserId(number), f"other{number}", f"Other{number}", ""))
    h.service.record_event(event)
    assert not h.notifications.find_all()
    assert not h.deliveries


def test_closed_scoped_repositories_reject_reads_and_writes(h):
    """閉じた確定境界のリポジトリは採番も保存も読取も許さない。"""
    with h.service._scope_factory.create() as context:
        repos = context.repositories
    with pytest.raises(CommandScopeStateException): repos.posts.generate_post_id()
    with pytest.raises(CommandScopeStateException): repos.read.find_user(1)


@pytest.mark.parametrize("body", ["", "   ", "x" * 281, 3, " ".join(f"#tag{i}" for i in range(11))])
def test_invalid_content_does_not_create_state(h, body):
    """空や長過ぎる本文、文字列でない入力は確定境界を開かずに拒否する。"""
    with pytest.raises(PublicSnsInvalidRequestError): h.service.publish(1, body)
    assert not h.posts.find_all()


def test_duplicate_display_names_do_not_misdirect_mentions(h):
    """同じ表示名の人が複数いても、表示名だけをメンション宛先へ変換しない。"""
    for number in (2, 3):
        user = h.users.find_by_id(UserId(number))
        user.update_user_profile(None, "同名")
        h.users.save(user)
    h.service.publish(1, "@同名 を本文に残す")
    assert not h.notifications.find_all()
    h.service.publish(1, "@user2 一意なアカウント名で呼ぶ")
    assert [recipient for recipient, _, _ in h.deliveries] == [2]


def test_tokenless_legacy_incoming_event_is_not_bound_at_delivery_time(h):
    """古い通知元が整数IDしか持たない場合、今の人物へ結び直して本文を漏らさない。"""
    event = SnsUserFollowedEvent.create(aggregate_id=2, aggregate_type="UserAggregate",
        follower_user_id=UserId(2), followee_user_id=UserId(1))
    h.service.record_event(event)
    assert not h.notifications.find_all()


def test_unknown_source_provenance_is_not_filled_from_later_request(h):
    """出典なしで生まれたイベントを別要求中に受け取っても、その要求の手番を借りない。"""
    actor = h.users.find_by_id(UserId(2)); recipient = h.users.find_by_id(UserId(1))
    actor.follow(recipient.user_id, followee_identity_token=recipient.identity_token)
    event = next(e for e in actor.get_events() if isinstance(e, SnsUserFollowedEvent))
    with execution_provenance_scope(ExecutionProvenance("unrelated", 3, 91)):
        h.service.record_event(event)
    assert h.deliveries[0][2] is None


def test_reply_at_ancestor_limit_is_rejected_before_creating_unreadable_child(h, monkeypatch):
    """読取上限の深さに達した親へ返信して、作成直後から見えない投稿を残さない。"""
    import ai_rpg_world.application.social.public_sns.command_service as module
    monkeypatch.setattr(module, "MAX_PUBLIC_SNS_ANCESTORS", 2)
    post = h.service.publish(1, "根")
    parent = h.service.publish(1, "親", post.target_id)
    with pytest.raises(PublicSnsUnavailableError): h.service.publish(1, "上限外", parent.target_id)
    assert get_reply(h, parent).get_reply_count() == 0


def test_incoming_like_of_private_content_never_creates_notice(h):
    """実際に発生したいいねでも対象が非公開になれば通知を保存も配送もしない。"""
    post = h.service.publish(1, "根")
    actor = h.users.find_by_id(UserId(2)); aggregate = get_post(h, post)
    aggregate.like_post(actor.user_id, liker_identity_token=actor.identity_token)
    event = next(e for e in aggregate.get_events() if isinstance(e, SnsContentLikedEvent))
    aggregate._content = PostContent.create("秘密", PostVisibility.PRIVATE); h.posts.save(aggregate)
    h.service.record_event(event)
    assert not h.notifications.find_all()


def test_foreign_namespace_target_does_not_create_a_reply(h):
    """同じ本文の不変IDでも保存領域の名前空間が違えば別世界として拒否する。"""
    from uuid import uuid4
    post = h.service.publish(1, "根")
    foreign = post.target_id.replace(h.read.namespace, uuid4().hex)
    with pytest.raises(PublicSnsUnavailableError): h.service.publish(2, "別世界", foreign)
    assert not h.replies.find_all()


def test_existing_command_emitters_supply_identity_and_source_metadata():
    """旧サービスの実際のフォロー・いいねも発生時の不変IDと出典を渡せるが、新publishは経由しない。"""
    from ai_rpg_world.application.social.contracts.commands import CreatePostCommand, FollowUserCommand, LikePostCommand
    from ai_rpg_world.application.social.services.post_command_service import PostCommandService
    from ai_rpg_world.application.social.services.user_command_service import UserCommandService
    from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
    store = InMemoryDataStore()
    store.sns_users.clear(); store.sns_username_to_user_id.clear(); store.posts.clear(); store.replies.clear()
    unit_of_work, publisher = InMemoryUnitOfWork.create_with_event_publisher(data_store=store)
    users = InMemorySnsUserRepository(store, unit_of_work)
    posts = InMemoryPostRepository(store, unit_of_work)
    for number in (1, 2):
        users.save(UserAggregate.create_new_user(UserId(number), f"user{number}", f"User{number}", ""))
    post_service = PostCommandService(posts, users, publisher, unit_of_work)
    user_service = UserCommandService(users, publisher, unit_of_work)
    result = post_service.create_post(CreatePostCommand(user_id=1, content="旧入口からの公開投稿", visibility=PostVisibility.PUBLIC))
    post_id = result.data["post_id"]
    provenance = ExecutionProvenance("legacy-request", 2, 3)
    with execution_provenance_scope(provenance):
        post_service.like_post(LikePostCommand(user_id=2, post_id=post_id))
        user_service.follow_user(FollowUserCommand(follower_user_id=2, followee_user_id=1))
    emitted = [e for e in publisher.get_published_events() if isinstance(e, (SnsContentLikedEvent, SnsUserFollowedEvent))]
    assert len(emitted) == 2
    delivered = []
    current = create_in_memory_public_sns_command_service(store, deliver_notification=lambda *args: delivered.append(args))
    for event in emitted: current.record_event(event)
    assert [dto.kind for _, dto, _ in delivered] == ["like", "follow"]
    assert all(source == provenance for _, _, source in delivered)


def test_stale_handle_index_does_not_rebind_a_mention_after_user_replacement(h):
    """同じ整数IDで利用者を入れ替えた後に古いアカウント名が索引へ残っても、新利用者を呼ばない。"""
    h.users.save(UserAggregate.create_new_user(UserId(2), "replacement", "新利用者", ""))
    h.service.publish(1, "@user2 古い相手への言及")
    assert not h.notifications.find_all()


def test_retry_delivery_failure_does_not_block_other_recipients_or_duplicate_success(h):
    """一件の再送が失敗しても後続へ配信し、失敗した相手の復旧後にも成功済みを重ねない。"""
    queued = h.create(None)
    queued.publish(2, "@user1 配送先停止")
    queued.publish(3, "@user4 後続へ届く")
    unavailable = {1}
    delivered = []

    def deliver(recipient, dto, provenance):
        if recipient in unavailable:
            raise RuntimeError("配送先停止")
        delivered.append((recipient, dto.notification_id))

    service = h.create(deliver)
    with pytest.raises(PublicSnsNotificationDeliveryError) as error:
        service.retry_pending_notifications()
    assert error.value.delivered_count == 1
    assert len(error.value.failures) == 1
    assert str(error.value.failures[0][1]) == "配送先停止"
    assert error.value.__cause__ is error.value.failures[0][1]
    assert [recipient for recipient, _ in delivered] == [4]
    assert sorted((n.user_id.value, n.observation_delivered) for n in h.notifications.find_all()) == [(1, False), (4, True)]
    unavailable.clear()
    assert service.retry_pending_notifications() == 1
    assert service.retry_pending_notifications() == 0
    assert [recipient for recipient, _ in delivered] == [4, 1]
    assert len({notification_id for _, notification_id in delivered}) == 2


def test_initial_handoff_attempts_later_recipients_before_reporting_committed_failure(h):
    """初回配送も一人の失敗で後続を止めず、投稿確定済みの例外と再送可能な状態を維持する。"""
    delivered = []
    unavailable = {1}

    def deliver(recipient, dto, provenance):
        if recipient in unavailable:
            raise RuntimeError("先頭の配送先停止")
        delivered.append(dto.notification_id)

    service = h.create(deliver)
    with pytest.raises(CommandPostCommitException) as error:
        service.publish(2, "@user1 @user4 同じ投稿の通知")
    assert error.value.result.target_id.startswith("sns:")
    assert isinstance(error.value.handoff_error, PublicSnsNotificationDeliveryError)
    assert error.value.handoff_error.delivered_count == 1
    assert len(error.value.handoff_error.failures) == 1
    assert len(delivered) == 1
    assert len(h.posts.find_all()) == 1
    assert sorted((n.user_id.value, n.observation_delivered) for n in h.notifications.find_all()) == [(1, False), (4, True)]
    unavailable.clear()
    assert service.retry_pending_notifications() == 1
    assert service.retry_pending_notifications() == 0
    assert len(set(delivered)) == len(delivered) == 2


def test_more_than_one_batch_of_failed_notifications_does_not_starve_later_success(h):
    """先頭101件が失敗しても、一度100件までの再送を継続して102件目へ到達し、末尾から再試行へ戻る。"""
    queued = h.create(None)
    for index in range(101):
        queued.publish(2, f"@user1 停止中の宛先 {index}")
    queued.publish(3, "@user4 百件を超えた後続")
    unavailable = {1}
    attempts = []
    delivered = []

    def deliver(recipient, dto, provenance):
        attempts.append(dto.notification_id)
        if recipient in unavailable:
            raise RuntimeError("配送先停止")
        delivered.append(dto.notification_id)

    service = h.create(deliver)
    with pytest.raises(RuntimeError):
        service.retry_pending_notifications()
    assert len(attempts) == 100
    with pytest.raises(RuntimeError):
        service.retry_pending_notifications()
    assert len(attempts) == 102
    assert len(delivered) == 1
    # 末尾から先頭へ戻り、後で復旧した宛先も失わない。
    unavailable.clear()
    assert service.retry_pending_notifications() == 100
    assert service.retry_pending_notifications() == 1
    assert service.retry_pending_notifications() == 0
    assert len(set(delivered)) == len(delivered) == 102


def test_recreated_retry_service_starts_at_head_without_losing_pending_notifications(h):
    """再送位置が失われるサービス再作成後も、保存済み未配送通知から再開して全件を届ける。"""
    queued = h.create(None)
    queued.publish(2, "@user1 一件目")
    queued.publish(3, "@user4 二件目")
    attempts = []

    def fail(recipient, dto, provenance):
        attempts.append(dto.notification_id)
        raise RuntimeError("配送先停止")

    failed_service = h.create(fail)
    with pytest.raises(RuntimeError):
        failed_service.retry_pending_notifications(limit=1)
    delivered = []
    restored_service = h.create(lambda recipient, dto, provenance: delivered.append(dto.notification_id))
    assert restored_service.retry_pending_notifications(limit=1) == 1
    assert delivered == attempts
    assert restored_service.retry_pending_notifications(limit=1) == 1
    assert restored_service.retry_pending_notifications(limit=1) == 0
    assert len(set(delivered)) == 2
