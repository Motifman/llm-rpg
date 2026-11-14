"""AggregateCodecs が memento と JSON の行を行き来させ、読めない行と保存できない値をはっきり止めることを保証する。"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pytest

from ai_rpg_world.game_world.domain.value_object import FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldClockMemento
from ai_rpg_world.game_world.domain.world_records.world_flags import FlagPosition, WorldFlagsMemento
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import (
    GAME_WORLD_CODECS,
    AggregateCodecs,
    StoredMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import (
    MementoNotStorableException,
    StoredMementoUnreadableException,
)
from ai_rpg_world.game_world.infrastructure.persistence.world_clock_codec import WorldClockCodec

_WORLD = WorldId("w1")
_CLOCK = WorldClockMemento(world_id=_WORLD, now=WorldTick(42))
_FLAGS = WorldFlagsMemento(
    world_id=_WORLD,
    positions=frozenset({FlagPosition(FlagId("gate_open"), True), FlagPosition(FlagId("bell_rung"), False)}),
)


def _with_state(
    stored: StoredMemento, change: dict[str, object] | None = None, drop: str | None = None
) -> StoredMemento:
    state = json.loads(stored.state)
    state.update(change or {})
    if drop is not None:
        del state[drop]
    return replace(stored, state=json.dumps(state))


class TestRoundTrip:
    """登録した集約の memento を JSON にして戻すと、同じ memento になることを保証する。"""

    def test_world_clock_memento_survives_a_round_trip(self) -> None:
        """WorldClock の memento を行にして読み戻すと、同じ世界と同じ tick の memento になる。"""
        stored = GAME_WORLD_CODECS.stored(_CLOCK)

        restored = GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

        assert restored == _CLOCK

    def test_world_flags_memento_survives_a_round_trip(self) -> None:
        """上げた旗と下げた旗を持つ WorldFlags の memento を行にして読み戻すと、同じ memento になる。"""
        stored = GAME_WORLD_CODECS.stored(_FLAGS)

        restored = GAME_WORLD_CODECS.memento(stored, WorldFlagsMemento)

        assert restored == _FLAGS

    def test_stored_memento_carries_kind_and_version(self) -> None:
        """行には集約の種類と、その種類の形の版が付く。"""
        stored = GAME_WORLD_CODECS.stored(_CLOCK)

        assert (stored.kind, stored.version) == ("world_clock", 1)

    def test_same_flags_give_the_same_state_text(self) -> None:
        """旗の並びが違うだけの同じ memento は、同じ JSON の文字列になる。"""
        reordered = WorldFlagsMemento(world_id=_WORLD, positions=frozenset(reversed(list(_FLAGS.positions))))

        assert GAME_WORLD_CODECS.stored(reordered).state == GAME_WORLD_CODECS.stored(_FLAGS).state


class TestUnreadableRows:
    """読み捨てずに止める行を保証する。"""

    def test_row_with_another_version_is_refused(self) -> None:
        """今の版と違う版の行を読むと StoredMementoUnreadableException で止まる。"""
        stored = replace(GAME_WORLD_CODECS.stored(_CLOCK), version=2)

        with pytest.raises(StoredMementoUnreadableException, match="version"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_row_with_an_unknown_key_is_refused(self) -> None:
        """知らないキーのある行を読むと、そのキーの名前を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_CLOCK), change={"speed": 2})

        with pytest.raises(StoredMementoUnreadableException, match="speed"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_row_missing_a_key_is_refused(self) -> None:
        """キーが足りない行を読むと、足りないキーの名前を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_CLOCK), drop="now")

        with pytest.raises(StoredMementoUnreadableException, match="now"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_flag_position_with_an_unknown_key_is_refused(self) -> None:
        """入れ子の旗の位置に知らないキーがあっても止まる。"""
        stored = _with_state(
            GAME_WORLD_CODECS.stored(_FLAGS),
            change={"positions": [{"flag": "gate_open", "raised": True, "since": 3}]},
        )

        with pytest.raises(StoredMementoUnreadableException, match="since"):
            GAME_WORLD_CODECS.memento(stored, WorldFlagsMemento)

    def test_flag_listed_twice_is_refused(self) -> None:
        """同じ旗の同じ位置が 2 度並んだ行は、1 つに畳まずに止まる。"""
        twice = {"flag": "gate_open", "raised": True}
        stored = _with_state(GAME_WORLD_CODECS.stored(_FLAGS), change={"positions": [twice, twice]})

        with pytest.raises(StoredMementoUnreadableException, match="more than once"):
            GAME_WORLD_CODECS.memento(stored, WorldFlagsMemento)

    def test_value_the_domain_refuses_is_reported_as_unreadable(self) -> None:
        """負の tick のようにドメインが断る値は、StoredMementoUnreadableException として種類を添えて止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_CLOCK), change={"now": -1})

        with pytest.raises(StoredMementoUnreadableException, match="world_clock"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_true_is_not_read_as_a_tick(self) -> None:
        """tick に true が書かれた行は 1 として読まずに止まる。"""
        stored = _with_state(GAME_WORLD_CODECS.stored(_CLOCK), change={"now": True})

        with pytest.raises(StoredMementoUnreadableException):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_state_that_is_not_json_is_refused(self) -> None:
        """JSON として読めない state の行は止まる。"""
        stored = replace(GAME_WORLD_CODECS.stored(_CLOCK), state="{not json")

        with pytest.raises(StoredMementoUnreadableException):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_unknown_kind_is_refused(self) -> None:
        """登録の無い種類の行を読むと止まる。"""
        stored = replace(GAME_WORLD_CODECS.stored(_CLOCK), kind="sundial")

        with pytest.raises(StoredMementoUnreadableException, match="sundial"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)

    def test_row_of_another_kind_is_refused(self) -> None:
        """旗の行を時計の memento として読もうとすると止まる。"""
        stored = GAME_WORLD_CODECS.stored(_FLAGS)

        with pytest.raises(StoredMementoUnreadableException, match="world_flags"):
            GAME_WORLD_CODECS.memento(stored, WorldClockMemento)


@dataclass(frozen=True)
class _UnregisteredMemento:
    value: int


class TestUnstorableValues:
    """JSON にできない値を黙って捨てずに止めることを保証する。"""

    def test_memento_without_a_codec_is_refused(self) -> None:
        """変換を登録していない型の memento を行にしようとすると MementoNotStorableException で止まる。"""
        with pytest.raises(MementoNotStorableException, match="_UnregisteredMemento"):
            GAME_WORLD_CODECS.stored(_UnregisteredMemento(1))


class TestRegistration:
    """同じ種類や同じ memento の型を 2 度登録できないことを保証する。"""

    def test_same_kind_registered_twice_is_refused(self) -> None:
        """同じ変換を 2 つ渡して AggregateCodecs を作ると ValueError になる。"""
        with pytest.raises(ValueError, match="world_clock"):
            AggregateCodecs([WorldClockCodec(), WorldClockCodec()])
