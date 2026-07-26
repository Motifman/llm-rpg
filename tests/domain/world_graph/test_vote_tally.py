"""投票の集計規則を保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md §2.3) の PR 6。
本家に合わせて **単純多数 (plurality)・同点は追放なし・棄権あり**。

## 棄権も 1 票として数える

棄権を「投票していない」と同じに扱うと、全員が保留を選んだときに「まだ
投票が終わっていない」と区別が付かない。棄権は**保留するという意思表示**
であって、票の不在ではない。棄権が最多なら誰も追放されない。

## 同点で追放しないのはなぜか

誰も追放されないことも結果であり、「誰も確信を持てなかった」という情報に
なる。同点をどちらかに倒すと、その情報が消える。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.service.vote_tally import resolve_vote

_A, _B, _C, _D = PlayerId(1), PlayerId(2), PlayerId(3), PlayerId(4)

#: 棄権を表す投票先。
_SKIP = None


class TestPlurality:
    """最多票の 1 人が追放される。"""

    def test_clear_winner_is_ejected(self) -> None:
        """2 対 1 なら多い方が追放される。"""
        result = resolve_vote({_A: _C, _B: _C, _C: _A})
        assert result.ejected_player_id == _C

    def test_a_lone_vote_loses_to_the_skips(self) -> None:
        """1 票の指名は、2 つの棄権に負ける。

        **棄権は票として数える。** 保留する側が多ければ「決めない」が
        勝つ。ここを「1 票でも最多なら通る」にすると、全員が保留した
        なかで 1 人が指名するだけで追放が成立してしまう。

        (最初この期待を逆に書いていた。本家は棄権も票として扱う。)
        """
        result = resolve_vote({_A: _C, _B: _SKIP, _C: _SKIP})
        assert result.ejected_player_id is None

    def test_a_lone_vote_wins_when_it_outnumbers_the_skips(self) -> None:
        """指名が棄権を上回れば通る。"""
        result = resolve_vote({_A: _C, _B: _C, _C: _SKIP})
        assert result.ejected_player_id == _C


class TestTiesEjectNobody:
    """同点なら誰も追放されない。"""

    def test_two_way_tie(self) -> None:
        """1 対 1 では決まらない。"""
        result = resolve_vote({_A: _C, _B: _A})
        assert result.ejected_player_id is None

    def test_tie_with_skip(self) -> None:
        """棄権と同数でも決まらない。

        棄権は票として数えるので、名指しと並んだら同点になる。
        """
        result = resolve_vote({_A: _C, _B: _SKIP})
        assert result.ejected_player_id is None

    def test_skip_alone_ejects_nobody(self) -> None:
        """棄権が最多なら誰も追放されない。"""
        result = resolve_vote({_A: _SKIP, _B: _SKIP, _C: _B})
        assert result.ejected_player_id is None


class TestEmptyVote:
    """1 票も無い場合。"""

    def test_no_votes_ejects_nobody(self) -> None:
        """誰も投票しなければ追放も無い。"""
        assert resolve_vote({}).ejected_player_id is None


class TestTallyIsReportable:
    """結果を全員に配れる形で返す。

    追放の有無にかかわらず集計を配る (設計 doc §6.4)。配らないと
    「誰も追放されなかった」のか「誰かが追放されたが自分は見ていなかった」
    のかを区別できない。
    """

    def test_counts_per_target(self) -> None:
        """誰が何票入ったかが分かる。"""
        result = resolve_vote({_A: _C, _B: _C, _C: _A})
        assert result.counts == {_C: 2, _A: 1}

    def test_skip_count_is_separate(self) -> None:
        """棄権の数も分かる。"""
        result = resolve_vote({_A: _SKIP, _B: _SKIP, _C: _A})
        assert result.skip_count == 2

    def test_who_voted_for_whom_is_kept(self) -> None:
        """誰が誰に入れたかが残る。

        投票行動そのものが次の会議の材料になる。集計だけにすると、
        社会的推論の材料が一段減る (設計 doc §2.3)。
        """
        votes = {_A: _C, _B: _SKIP}
        assert resolve_vote(votes).ballots == votes


class TestSelfVote:
    """自分に入れることも妨げない。"""

    def test_self_vote_counts(self) -> None:
        """自分を指名する票も 1 票として数える。

        禁じる理由が無い。追い詰められて自分を差し出す、という選択を
        engine が潰す必要はない。
        """
        result = resolve_vote({_A: _A, _B: _A, _C: _SKIP})
        assert result.ejected_player_id == _A
