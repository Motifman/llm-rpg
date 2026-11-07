from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.whereabouts_exception import UnknownSpotException
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import SpotId
from ai_rpg_world.game_world.domain.whereabouts import SpotAtmosphereChangedEvent, SpotAtmospheres
from tests.game_world.domain.whereabouts._builders import WORLD, atmosphere, spot

HALL = spot("hall", Lighting.BRIGHT)
CELLAR = spot("cellar", Lighting.DARK)


def _atmospheres() -> SpotAtmospheres:
    return SpotAtmospheres(WORLD, (HALL, CELLAR))


class TestSpotAtmospheresInitially:
    """SpotAtmospheres が、場所ごとに宣言の雰囲気から始まることを保証する。"""

    def test_world_id_is_the_given_world(self) -> None:
        """作るときに渡した WorldId を自分の ID として持つ。"""
        assert _atmospheres().world_id == WORLD

    def test_atmosphere_starts_as_declared(self) -> None:
        """何も変えていない場所の atmosphere_of は、その場所の宣言の雰囲気を返す。"""
        assert _atmospheres().atmosphere_of(CELLAR) == CELLAR.atmosphere

    def test_spot_not_given_at_creation_is_rejected(self) -> None:
        """作るときに渡していない場所について聞くと UnknownSpotException を投げる。"""
        with pytest.raises(UnknownSpotException):
            _atmospheres().atmosphere_of(spot("elsewhere"))


class TestSpotAtmospheresChange:
    """change が場所の雰囲気を書き換え、変わる前と後の雰囲気をイベントに残すことを保証する。"""

    def test_change_records_atmosphere_before_and_after(self) -> None:
        """地下室を明るくすると atmosphere_of が新しい雰囲気を返し、before=暗い・after=明るいの SpotAtmosphereChangedEvent を 1 件ためる。"""
        atmospheres = _atmospheres()
        brightened = atmosphere(Lighting.BRIGHT)

        atmospheres.change(CELLAR, brightened)

        assert atmospheres.atmosphere_of(CELLAR) == brightened
        [event] = atmospheres.get_events()
        assert isinstance(event, SpotAtmosphereChangedEvent)
        assert (event.world_id, event.spot, event.before, event.after) == (
            WORLD,
            SpotId("cellar"),
            CELLAR.atmosphere,
            brightened,
        )

    def test_change_leaves_other_spots_as_they_were(self) -> None:
        """地下室の雰囲気を変えても、広間の雰囲気は宣言のまま。"""
        atmospheres = _atmospheres()

        atmospheres.change(CELLAR, atmosphere(Lighting.BRIGHT))

        assert atmospheres.atmosphere_of(HALL) == HALL.atmosphere

    def test_change_to_the_current_atmosphere_does_nothing(self) -> None:
        """今と同じ雰囲気を渡すと、例外もイベントも出さない。"""
        atmospheres = _atmospheres()

        atmospheres.change(CELLAR, CELLAR.atmosphere)

        assert atmospheres.get_events() == []

    def test_change_of_an_unknown_spot_is_rejected_without_events(self) -> None:
        """作るときに渡していない場所を change すると UnknownSpotException を投げ、イベントを出さない。"""
        atmospheres = _atmospheres()

        with pytest.raises(UnknownSpotException):
            atmospheres.change(spot("elsewhere"), atmosphere())

        assert atmospheres.get_events() == []
