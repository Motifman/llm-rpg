from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_index_selection import (
    EpisodeIndexSelection,
    NewestFirst,
    RecalledRisesToTop,
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


class TestRecalledRisesToTop:
    """RecalledRisesToTop が、書いた時と最後に呼び出した時のうち新しいほうで並べ、上から N 件を返すことを保証する。"""

    def test_is_an_episode_index_selection(self) -> None:
        """RecalledRisesToTop は、profile で NewestFirst と取り替えられるよう EpisodeIndexSelection として使える。"""
        assert isinstance(RecalledRisesToTop(), EpisodeIndexSelection)

    def test_recalled_old_episode_rises_above_newer_ones(self) -> None:
        """ターン 1 に書いてターン 8 に呼び出したエピソードは、ターン 5 と 3 に書いた呼び出されていないエピソードより上に来る。"""
        old = _episode(1, 1).recalled_at(turn=8)
        episodes = [old, _episode(2, 3), _episode(3, 5)]

        chosen = RecalledRisesToTop().select(episodes, limit=3)

        assert chosen == (old, episodes[2], episodes[1])

    def test_unrecalled_episodes_sink_out_of_the_n(self) -> None:
        """呼び出されないまま、書いた時が呼び出しより古いエピソードは、N 件から外れる。"""
        recalled = _episode(1, 1).recalled_at(turn=9)
        newer = _episode(2, 6)
        sunk = _episode(3, 4)

        chosen = RecalledRisesToTop().select([recalled, newer, sunk], limit=2)

        assert chosen == (recalled, newer)

    def test_episode_recalled_long_ago_sinks_below_newer_writing(self) -> None:
        """前に呼び出したエピソードも、その後に書いたエピソードより下になる。"""
        recalled = _episode(1, 1).recalled_at(turn=3)
        newer = _episode(2, 7)

        chosen = RecalledRisesToTop().select([recalled, newer], limit=2)

        assert chosen == (newer, recalled)

    def test_later_added_comes_first_within_the_same_turn(self) -> None:
        """書いた時か呼び出した時が同じターンなら、一覧で後ろにある (後から足した) ものが先に来る。"""
        recalled = _episode(1, 1).recalled_at(turn=4)
        written = _episode(2, 4)

        chosen = RecalledRisesToTop().select([recalled, written], limit=2)

        assert chosen == (written, recalled)

    def test_limit_that_is_negative_is_rejected(self) -> None:
        """N が負なら EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            RecalledRisesToTop().select([_episode(1, 2)], limit=-1)
