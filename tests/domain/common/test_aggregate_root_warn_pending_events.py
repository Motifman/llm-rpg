"""
``AggregateRoot.warn_if_pending_events`` の挙動を保証する。

「add_event した events が publish されずに save される silent failure」を
構造的に検出するための道具 (PR-L = B1)。task #30 (= 同型 publish 漏れの実
修正 / harvest / monster_behavior / reactive_object) で実適用する前段。

opt-in 設計: Repository.save() に強制的に組み込むのではなく、Application
層 / Orchestrator が「ここで publish 漏れがあったらバグ」と判断した箇所で
明示的に呼ぶ。これにより:

- 「graph events が別経路で flow する」「intentional に events を持ち越す」
  ケースを noise なく回避できる
- 道具自体は副作用なし (= warning ログを出すだけ、events は clear しない)
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


class _FakeEvent(BaseDomainEvent):
    """テスト用ダミー event。"""

    @classmethod
    def create_at(cls, aggregate_id: str = "agg-1") -> "_FakeEvent":
        return cls.create(
            aggregate_id=aggregate_id,
            aggregate_type="TestAggregate",
        )


class _StubAggregate(AggregateRoot):
    """AggregateRoot を継承した最小スタブ。"""

    def __init__(self) -> None:
        super().__init__()


class TestWarnIfPendingEventsNoWarn:
    """events が空のとき warning を出さない。"""

    def test_no_pending_events_no_warning(self, caplog: pytest.LogCaptureFixture):
        agg = _StubAggregate()
        with caplog.at_level(logging.WARNING, logger="ai_rpg_world.domain.common.aggregate_root"):
            agg.warn_if_pending_events(context="MyRepo.save")
        assert "pending" not in caplog.text.lower()
        assert "publish" not in caplog.text.lower()


class TestWarnIfPendingEventsWithEvents:
    """events が残っていれば warning ログを出す。"""

    def test_pending_events_emits_warning(self, caplog: pytest.LogCaptureFixture):
        agg = _StubAggregate()
        agg.add_event(_FakeEvent.create_at("agg-1"))
        agg.add_event(_FakeEvent.create_at("agg-1"))
        with caplog.at_level(logging.WARNING, logger="ai_rpg_world.domain.common.aggregate_root"):
            agg.warn_if_pending_events(context="MyRepo.save")
        # warning ログが 1 件以上出ている
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warns) >= 1, "events 非空時に warning が出ていない"

    def test_warning_includes_context_and_count(self, caplog: pytest.LogCaptureFixture):
        """warning メッセージに context, event 件数, event 型名が含まれる。"""
        agg = _StubAggregate()
        agg.add_event(_FakeEvent.create_at("agg-x"))
        with caplog.at_level(logging.WARNING, logger="ai_rpg_world.domain.common.aggregate_root"):
            agg.warn_if_pending_events(context="SpotAttackOrchestrator.flush")
        text = caplog.text
        # context が含まれる (= どこで漏れたかを特定できる)
        assert "SpotAttackOrchestrator.flush" in text
        # event 件数 / event 型名が含まれる
        assert "_FakeEvent" in text or "FakeEvent" in text


class TestWarnIfPendingEventsNoSideEffect:
    """warn_if_pending_events は events を消費しない (= 観測だけ)。"""

    def test_events_remain_after_warn(self, caplog: pytest.LogCaptureFixture):
        agg = _StubAggregate()
        agg.add_event(_FakeEvent.create_at("agg-1"))
        agg.add_event(_FakeEvent.create_at("agg-2"))
        with caplog.at_level(logging.WARNING, logger="ai_rpg_world.domain.common.aggregate_root"):
            agg.warn_if_pending_events(context="ctx")
        # events は残っている (= 後で publish できる、安全側)
        assert len(agg.get_events()) == 2
