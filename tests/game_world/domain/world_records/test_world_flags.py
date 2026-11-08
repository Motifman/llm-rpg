from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired, WorldTimePassing
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.world_records import WorldFlagLoweredEvent, WorldFlagRaisedEvent, WorldFlags

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
_TICK = WorldTimePassing(WorldTick(3))


class TestWorldFlagsAtStart:
    """WorldFlags が、まだ立て下ろししていない旗について宣言の初めの値を答えることを保証する。"""

    def test_flag_declared_lowered_is_not_raised_at_first(self) -> None:
        """initially_raised が偽の旗は、作った直後は立っていない。"""
        assert not WorldFlags(_WORLD).is_raised(_BRIDGE_REPAIRED)

    def test_flag_declared_raised_is_raised_at_first(self) -> None:
        """initially_raised が真の旗は、作った直後から立っている。"""
        assert WorldFlags(_WORLD).is_raised(_GATE_LOCKED)

    def test_keeps_its_world_id_and_records_no_event_at_first(self) -> None:
        """作った直後は自分の世界の ID を持ち、イベントをためていない。"""
        flags = WorldFlags(_WORLD)

        assert flags.world_id == _WORLD
        assert flags.get_events() == []


class TestWorldFlagsRaise:
    """WorldFlags.raise_flag が旗を立て、立てたときだけきっかけを持つイベントをためることを保証する。"""

    def test_raise_flag_raises_the_flag(self) -> None:
        """立っていない旗を raise_flag すると、立っている。"""
        flags = WorldFlags(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        assert flags.is_raised(_BRIDGE_REPAIRED)

    def test_raise_flag_records_event_with_its_trigger(self) -> None:
        """嵐の出来事がきっかけで旗を立てると、世界・旗・きっかけ (嵐の HappeningFired) を持つ WorldFlagRaisedEvent をためる。"""
        flags = WorldFlags(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        [event] = flags.get_events()
        assert isinstance(event, WorldFlagRaisedEvent)
        assert (event.world_id, event.flag_id, event.trigger) == (_WORLD, FlagId("bridge_repaired"), _STORM)

    def test_raising_raised_flag_changes_nothing(self) -> None:
        """初めから立っている旗を raise_flag しても、断らず、イベントもためない。"""
        flags = WorldFlags(_WORLD)

        flags.raise_flag(_GATE_LOCKED, _STORM)

        assert flags.is_raised(_GATE_LOCKED)
        assert flags.get_events() == []

    def test_raising_one_flag_leaves_others(self) -> None:
        """ある旗を立てても、別の旗の立ち下がりは変わらない。"""
        flags = WorldFlags(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)

        assert flags.is_raised(_GATE_LOCKED)
        assert not flags.is_raised(_flag("boat_found"))


class TestWorldFlagsLower:
    """WorldFlags.lower_flag が旗を下ろし、下ろしたときだけきっかけを持つイベントをためることを保証する。"""

    def test_lower_flag_lowers_raised_flag_and_records_event_with_its_trigger(self) -> None:
        """初めから立っている旗を時間の経過がきっかけで下ろすと、立っていなくなり、世界・旗・きっかけを持つ WorldFlagLoweredEvent をためる。"""
        flags = WorldFlags(_WORLD)

        flags.lower_flag(_GATE_LOCKED, _TICK)

        assert not flags.is_raised(_GATE_LOCKED)
        [event] = flags.get_events()
        assert isinstance(event, WorldFlagLoweredEvent)
        assert (event.world_id, event.flag_id, event.trigger) == (_WORLD, FlagId("gate_locked"), _TICK)

    def test_lowering_lowered_flag_changes_nothing(self) -> None:
        """立っていない旗を lower_flag しても、断らず、イベントもためない。"""
        flags = WorldFlags(_WORLD)

        flags.lower_flag(_BRIDGE_REPAIRED, _TICK)

        assert not flags.is_raised(_BRIDGE_REPAIRED)
        assert flags.get_events() == []

    def test_flag_raised_after_lowering_is_raised_again(self) -> None:
        """立てて、下ろして、また立てた旗は立っていて、3 つのイベントを順にためる。"""
        flags = WorldFlags(_WORLD)

        flags.raise_flag(_BRIDGE_REPAIRED, _STORM)
        flags.lower_flag(_BRIDGE_REPAIRED, _TICK)
        flags.raise_flag(_BRIDGE_REPAIRED, _TICK)

        assert flags.is_raised(_BRIDGE_REPAIRED)
        assert [type(e) for e in flags.get_events()] == [
            WorldFlagRaisedEvent,
            WorldFlagLoweredEvent,
            WorldFlagRaisedEvent,
        ]
