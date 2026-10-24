"""作者限定の本文は、既に宛先を持つイベントを再配送しても他者へ通知しない。"""

from contextlib import nullcontext
from itertools import count
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.recipient_strategies.sns_recipient_strategy import (
    SnsRecipientStrategy,
)
from ai_rpg_world.application.social.services.notification_event_handler_service import (
    NotificationEventHandlerService,
)
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.event import SnsPostCreatedEvent, SnsReplyCreatedEvent
from ai_rpg_world.domain.sns.value_object import NotificationId, PostContent, PostId, ReplyId, UserId


def _event(kind: str, visibility: PostVisibility, *, self_reply: bool = False):
    content = PostContent.create("作者だけの本文", visibility)
    if kind == "post":
        return SnsPostCreatedEvent.create(
            aggregate_id=PostId(1), aggregate_type="PostAggregate", post_id=PostId(1),
            author_user_id=UserId(1), author_display_name="作者", content=content,
            mentioned_user_ids=frozenset({UserId(2)}),
            subscriber_user_ids=frozenset({UserId(3)}),
        )
    return SnsReplyCreatedEvent.create(
        aggregate_id=ReplyId(1), aggregate_type="ReplyAggregate", reply_id=ReplyId(1),
        author_user_id=UserId(1), author_display_name="作者", content=content,
        parent_post_id=PostId(1), parent_author_id=UserId(1) if self_reply else UserId(3),
        mentioned_user_ids=frozenset({UserId(2)}),
    )


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_private_event_with_existing_targets_has_no_observation_recipients(kind: str) -> None:
    """宛先付きの作者限定投稿・返信を受け取っても、観測を配信する相手はゼロになる。"""
    event = _event(kind, PostVisibility.PRIVATE)
    assert SnsRecipientStrategy(MagicMock()).resolve(event) == []


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_private_event_with_existing_targets_creates_no_persistent_notifications(kind: str) -> None:
    """過去と同じ宛先付きの作者限定イベントを再配送しても、通知行と本文を保存しない。"""
    repository = MagicMock()
    factory = MagicMock()
    factory.create.side_effect = lambda: nullcontext()
    handler = NotificationEventHandlerService(MagicMock(), repository, factory)
    event = _event(kind, PostVisibility.PRIVATE)

    getattr(handler, f"handle_{kind}_created")(event)
    getattr(handler, f"handle_{kind}_created")(event)

    repository.save.assert_not_called()
    repository.generate_notification_id.assert_not_called()


def test_private_self_reply_does_not_wake_author_or_mentioned_user() -> None:
    """自分への作者限定返信は、本人にもメンション先にも観測を送らない。"""
    event = _event("reply", PostVisibility.PRIVATE, self_reply=True)
    assert SnsRecipientStrategy(MagicMock()).resolve(event) == []


def test_private_self_reply_does_not_save_mention_notification() -> None:
    """作者限定の自己返信からも、メンション先への永続通知は作られない。"""
    repository = MagicMock()
    factory = MagicMock()
    factory.create.side_effect = lambda: nullcontext()
    handler = NotificationEventHandlerService(MagicMock(), repository, factory)
    handler.handle_reply_created(_event("reply", PostVisibility.PRIVATE, self_reply=True))
    repository.save.assert_not_called()


@pytest.mark.parametrize("kind", ["post", "reply"])
@pytest.mark.parametrize("visibility", [PostVisibility.PUBLIC, PostVisibility.FOLLOWERS_ONLY])
def test_non_private_events_keep_existing_observation_targets(kind: str, visibility: PostVisibility) -> None:
    """公開・フォロワー限定の配信先は、この限定修正では従来どおりに保つ。"""
    event = _event(kind, visibility)
    assert {user.value for user in SnsRecipientStrategy(MagicMock()).resolve(event)} == {2, 3}


@pytest.mark.parametrize("kind", ["post", "reply"])
@pytest.mark.parametrize("visibility", [PostVisibility.PUBLIC, PostVisibility.FOLLOWERS_ONLY])
def test_non_private_events_keep_existing_persistent_notifications(kind: str, visibility: PostVisibility) -> None:
    """公開・フォロワー限定では、メンション先と購読者または親作者への通知を維持する。"""
    repository = MagicMock()
    ids = count(1)
    repository.generate_notification_id.side_effect = lambda: NotificationId(next(ids))
    factory = MagicMock()
    factory.create.side_effect = lambda: nullcontext()
    handler = NotificationEventHandlerService(MagicMock(), repository, factory)
    getattr(handler, f"handle_{kind}_created")(_event(kind, visibility))
    assert {call.args[0].user_id.value for call in repository.save.call_args_list} == {2, 3}
    assert repository.save.call_count == 2
