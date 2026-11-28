from __future__ import annotations

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import _dict_to_route, _route_to_dict
from ai_rpg_world.being.contract import EnvironmentNotice, OwnAction, OwnBodyState, SeenOrHeard, ToldOrWritten


class TestRouteCodec:
    """Being の snapshot が、観測の経路を種類の名前だけで読み書きすることを保証する。"""

    @pytest.mark.parametrize(
        "route", [SeenOrHeard(), ToldOrWritten(), OwnBodyState(), OwnAction(), EnvironmentNotice()]
    )
    def test_every_route_survives_a_round_trip(self, route: object) -> None:
        """どの経路も、書いて読み直すと同じ経路に戻る。"""
        assert _dict_to_route(_route_to_dict(route)) == route

    def test_own_action_is_written_by_its_kind_only(self) -> None:
        """自分の行為について本人が知ったことの経路は {"kind": "own_action"} で書く。"""
        assert _route_to_dict(OwnAction()) == {"kind": "own_action"}
