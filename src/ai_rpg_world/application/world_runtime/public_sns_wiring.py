"""公開SNSを物理世界や旧SNSアプリから独立した状態として配線する。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.llm.services.executors.public_sns_executor import PublicSnsToolExecutor
from ai_rpg_world.application.social.public_sns.prompt_projection import (
    PublicSnsPromptProjection,
    notification_observation,
)
from ai_rpg_world.application.social.public_sns.read_service import PublicSnsReadService
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.sns_user import SnsUser
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_public_sns_read_repository import InMemoryPublicSnsReadRepository
from ai_rpg_world.infrastructure.social.public_sns_factory import create_in_memory_public_sns_command_service


def wire_public_sns(runtime: Any) -> None:
    if not runtime.scenario.public_sns_enabled:
        return
    store = InMemoryDataStore()
    # 旧repositoryのデモデータは、この世界の事実として公開しない。
    store.sns_users.clear()
    store.sns_username_to_user_id.clear()
    store.posts.clear()
    store.replies.clear()
    store.sns_notifications.clear()
    store.next_post_id = store.next_reply_id = store.next_sns_notification_id = 1
    for pid in runtime.get_player_ids():
        uid = UserId(int(pid))
        username = f"player_{int(pid)}"
        user = UserAggregate(
            uid, SnsUser(uid, UserProfile(username, runtime.get_player_name(pid)[:30], "")), [], [], []
        )
        store.sns_users[uid] = user
        store.sns_username_to_user_id[username] = uid
    store.sns_next_user_id = max((int(uid) for uid in store.sns_users), default=0) + 1
    runtime._public_sns_data_store = store
    runtime._public_sns_read_service = PublicSnsReadService(InMemoryPublicSnsReadRepository(store))
    runtime._public_sns_projection = PublicSnsPromptProjection(
        runtime._public_sns_screens,
        budget_chars=runtime.scenario.public_sns_push_budget_chars,
        header_chars_provider=lambda pid: (
            len(runtime._public_sns_header_text(PlayerId(pid)))
            + len(runtime._public_sns_screens.presentation_status(pid))
            + 2
        ),
    )

    def deliver(recipient: int, notification: Any, provenance: Any) -> None:
        projection = runtime._public_sns_projection
        if projection.has_received(recipient, notification.notification_id):
            return
        if runtime._observation_appender is None:
            raise RuntimeError("SNS通知の観測配信先が未設定です")
        runtime._emit_observation_directly(PlayerId(recipient), notification_observation(notification, provenance))
        projection.note_incoming(recipient, notification.notification_id)

    runtime._public_sns_command_service = create_in_memory_public_sns_command_service(
        store, deliver_notification=deliver
    )
    runtime._public_sns_executor = PublicSnsToolExecutor(
        runtime._public_sns_read_service, runtime._public_sns_command_service, runtime._public_sns_screens
    )
