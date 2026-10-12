from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_index_selection import (
    EpisodeIndexSelection,
    NewestFirst,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)


def _episode(number: int, written_turn: int) -> Episode:
    return Episode.write(
        episode_id=f"{number:08x}-0000-4000-8000-000000000000",
        environment_name="島",
        written_turn=written_turn,
        index=EpisodeIndex(summary=f"出来事 {number}", recall_when="いつでも"),
        body=f"出来事 {number} の本文",
    )


class TestNewestFirst:
    """NewestFirst が、エピソードの一覧から、書いた時の新しい順に N 件だけを返すことを保証する。"""

    def test_is_an_episode_index_selection(self) -> None:
        """NewestFirst は、組み立ての段で差し替えられるよう EpisodeIndexSelection として使える。"""
        assert isinstance(NewestFirst(), EpisodeIndexSelection)

    def test_returns_only_n_newest_in_descending_written_turn(self) -> None:
        """5 件から N=3 を選ぶと、書いた時の新しい 3 件が新しい順に返り、古い 2 件は返らない。"""
        episodes = [_episode(1, 2), _episode(2, 9), _episode(3, 4), _episode(4, 7), _episode(5, 1)]

        chosen = NewestFirst().select(episodes, limit=3)

        assert [e.written_turn for e in chosen] == [9, 7, 4]

    def test_returns_all_when_fewer_than_n(self) -> None:
        """一覧が N 件より少なければ、全部を新しい順に返す。"""
        episodes = [_episode(1, 2), _episode(2, 5)]

        chosen = NewestFirst().select(episodes, limit=10)

        assert [e.written_turn for e in chosen] == [5, 2]

    def test_later_added_comes_first_within_the_same_turn(self) -> None:
        """同じターンに書いたエピソードは、一覧で後ろにある (後から足した) ものが先に来る。"""
        first, second = _episode(1, 3), _episode(2, 3)

        chosen = NewestFirst().select([first, second], limit=2)

        assert chosen == (second, first)

    def test_zero_returns_nothing(self) -> None:
        """N=0 なら空を返す。"""
        assert NewestFirst().select([_episode(1, 2)], limit=0) == ()

    @pytest.mark.parametrize("limit", [-1, True, 1.5])
    def test_limit_that_is_not_a_non_negative_int_is_rejected(self, limit: object) -> None:
        """N が 0 以上の整数でなければ EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            NewestFirst().select([_episode(1, 2)], limit=limit)  # type: ignore[arg-type]
