"""公開SNSの通知先と出典を操作時点で固定する、確定境界内のイベント。"""
from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


@dataclass(frozen=True)
class PublicSnsActivityEvent(BaseDomainEvent[str, object]):
    actor_user_id: int
    actor_identity_token: str
    # (利用者ID、利用者の不変ID、通知種類)。二重の通知目的は操作側で統合する。
    recipients: tuple[tuple[int, str, str], ...]
    target_id: str | None
    provenance: ExecutionProvenance | None = None


@dataclass(frozen=True)
class PublicSnsNotificationReadyEvent(BaseDomainEvent[str, object]):
    notification_id: int
    notification_identity_token: str
