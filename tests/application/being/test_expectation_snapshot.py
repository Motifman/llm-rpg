"""BeingMemorySnapshotService が、予期・未配信の出来事・記憶のターン数を状態のまま保存して戻す挙動を保証する。"""

from __future__ import annotations

import json
from dataclasses import replace
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
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
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


def _advance_to(store: InMemoryExpectationRepository, turn: int) -> None:
    while store.current_turn(RIO) < turn:
        store.advance_turn(RIO)


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
        store.save(expectation, [])
        _advance_to(store, 12)

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
        expired_event = expired.expire_if_overdue(now_turn=EXPIRES_AT + 2)
        dismissed = _expectation("exp-dismissed")
        dismissed_event = dismissed.judge_shape(
            ShapeVerdict.TRUE_EITHER_WAY, turn=FORMED_AT + 1, grounds=ExpectationGrounds()
        )
        store.save(expired, [expired_event])
        store.save(dismissed, [dismissed_event])
        _advance_to(store, EXPIRES_AT + 2)

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
        _advance_to(store, 12)
        delivered, kept = store.list_undelivered_by_being(RIO)
        store.mark_delivered(RIO, delivered.event_id)

        restored, _ = _round_trip(source)

        assert restored.list_undelivered_by_being(RIO) == [kept]

    @pytest.mark.parametrize(
        "drive",
        [
            lambda e: [e.judge_shape(ShapeVerdict.OWN_ACTION, turn=FORMED_AT, grounds=ExpectationGrounds())],
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
        _advance_to(store, EXPIRES_AT + 1)

        restored, _ = _round_trip(source)

        assert restored.list_undelivered_by_being(
            RIO
        ) == store.list_undelivered_by_being(RIO)

    def test_grounds_and_settled_event_grounds_come_back(self) -> None:
        """形と一緒に受けた根拠は、予期と未配信の確定の出来事の両方で同じ値のまま戻る。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        grounds = ExpectationGrounds(beliefs=("belief-1",), episodes=("episode-3",))
        expectation.judge_shape(ShapeVerdict.SETTLEABLE, turn=FORMED_AT, grounds=grounds)
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.HIT))
        store.save(expectation, [settled])
        _advance_to(store, 12)

        restored, _ = _round_trip(source)

        assert _snapshots(restored)[0].grounds == grounds
        [entry] = restored.list_undelivered_by_being(RIO)
        assert entry.event.grounds == grounds  # type: ignore[union-attr]

    def test_settled_miss_comes_back_with_what_happened(self) -> None:
        """未配信の外れの確定の出来事は、運んでいた時系列ごと保存され、復元で同じ並びのまま戻る (#1509)。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        settled = expectation.record(Check(turn=12, verdict=CheckVerdict.MISS))
        lines = ("ノアは井戸に来なかった", "カイ「ノアは浜にいる」")
        store.save(expectation, [replace(settled, what_happened=lines)])
        _advance_to(store, 12)

        restored, _ = _round_trip(source)

        [entry] = restored.list_undelivered_by_being(RIO)
        assert entry.event.what_happened == lines  # type: ignore[union-attr]

    def test_settled_event_without_what_happened_key_comes_back_empty(self) -> None:
        """時系列のキーが無い #1509 より前の未配信の確定の出来事は、拒まずに空の時系列として戻る。材料が理由を持たないだけで、状態は壊れない。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        expectation.record(Check(turn=11, verdict=CheckVerdict.MISS))
        store.save(expectation, [expectation.record(Check(turn=12, verdict=CheckVerdict.MISS))])
        _advance_to(store, 12)
        payload = json.loads(source.capture(RIO))
        del payload["expectation_undelivered_events"][0]["what_happened"]
        target, restored = _service()

        target.restore(RIO, json.dumps(payload))

        [entry] = restored.list_undelivered_by_being(RIO)
        assert entry.event.what_happened == ()  # type: ignore[union-attr]

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
        store.save(expectation, [])
        _advance_to(store, 11)
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
        _advance_to(store, 11)
        payload = json.loads(source.capture(RIO))
        payload["expectation_undelivered_events"][0]["kind"] = "surprised"
        target, _ = _service()

        with pytest.raises(
            BeingMemoryPayloadFormatError, match="expectation_undelivered_events"
        ):
            target.restore(RIO, json.dumps(payload))

    @pytest.mark.parametrize(
        "memory_turn",
        [[3, 4], [0], [-1], [True], ["3"], [1.5]],
        ids=["two_elements", "zero", "negative", "bool", "str", "float"],
    )
    def test_malformed_memory_turn_is_format_error(self, memory_turn: list[Any]) -> None:
        """ターン数が空でも正の int 1 つでもないと、BeingMemoryPayloadFormatError で拒む。0 は空の list で表すので [0] も拒む。"""
        source, _ = _service()
        payload = json.loads(source.capture(RIO))
        payload["memory_turn"] = memory_turn
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="memory_turn"):
            target.restore(RIO, json.dumps(payload))

    def test_beliefs_in_mind_as_str_is_format_error(self) -> None:
        """頭にあった信念が list でなく文字列だと、1 文字ずつの tuple に化けさせずに BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        store.save(_expectation("exp-1"), [])
        _advance_to(store, FORMED_AT)
        payload = json.loads(source.capture(RIO))
        payload["expectations"][0]["beliefs_in_mind"] = "belief-1"
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="expectations"):
            target.restore(RIO, json.dumps(payload))

    def test_judged_shape_without_grounds_key_is_format_error(self) -> None:
        """形を判定した予期に根拠のキーが無い payload (#1484 より前の保存) は、根拠を空と捏造せずに BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        expectation.judge_shape(
            ShapeVerdict.SETTLEABLE, turn=FORMED_AT, grounds=ExpectationGrounds()
        )
        store.save(expectation, [])
        _advance_to(store, FORMED_AT)
        payload = json.loads(source.capture(RIO))
        del payload["expectations"][0]["grounds"]
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="grounds"):
            target.restore(RIO, json.dumps(payload))

    def test_settled_event_without_grounds_key_is_format_error(self) -> None:
        """未配信の確定の出来事に根拠のキーが無い payload は、BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        expectation = _expectation("exp-1")
        expectation.record(Check(turn=11, verdict=CheckVerdict.HIT))
        store.save(expectation, [expectation.record(Check(turn=12, verdict=CheckVerdict.HIT))])
        _advance_to(store, 12)
        payload = json.loads(source.capture(RIO))
        del payload["expectation_undelivered_events"][0]["grounds"]
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="grounds"):
            target.restore(RIO, json.dumps(payload))

    def test_expectation_of_other_being_is_rejected_before_any_store_is_written(
        self,
    ) -> None:
        """別の Being の予期が混じった payload は BeingMemoryPayloadFormatError で拒み、ほかの store も予期の store も書き換えない。"""
        source, store = _service()
        store.save(_expectation("exp-1"), [])
        _advance_to(store, FORMED_AT)
        payload = json.loads(source.capture(RIO))
        payload["expectations"][0]["holder"] = "being-noa"
        payload["memo"] = [
            {
                "id": "memo-1",
                "content": "井戸を見る",
                "added_at": "2026-10-03T00:00:00+00:00",
                "completed": False,
                "added_at_tick": 1,
                "completed_at": None,
                "fulfillment_context": None,
            }
        ]
        target, _ = _service()
        before = target.capture(RIO)

        with pytest.raises(BeingMemoryPayloadFormatError, match="being-noa"):
            target.restore(RIO, json.dumps(payload))

        assert target.capture(RIO) == before

    def test_turn_before_expectation_is_format_error(self) -> None:
        """記憶のターン数が予期を持ったターンより前なら、BeingMemoryPayloadFormatError で拒む。"""
        source, store = _service()
        store.save(_expectation("exp-1"), [])
        _advance_to(store, FORMED_AT)
        payload = json.loads(source.capture(RIO))
        payload["memory_turn"] = [FORMED_AT - 1]
        target, _ = _service()

        with pytest.raises(BeingMemoryPayloadFormatError, match="turn"):
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
