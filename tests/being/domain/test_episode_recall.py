from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_recall import RecallResult, recall_episodes
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")


def _episode(episode_id: str, body: str) -> Episode:
    return Episode.write(
        episode_id=episode_id,
        environment_name="地下の金庫室",
        written_turn=2,
        index=EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫の話が出たとき"),
        body=body,
    )


VAULT = _episode("3f2a7b9c-1d2e-4f00-8a00-000000000001", "棚の裏に紙が貼ってあった。")
KEY = _episode("aa11bb22-1d2e-4f00-8a00-000000000002", "鍵は井戸の底に落ちた。")


def _repo() -> InMemoryEpisodeRepository:
    repo = InMemoryEpisodeRepository()
    repo.add(ADA, VAULT)
    repo.add(ADA, KEY)
    return repo


class TestRecallEpisodes:
    """recall_episodes が、呼び名をまとめて受け取り、呼び名ごとに本文を返し、呼び出したエピソードだけ回数を増やして書き戻すことを保証する。"""

    def test_each_handle_gets_its_episode_in_the_given_order(self) -> None:
        """2 つの呼び名を渡すと、渡した順に、それぞれの呼び名と呼び出したあとのエピソードが返る。"""
        results = recall_episodes(_repo(), ADA, ["ep_aa11bb", "ep_3f2a7b"], turn=6)

        assert [(r.handle, r.episode.body if r.episode else None) for r in results] == [
            ("ep_aa11bb", "鍵は井戸の底に落ちた。"),
            ("ep_3f2a7b", "棚の裏に紙が貼ってあった。"),
        ]

    def test_recalled_episodes_are_counted_and_written_back(self) -> None:
        """呼び出したエピソードは、保存の側でも回数が 1 増え、最後に呼び出した時がそのターンになる。"""
        repo = _repo()

        recall_episodes(repo, ADA, ["ep_3f2a7b", "ep_aa11bb"], turn=6)

        assert [(e.recall_count, e.last_recalled_turn) for e in repo.list_by_being(ADA)] == [(1, 6), (1, 6)]

    def test_returned_episode_is_the_recalled_version(self) -> None:
        """返るエピソードは、回数を増やしたあとの版になる。"""
        (result,) = recall_episodes(_repo(), ADA, ["ep_3f2a7b"], turn=6)

        assert result.episode == VAULT.recalled_at(turn=6)

    def test_unknown_handle_returns_none_and_others_are_recalled(self) -> None:
        """知らない呼び名には None が返り、ほかの呼び名は通常どおり呼び出され、知らない呼び名のせいで記録は増えない。"""
        repo = _repo()

        results = recall_episodes(repo, ADA, ["ep_000000", "ep_3f2a7b"], turn=6)

        assert results[0] == RecallResult(handle="ep_000000", episode=None)
        assert results[1].episode is not None
        assert [e.recall_count for e in repo.list_by_being(ADA)] == [1, 0]
        assert len(repo.list_by_being(ADA)) == 2

    def test_handle_of_another_being_is_unknown(self) -> None:
        """別の Being のエピソードの呼び名は、知らない呼び名として扱い、その Being の回数も増やさない。"""
        repo = _repo()

        (result,) = recall_episodes(repo, KAI, ["ep_3f2a7b"], turn=6)

        assert result.episode is None
        assert repo.list_by_being(ADA)[0].recall_count == 0

    def test_same_handle_twice_is_recalled_once(self) -> None:
        """1 回の呼び出しで同じ呼び名を 2 回渡すと、結果は 1 件で、回数は 1 だけ増える。"""
        repo = _repo()

        results = recall_episodes(repo, ADA, ["ep_3f2a7b", "ep_3f2a7b"], turn=6)

        assert [r.handle for r in results] == ["ep_3f2a7b"]
        assert repo.list_by_being(ADA)[0].recall_count == 1

    def test_no_handles_is_rejected(self) -> None:
        """呼び名を 1 件も渡さないと EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            recall_episodes(_repo(), ADA, [], turn=6)

    def test_turn_before_writing_rejects_the_whole_call(self) -> None:
        """2 件目だけが書いた時より前のターンになる呼び出しは EpisodeValidationException を投げ、先に呼び出せた 1 件目の回数も増えない。"""
        repo = _repo()
        late = Episode.write(
            episode_id="cc33dd44-1d2e-4f00-8a00-000000000003",
            environment_name="島",
            written_turn=5,
            index=EpisodeIndex(summary="浜で火をおこした", recall_when="寒いとき"),
            body="流木を集めた。",
        )
        repo.add(ADA, late)

        with pytest.raises(EpisodeValidationException):
            recall_episodes(repo, ADA, ["ep_aa11bb", "ep_cc33dd"], turn=3)
        assert [e.recall_count for e in repo.list_by_being(ADA)] == [0, 0, 0]
