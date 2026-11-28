from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.episode_recall import EpisodeRecallHandles, RecallResult, recall_episodes
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeRecallLimitExceededException,
    EpisodeValidationException,
)
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")


def _episode(episode_id: str, body: str) -> Episode:
    return Episode.write(
        being_id=ADA,
        episode_id=episode_id,
        environment_name="地下の金庫室",
        written_turn=2,
        index=EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫の話が出たとき"),
        body=body,
    )


VAULT = _episode("3f2a7b9c-1d2e-4f00-8a00-000000000001", "棚の裏に紙が貼ってあった。")
KEY = _episode("aa11bb22-1d2e-4f00-8a00-000000000002", "鍵は井戸の底に落ちた。")


def _handles(handles: list[str]) -> EpisodeRecallHandles:
    return EpisodeRecallHandles.within(handles, limit=3)


def _repo() -> InMemoryEpisodeRepository:
    repo = InMemoryEpisodeRepository(handoff=discard_events)
    repo.add(VAULT)
    repo.add(KEY)
    return repo


class TestRecallEpisodes:
    """recall_episodes が、呼び名をまとめて受け取り、呼び名ごとに本文を返し、呼び出したエピソードだけ回数を増やして書き戻すことを保証する。"""

    def test_each_handle_gets_its_episode_in_the_given_order(self) -> None:
        """2 つの呼び名を渡すと、渡した順に、それぞれの呼び名と呼び出したあとのエピソードが返る。"""
        results = recall_episodes(_repo(), ADA, _handles(["ep_aa11bb", "ep_3f2a7b"]), turn=6)

        assert [(r.handle, r.episode.body if r.episode else None) for r in results] == [
            ("ep_aa11bb", "鍵は井戸の底に落ちた。"),
            ("ep_3f2a7b", "棚の裏に紙が貼ってあった。"),
        ]

    def test_recalled_episodes_are_counted_and_written_back(self) -> None:
        """呼び出したエピソードは、保存の側でも回数が 1 増え、最後に呼び出した時がそのターンになる。"""
        repo = _repo()

        recall_episodes(repo, ADA, _handles(["ep_3f2a7b", "ep_aa11bb"]), turn=6)

        assert [(e.recall_count, e.last_recalled_turn) for e in repo.list_by_being(ADA)] == [(1, 6), (1, 6)]

    def test_returned_episode_is_the_recalled_version(self) -> None:
        """返るエピソードは、回数を増やしたあとの版になる。"""
        (result,) = recall_episodes(_repo(), ADA, _handles(["ep_3f2a7b"]), turn=6)

        assert result.episode is not None
        assert (result.episode.episode_id, result.episode.recall_count, result.episode.last_recalled_turn) == (
            VAULT.episode_id,
            1,
            6,
        )

    def test_unknown_handle_returns_none_and_others_are_recalled(self) -> None:
        """知らない呼び名には None が返り、ほかの呼び名は通常どおり呼び出され、知らない呼び名のせいで記録は増えない。"""
        repo = _repo()

        results = recall_episodes(repo, ADA, _handles(["ep_000000", "ep_3f2a7b"]), turn=6)

        assert results[0] == RecallResult(handle="ep_000000", episode=None)
        assert results[1].episode is not None
        assert [e.recall_count for e in repo.list_by_being(ADA)] == [1, 0]
        assert len(repo.list_by_being(ADA)) == 2

    def test_handle_of_another_being_is_unknown(self) -> None:
        """別の Being のエピソードの呼び名は、知らない呼び名として扱い、その Being の回数も増やさない。"""
        repo = _repo()

        (result,) = recall_episodes(repo, KAI, _handles(["ep_3f2a7b"]), turn=6)

        assert result.episode is None
        assert repo.list_by_being(ADA)[0].recall_count == 0

    def test_same_handle_twice_is_recalled_once(self) -> None:
        """同じ呼び名を 2 回書いた呼び出しは、結果が 1 件で、回数は 1 だけ増える。"""
        repo = _repo()

        results = recall_episodes(repo, ADA, _handles(["ep_3f2a7b", "ep_3f2a7b"]), turn=6)

        assert [r.handle for r in results] == ["ep_3f2a7b"]
        assert repo.list_by_being(ADA)[0].recall_count == 1

    def test_turn_before_writing_rejects_the_whole_call(self) -> None:
        """2 件目だけが書いた時より前のターンになる呼び出しは EpisodeValidationException を投げ、先に呼び出せた 1 件目の回数も増えない。"""
        repo = _repo()
        late = Episode.write(
            being_id=ADA,
            episode_id="cc33dd44-1d2e-4f00-8a00-000000000003",
            environment_name="島",
            written_turn=5,
            index=EpisodeIndex(summary="浜で火をおこした", recall_when="寒いとき"),
            body="流木を集めた。",
        )
        repo.add(late)

        with pytest.raises(EpisodeValidationException):
            recall_episodes(repo, ADA, _handles(["ep_aa11bb", "ep_cc33dd"]), turn=3)
        assert [e.recall_count for e in repo.list_by_being(ADA)] == [0, 0, 0]


class TestEpisodeRecallHandles:
    """EpisodeRecallHandles.within が、同じ呼び名を 1 件と数え、一度に思い出せる件数を超えた呼び出しを断ることを保証する。"""

    def test_same_handle_twice_counts_as_one(self) -> None:
        """同じ呼び名を 2 回書くと、書いた順に 1 度だけ持ち、上限 2 の中に収まる。"""
        handles = EpisodeRecallHandles.within(["ep_3f2a7b", "ep_aa11bb", "ep_3f2a7b"], limit=2)

        assert handles.handles == ("ep_3f2a7b", "ep_aa11bb")

    def test_more_handles_than_the_limit_are_refused(self) -> None:
        """違う呼び名を上限より多く書くと、上限を持つ EpisodeRecallLimitExceededException を投げる。"""
        with pytest.raises(EpisodeRecallLimitExceededException) as raised:
            EpisodeRecallHandles.within(["ep_3f2a7b", "ep_aa11bb", "ep_cc33dd"], limit=2)

        assert raised.value.limit == 2

    def test_handles_up_to_the_limit_are_accepted(self) -> None:
        """違う呼び名がちょうど上限の件数なら受け付ける。"""
        handles = EpisodeRecallHandles.within(["ep_3f2a7b", "ep_aa11bb"], limit=2)

        assert len(handles.handles) == 2

    def test_no_handles_is_rejected(self) -> None:
        """呼び名を 1 件も書かないと EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            EpisodeRecallHandles.within([], limit=3)

    def test_limit_below_one_is_rejected(self) -> None:
        """上限が 1 より小さいと EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            EpisodeRecallHandles.within(["ep_3f2a7b"], limit=0)

    def test_repeated_handles_cannot_be_held_directly(self) -> None:
        """同じ呼び名を重ねて直接持たせると EpisodeValidationException を投げる。"""
        with pytest.raises(EpisodeValidationException):
            EpisodeRecallHandles(("ep_3f2a7b", "ep_3f2a7b"))
