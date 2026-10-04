"""SNSの世界保存が対象の同一性を保ち、不正な入力で一部だけ変わらないことを検査する。"""
import json
from copy import deepcopy
from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.public_sns_snapshot_codec import (
    capture_public_sns_store,
    restore_public_sns_store,
)


def test_round_trip_is_json_and_preserves_every_object_identity():
    """JSONを通した再開でも名前空間・全対象・関係・採番位置が一致する。"""
    original = InMemoryDataStore()
    payload = capture_public_sns_store(original)
    destination = InMemoryDataStore()
    assert destination.sns_public_namespace != original.sns_public_namespace
    restore_public_sns_store(destination, json.loads(json.dumps(payload)))
    assert capture_public_sns_store(destination) == payload
    assert all(not item.get_events() for item in destination.posts.values())
    assert all(not item.get_events() for item in destination.replies.values())
    assert all(not item.get_events() for item in destination.sns_users.values())


@pytest.mark.parametrize('corruption', ['namespace', 'duplicate', 'counter', 'version'])
def test_corrupted_snapshot_keeps_destination_intact(corruption):
    """不正な名前空間・重複対象・再利用される採番位置は復元前に拒む。"""
    destination = InMemoryDataStore()
    before = capture_public_sns_store(destination)
    broken = deepcopy(before)
    if corruption == 'namespace':
        broken['namespace'] = 'bad'
    elif corruption == 'duplicate':
        broken['posts'].append(deepcopy(broken['posts'][0]))
    elif corruption == 'counter':
        broken['next_ids']['posts'] = 1
    else:
        broken['schema_version'] = 2
    with pytest.raises((ValueError, TypeError)):
        restore_public_sns_store(destination, broken)
    assert capture_public_sns_store(destination) == before


def test_notification_binding_and_read_state_survive_json_restore():
    """実際の通知の宛先・発信者・対象・再配送識別子と既読状態を失わない。"""
    source = InMemoryDataStore()
    post = next(iter(source.posts.values()))
    actor = source.sns_users[post.author_user_id]
    recipient = source.sns_users[UserId(2)]
    notice = Notification(
        notification_id=NotificationId(1), user_id=recipient.user_id,
        notification_type=NotificationType.MENTION,
        content=NotificationContent(
            title='言及', message='届いた本文', actor_user_id=actor.user_id,
            actor_user_name=actor.profile.display_name, related_post_id=post.post_id,
            related_target_id=f'sns:{source.sns_public_namespace}:post:{post.identity_token}',
            actor_identity_token=actor.identity_token,
        ),
        created_at=datetime(2026, 10, 4), is_read=True,
        recipient_identity_token=recipient.identity_token, source_event_id='event-source',
        observation_delivered=True, execution_provenance={'execution_request_id': 'actual-execution'},
    )
    source.sns_notifications[notice.notification_id] = notice
    source.next_sns_notification_id = 2
    payload = capture_public_sns_store(source)
    destination = InMemoryDataStore()
    restore_public_sns_store(destination, json.loads(json.dumps(payload)))
    assert capture_public_sns_store(destination) == payload


def test_same_token_on_two_local_ids_is_rejected_atomically():
    """異なる整数に同じ不変IDを割り当てた保存データを採用しない。"""
    destination = InMemoryDataStore()
    before = capture_public_sns_store(destination)
    broken = deepcopy(before)
    broken['posts'][1]['identity_token'] = broken['posts'][0]['identity_token']
    with pytest.raises(ValueError, match='重複'):
        restore_public_sns_store(destination, broken)
    assert capture_public_sns_store(destination) == before
