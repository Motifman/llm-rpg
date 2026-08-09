from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class TestDepartedPositionStore:
    """去った主体の位置が物理グラフと独立して保持されることを保証する。"""

    def test_places_moves_and_lists_departed_players_by_spot(self) -> None:
        """配置後の移動は対象だけを移し、場所ごとの一覧を安定順で返す。"""
        store = DepartedPositionStore()
        first = PlayerId(1)
        second = PlayerId(2)
        spot_a = SpotId.create(10)
        spot_b = SpotId.create(20)

        store.place(second, spot_a)
        store.place(first, spot_a)
        assert store.players_at(spot_a) == (first, second)

        store.move(first, spot_b)

        assert store.find(first) == spot_b
        assert store.players_at(spot_a) == (second,)
        assert store.players_at(spot_b) == (first,)

    def test_moving_an_unplaced_player_fails(self) -> None:
        """未配置の主体を move して位置を捏造しようとすると失敗する。"""
        import pytest

        store = DepartedPositionStore()
        with pytest.raises(ValueError, match="not placed"):
            store.move(PlayerId(1), SpotId.create(10))
