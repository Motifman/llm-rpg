"""既存のフォロー・いいねイベントを、不変ID付きの公開通知へ変換する。"""

from __future__ import annotations

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.social.public_sns.notification_events import PublicSnsActivityEvent
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.sns.event.post_event import SnsContentLikedEvent
from ai_rpg_world.domain.sns.event.sns_user_event import SnsUserFollowedEvent


def activity_from_domain_event(event: DomainEvent, namespace: str) -> PublicSnsActivityEvent | None:
    """旧イベントの整数だけから人や本文を復元しない。出典も配送時点から借りない。"""
    if not isinstance(event, (SnsContentLikedEvent, SnsUserFollowedEvent)):
        return None
    if not event.actor_identity_token or not event.recipient_identity_token:
        return None
    if isinstance(event, SnsContentLikedEvent):
        if not event.target_identity_token or not event.is_liked or event.content_type not in {"post", "reply"}:
            return None
        actor_id = event.user_id.value
        recipient_id = event.content_author_id.value
        kind = "like"
        target_id = f"sns:{namespace}:{event.content_type}:{event.target_identity_token}"
    else:
        actor_id = event.follower_user_id.value
        recipient_id = event.followee_user_id.value
        kind = "follow"
        target_id = None
    provenance = ExecutionProvenance.from_dict(event.execution_provenance) if event.execution_provenance else None
    return PublicSnsActivityEvent(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        aggregate_id=str(event.aggregate_id),
        aggregate_type="PublicSnsActivity",
        actor_user_id=actor_id,
        actor_identity_token=event.actor_identity_token,
        recipients=((recipient_id, event.recipient_identity_token, kind),),
        target_id=target_id,
        provenance=provenance,
    )
