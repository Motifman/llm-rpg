"""SnsObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.sns_formatter import (
    SnsObservationFormatter,
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
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context(
    sns_user_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=None,
        item_repository=None,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=sns_user_repository,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestSnsObservationFormatterCreation:
    """SnsObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる。"""
        ctx = _make_context()
        formatter = SnsObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = SnsObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestSnsObservationFormatterPostCreated:
    """SnsPostCreatedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """投稿作成は prose と structured を返す。"""
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent("こんにちは世界"),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "投稿しました" in out.prose
        assert out.structured.get("type") == "sns_post_created"
        assert out.structured.get("post_id_value") == 1
        assert out.observation_category == "social"
        assert out.schedules_turn is True

    def test_content_preview_truncates_long_content(self, formatter):
        """長いコンテンツは50文字で切り詰められる。"""
        long_content = "a" * 60
        event = SnsPostCreatedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            post_id=PostId(1),
            author_user_id=UserId(1),
            content=PostContent(long_content),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "..." in out.prose
        assert out.structured.get("content_preview") == "a" * 50 + "..."


class TestSnsObservationFormatterReplyCreated:
    """SnsReplyCreatedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """リプライ作成は prose と structured を返す。"""
        event = SnsReplyCreatedEvent.create(
            aggregate_id=ReplyId(1),
            aggregate_type="ReplyAggregate",
            reply_id=ReplyId(1),
            author_user_id=UserId(1),
            content=PostContent("リプライです"),
            parent_post_id=PostId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "リプライしました" in out.prose
        assert out.structured.get("type") == "sns_reply_created"
        assert out.structured.get("reply_id_value") == 1
        assert out.structured.get("parent_post_id_value") == 1
        assert out.observation_category == "social"


class TestSnsObservationFormatterContentLiked:
    """SnsContentLikedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """いいねは prose と structured を返す。"""
        event = SnsContentLikedEvent.create(
            aggregate_id=PostId(1),
            aggregate_type="PostAggregate",
            target_id=PostId(1),
            user_id=UserId(2),
            content_author_id=UserId(1),
            content_type="post",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "いいね" in out.prose
        assert out.structured.get("type") == "sns_content_liked"
        assert out.structured.get("target_id_value") == 1
        assert out.structured.get("content_type") == "post"
        assert out.observation_category == "social"


class TestSnsObservationFormatterUserFollowed:
    """SnsUserFollowedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """フォローは prose と structured を返す。"""
        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "フォロー" in out.prose
        assert out.structured.get("type") == "sns_user_followed"
        assert out.observation_category == "social"

    def test_uses_sns_user_repository_for_display_names(self):
        """sns_user_repository があれば表示名を解決する。"""
        sns_repo = MagicMock()
        follower_info = {"display_name": "Alice"}
        followee_info = {"display_name": "Bob"}
        sns_repo.find_by_id.side_effect = [
            MagicMock(get_user_profile_info=lambda: follower_info),
            MagicMock(get_user_profile_info=lambda: followee_info),
        ]
        ctx = _make_context(sns_user_repository=sns_repo)
        formatter = SnsObservationFormatter(ctx)
        event = SnsUserFollowedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            follower_user_id=UserId(1),
            followee_user_id=UserId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Alice" in out.prose
        assert "Bob" in out.prose


class TestSnsObservationFormatterUserSubscribed:
    """SnsUserSubscribedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """サブスクライブは prose と structured を返す。"""
        event = SnsUserSubscribedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            subscriber_user_id=UserId(1),
            subscribed_user_id=UserId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "サブスクライブ" in out.prose
        assert out.structured.get("type") == "sns_user_subscribed"
        assert out.observation_category == "social"


class TestSnsObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return SnsObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""
        class UnknownEvent:
            pass
        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self, formatter):
        """Harvest イベントは None。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None
