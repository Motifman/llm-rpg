"""SQLite SNS notification repository tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import (
    SqliteSnsNotificationRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _notification(notification_id: int, *, user_id: int = 1) -> Notification:
    return Notification.create_persistent_notification(
        notification_id=NotificationId(notification_id),
        user_id=UserId(user_id),
        notification_type=NotificationType.FOLLOW,
        content=NotificationContent.create_follow_notification(
            follower_user_id=UserId(2),
            follower_user_name="mage_user",
        ),
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


def test_notification_repository_roundtrip_and_mark_read() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteSnsNotificationRepository.for_standalone_connection(conn)
    repo.save(_notification(1))

    loaded = repo.find_by_id(NotificationId(1))
    assert loaded is not None
    assert loaded.is_read is False
    assert repo.get_unread_count(UserId(1)) == 1

    with SqliteUnitOfWork(connection=conn) as uow:
        tx_repo = SqliteSnsNotificationRepository.for_shared_unit_of_work(uow.connection)
        tx_repo.mark_as_read(NotificationId(1))

    loaded = repo.find_by_id(NotificationId(1))
    assert loaded is not None
    assert loaded.is_read is True


def test_notification_repository_delete_expired_and_keep_recent() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteSnsNotificationRepository.for_standalone_connection(conn)
    expired = Notification.create_push_notification(
        notification_id=NotificationId(1),
        user_id=UserId(1),
        notification_type=NotificationType.POST,
        content=NotificationContent.create_post_notification(
            author_user_id=UserId(2),
            author_user_name="mage_user",
            content_text="hello",
        ),
        expires_at=datetime(2026, 1, 1, 0, 0, 0),
        created_at=datetime(2025, 12, 31, 23, 0, 0),
    )
    recent = _notification(2)
    repo.save(expired)
    repo.save(recent)

    with SqliteUnitOfWork(connection=conn) as uow:
        tx_repo = SqliteSnsNotificationRepository.for_shared_unit_of_work(uow.connection)
        deleted = tx_repo.delete_expired_notifications(datetime(2026, 1, 2, 0, 0, 0))
        assert deleted == 1

    assert repo.find_by_id(NotificationId(1)) is None
    assert repo.find_by_id(NotificationId(2)) is not None
