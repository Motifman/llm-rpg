from __future__ import annotations

from ai_rpg_world.game_world.domain.sound import (
    NotReached,
    SoundLevel,
    SoundLink,
    SoundLoss,
    SoundNetwork,
    SoundReach,
)
from ai_rpg_world.game_world.domain.value_object import SpotId

HALL = SpotId("hall")
CORRIDOR = SpotId("corridor")
CELLAR = SpotId("cellar")
TOWER = SpotId("tower")
FAR_ROOM = SpotId("far_room")

AUDIBLE_FLOOR = SoundLevel(20)


def _link(a: SpotId, b: SpotId, loss: int) -> SoundLink:
    return SoundLink(ends=(a, b), loss=SoundLoss(loss))


class TestSoundNetworkSpread:
    """SoundNetwork.spread が、減衰の合計が最も小さい道で音を届け、聞こえる下限を下回る場所へは広げないことを保証する。"""

    def test_origin_hears_the_sound_at_its_starting_level(self) -> None:
        """音が鳴った場所には、元の大きさのまま届く。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15),))

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(HALL) == SoundLevel(60)

    def test_neighbour_through_one_passage_hears_start_minus_the_passage_loss(self) -> None:
        """隣の場所へ 1 本の通路で届くとき、届いた大きさは元の大きさから通路の減衰を引いたものになる。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15),))

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(CORRIDOR) == SoundLevel(45)

    def test_link_carries_sound_from_either_end(self) -> None:
        """通路の端の並びに関わらず、どちらの端で鳴った音も反対の端へ届く。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15),))

        reach = network.spread(CORRIDOR, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(HALL) == SoundLevel(45)

    def test_losses_add_up_along_a_path_of_several_passages(self) -> None:
        """2 本の通路を続けて通ると、2 本の減衰の合計だけ小さくなる。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15), _link(CORRIDOR, CELLAR, 15)))

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(CELLAR) == SoundLevel(30)

    def test_the_path_with_the_smallest_total_loss_wins(self) -> None:
        """2 つの道があるとき、減衰の合計が小さい道の大きさで届く (直通の閉じた扉 40 より、回り道の 15 + 15)。"""
        network = SoundNetwork(
            links=(
                _link(HALL, CELLAR, 40),
                _link(HALL, CORRIDOR, 15),
                _link(CORRIDOR, CELLAR, 15),
            )
        )

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(CELLAR) == SoundLevel(30)

    def test_the_smallest_loss_wins_even_when_it_takes_more_passages(self) -> None:
        """通路の本数が多い道でも、減衰の合計が小さければその大きさで届く (本数ではなく減衰で選ぶ)。"""
        network = SoundNetwork(
            links=(
                _link(HALL, TOWER, 50),
                _link(HALL, CORRIDOR, 5),
                _link(CORRIDOR, CELLAR, 5),
                _link(CELLAR, TOWER, 5),
            )
        )

        reach = network.spread(HALL, SoundLevel(90), AUDIBLE_FLOOR)

        assert reach.level_at(TOWER) == SoundLevel(75)

    def test_spot_whose_level_falls_below_the_floor_is_not_reached(self) -> None:
        """聞こえる下限を下回る場所は SoundReach に入らず、level_at が NotReached を返す。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15),))

        reach = network.spread(HALL, SoundLevel(30), AUDIBLE_FLOOR)

        assert CORRIDOR not in reach.levels
        assert reach.level_at(CORRIDOR) == NotReached()

    def test_spot_exactly_at_the_floor_is_reached(self) -> None:
        """届いた大きさが聞こえる下限ちょうどの場所には届く。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15),))

        reach = network.spread(HALL, SoundLevel(35), AUDIBLE_FLOOR)

        assert reach.level_at(CORRIDOR) == SoundLevel(20)

    def test_sound_does_not_spread_beyond_a_spot_below_the_floor(self) -> None:
        """下限を下回った場所の先へは、減衰 0 の通路が続いていても広げない。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15), _link(CORRIDOR, CELLAR, 0)))

        reach = network.spread(HALL, SoundLevel(30), AUDIBLE_FLOOR)

        assert reach.level_at(CELLAR) == NotReached()

    def test_spot_without_any_link_to_the_origin_is_not_reached(self) -> None:
        """音の鳴った場所と通路でつながっていない場所には届かない。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 15), _link(TOWER, FAR_ROOM, 0)))

        reach = network.spread(HALL, SoundLevel(90), AUDIBLE_FLOOR)

        assert reach.level_at(FAR_ROOM) == NotReached()
        assert set(reach.levels) == {HALL, CORRIDOR}

    def test_paths_with_equal_total_loss_reach_the_spot_at_that_level(self) -> None:
        """減衰の合計が同じ道が 2 つあっても、その合計の大きさで 1 度だけ届く。"""
        network = SoundNetwork(
            links=(
                _link(HALL, CORRIDOR, 15),
                _link(HALL, TOWER, 15),
                _link(CORRIDOR, CELLAR, 15),
                _link(TOWER, CELLAR, 15),
            )
        )

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(CELLAR) == SoundLevel(30)

    def test_zero_loss_passages_carry_the_sound_unchanged(self) -> None:
        """減衰 0 の通路が続くと、その先の場所にも元の大きさのまま届く。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 0), _link(CORRIDOR, CELLAR, 0)))

        reach = network.spread(HALL, SoundLevel(60), AUDIBLE_FLOOR)

        assert reach.level_at(CORRIDOR) == SoundLevel(60)
        assert reach.level_at(CELLAR) == SoundLevel(60)

    def test_origin_is_not_reached_when_the_start_is_below_the_floor(self) -> None:
        """元の大きさが聞こえる下限を下回るとき、音の鳴った場所も SoundReach に入らない。"""
        network = SoundNetwork(links=(_link(HALL, CORRIDOR, 0),))

        reach = network.spread(HALL, SoundLevel(10), AUDIBLE_FLOOR)

        assert reach.level_at(HALL) == NotReached()
        assert reach.level_at(CORRIDOR) == NotReached()


class TestSoundReach:
    """SoundReach が作ったときの届き方を持ち続けることを保証する。"""

    def test_changing_the_given_mapping_afterwards_does_not_change_the_reach(self) -> None:
        """作るときに渡した辞書をあとで書き換えても、SoundReach の届き方は変わらない。"""
        levels = {HALL: SoundLevel(60)}
        reach = SoundReach(levels=levels)

        levels[CORRIDOR] = SoundLevel(45)

        assert reach.level_at(CORRIDOR) == NotReached()
