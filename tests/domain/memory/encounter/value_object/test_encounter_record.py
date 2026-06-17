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

    def test_正常値で_record_を_構築できる(self) -> None:
        r = EncounterRecord(first_seen_tick=5, last_seen_tick=10, count=3)
        assert r.first_seen_tick == 5
        assert r.last_seen_tick == 10
        assert r.count == 3

    def test_first_seen_が_負なら_validation_例外を投げる(self) -> None:
        with pytest.raises(
            EncounterRecordValidationException, match="first_seen_tick"
        ):
            EncounterRecord(first_seen_tick=-1, last_seen_tick=0, count=1)

    def test_last_seen_が_first_seen_未満なら_validation_例外を投げる(self) -> None:
        """時系列が逆転している record は許容しない。"""
        with pytest.raises(
            EncounterRecordValidationException, match="last_seen_tick"
        ):
            EncounterRecord(first_seen_tick=10, last_seen_tick=5, count=2)

    def test_count_が_0_以下なら_validation_例外を投げる(self) -> None:
        """count=0 は record の存在自体と矛盾する。"""
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(first_seen_tick=0, last_seen_tick=0, count=0)

    def test_count_が_負なら_validation_例外を投げる(self) -> None:
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(first_seen_tick=0, last_seen_tick=0, count=-1)

    def test_tick_が_int_でなく_bool_なら_validation_例外を投げる(self) -> None:
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

    def test_count_が_int_でなく_bool_なら_validation_例外を投げる(self) -> None:
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterRecord(
                first_seen_tick=0,
                last_seen_tick=0,
                count=True,  # type: ignore[arg-type]
            )


class TestEncounterRecordFirst:
    """``first`` factory による初回遭遇の生成。"""

    def test_first_は_count1_かつ_first_seen_と_last_seen_が_now_に_なる(self) -> None:
        r = EncounterRecord.first(now_tick=42)
        assert r.count == 1
        assert r.first_seen_tick == 42
        assert r.last_seen_tick == 42

    def test_first_の_record_は_is_first_が_True(self) -> None:
        assert EncounterRecord.first(now_tick=0).is_first is True

    def test_first_に_負の_tick_を_渡すと_validation_例外を投げる(self) -> None:
        with pytest.raises(EncounterRecordValidationException):
            EncounterRecord.first(now_tick=-1)


class TestEncounterRecordObservedAgain:
    """``observed_again`` による immutable update の挙動。"""

    def test_再遭遇で_count_が_1_増え_last_seen_が_更新される(self) -> None:
        r = EncounterRecord.first(now_tick=10)
        r2 = r.observed_again(now_tick=42)
        assert r2.count == 2
        assert r2.first_seen_tick == 10  # 不変
        assert r2.last_seen_tick == 42

    def test_observed_again_は_元_record_を_破壊しない_immutable(self) -> None:
        """frozen dataclass による immutable update の確認。"""
        r = EncounterRecord.first(now_tick=10)
        r.observed_again(now_tick=42)
        # r は変わらないことを確認
        assert r.count == 1
        assert r.last_seen_tick == 10

    def test_同_tick_での_再遭遇も_count_が_進む(self) -> None:
        """observation pipeline が同 tick で複数 observation を出す経路を想定。"""
        r = EncounterRecord.first(now_tick=5)
        r2 = r.observed_again(now_tick=5)
        assert r2.count == 2
        assert r2.last_seen_tick == 5

    def test_時系列_逆行は_rule_例外を投げる(self) -> None:
        """now_tick < last_seen_tick は呼出側の bug として表明する。"""
        r = EncounterRecord.first(now_tick=10)
        with pytest.raises(EncounterRecordRuleException, match="now_tick"):
            r.observed_again(now_tick=5)

    def test_is_first_は_2_回目以降_False(self) -> None:
        r = EncounterRecord.first(now_tick=0).observed_again(now_tick=1)
        assert r.is_first is False


class TestEncounterRecordTicksSinceLast:
    """``ticks_since_last`` のエッジケース。"""

    def test_current_が_last_と_同じなら_0_を_返す(self) -> None:
        r = EncounterRecord.first(now_tick=10)
        assert r.ticks_since_last(10) == 0

    def test_current_が_last_より_大きいなら_差分_tick_数を_返す(self) -> None:
        r = EncounterRecord.first(now_tick=10)
        assert r.ticks_since_last(42) == 32

    def test_current_が_last_未満なら_rule_例外を投げる(self) -> None:
        r = EncounterRecord.first(now_tick=10)
        with pytest.raises(EncounterRecordRuleException, match="current_tick"):
            r.ticks_since_last(5)

    def test_current_が_int_でなく_bool_なら_validation_例外を投げる(self) -> None:
        r = EncounterRecord.first(now_tick=0)
        with pytest.raises(EncounterRecordValidationException, match="current_tick"):
            r.ticks_since_last(True)  # type: ignore[arg-type]
