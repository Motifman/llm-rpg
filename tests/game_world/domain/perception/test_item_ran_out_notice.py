from __future__ import annotations

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Background,
    BodilyStimulus,
    ItemRanOutNotice,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick

_TEXT = TextWithUnassignedPeople("カンテラの灯が燃え尽きた。").about({})
_NOTICE = ItemRanOutNotice(_TEXT, WorldTick(7))


class TestItemRanOutNotice:
    """ItemRanOutNotice が、時間の切れた品物があった場所ごとに、合った刺激を作ることを保証する。"""

    def test_item_carried_by_hal_becomes_a_notable_bodily_stimulus_to_hal(self) -> None:
        """ハルが持っていた品物の時間が切れると、ハル本人の体の刺激になり、目立つ刺激になる。"""
        assert CarriedBy(PersonId("hal")).read(_NOTICE) == BodilyStimulus(
            person=PersonId("hal"), text=_TEXT, salience=Notable(), at=WorldTick(7)
        )

    def test_item_lying_at_the_plaza_becomes_a_background_sight_there(self) -> None:
        """広場の地面にあった品物の時間が切れると、広場の見える刺激になる。暗いときの文は無く、目立たない刺激になる。"""
        assert LyingAt(SpotId("plaza")).read(_NOTICE) == SightStimulus(
            where=SpotId("plaza"),
            witness=SightTexts(
                clear=_TEXT, dim=NotSeenInDim(), unseen_actor=NotSeenWithoutActor(), noticed_later=NotNoticedLater()
            ),
            target=NoTarget(),
            seen_in_dark=False,
            manner=Openly(),
            actor_departed=False,
            involved=(),
            salience=Background(),
            always_delivered=False,
            at=WorldTick(7),
        )
