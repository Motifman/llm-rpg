"""公開SNS通知の不変参照と再送情報を、本文を切り詰めずに保存する。"""
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import (
    InMemorySnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import SqliteSnsNotificationRepository


@pytest.mark.parametrize("storage", ["memory", "sqlite"])
def test_notification_metadata_survives_save_reload_without_truncation(storage, tmp_path):
    """通知と人と本文の不変ID、全文、発生時出典、配送状態を保存後も完全に保持する。"""
    connection = None
    if storage == "memory":
        repository = InMemorySnsNotificationRepository(InMemoryDataStore())
    else:
        connection = sqlite3.connect(tmp_path / "notifications.sqlite3")
        repository = SqliteSnsNotificationRepository.for_standalone_connection(connection)
    actor_token, recipient_token = uuid4().hex, uuid4().hex
    target = f"sns:{uuid4().hex}:reply:{uuid4().hex}"
    provenance = {"execution_request_id": "request-one", "actor_player_id": 1, "actor_turn": 12}
    notification = Notification(
        notification_id=NotificationId(999), user_id=UserId(2), notification_type=NotificationType.REPLY,
        content=NotificationContent(title="返信", message="届きました", actor_user_id=UserId(1), actor_user_name="一郎",
                                    content_text="全文" * 140, related_target_id=target, actor_identity_token=actor_token),
        created_at=datetime.now(timezone.utc), source_event_id="source-event", recipient_identity_token=recipient_token,
        execution_provenance=provenance,
    )
    repository.save(notification)
    restored = repository.find_by_id(notification.notification_id)
    assert restored.identity_token == notification.identity_token
    assert restored.content.related_target_id == target
    assert restored.content.actor_identity_token == actor_token
    assert restored.content.content_text == "全文" * 140
    assert restored.recipient_identity_token == recipient_token
    assert restored.source_event_id == "source-event"
    assert restored.execution_provenance == provenance
    provenance["actor_turn"] = 99
    assert restored.execution_provenance["actor_turn"] == 12
    restored.mark_observation_delivered(); repository.save(restored)
    assert repository.find_by_id(notification.notification_id).observation_delivered
    if connection is not None:
        connection.close()


def test_sqlite_missing_stored_identity_is_rejected_instead_of_regenerated(tmp_path):
    """破損した保存済み通知に別の不変IDを付け直して正常な通知として返さない。"""
    from ai_rpg_world.domain.sns.exception.identity_token_exception import SnsIdentityValidationException
    connection = sqlite3.connect(tmp_path / "corrupted.sqlite3")
    repository = SqliteSnsNotificationRepository.for_standalone_connection(connection)
    notification = Notification(NotificationId(1), UserId(1), NotificationType.FOLLOW,
        NotificationContent("follow", "message", UserId(2), "actor"), datetime.now(timezone.utc))
    repository.save(notification)
    connection.execute("UPDATE game_sns_notifications SET identity_token=NULL")
    connection.commit()
    with pytest.raises(SnsIdentityValidationException):
        repository.find_by_id(NotificationId(1))
    connection.close()
