"""取引 outbox が使う EventPayloadSerializer の保存形式を保証する。"""

import json
from datetime import datetime
from typing import Any

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_payload_serializer import EventPayloadSerializer
from ai_rpg_world.domain.common.value_object import WorldTick

# --- EventPayloadSerializer 契約検証用の最小実装（outbox 実装時の参照。in-process では不使用）---


class JsonEventPayloadSerializer:
    """EventPayloadSerializer 契約を満たすテスト用実装（JSON / UTF-8）。"""

    @property
    def schema_version(self) -> int:
        return 1

    def serialize(self, event: BaseDomainEvent) -> bytes:
        tick = event.occurred_tick.value if event.occurred_tick is not None else None
        body: dict[str, Any] = {
            "event_id": event.event_id,
            "occurred_at": event.occurred_at.isoformat(),
            "aggregate_id": event.aggregate_id,
            "aggregate_type": event.aggregate_type,
            "occurred_tick": tick,
        }
        return json.dumps(body, sort_keys=True).encode("utf-8")

    def deserialize(self, payload: bytes, event_type: type[BaseDomainEvent]) -> BaseDomainEvent:
        data = json.loads(payload.decode("utf-8"))
        tick_raw = data.get("occurred_tick")
        tick: WorldTick | None = WorldTick(int(tick_raw)) if tick_raw is not None else None
        return event_type(
            event_id=int(data["event_id"]),
            occurred_at=datetime.fromisoformat(str(data["occurred_at"])),
            aggregate_id=data["aggregate_id"],
            aggregate_type=data["aggregate_type"],
            occurred_tick=tick,
        )


# --- RecordingHandler (テスト用) ---


class TestEventPayloadSerializerSeam:
    """EventPayloadSerializer port の契約検証"""

    def test_json_serializer_roundtrip(self) -> None:
        """JsonEventPayloadSerializer が EventPayloadSerializer 契約を満たし、
        serialize → deserialize で roundtrip する"""
        serializer: EventPayloadSerializer = JsonEventPayloadSerializer()
        event = BaseDomainEvent.create(aggregate_id=42, aggregate_type="Test")

        payload = serializer.serialize(event)
        restored = serializer.deserialize(payload, type(event))

        assert restored.aggregate_id == event.aggregate_id
        assert restored.aggregate_type == event.aggregate_type
        assert restored.event_id == event.event_id
