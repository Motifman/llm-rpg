from __future__ import annotations

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import LookingAround
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb import NoLook, ObjectLook, ObjectLooksDeclaration
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, ObjectId, WorldTick
from tests.game_world.domain.condition._builders import world
from tests.game_world.support.world_in_memory import world_in_memory

_FLOODGATE_OPEN = FlagDeclaration(
    flag_id=FlagId("north_floodgate_open"), meaning=DescriptionText("北の水門が開いている"), initially_raised=False
)
_WATER_DRAINED = FlagDeclaration(
    flag_id=FlagId("water_drained"), meaning=DescriptionText("水が抜けた"), initially_raised=False
)
_OPEN_TEXT = DescriptionText("開いていて、水の流れる音がする")
_DRAINED_TEXT = DescriptionText("水が抜けて、底の泥が見える")


def _floodgate_looks(*looks: ObjectLook) -> ObjectLooksDeclaration:
    return ObjectLooksDeclaration(object_id=ObjectId("north_floodgate"), looks=looks)


def _raised(flag: FlagDeclaration) -> FlagIsRaisedCondition:
    return FlagIsRaisedCondition(flag=flag, failure_text=NoText())


def _world_with_raised(*flags: FlagDeclaration) -> WorldSession:
    a_world = world()
    for flag in flags:
        a_world.aggregates().flags().raise_flag(flag, LookingAround(WorldTick(0)))
    return a_world


class TestObjectLooksNow:
    """ObjectLooksDeclaration.look_now が、見え方を書いた順に確かめて、いまの見え方を 1 つだけ決めることを保証する。"""

    def test_returns_the_text_of_the_look_whose_condition_holds(self) -> None:
        """水門が開いている旗が立っているとき、「開いていて、水の流れる音がする」を返す。"""
        looks = _floodgate_looks(ObjectLook(when=_raised(_FLOODGATE_OPEN), text=_OPEN_TEXT))

        look = looks.look_now(_world_with_raised(_FLOODGATE_OPEN).facts())

        assert look == _OPEN_TEXT

    def test_returns_only_the_first_written_look_when_two_hold(self) -> None:
        """当てはまる見え方が 2 つあるとき、先に書いた 1 つだけを返す。"""
        looks = _floodgate_looks(
            ObjectLook(when=_raised(_WATER_DRAINED), text=_DRAINED_TEXT),
            ObjectLook(when=_raised(_FLOODGATE_OPEN), text=_OPEN_TEXT),
        )

        look = looks.look_now(_world_with_raised(_FLOODGATE_OPEN, _WATER_DRAINED).facts())

        assert look == _DRAINED_TEXT

    def test_returns_no_look_when_no_look_holds(self) -> None:
        """どの見え方の条件にも当てはまらないとき、NoLook を返す。"""
        looks = _floodgate_looks(ObjectLook(when=_raised(_FLOODGATE_OPEN), text=_OPEN_TEXT))

        look = looks.look_now(world().facts())

        assert look == NoLook()

    def test_declaration_without_looks_has_no_look(self) -> None:
        """見え方を 1 つも持たない宣言は、旗が立っていても NoLook を返す。"""
        assert _floodgate_looks().look_now(_world_with_raised(_FLOODGATE_OPEN).facts()) == NoLook()
