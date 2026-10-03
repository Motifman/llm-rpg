"""BeingMemorySnapshotService が、予期・未配信の出来事・記憶のターン数を状態のまま保存して戻す挙動を保証する。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.application.being.test_being_memory_snapshot_coverage import (
    _make_service,
)

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemoryPayloadFormatError,
    BeingMemorySnapshotService,
    SnapshotCoverageError,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_status import (
    ExpectationStatus,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

RIO = BeingId("being-rio")
FORMED_AT = 10
EXPIRES_AT = 20


def _expectation(expectation_id: str) -> Expectation:
    return Expectation(
        expectation_id=ExpectationId(expectation_id),
        holder=RIO,
        content="二日後の朝にノアと井戸で会う",
        origin=ExpectationOrigin.PROMISE_OR_OUTLOOK,
        likelihood=Likelihood.ALMOST_CERTAIN,
        formed_at_turn=FORMED_AT,
        expires_at_turn=EXPIRES_AT,
        formed_with="ノアに約束する",
        due="二日後の朝",
        beliefs_in_mind=("belief-1",),
        episodes_in_mind=("episode-3",),
    )


def _service() -> tuple[BeingMemorySnapshotService, InMemoryExpectationRepository]:
    store = InMemoryExpectationRepository()
    return _make_service(expectation_store=store), store


def _round_trip(
    source: BeingMemorySnapshotService,
) -> tuple[InMemoryExpectationRepository, str]:
    payload = source.capture(RIO)
    restored, store = _service()
    restored.restore(RIO, payload)
    return store, payload


def _snapshots(store: InMemoryExpectationRepository) -> list[Any]:
    return [e.snapshot() for e in store.list_all_by_being(RIO)]


class TestRoundTrip:
    """capture した予期・出来事・ターン数が、restore でそのまま戻る挙動を保証する。"""

    def test_open_expectation_checks_and_turn_come_back(self) -> None:
        """清算待ちの予期と照合の記録とターン数は、保存して復元すると元に戻る。"""
        source, store = _service()
        expectation = _expectation("exp-open")
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        expectation.record(Check(turn=12, verdict=CheckVerdict.UNDETERMINED))
        store.save(expectation)
        for _ in range(12):
            store.advance_turn(RIO)

        restored, _ = _round_trip(source)

        assert _snapshots(restored) == [expectation.snapshot()]
        assert [e.expectation_id for e in restored.list_open_by_being(RIO)] == [
            ExpectationId("exp-open")
        ]
        assert restored.current_turn(RIO) == 12

    def test_closed_expectations_come_back_closed_at_same_turn(self) -> None:
        """期限切れと形の判定で外した予期は、終わった状態と終わったターンのまま戻り、清算待ちの一覧に出ない。"""
        source, store = _service()
        expired = _expectation("exp-expired")
        expired.expire_if_overdue(now_turn=EXPIRES_AT + 2)
        dismissed = _expectation("exp-dismissed")
        dismissed.judge_shape(ShapeVerdict.TRUE_EITHER_WAY, turn=FORMED_AT + 1)
        store.save(expired)
        store.save(dismissed)

        restored, _ = _round_trip(source)

        assert [
            (s.status, s.closed_at_turn) for s in _snapshots(restored)
        ] == [
            (ExpectationStatus.EXPIRED, EXPIRES_AT + 2),
            (ExpectationStatus.DISMISSED, FORMED_AT + 1),
        ]
        assert restored.list_open_by_being(RIO) == []

    def test_undelivered_events_come_back_undelivered(self) -> None:
        """未配信の出来事は、ID と中身を保ったまま未配信として戻り、配信済みの出来事は戻らない。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        store.save(expectation, [missed])
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.MISS))
        store.save(expectation, [settled])
        delivered, kept = store.list_undelivered_by_being(RIO)
        store.mark_delivered(RIO, delivered.event_id)

        restored, _ = _round_trip(source)

        assert restored.list_undelivered_by_being(RIO) == [kept]

    @pytest.mark.parametrize(
        "drive",
        [
            lambda e: [e.judge_shape(ShapeVerdict.OWN_ACTION, turn=FORMED_AT)],
            lambda e: [
                e.record(Check(turn=11, verdict=CheckVerdict.HIT)),
                e.record(Check(turn=12, verdict=CheckVerdict.NOT_AN_EXPECTATION)),
            ],
            lambda e: [e.expire_if_overdue(now_turn=EXPIRES_AT + 1)],
            lambda e: [
                e.record(Check(turn=11, verdict=CheckVerdict.HIT)),
                e.expire_if_overdue(now_turn=EXPIRES_AT + 1),
            ],
        ],
        ids=["dismissed", "voided", "expired", "settled_by_expiry"],
    )
    def test_every_event_kind_survives_payload(self, drive: Any) -> None:
        """どの種類の出来事も、payload を通って同じ値の未配信として戻る。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        events = [event for event in drive(expectation) if event is not None]
        store.save(expectation, events)

        restored, _ = _round_trip(source)

        assert restored.list_undelivered_by_being(
            RIO
        ) == store.list_undelivered_by_being(RIO)

    def test_empty_store_round_trips_as_empty(self) -> None:
        """予期もターン数も無い Being は空の list で保存され、復元しても空のまま。"""
        source, _ = _service()

        restored, payload = _round_trip(source)

        decoded = json.loads(payload)
        assert decoded["expectations"] == []
        assert decoded["expectation_undelivered_events"] == []
        assert decoded["memory_turn"] == []
        assert restored.current_turn(RIO) == 0


class TestRejectBrokenPayload:
    """規則と食い違う payload を、作り直さずに形式エラーとして拒む挙動を保証する。"""

    def test_status_contradicting_checks_is_format_error(self) -> None:
        """照合の記録と食い違う状態を持つ予期は、BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        store.save(expectation)
        payload = json.loads(source.capture(RIO))
        payload["expectations"][0]["status"] = ExpectationStatus.SETTLED.value
        payload["expectations"][0]["closed_at_turn"] = 11
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="expectations"):
            target.restore(RIO, json.dumps(payload))

    def test_unknown_event_kind_is_format_error(self) -> None:
        """知らない種類の出来事は、BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        missed = expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        store.save(expectation, [missed])
        payload = json.loads(source.capture(RIO))
        payload["expectation_undelivered_events"][0]["kind"] = "surprised"
        target, _ = _service()

        with pytest.raises(
            BeingMemoryPayloadFormatError, match="expectation_undelivered_events"
        ):
            target.restore(RIO, json.dumps(payload))

    def test_more_than_one_memory_turn_is_format_error(self) -> None:
        """ターン数が 2 要素以上あると、BeingMemoryPayloadFormatError で拒む。"""
        source, _ = _service()
        payload = json.loads(source.capture(RIO))
        payload["memory_turn"] = [3, 4]
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="memory_turn"):
            target.restore(RIO, json.dumps(payload))


class TestCoverage:
    """予期の key の capture 漏れを、既存の起動時の検査が止める挙動を保証する。"""

    @pytest.mark.parametrize(
        "key", ["expectations", "expectation_undelivered_events", "memory_turn"]
    )
    def test_forgetting_expectation_key_in_capture_raises(
        self, key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """予期の key を EXPECTED_PAYLOAD_KEYS に持ったまま capture がその key を出さないと、SnapshotCoverageError で止まる。"""
        import ai_rpg_world.application.being.being_memory_snapshot_service as module

        original = module._validate_snapshot_payload_coverage

        def dropping(*, emitted_keys: Any, expected_keys: Any) -> None:
            original(emitted_keys=set(emitted_keys) - {key}, expected_keys=expected_keys)

        monkeypatch.setattr(module, "_validate_snapshot_payload_coverage", dropping)
        source, _ = _service()

        with pytest.raises(SnapshotCoverageError, match=key):
            source.capture(RIO)
