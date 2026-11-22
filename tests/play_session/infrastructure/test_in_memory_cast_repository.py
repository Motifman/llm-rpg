from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import Orientation
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.cast import BeingCastInWorldEvent, Cast, CastMember
from ai_rpg_world.play_session.domain.play_session_exception import CastNotFoundException, PersonNotBriefedException
from ai_rpg_world.play_session.infrastructure.in_memory_cast_repository import InMemoryCastRepository

_WORLD = WorldId("mine#1")
_GEN = PersonId("gen")


def _cast() -> Cast:
    return Cast(_WORLD, "廃坑の山村", (CastMember(_GEN, BeingId("being_gen"), "ゲン"),))


class TestInMemoryCastRepository:
    """InMemoryCastRepository が、世界ごとに配役を写しで出し入れし、ためたイベントを保存のときに渡すことを保証する。"""

    def test_cast_not_saved_is_refused(self) -> None:
        """保存していない世界の配役を get すると CastNotFoundException を投げる。"""
        with pytest.raises(CastNotFoundException):
            InMemoryCastRepository().get(_WORLD)

    def test_save_hands_off_events_once(self) -> None:
        """渡したあとの配役を保存すると BeingCastInWorldEvent が 1 件渡り、もう一度保存しても重ねて渡らない。"""
        handed: list[BeingCastInWorldEvent] = []
        casts = InMemoryCastRepository(handoff=handed.extend)
        cast = _cast()
        cast.brief(_GEN, orientation=Orientation(), imposed_goal="外へ出る。", known_people=())

        casts.save(cast)
        casts.save(casts.get(_WORLD))

        assert [e.person for e in handed] == [_GEN]

    def test_changes_after_get_are_not_saved_until_save(self) -> None:
        """get した配役でゲンに渡しても、save するまで保存先の配役はゲンに渡していない。"""
        casts = InMemoryCastRepository()
        casts.save(_cast())

        casts.get(_WORLD).brief(_GEN, orientation=Orientation(), imposed_goal="外へ出る。", known_people=())

        with pytest.raises(PersonNotBriefedException):
            casts.get(_WORLD).entry_of(_GEN)
