"""利用者の公開状態と、同じ操作で積まれる専用イベントを一緒に守る。"""

import pytest

from ai_rpg_world.domain.sns.aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity import SnsUser
from ai_rpg_world.domain.sns.event import (
    SnsUserBlockedEvent,
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnblockedEvent,
    SnsUserUnfollowedEvent,
    SnsUserUnsubscribedEvent,
)
from ai_rpg_world.domain.sns.exception import (
    CannotFollowBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnfollowNotFollowedUserException,
)
from ai_rpg_world.domain.sns.value_object import UserId, UserProfile


def _user(owner):
    return UserAggregate(owner, SnsUser(owner, UserProfile("testuser", "テストユーザー", "テストです")), [], [], [])


def _seed_other_relationships(aggregate):
    aggregate.follow(UserId(3))
    aggregate.subscribe(UserId(3))
    aggregate.block(UserId(4))


def _relationships(aggregate):
    return (
        tuple((r.follower_user_id, r.followee_user_id) for r in aggregate.follow_relationships),
        tuple((r.blocker_user_id, r.blocked_user_id) for r in aggregate.block_relationships),
        tuple((r.subscriber_user_id, r.subscribed_user_id) for r in aggregate.subscribe_relationships),
    )


def _state(aggregate):
    # getterのlistを参照したままにせず、拒否前の独立した状態を残す。
    return (
        tuple(aggregate.follow_relationships), tuple(aggregate.block_relationships),
        tuple(aggregate.subscribe_relationships), aggregate.profile, aggregate.identity_token,
    )


@pytest.fixture(params=["integers", "mixed", "typed"])
def relationship_case(request):
    owner = UserId(1) if request.param == "typed" else 1
    target = 2 if request.param == "integers" else UserId(2)
    aggregate = _user(owner)
    if request.param == "typed":
        _seed_other_relationships(aggregate)
        assert _relationships(aggregate) == (((owner, UserId(3)),), ((owner, UserId(4)),), ((owner, UserId(3)),))
    else:
        assert _relationships(aggregate) == ((), (), ())
    return aggregate, owner, target, request.param


def _event_prefix(aggregate, case):
    if case == "mixed":
        # 元のイベント行は前提操作後にclearし、単一通知を観測していた。
        aggregate.clear_events()
    return tuple(aggregate.get_events())


def _assert_event(aggregate, prefix, event_type, aggregate_id, **payload):
    events = tuple(aggregate.get_events())
    assert len(events) == len(prefix) + 1
    assert events[:-1] == prefix
    event = events[-1]
    assert isinstance(event, event_type)
    assert event.aggregate_id == aggregate_id
    assert event.aggregate_type == "UserAggregate"
    for name, expected in payload.items():
        assert getattr(event, name) == expected
    return events


class TestUserAggregate:
    """利用者の関係・プロフィール変更と拒否が状態と通知を矛盾させない。"""
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.user_id = 1
        self.user_profile = UserProfile("testuser", "テストユーザー", "テストです")
        self.sns_user = SnsUser(self.user_id, self.user_profile)

        # 空の関係性リストで集約を作成
        self.aggregate = UserAggregate(
            user_id=self.user_id,
            sns_user=self.sns_user,
            follow_relationships=[],
            block_relationships=[],
            subscribe_relationships=[]
        )

    def test_create_user_aggregate_success(self):
        """整数IDと元のSnsUserを公開属性から取得でき、三つの関係は空である。"""
        assert self.aggregate.user_id == self.user_id
        assert self.aggregate.sns_user is self.sns_user
        assert self.aggregate.follow_relationships == []
        assert self.aggregate.block_relationships == []
        assert self.aggregate.subscribe_relationships == []

    @pytest.mark.parametrize("with_others", [False, True])
    def test_follow_blocked_user_raises_error(self, with_others):
        """ブロックした整数2のフォローを専用例外で拒否し、既存の関係と通知を保つ。"""
        if with_others:
            _seed_other_relationships(self.aggregate)
        self.aggregate.block(2)
        before, events = _state(self.aggregate), tuple(self.aggregate.get_events())
        with pytest.raises(CannotFollowBlockedUserException):
            self.aggregate.follow(2)
        assert _state(self.aggregate) == before
        assert tuple(self.aggregate.get_events()) == events

    @pytest.mark.parametrize("with_others", [False, True])
    def test_unfollow_not_followed_user_raises_error(self, with_others):
        """フォローしていない整数2の解除を拒否し、他者の関係や既存通知を消さない。"""
        if with_others:
            _seed_other_relationships(self.aggregate)
        before, events = _state(self.aggregate), tuple(self.aggregate.get_events())
        with pytest.raises(CannotUnfollowNotFollowedUserException):
            self.aggregate.unfollow(2)
        assert _state(self.aggregate) == before
        assert tuple(self.aggregate.get_events()) == events

    @pytest.mark.parametrize("with_others", [False, True])
    def test_subscribe_not_followed_user_raises_error(self, with_others):
        """未フォローの整数2への購読を正しい例外で拒否し、関係と既存通知を保つ。"""
        if with_others:
            _seed_other_relationships(self.aggregate)
        before, events = _state(self.aggregate), tuple(self.aggregate.get_events())
        with pytest.raises(CannotSubscribeNotFollowedUserException):
            self.aggregate.subscribe(2)
        assert _state(self.aggregate) == before
        assert tuple(self.aggregate.get_events()) == events

    @pytest.mark.parametrize("with_others", [False, True])
    def test_block_removes_follow_and_subscribe(self, with_others):
        """ブロックは対象のフォローと購読だけを解除し、三つの通知を解除順に追加する。"""
        owner, target = (UserId(1), UserId(2)) if with_others else (1, 2)
        aggregate = _user(owner)
        if with_others:
            _seed_other_relationships(aggregate)
        follows, blocks, subscriptions = _relationships(aggregate)
        aggregate.follow(target)
        aggregate.subscribe(target)
        prefix = tuple(aggregate.get_events())
        aggregate.block(target)
        assert _relationships(aggregate) == (follows, blocks + ((owner, target),), subscriptions)
        assert not aggregate.is_following(target)
        assert not aggregate.is_subscribed(target)
        assert aggregate.is_blocked(target)
        events = tuple(aggregate.get_events())
        assert len(events) == len(prefix) + 3
        assert events[:-3] == prefix
        for event, event_type, fields in zip(events[-3:], (
            SnsUserUnfollowedEvent, SnsUserUnsubscribedEvent, SnsUserBlockedEvent,
        ), (("follower_user_id", "followee_user_id"),
            ("subscriber_user_id", "subscribed_user_id"), ("blocker_user_id", "blocked_user_id")), strict=True):
            assert isinstance(event, event_type)
            assert event.aggregate_id == owner
            assert event.aggregate_type == "UserAggregate"
            assert getattr(event, fields[0]) == owner
            assert getattr(event, fields[1]) == target

    def test_create_new_user_generates_event(self):
        """新規利用者は指定プロフィールと空の関係を持ち、全入力を作成通知に一件残す。"""
        user_id = UserId(1)
        aggregate = UserAggregate.create_new_user(user_id, "testuser", "テストユーザー", "テストです")
        assert aggregate.user_id == user_id
        assert aggregate.profile == UserProfile("testuser", "テストユーザー", "テストです")
        assert _relationships(aggregate) == ((), (), ())
        _assert_event(aggregate, (), SnsUserCreatedEvent, user_id, user_id=user_id,
                      user_name="testuser", display_name="テストユーザー", bio="テストです")

    def test_follow_generates_event(self, relationship_case):
        """フォローは指定した両端点を一件追加し、既存通知を保って専用イベントを一件積む。"""
        aggregate, owner, target, case = relationship_case
        follows, blocks, subscriptions = _relationships(aggregate)
        prefix = _event_prefix(aggregate, case)
        aggregate.follow(target)
        assert _relationships(aggregate) == (follows + ((owner, target),), blocks, subscriptions)
        assert aggregate.is_following(target)
        _assert_event(aggregate, prefix, SnsUserFollowedEvent, int(owner),
                      follower_user_id=owner, followee_user_id=target)

    def test_unfollow_generates_event(self, relationship_case):
        """フォロー解除は対象だけを取り除き、他者の関係と通知を保って解除を一件知らせる。"""
        aggregate, owner, target, case = relationship_case
        before = _relationships(aggregate)
        aggregate.follow(target)
        prefix = _event_prefix(aggregate, case)
        aggregate.unfollow(target)
        assert _relationships(aggregate) == before
        assert not aggregate.is_following(target)
        _assert_event(aggregate, prefix, SnsUserUnfollowedEvent, owner,
                      follower_user_id=owner, followee_user_id=target)

    def test_block_generates_event(self, relationship_case):
        """無関係な対象のブロックは一件だけ追加され、既存関係を消さず専用イベントを積む。"""
        aggregate, owner, target, case = relationship_case
        follows, blocks, subscriptions = _relationships(aggregate)
        prefix = _event_prefix(aggregate, case)
        aggregate.block(target)
        assert _relationships(aggregate) == (follows, blocks + ((owner, target),), subscriptions)
        assert aggregate.is_blocked(target)
        _assert_event(aggregate, prefix, SnsUserBlockedEvent, owner,
                      blocker_user_id=owner, blocked_user_id=target)

    def test_unblock_generates_event(self, relationship_case):
        """ブロック解除は対象だけを取り除き、残る関係と通知を保って専用イベントを積む。"""
        aggregate, owner, target, case = relationship_case
        before = _relationships(aggregate)
        aggregate.block(target)
        prefix = _event_prefix(aggregate, case)
        aggregate.unblock(target)
        assert _relationships(aggregate) == before
        assert not aggregate.is_blocked(target)
        _assert_event(aggregate, prefix, SnsUserUnblockedEvent, owner,
                      blocker_user_id=owner, blocked_user_id=target)

    def test_subscribe_generates_event(self, relationship_case):
        """フォロー済み対象の購読を一件追加し、元のフォローと通知を保って購読を知らせる。"""
        aggregate, owner, target, case = relationship_case
        aggregate.follow(target)
        follows, blocks, subscriptions = _relationships(aggregate)
        prefix = _event_prefix(aggregate, case)
        aggregate.subscribe(target)
        assert _relationships(aggregate) == (follows, blocks, subscriptions + ((owner, target),))
        assert aggregate.is_subscribed(target)
        assert aggregate.is_following(target)
        _assert_event(aggregate, prefix, SnsUserSubscribedEvent, owner,
                      subscriber_user_id=owner, subscribed_user_id=target)

    def test_unsubscribe_generates_event(self, relationship_case):
        """購読解除は対象の購読だけを取り除き、フォローと既存通知を保って解除を知らせる。"""
        aggregate, owner, target, case = relationship_case
        aggregate.follow(target)
        before = _relationships(aggregate)
        aggregate.subscribe(target)
        prefix = _event_prefix(aggregate, case)
        aggregate.unsubscribe(target)
        assert _relationships(aggregate) == before
        assert not aggregate.is_subscribed(target)
        assert aggregate.is_following(target)
        _assert_event(aggregate, prefix, SnsUserUnsubscribedEvent, owner,
                      subscriber_user_id=owner, subscribed_user_id=target)

    @pytest.mark.parametrize("owner,new_bio,new_display_name,expected_bio,expected_name", [
        (1, "新しいbio", "新しい表示名", "新しいbio", "新しい表示名"),
        (UserId(1), "新しいbio", None, "新しいbio", "テストユーザー"),
        (UserId(1), None, "新しい表示名", "テストです", "新しい表示名"),
    ])
    def test_update_profile_generates_event(self, owner, new_bio, new_display_name, expected_bio, expected_name):
        """指定したプロフィール項目だけを更新し、利用者名を保って元の更新入力を一件通知する。"""
        aggregate = _user(owner)
        aggregate.update_user_profile(new_bio, new_display_name)
        assert aggregate.profile.bio == expected_bio
        assert aggregate.profile.display_name == expected_name
        assert aggregate.profile.user_name == "testuser"
        _assert_event(aggregate, (), SnsUserProfileUpdatedEvent, owner,
                      user_id=owner, new_bio=new_bio, new_display_name=new_display_name)

    def test_multiple_events_are_accumulated(self):
        """フォロー・購読・プロフィール更新は各入力の通知を順に一件ずつ積み、先行通知を保つ。"""
        target = UserId(2)
        self.aggregate.follow(target)
        prefix = _assert_event(self.aggregate, (), SnsUserFollowedEvent, 1,
                               follower_user_id=1, followee_user_id=target)
        self.aggregate.subscribe(target)
        prefix = _assert_event(self.aggregate, prefix, SnsUserSubscribedEvent, 1,
                               subscriber_user_id=1, subscribed_user_id=target)
        self.aggregate.update_user_profile("新しいbio", "新しい名前")
        _assert_event(self.aggregate, prefix, SnsUserProfileUpdatedEvent, 1,
                      user_id=1, new_bio="新しいbio", new_display_name="新しい名前")
