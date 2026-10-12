from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeConflictException,
    EpisodeNotFoundException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")
INDEX = EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫や鍵の話が出たとき")


def _episode(episode_id: str, *, taken_handles: set[str] | None = None) -> Episode:
    return Episode.write(
        episode_id=episode_id,
        environment_name="地下の金庫室",
        written_turn=3,
        index=INDEX,
        body="棚の裏に紙が貼ってあった。",
        taken_handles=taken_handles or set(),
    )


FIRST = _episode("3f2a7b9c-1d2e-4f00-8a00-000000000001")
SECOND = _episode("aa11bb22-1d2e-4f00-8a00-000000000002")


class TestInMemoryEpisodeRepository:
    """InMemoryEpisodeRepository が、Being ごとにエピソードを足した順に持ち、呼び名で引けることを保証する。"""

    def test_added_episode_is_found_by_its_handle(self) -> None:
        """足したエピソードは、その呼び名で引ける。"""
        repo = InMemoryEpisodeRepository()

        repo.add(ADA, FIRST)

        assert repo.find_by_handle(ADA, "ep_3f2a7b") == FIRST

    def test_unknown_handle_returns_none(self) -> None:
        """記録に無い呼び名で引くと None を返す。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        assert repo.find_by_handle(ADA, "ep_000000") is None

    def test_longer_handle_finds_only_the_episode_that_owns_it(self) -> None:
        """6 文字の呼び名が重なって 7 文字になったエピソードは 7 文字で引け、6 文字の呼び名は前からあるエピソードを指したままになる。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        taken = {e.handle for e in repo.list_by_being(ADA)}
        clash = _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003", taken_handles=taken)

        repo.add(ADA, clash)

        assert repo.find_by_handle(ADA, "ep_3f2a7b") == FIRST
        assert repo.find_by_handle(ADA, "ep_3f2a7bc") == clash

    def test_episodes_are_kept_apart_per_being(self) -> None:
        """ある Being に足したエピソードは、別の Being の一覧にも呼び名にも出ない。"""
        repo = InMemoryEpisodeRepository()

        repo.add(ADA, FIRST)

        assert repo.list_by_being(KAI) == ()
        assert repo.find_by_handle(KAI, FIRST.handle) is None

    def test_list_returns_episodes_in_the_order_added(self) -> None:
        """一覧は足した順に返る。"""
        repo = InMemoryEpisodeRepository()

        repo.add(ADA, SECOND)
        repo.add(ADA, FIRST)

        assert repo.list_by_being(ADA) == (SECOND, FIRST)

    def test_adding_the_same_id_again_is_rejected(self) -> None:
        """同じ ID のエピソードをもう一度足すと EpisodeConflictException を投げ、記録は 1 件のままになる。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        with pytest.raises(EpisodeConflictException):
            repo.add(ADA, FIRST.recalled_at(turn=5))
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_adding_a_taken_handle_is_rejected(self) -> None:
        """使われている呼び名のエピソードを足すと EpisodeConflictException を投げ、記録は増えない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        clash = _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003")

        with pytest.raises(EpisodeConflictException):
            repo.add(ADA, clash)
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_save_writes_back_in_the_same_position(self) -> None:
        """呼び出したエピソードを書き戻すと、同じ ID の記録が置き換わり、一覧の位置は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        repo.add(ADA, SECOND)
        recalled = FIRST.recalled_at(turn=8)

        repo.save(ADA, recalled)

        assert repo.list_by_being(ADA) == (recalled, SECOND)
        assert repo.find_by_handle(ADA, FIRST.handle) == recalled

    def test_save_of_an_unknown_episode_is_rejected(self) -> None:
        """記録に無いエピソードを書き戻すと EpisodeNotFoundException を投げ、記録は増えない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        with pytest.raises(EpisodeNotFoundException):
            repo.save(ADA, SECOND)
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_save_that_changes_the_handle_is_rejected(self) -> None:
        """同じ ID でも呼び名が変わったエピソードを書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        renamed = _episode(FIRST.episode_id, taken_handles={FIRST.handle})

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, renamed)
        assert repo.list_by_being(ADA) == (FIRST,)

    @pytest.mark.parametrize(
        "changes",
        [
            {"body": "書き換えた本文"},
            {"written_turn": 4},
            {"environment_name": "島"},
        ],
        ids=["body", "written_turn", "environment_name"],
    )
    def test_save_that_changes_what_was_written_is_rejected(self, changes: dict[str, object]) -> None:
        """本文・書いた時・環境の名前のどれかを変えた版を書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, dataclasses.replace(FIRST, **changes))
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_save_that_drops_index_history_is_rejected(self) -> None:
        """目次の履歴から前の版を消した版を書き戻すと EpisodeConflictException を投げ、履歴は残る。"""
        repo = InMemoryEpisodeRepository()
        revised = FIRST.with_revised_index(EpisodeIndex(summary="番号を見つけた", recall_when="数字のとき"), turn=6)
        repo.add(ADA, revised)

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, dataclasses.replace(revised, index=INDEX, index_history=()))
        assert repo.list_by_being(ADA) == (revised,)

    def test_save_that_lowers_recall_count_is_rejected(self) -> None:
        """呼び出された回数を減らした版を書き戻すと EpisodeConflictException を投げ、回数は変わらない。"""
        repo = InMemoryEpisodeRepository()
        recalled = FIRST.recalled_at(turn=5).recalled_at(turn=6)
        repo.add(ADA, recalled)

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, FIRST.recalled_at(turn=7))
        assert repo.list_by_being(ADA) == (recalled,)

    def test_save_that_replaces_index_without_history_is_rejected(self) -> None:
        """前の版を履歴に残さずに目次だけを替えた版を書き戻すと EpisodeConflictException を投げ、目次は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, dataclasses.replace(FIRST, index=EpisodeIndex(summary="別の目次", recall_when="別の条件")))
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_save_with_forged_previous_index_is_rejected(self) -> None:
        """履歴に足した前の版が、記録の目次と違う版を書き戻すと EpisodeConflictException を投げ、記録は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        forged = dataclasses.replace(FIRST, index=EpisodeIndex(summary="偽の前の版", recall_when="偽の条件")).with_revised_index(
            EpisodeIndex(summary="新しい目次", recall_when="新しい条件"), turn=6
        )

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, forged)
        assert repo.list_by_being(ADA) == (FIRST,)

    def test_save_that_moves_last_recall_back_is_rejected(self) -> None:
        """回数は同じでも、最後に呼び出した時を前のターンに戻した版を書き戻すと EpisodeConflictException を投げる。"""
        repo = InMemoryEpisodeRepository()
        recalled = FIRST.recalled_at(turn=8)
        repo.add(ADA, recalled)

        with pytest.raises(EpisodeConflictException):
            repo.save(ADA, FIRST.recalled_at(turn=5))
        assert repo.list_by_being(ADA) == (recalled,)

    def test_replace_all_overwrites_the_being(self) -> None:
        """全部を書き戻すと、その Being の記録が渡した並びに置き換わり、前の記録は残らない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)

        repo.replace_all_by_being(ADA, [SECOND])

        assert repo.list_by_being(ADA) == (SECOND,)
        assert repo.find_by_handle(ADA, FIRST.handle) is None

    def test_replace_all_with_nothing_empties_the_being(self) -> None:
        """空の並びで全部を書き戻すと、その Being の記録が無くなり、ほかの Being は変わらない。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, FIRST)
        repo.add(KAI, SECOND)

        repo.replace_all_by_being(ADA, [])

        assert repo.list_by_being(ADA) == ()
        assert repo.list_by_being(KAI) == (SECOND,)

    @pytest.mark.parametrize(
        "episodes",
        [
            [FIRST, FIRST.recalled_at(turn=5)],
            [FIRST, _episode("3f2a7bcc-1d2e-4f00-8a00-000000000003")],
        ],
        ids=["same_id", "same_handle"],
    )
    def test_replace_all_with_overlaps_is_rejected(self, episodes: list[Episode]) -> None:
        """ID か呼び名が重なる並びで全部を書き戻すと EpisodeConflictException を投げ、前の記録が残る。"""
        repo = InMemoryEpisodeRepository()
        repo.add(ADA, SECOND)

        with pytest.raises(EpisodeConflictException):
            repo.replace_all_by_being(ADA, episodes)
        assert repo.list_by_being(ADA) == (SECOND,)
