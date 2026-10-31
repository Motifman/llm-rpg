"""PlayerBeings が、1 人のプレイヤーを動かす Being を 1 つ、1 つの Being が動かすプレイヤーを 1 人に保つことを保証する (design_decisions D1928)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.exception.player_beings_exception import (
    PlayerAlreadyDrivenException,
    PlayerBeingsValidationException,
)
from ai_rpg_world.domain.world.value_object.world_id import WorldId

ADA, BEN = BeingId("ada"), BeingId("ben")
P1, P2 = PlayerId(1), PlayerId(2)


class TestDrive:
    """drive がプレイヤーと Being を結び付ける決まりを保証する。"""

    def test_driven_player_and_being_are_found_both_ways(self) -> None:
        """Being にプレイヤーを動かさせると、プレイヤーからも Being からも引ける。"""
        table = PlayerBeings(WorldId(1))

        table.drive(P1, ADA)

        assert (table.being_of(P1), table.player_of(ADA)) == (ADA, P1)

    def test_same_pair_again_changes_nothing(self) -> None:
        """同じ組をもう一度結び付けても、表は変わらない。"""
        table = PlayerBeings(WorldId(1), [(P1, ADA)])

        table.drive(P1, ADA)

        assert table.pairs() == ((P1, ADA),)

    def test_player_driven_by_another_being_is_refused(self) -> None:
        """別の Being がもう動かしているプレイヤーは、PlayerAlreadyDrivenException で断り、表を変えない。"""
        table = PlayerBeings(WorldId(1), [(P1, ADA)])

        with pytest.raises(PlayerAlreadyDrivenException):
            table.drive(P1, BEN)

        assert table.pairs() == ((P1, ADA),)
        assert table.player_of(BEN) is None

    def test_being_driving_another_player_moves(self) -> None:
        """ほかのプレイヤーを動かしている Being は、そこを離れて新しいプレイヤーを動かす。"""
        table = PlayerBeings(WorldId(1), [(P1, ADA)])

        table.drive(P2, ADA)

        assert table.pairs() == ((P2, ADA),)
        assert table.being_of(P1) is None

    def test_wrong_types_are_refused(self) -> None:
        """プレイヤーや Being の ID の型が違うと PlayerBeingsValidationException で断る。"""
        table = PlayerBeings(WorldId(1))

        with pytest.raises(PlayerBeingsValidationException, match="player_id"):
            table.drive(1, ADA)  # type: ignore[arg-type]
        with pytest.raises(PlayerBeingsValidationException, match="being_id"):
            table.drive(P1, "ada")  # type: ignore[arg-type]


class TestReplaceWith:
    """snapshot から戻すときの、表の入れ替えの決まりを保証する。"""

    def test_pairs_are_replaced_and_listed_in_player_order(self) -> None:
        """表はまるごと入れ替わり、プレイヤーの番号の順に並ぶ。"""
        table = PlayerBeings(WorldId(1), [(P1, ADA)])

        table.replace_with([(P2, ADA), (P1, BEN)])

        assert table.pairs() == ((P1, BEN), (P2, ADA))

    @pytest.mark.parametrize(
        "pairs",
        [[(P1, ADA), (P1, BEN)], [(P1, ADA), (P2, ADA)], [(1, ADA)]],
        ids=["player-twice", "being-twice", "not-ids"],
    )
    def test_broken_pairs_are_refused_and_the_table_is_kept(self, pairs: list) -> None:
        """同じプレイヤーか同じ Being が 2 回出てくるか、ID でない値があれば断り、今の表を変えない。"""
        table = PlayerBeings(WorldId(1), [(P1, ADA)])

        with pytest.raises(PlayerBeingsValidationException):
            table.replace_with(pairs)

        assert table.pairs() == ((P1, ADA),)

    def test_non_world_id_is_refused(self) -> None:
        """世界の ID でない値で作ると PlayerBeingsValidationException で断る。"""
        with pytest.raises(PlayerBeingsValidationException, match="world_id"):
            PlayerBeings(1)  # type: ignore[arg-type]
