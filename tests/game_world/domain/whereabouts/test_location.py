from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.sound import Loudness, NotReached, SoundLevel, SoundReach
from ai_rpg_world.game_world.domain.value_object import SpotId, Ticks
from ai_rpg_world.game_world.domain.whereabouts.location import AtSpot, OpenArea, TravelInProgress
from ai_rpg_world.game_world.domain.whereabouts.route import Route
from tests.game_world.domain.whereabouts._builders import path
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_VALUES = world_rules_for_tests().hearing
SQUARE, HALL, CELLAR = SpotId("square"), SpotId("hall"), SpotId("cellar")
_ROUTE = Route(start=SQUARE, passages=(path("square_hall", "square", "hall"), path("hall_cellar", "hall", "cellar")))


def _on_passage(index: int) -> TravelInProgress:
    return TravelInProgress(route=_ROUTE, passage_index=index, ticks_left_on_passage=Ticks(1), departed_from=SQUARE)


class TestLocationIsAt:
    """Location.is_at が、その場所にいるときだけ真を返し、移動中はどこにもいないことを保証する。"""

    def test_someone_at_the_spot_is_there(self) -> None:
        """AtSpot は自分の場所で真、ほかの場所で偽を返す。"""
        here = AtSpot(spot=SQUARE, section=OpenArea())

        assert here.is_at(SQUARE) is True
        assert here.is_at(HALL) is False

    @pytest.mark.parametrize("spot", [SQUARE, HALL, CELLAR])
    def test_someone_travelling_is_nowhere(self, spot: SpotId) -> None:
        """TravelInProgress は、区間の端の場所を含めてどの場所でも偽を返す。"""
        assert _on_passage(1).is_at(spot) is False


class TestLocationSoundLevelFrom:
    """Location.sound_level_from が、居場所に届いた音の大きさを決めることを保証する。"""

    def test_at_a_spot_the_level_reaching_the_spot_is_heard(self) -> None:
        """AtSpot には、音の広がりがその場所に届けた大きさが届く。"""
        reach = SoundReach(levels={SQUARE: SoundLevel(60), HALL: SoundLevel(45)})

        assert AtSpot(spot=HALL, section=OpenArea()).sound_level_from(
            SQUARE, Loudness.NORMAL, reach, _VALUES
        ) == SoundLevel(45)

    @pytest.mark.parametrize(("index", "origin"), [(0, SQUARE), (0, HALL), (1, HALL), (1, CELLAR)])
    def test_a_loud_sound_at_an_end_of_the_current_passage_is_one_passage_weaker(
        self, index: int, origin: SpotId
    ) -> None:
        """移動中は、今の区間の両端で鳴った大きい音が loss_per_passage 15 だけ弱まって届く (75→60)。"""
        assert _on_passage(index).sound_level_from(origin, Loudness.LOUD, SoundReach(levels={}), _VALUES) == SoundLevel(
            60
        )

    def test_a_loud_sound_off_the_current_passage_does_not_reach(self) -> None:
        """今の区間の端でない場所で鳴った大きい音は NotReached。"""
        assert (
            _on_passage(1).sound_level_from(SQUARE, Loudness.VERY_LOUD, SoundReach(levels={}), _VALUES) == NotReached()
        )

    @pytest.mark.parametrize("loudness", [Loudness.WHISPER, Loudness.NORMAL])
    def test_a_quieter_sound_does_not_reach_a_traveller(self, loudness: Loudness) -> None:
        """区間の端で鳴っても、ささやき・ふつうの音は NotReached。"""
        assert _on_passage(1).sound_level_from(HALL, loudness, SoundReach(levels={}), _VALUES) == NotReached()
