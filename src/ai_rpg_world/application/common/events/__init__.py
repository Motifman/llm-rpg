"""オペレーション境界でドメインイベントを収集・冪等化するための基盤機能。"""

from ai_rpg_world.application.common.events.domain_event_collector import (
    DomainEventCollector,
)

__all__ = ["DomainEventCollector"]
