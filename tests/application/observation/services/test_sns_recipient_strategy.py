"""SnsRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.sns_recipient_strategy import (
    SnsRecipientStrategy,
)
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId


class TestSnsRecipientStrategyNormal:
    """SnsRecipientStrategy 正常系テスト"""

    def test_post_created_returns_author_only_when_no_extra_ids(self):
        """SnsPostCreatedEvent: メンション・購読者 ID が空なら著者のみ"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(5),
            content=PostContent("テスト投稿"),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_post_created_includes_mentioned_and_subscribers_from_event(self):
        """SnsPostCreatedEvent: イベント上の user_id で配信先を解決する"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentioned_user_ids=frozenset({UserId(3)}),
            subscriber_user_ids=frozenset({UserId(4)}),
        )
        result = strategy.resolve(event)
        assert {p.value for p in result} == {1, 3, 4}

    def test_reply_created_returns_parent_author_only_when_no_mentions(self):
        """SnsReplyCreatedEvent: parent_author_id あり・メンション空なら親作成者のみ"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=UserId(2),
            content=PostContent("リプライ"),
            parent_post_id=PostId(1),
            parent_author_id=UserId(7),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 7

    def test_reply_created_returns_empty_when_no_parent_author_and_no_mentions(self):
        """SnsReplyCreatedEvent: parent_author_id なし・メンション空なら空"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=UserId(2),
            content=PostContent("リプライ"),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_content_liked_returns_content_author(self):
        """SnsContentLikedEvent: コンテンツ著者が配信先"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=UserId(2),
            content_author_id=UserId(4),
            content_type="post",
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 4

    def test_user_followed_returns_followee(self):
        """SnsUserFollowedEvent: フォローされた人が配信先"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(2),
            followee_user_id=UserId(5),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_user_subscribed_returns_subscribed_user(self):
        """SnsUserSubscribedEvent: サブスクライブされた人が配信先"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(3),
            subscribed_user_id=UserId(8),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 8


class TestSnsRecipientStrategyExceptions:
    """SnsRecipientStrategy 境界テスト"""

    def test_post_created_skips_unknown_mention_ids_not_in_event(self):
        """SnsPostCreatedEvent: mentioned_user_ids が空なら著者のみ（コマンド側で解決されなかったメンションは載らない）"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト @unknown"),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_post_created_excludes_author_from_mentioned_user_ids(self):
        """SnsPostCreatedEvent: 著者 ID と同じ mentioned は配信先に重複しない"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentioned_user_ids=frozenset({UserId(1), UserId(2)}),
        )
        result = strategy.resolve(event)
        assert {p.value for p in result} == {1, 2}


class TestSnsRecipientStrategySupports:
    """SnsRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )

    def test_supports_sns_post_created_event(self, strategy):
        """SnsPostCreatedEvent を supports"""
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
        )
        assert strategy.supports(event) is True

    def test_supports_sns_content_liked_event(self, strategy):
        """SnsContentLikedEvent を supports"""
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=UserId(2),
            content_author_id=UserId(1),
            content_type="post",
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
