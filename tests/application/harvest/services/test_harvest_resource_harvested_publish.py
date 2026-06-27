"""
PR-M (task #30): ``HarvestCommandService`` が ``ResourceHarvestedEvent`` を
``PipelineEventPublisher`` 経路に届けないまま save している silent failure を
回帰固定する。

PR-K (#599) で発見した ``PlayerDownedEvent`` 漏れと同型: aggregate
(physical_map) に add_event した event が、UoW 経路では UoW pending に積まれる
が、production の ``PipelineEventPublisher`` には届かない。観測 broadcast /
side handler (= ``_format_resource_harvested`` 経由) が発火しない。

修正後の挙動:
- ``event_publisher`` を keyword-only で注入できる
- ``set_event_publisher`` setter で二段階構築 patternに対応
- ``_finish_harvest_core`` の save 前に ``publish_all`` に events を流す
- publisher 未注入時は no-op (= 後方互換)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

import pytest

from ai_rpg_world.application.harvest.services.harvest_command_service import (
    HarvestCommandService,
)


@dataclass
class _SpyPublisher:
    """publish_all 呼出を記録する spy。"""

    events_published: List[Any] = field(default_factory=list)

    def publish_all(self, events) -> None:
        self.events_published.extend(events)


class TestEventPublisherInjection:
    """publisher は keyword-only で注入できる。未注入時は no-op (= 後方互換)。"""

    def test_no_publisher_accepted_for_backward_compat(self):
        """既存 caller (= publisher を渡さない) は引き続き動く。"""
        from unittest.mock import MagicMock

        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
        )
        # event_publisher は内部的に None
        assert svc._event_publisher is None

    def test_explicit_publisher_keyword_only(self):
        """publisher は keyword-only で受け取れる。"""
        from unittest.mock import MagicMock

        publisher = _SpyPublisher()
        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
            event_publisher=publisher,
        )
        assert svc._event_publisher is publisher

    def test_set_event_publisher_setter_bindings_later(self):
        """二段階構築用 setter (= PR-K と同型) が動く。"""
        from unittest.mock import MagicMock

        svc = HarvestCommandService(
            physical_map_repository=MagicMock(),
            loot_table_repository=MagicMock(),
            item_repository=MagicMock(),
            item_spec_repository=MagicMock(),
            player_inventory_repository=MagicMock(),
            player_status_repository=MagicMock(),
            harvest_domain_service=MagicMock(),
            unit_of_work=MagicMock(),
        )
        publisher = _SpyPublisher()
        svc.set_event_publisher(publisher)
        assert svc._event_publisher is publisher
