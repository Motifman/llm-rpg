from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired, WorldTimePassing
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.world_records import (
    FlagPosition,
    WorldFlagLoweredEvent,
    WorldFlagRaisedEvent,
    WorldFlags,
    WorldFlagsMemento,
)

_WORLD = WorldId("island")


def _flag(flag_id: str, *, initially_raised: bool = False) -> FlagDeclaration:
    return FlagDeclaration(
        flag_id=FlagId(flag_id), meaning=DescriptionText(f"{flag_id}の旗"), initially_raised=initially_raised
    )


_BRIDGE_REPAIRED = _flag("bridge_repaired")
_GATE_LOCKED = _flag("gate_locked", initially_raised=True)
_STORM = HappeningFired(
    HappeningDeclaration(
        happening_id=HappeningId("storm"),
        condition=TickAtLeastCondition(tick=WorldTick(5), failure_text=NoText()),
        effect=NoEffect(),
        once=True,
        notice=NoNotice(),
    )
)
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_TICK = WorldTimePassing(WorldTick(3))


class TestWorldFlagsAtStart:
    """WorldFlags が、まだ立て下ろししていない旗について宣言の初めの値を答えることを保証する。"""

    def test_flag_declared_lowered_is_not_raised_at_first(self) -> None:
        """initially_raised が偽の旗は、作った直後は立っていない。"""
        assert not WorldFlags.start(_WORLD).is_raised(_BRIDGE_REPAIRED)

    def test_flag_declared_raised_is_raised_at_first(self) -> None:
        """initially_raised が真の旗は、作った直後から立っている。"""
        assert WorldFlags.start(_WORLD).is_raised(_GATE_LOCKED)

    def test_keeps_its_world_id_and_records_no_event_at_first(self) -> None:
        """作った直後は自分の世界の ID を持ち、イベントをためていない。"""
        flags = WorldFlags.start(_WORLD)

        assert flags.world_id == _WORLD
        assert flags.get_events() == []


class TestWorldFlagsRaise:
    """WorldFlags.raise_flag が旗を立て、立てたときだけきっかけを持つイベントをためることを保証する。"""

    def test_raise_flag_raises_the_flag(self) -> None:
        """立っていない旗を raise_flag すると、立っている。"""
        flags = WorldFlags.start(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        assert flags.is_raised(_BRIDGE_REPAIRED)

    def test_raise_flag_records_event_with_its_trigger(self) -> None:
        """嵐の出来事がきっかけで旗を立てると、世界・旗・きっかけ (嵐の HappeningFired) を持つ WorldFlagRaisedEvent をためる。"""
        flags = WorldFlags.start(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        [event] = flags.get_events()
        assert isinstance(event, WorldFlagRaisedEvent)
        assert (event.world_id, event.flag_id, event.trigger) == (_WORLD, FlagId("bridge_repaired"), _STORM)

    def test_raising_raised_flag_changes_nothing(self) -> None:
        """初めから立っている旗を raise_flag しても、断らず、イベントもためない。"""
        flags = WorldFlags.start(_WORLD)

        flags.raise_flag(_GATE_LOCKED, _STORM)

        assert flags.is_raised(_GATE_LOCKED)
        assert flags.get_events() == []

    def test_raising_one_flag_leaves_others(self) -> None:
        """ある旗を立てても、別の旗の立ち下がりは変わらない。"""
        flags = WorldFlags.start(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        assert flags.is_raised(_GATE_LOCKED)
        assert not flags.is_raised(_flag("boat_found"))


class TestWorldFlagsLower:
    """WorldFlags.lower_flag が旗を下ろし、下ろしたときだけきっかけを持つイベントをためることを保証する。"""

    def test_lower_flag_lowers_raised_flag_and_records_event_with_its_trigger(self) -> None:
        """初めから立っている旗を時間の経過がきっかけで下ろすと、立っていなくなり、世界・旗・きっかけを持つ WorldFlagLoweredEvent をためる。"""
        flags = WorldFlags.start(_WORLD)

        flags.lower_flag(_GATE_LOCKED, _TICK)

        assert not flags.is_raised(_GATE_LOCKED)
        [event] = flags.get_events()
        assert isinstance(event, WorldFlagLoweredEvent)
        assert (event.world_id, event.flag_id, event.trigger) == (_WORLD, FlagId("gate_locked"), _TICK)

    def test_lowering_lowered_flag_changes_nothing(self) -> None:
        """立っていない旗を lower_flag しても、断らず、イベントもためない。"""
        flags = WorldFlags.start(_WORLD)

        flags.lower_flag(_BRIDGE_REPAIRED, _TICK)

        assert not flags.is_raised(_BRIDGE_REPAIRED)
        assert flags.get_events() == []

    def test_flag_raised_after_lowering_is_raised_again(self) -> None:
        """立てて、下ろして、また立てた旗は立っていて、3 つのイベントを順にためる。"""
        flags = WorldFlags.start(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)
        flags.lower_flag(_BRIDGE_REPAIRED, _TICK)
        flags.raise_flag(_BRIDGE_REPAIRED, _TICK)

        assert flags.is_raised(_BRIDGE_REPAIRED)
        assert [type(e) for e in flags.get_events()] == [
            WorldFlagRaisedEvent,
            WorldFlagLoweredEvent,
            WorldFlagRaisedEvent,
        ]


_WELL_DUG = _flag("well_dug")


class TestWorldFlagsMemento:
    """WorldFlags を memento から作り直すと、立て下ろしした旗の向きが元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_flags_have_the_same_flags_raised(self) -> None:
        """橋の修理と井戸掘りの旗を立てた WorldFlags を memento から作り直すと、2 つとも立っている。"""
        flags = WorldFlags.start(_WORLD)
        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)
        flags.raise_flag(_WELL_DUG, _TICK)

        rebuilt = rebuilt_from_memento(flags)

        assert rebuilt.is_raised(_BRIDGE_REPAIRED)
        assert rebuilt.is_raised(_WELL_DUG)

    def test_rebuilt_flags_keep_a_lowered_flag_lowered(self) -> None:
        """宣言で立っている門の旗を下ろしてから作り直すと、門の旗は下りたまま。"""
        flags = WorldFlags.start(_WORLD)
        flags.lower_flag(_GATE_LOCKED, _TICK)

        rebuilt = rebuilt_from_memento(flags)

        assert not rebuilt.is_raised(_GATE_LOCKED)

    def test_memento_of_rebuilt_flags_equals_the_original(self) -> None:
        """旗を 2 つ立てて 1 つ下ろしたあとの memento は、作り直したものの memento と等しく、作り直したてとは違う。"""
        flags = WorldFlags.start(_WORLD)
        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)
        flags.raise_flag(_WELL_DUG, _TICK)
        flags.lower_flag(_GATE_LOCKED, _TICK)

        rebuilt = rebuilt_from_memento(flags)

        assert rebuilt.memento() == flags.memento()
        assert rebuilt.memento() != WorldFlags.start(_WORLD).memento()
        assert rebuilt.world_id == _WORLD

    def test_rebuilding_records_no_event(self) -> None:
        """旗を立てたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        flags = WorldFlags.start(_WORLD)
        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        assert rebuilt_from_memento(flags).get_events() == []


class TestWorldFlagsMementoRefusesRepeatedFlag:
    """WorldFlagsMemento が、同じ旗の向きを 2 つ持つ memento を作ることを断ることを保証する。"""

    def test_same_flag_raised_and_lowered_is_refused(self) -> None:
        """gate_a_open が「立っている」と「下りている」の 2 つある memento を作ると、RepeatedMementoKeyException を投げる。"""
        gate = FlagId("gate_a_open")

        with pytest.raises(RepeatedMementoKeyException):
            WorldFlagsMemento(
                world_id=_WORLD, positions=frozenset({FlagPosition(gate, True), FlagPosition(gate, False)})
            )
