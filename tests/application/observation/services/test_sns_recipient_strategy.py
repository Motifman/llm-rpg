"""SnsRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.sns_recipient_strategy import (
    SnsRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.domain.sns.value_object.mention import Mention


class TestSnsRecipientStrategyNormal:
    """SnsRecipientStrategy 正常系テスト"""

    def test_post_created_returns_author_only_when_no_repo(self):
        """SnsPostCreatedEvent: リポジトリなしのとき著者のみ"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=None,
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

    def test_post_created_includes_mentions_when_repo_finds_users(self):
        """SnsPostCreatedEvent: メンションされたユーザーがリポジトリで見つかると配信先に含まれる"""
        sns_repo = MagicMock()
        mentioned_user = MagicMock()
        mentioned_user.user_id = UserId(3)
        sns_repo.find_by_display_name.return_value = mentioned_user
        sns_repo.find_subscribers.return_value = []
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=sns_repo,
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentions=frozenset([Mention(mentioned_user_name="alice", post_id=PostId(1))]),
        )
        result = strategy.resolve(event)
        assert len(result) >= 2
        assert any(p.value == 1 for p in result)
        assert any(p.value == 3 for p in result)
        sns_repo.find_by_display_name.assert_called_with("alice")

    def test_reply_created_returns_parent_author_only_when_no_repo(self):
        """SnsReplyCreatedEvent: リポジトリなし・parent_author_id ありなら親作成者のみ"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=None,
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

    def test_reply_created_returns_empty_when_no_parent_author_and_no_repo(self):
        """SnsReplyCreatedEvent: parent_author_id なし・リポジトリなしなら空"""
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=None,
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
            sns_user_repository=None,
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
            sns_user_repository=None,
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
            sns_user_repository=None,
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
    """SnsRecipientStrategy 例外・境界テスト"""

    def test_post_created_skips_mention_when_find_by_display_name_returns_none(self):
        """SnsPostCreatedEvent: メンション先が find_by_display_name で見つからないときスキップ"""
        sns_repo = MagicMock()
        sns_repo.find_by_display_name.return_value = None
        sns_repo.find_subscribers.return_value = []
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=sns_repo,
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentions=frozenset([Mention(mentioned_user_name="unknown", post_id=PostId(1))]),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_post_created_excludes_author_from_mentions(self):
        """SnsPostCreatedEvent: 著者自身がメンションされていても重複して配信先に含めない"""
        sns_repo = MagicMock()
        author_as_user = MagicMock()
        author_as_user.user_id = UserId(1)
        sns_repo.find_by_display_name.return_value = author_as_user
        sns_repo.find_subscribers.return_value = []
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=sns_repo,
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentions=frozenset([Mention(mentioned_user_name="self", post_id=PostId(1))]),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_resolve_propagates_repository_exception(self):
        """resolve: リポジトリが例外を投げた場合、その例外が伝播する"""
        sns_repo = MagicMock()
        sns_repo.find_by_display_name.side_effect = RuntimeError("find failed")
        strategy = SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=sns_repo,
        )
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("テスト"),
            mentions=frozenset([Mention(mentioned_user_name="x", post_id=PostId(1))]),
        )
        with pytest.raises(RuntimeError, match="find failed"):
            strategy.resolve(event)


class TestSnsRecipientStrategySupports:
    """SnsRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return SnsRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            sns_user_repository=None,
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
