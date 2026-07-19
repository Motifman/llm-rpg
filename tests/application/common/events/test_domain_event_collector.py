"""DomainEventCollector の収集・冪等化・fail-fast 挙動を保証する。

ドメインイベント配信一元化リファクタ Stage 2 の新プリミティブ。オペレーション
境界でイベントを集め、event_id で二重 dispatch を防ぎ、event_id 欠落は静かに
無視せず即失敗する、を固定する。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.application.common.events.domain_event_collector import (
    DomainEventCollector,
)


@dataclass(frozen=True)
class _FakeEvent:
    """event_id を持つ最小のイベント風オブジェクト。"""

    event_id: int
    name: str = "e"


class _NoEventId:
    """event_id を持たない非イベントオブジェクト (fail-fast 検証用)。"""


class TestCollectAndDrain:
    """収集したイベントを挿入順に drain できる。"""

    def test_drain_returns_added_events_in_insertion_order(self) -> None:
        """add した順序のまま drain で返る。"""
        collector = DomainEventCollector()
        collector.add(_FakeEvent(event_id=1, name="a"))
        collector.add(_FakeEvent(event_id=2, name="b"))

        drained = collector.drain()

        assert [e.name for e in drained] == ["a", "b"]

    def test_add_all_preserves_order(self) -> None:
        """add_all は渡した iterable の順で収集する。"""
        collector = DomainEventCollector()
        collector.add_all(
            [_FakeEvent(event_id=1, name="a"), _FakeEvent(event_id=2, name="b")]
        )

        assert [e.name for e in collector.drain()] == ["a", "b"]

    def test_drain_empties_buffer(self) -> None:
        """drain 後は buffer が空になり、2 回目の drain は空リストを返す。"""
        collector = DomainEventCollector()
        collector.add(_FakeEvent(event_id=1))

        assert len(collector.drain()) == 1
        assert collector.drain() == []

    def test_len_reflects_pending_count(self) -> None:
        """len(collector) は未 drain の収集件数を返す。"""
        collector = DomainEventCollector()
        assert len(collector) == 0
        collector.add(_FakeEvent(event_id=1))
        assert len(collector) == 1


class TestEventIdDedup:
    """同一 event_id の二重 add は 1 件に畳む (operation-local dedup)。"""

    def test_same_event_id_added_twice_kept_once(self) -> None:
        """同一 event_id を 2 度 add しても drain は 1 件。"""
        collector = DomainEventCollector()
        collector.add(_FakeEvent(event_id=7, name="first"))
        collector.add(_FakeEvent(event_id=7, name="second"))

        drained = collector.drain()

        assert len(drained) == 1
        assert drained[0].name == "first"  # 先勝ち

    def test_dedup_state_resets_after_drain(self) -> None:
        """drain 後は dedup 状態もリセットされ、同 event_id を再収集できる。"""
        collector = DomainEventCollector()
        collector.add(_FakeEvent(event_id=7))
        collector.drain()

        collector.add(_FakeEvent(event_id=7))
        assert len(collector.drain()) == 1

    def test_distinct_event_ids_all_kept(self) -> None:
        """異なる event_id は全て残る。"""
        collector = DomainEventCollector()
        collector.add_all([_FakeEvent(event_id=i) for i in range(3)])

        assert len(collector.drain()) == 3


class TestFailFast:
    """event_id を持たない入力は静かに無視せず即失敗する。"""

    def test_add_object_without_event_id_raises(self) -> None:
        """event_id 属性が無いオブジェクトは ValueError。"""
        collector = DomainEventCollector()
        with pytest.raises(ValueError):
            collector.add(_NoEventId())  # type: ignore[arg-type]

    def test_add_event_with_none_event_id_raises(self) -> None:
        """event_id が None のイベントは ValueError。"""
        collector = DomainEventCollector()
        with pytest.raises(ValueError):
            collector.add(_FakeEvent(event_id=None))  # type: ignore[arg-type]
