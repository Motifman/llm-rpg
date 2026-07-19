"""EncounterRecord の不変条件 / immutable update の挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterRecordRuleException,
    EncounterRecordValidationException,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_record import (
    EncounterRecord,
)


class TestEncounterRecordConstruction:
    """``EncounterRecord`` 直接構築時の不変条件検証。"""

    def test_value_record_can_build(self) -> None:
        """正常値で record を構築できる。"""
        r = EncounterRecord(first_seen_tick=5, last_seen_tick=10, count=3)
        assert r.first_seen_tick == 5
        assert r.last_seen_tick == 10
        assert r.count == 3

    def test_first_seen_validation_raises_validation_exception(self) -> None:
        """firstseen が負なら validation 例外を投げる。"""
        with pytest.raises(
            EncounterRecordValidationException, match="first_seen_tick"
        ):
            EncounterRecord(first_seen_tick=-1, last_seen_tick=0, count=1)

    def test_last_seen_first_seen_validation_raises_validation_exception(self) -> None:
        """時系列が逆転している record は許容しない。"""
        with pytest.raises(
            EncounterRecordValidationException, match="last_seen_tick"
        ):
            EncounterRecord(first_seen_tick=10, last_seen_tick=5, count=2)

    def test_count_zero_validation_raises_validation_exception(self) -> None:
        """count=0 は record の存在自体と矛盾する。"""
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(first_seen_tick=0, last_seen_tick=0, count=0)

    def test_count_validation_raises_validation_exception(self) -> None:
        """count が負なら validation 例外を投げる。"""
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(first_seen_tick=0, last_seen_tick=0, count=-1)

    def test_tick_int_bool_validation_raises_validation_exception(self) -> None:
        """python の bool は int サブクラスなので isinstance(x, int) で漏れる。
        明示的に弾く (= silent failure 防止)。
        """
        with pytest.raises(
            EncounterRecordValidationException, match="first_seen_tick"
        ):
            EncounterRecord(
                first_seen_tick=True,  # type: ignore[arg-type]
                last_seen_tick=1,
                count=1,
            )

    def test_count_int_bool_validation_raises_validation_exception(self) -> None:
        """count が int でなく bool なら validation 例外を投げる。"""
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(
                first_seen_tick=0,
                last_seen_tick=0,
                count=True,  # type: ignore[arg-type]
            )


class TestEncounterRecordFirst:
    """``first`` factory による初回遭遇の生成。"""

    def test_first_count1_first_seen_last_seen_now(self) -> None:
        """first は count1 かつ firstseen と lastseen が now になる。"""
        r = EncounterRecord.first(now_tick=42)
        assert r.count == 1
        assert r.first_seen_tick == 42
        assert r.last_seen_tick == 42

    def test_first_record_first_true(self) -> None:
        """first の record は is first が True。"""
        assert EncounterRecord.first(now_tick=0).is_first is True

    def test_first_negative_tick_validation_raises_validation_exception(self) -> None:
        """first に負の tick を渡すと validation 例外を投げる。"""
        with pytest.raises(EncounterRecordValidationException):
            EncounterRecord.first(now_tick=-1)


class TestEncounterRecordObservedAgain:
    """``observed_again`` による immutable update の挙動。"""

    def test_count_one_last_seen_updated(self) -> None:
        """再遭遇で count が 1 増え lastseen が更新される。"""
        r = EncounterRecord.first(now_tick=10)
        r2 = r.observed_again(now_tick=42)
        assert r2.count == 2
        assert r2.first_seen_tick == 10  # 不変
        assert r2.last_seen_tick == 42

    def test_observed_again_record_immutable(self) -> None:
        """frozen dataclass による immutable update の確認。"""
        r = EncounterRecord.first(now_tick=10)
        r.observed_again(now_tick=42)
        # r は変わらないことを確認
        assert r.count == 1
        assert r.last_seen_tick == 10

    def test_advances_tick_count(self) -> None:
        """observation pipeline が同 tick で複数 observation を出す経路を想定。"""
        r = EncounterRecord.first(now_tick=5)
        r2 = r.observed_again(now_tick=5)
        assert r2.count == 2
        assert r2.last_seen_tick == 5

    def test_rule_raises_exception(self) -> None:
        """now_tick < last_seen_tick は呼出側の bug として表明する。"""
        r = EncounterRecord.first(now_tick=10)
        with pytest.raises(EncounterRecordRuleException, match="now_tick"):
            r.observed_again(now_tick=5)

    def test_first_two_false(self) -> None:
        """is first は 2 回目以降 False。"""
        r = EncounterRecord.first(now_tick=0).observed_again(now_tick=1)
        assert r.is_first is False


class TestEncounterRecordTicksSinceLast:
    """``ticks_since_last`` のエッジケース。"""

    def test_returns_current_last_same_zero(self) -> None:
        """current が last と同じなら 0 を返す。"""
        r = EncounterRecord.first(now_tick=10)
        assert r.ticks_since_last(10) == 0

    def test_returns_current_last_tick(self) -> None:
        """current が last より 大きいなら 差分 tick 数を 返す。"""
        r = EncounterRecord.first(now_tick=10)
        assert r.ticks_since_last(42) == 32

    def test_current_last_rule_raises_exception(self) -> None:
        """current が last 未満なら rule 例外を投げる。"""
        r = EncounterRecord.first(now_tick=10)
        with pytest.raises(EncounterRecordRuleException, match="current_tick"):
            r.ticks_since_last(5)

    def test_current_int_bool_validation_raises_validation_exception(self) -> None:
        """current が int でなく bool なら validation 例外を投げる。"""
        r = EncounterRecord.first(now_tick=0)
        with pytest.raises(EncounterRecordValidationException, match="current_tick"):
            r.ticks_since_last(True)  # type: ignore[arg-type]
