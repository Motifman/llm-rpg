"""公開の任意診断が、未発行イベントを変えずに警告の要否と内容を伝える。

PR #600 で導入した診断は、発行漏れを検出したい呼出側が明示的に使う。
イベントを持ち越す正常な経路もあるため、保存時に強制実行する契約ではない。
"""

from __future__ import annotations

import logging
import re

import pytest

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent

_LOGGER = "ai_rpg_world.domain.common.aggregate_root"


class _FakeEvent(BaseDomainEvent):
    """型別の診断内容を区別するためのイベント。"""

    @classmethod
    def create_at(cls, aggregate_id: str = "agg-1") -> _FakeEvent:
        return cls.create(
            aggregate_id=aggregate_id,
            aggregate_type="TestAggregate",
        )


class TestWarnIfPendingEventsNoWarn:
    """未発行イベントが空なら警告を出さない。"""

    def test_no_pending_events_no_warning(self, caplog: pytest.LogCaptureFixture):
        """空の集約では、診断文面にかかわらず WARNING 以上の記録が残らない。"""
        agg = AggregateRoot()
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            agg.warn_if_pending_events(context="MyRepo.save")
        assert not [
            record
            for record in caplog.records
            if record.name == _LOGGER and record.levelno >= logging.WARNING
        ]


class TestWarnIfPendingEventsWithEvents:
    """未発行イベントの場所・総数・型別件数が警告から分かる。"""

    @pytest.mark.parametrize(
        ("event_specs", "context", "expected_total", "expected_counts"),
        [
            pytest.param(
                [(_FakeEvent, "agg-x")], "SpotAttackOrchestrator.flush", 1,
                {"_FakeEvent": 1}, id="single-event",
            ),
            pytest.param(
                [(_FakeEvent, "agg-1"), (_FakeEvent, "agg-1")], "MyRepo.save", 2,
                {"_FakeEvent": 2}, id="two-same-type-events",
            ),
            pytest.param(
                [(_FakeEvent, "agg-1"), (_FakeEvent, "agg-1"), (BaseDomainEvent, "agg-other")],
                "SpotAttackOrchestrator.flush", 3,
                {"_FakeEvent": 2, "BaseDomainEvent": 1}, id="mixed-event-types",
            ),
        ],
    )
    def test_warning_includes_context_and_count(
        self, caplog: pytest.LogCaptureFixture, event_specs, context, expected_total, expected_counts,
    ):
        """1件・同型2件・混在3件の総数と型別件数を、呼出場所とともに WARNING で伝える。"""
        agg = AggregateRoot()
        for event_type, aggregate_id in event_specs:
            agg.add_event(event_type.create(aggregate_id=aggregate_id, aggregate_type="TestAggregate"))

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            agg.warn_if_pending_events(context=context)

        messages = [
            record.getMessage()
            for record in caplog.records
            if record.name == _LOGGER and record.levelno == logging.WARNING
        ]
        assert messages, "未発行イベントがあるのに対象の診断から WARNING が出ていない"
        # 全文や内訳の順序は固定せず、同じ警告に必要な情報がそろうことを確かめる。
        assert any(
            context in message
            and re.search(rf"\b{expected_total} pending domain events\b", message)
            and all(
                re.search(rf"\b{re.escape(event_type)}={count}\b", message)
                for event_type, count in expected_counts.items()
            )
            for message in messages
        ), messages


class TestWarnIfPendingEventsNoSideEffect:
    """診断後も同じイベントを同じ順序で発行できる。"""

    def test_events_remain_after_warn(self, caplog: pytest.LogCaptureFixture):
        """2件の異なるイベントについて、診断前後で内容と順序が変わらない。"""
        agg = AggregateRoot()
        events = [_FakeEvent.create_at("agg-1"), _FakeEvent.create_at("agg-2")]
        for event in events:
            agg.add_event(event)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            agg.warn_if_pending_events(context="ctx")
        assert agg.get_events() == events
