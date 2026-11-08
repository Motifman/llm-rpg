from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.effect.flag_effects import LowerFlagEffect, RaiseFlagEffect
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.world_records import WorldFlagLoweredEvent, WorldFlagRaisedEvent
from tests.game_world.domain.effect._builders import WORLD
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_FLOOD = HappeningFired(HappeningForTests(HappeningId("flood")))
_BRIDGE_OUT = FlagDeclaration(
    flag_id=FlagId("bridge_out"), meaning=DescriptionText("橋が流れた"), initially_raised=False
)
_LAMP_LIT = FlagDeclaration(
    flag_id=FlagId("lamp_lit"), meaning=DescriptionText("灯台が灯っている"), initially_raised=True
)


class TestRaiseFlagEffect:
    """RaiseFlagEffect が、きっかけを渡して世界の旗を立てることを保証する。"""

    def test_apply_raises_the_flag_with_the_trigger(self) -> None:
        """洪水の出来事で当てると、橋が流れた旗が立ち、旗の集約に洪水をきっかけとする WorldFlagRaisedEvent がたまる。"""
        a_world = WorldInMemory(world=WORLD)

        RaiseFlagEffect(flag=_BRIDGE_OUT).apply(a_world.facts(), a_world.aggregates(), _FLOOD)

        assert a_world.facts().flags().is_raised(_BRIDGE_OUT)
        [event] = a_world.flags.get_events()
        assert isinstance(event, WorldFlagRaisedEvent)
        assert event.trigger == _FLOOD

    def test_requirements_need_nothing(self) -> None:
        """RaiseFlagEffect の requirements() は何も要らない。"""
        assert RaiseFlagEffect(flag=_BRIDGE_OUT).requirements() == Requirements.nothing()


class TestLowerFlagEffect:
    """LowerFlagEffect が、きっかけを渡して世界の旗を下ろすことを保証する。"""

    def test_apply_lowers_the_flag_with_the_trigger(self) -> None:
        """洪水の出来事で当てると、初めから立っている灯台の旗が下り、洪水をきっかけとする WorldFlagLoweredEvent がたまる。"""
        a_world = WorldInMemory(world=WORLD)

        LowerFlagEffect(flag=_LAMP_LIT).apply(a_world.facts(), a_world.aggregates(), _FLOOD)

        assert not a_world.facts().flags().is_raised(_LAMP_LIT)
        [event] = a_world.flags.get_events()
        assert isinstance(event, WorldFlagLoweredEvent)
        assert event.trigger == _FLOOD

    def test_requirements_need_nothing(self) -> None:
        """LowerFlagEffect の requirements() は何も要らない。"""
        assert LowerFlagEffect(flag=_LAMP_LIT).requirements() == Requirements.nothing()
