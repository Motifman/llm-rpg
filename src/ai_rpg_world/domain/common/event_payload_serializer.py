"""EventPayloadSerializer - イベント永続化・配送のシリアライズ port (Phase 6)

outbox 実装で使用する。in-process では不使用（オブジェクト参照をそのまま渡す）。
SEAM.md の Serialization Seam に従い、将来的な差し替え境界を定義する。
"""
from typing import Protocol, Type

from ai_rpg_world.domain.common.domain_event import DomainEvent


class EventPayloadSerializer(Protocol):
    """イベントのシリアライズ／デシリアライズの port

    永続化や broker 配送の際に使用する。in-process では identity 相当として
    オブジェクトをそのまま扱うため、本 port は使用しない。
    outbox / worker 実装で JSON 等の具体実装を提供する。
    """

    def serialize(self, event: DomainEvent) -> bytes:
        """イベントをバイト列にシリアライズする"""
        ...

    def deserialize(self, payload: bytes, event_type: Type[DomainEvent]) -> DomainEvent:
        """バイト列からイベントを復元する"""
        ...
