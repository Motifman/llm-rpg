"""outboxの安定event type名を明示codecへ解決するregistry。"""

from __future__ import annotations

from typing import Type

from ai_rpg_world.application.common.outbox_worker import (
    PermanentOutboxMessageException,
    StoredOutboxMessage,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_payload_serializer import EventPayloadSerializer


def event_type_name(event_type: Type[DomainEvent]) -> str:
    """モジュールと修飾名から決定的な保存名を作る。"""
    return f"{event_type.__module__}:{event_type.__qualname__}"


class OutboxEventCodecRegistry:
    """動的importを使わず、許可したイベントだけを復元する。"""

    def __init__(self) -> None:
        self._registrations: dict[
            str,
            tuple[Type[DomainEvent], EventPayloadSerializer],
        ] = {}

    def register(
        self,
        event_type: Type[DomainEvent],
        serializer: EventPayloadSerializer,
    ) -> None:
        """イベント型とschema versionを所有するcodecを登録する。"""
        if not isinstance(event_type, type):
            raise TypeError("event_typeは型である必要があります")
        name = event_type_name(event_type)
        if name in self._registrations:
            raise ValueError(f"outbox event typeは登録済みです: {name}")
        self._registrations[name] = (event_type, serializer)

    def deserialize(self, message: StoredOutboxMessage) -> DomainEvent:
        """保存名とschema versionが一致するcodecでpayloadを復元する。"""
        registration = self._registrations.get(message.event_type)
        if registration is None:
            raise PermanentOutboxMessageException(
                f"未登録のoutbox event typeです: {message.event_type}"
            )
        event_type, serializer = registration
        if message.payload_schema_version != serializer.schema_version:
            raise PermanentOutboxMessageException(
                "未対応のoutbox payload schema versionです: "
                f"event_type={message.event_type}, "
                f"stored={message.payload_schema_version}, "
                f"supported={serializer.schema_version}"
            )
        try:
            restored = serializer.deserialize(message.payload, event_type)
        except Exception as error:
            raise PermanentOutboxMessageException(
                "outbox payloadを復元できません: "
                f"event_type={message.event_type}",
                cause=error,
            ) from error
        if not isinstance(restored, event_type):
            raise PermanentOutboxMessageException(
                "outbox codecが登録型と異なるイベントを返しました: "
                f"event_type={message.event_type}"
            )
        if str(restored.event_id) != message.event_id:
            raise PermanentOutboxMessageException(
                "outbox行とpayloadのevent_idが一致しません: "
                f"stored={message.event_id}, payload={restored.event_id}"
            )
        return restored


__all__ = ["OutboxEventCodecRegistry", "event_type_name"]
